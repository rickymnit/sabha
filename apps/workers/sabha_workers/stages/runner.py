"""The shared runner every pipeline stage task uses (plan task P2.4; golden rule 3).

A stage (preprocess, diarize, transcribe, analyze) is a `work` function plus a StageSpec saying which statuses it
moves between. `StageRunner.run(spec, work, tenant_id, recording_id, attempt=n)`:

1. Loads the recording through the tenant-scoped repository. Gone: nothing to do. FAILED or NEEDS_REVIEW: stopped.
2. Enters the working status if the stage has an entry step (preprocess: UPLOADED -> PREPROCESSING), with its
   outbox event, in one transaction. A redelivered task finds the recording already in the working status and
   carries on; a recording already past the stage is left alone.
3. Starts a stage run (one document per attempt) and keeps its heartbeat fresh while working.
4. Skips the work if `{tenant}/{recording}/{stage}@{version}/_DONE` exists (golden rule 3); otherwise runs it and
   writes `_DONE` last, so a half-written stage is never mistaken for a finished one.
5. Moves to the next status with its outbox event (the relay starts the next stage), and closes the stage run.

Errors raised by `work`:
- NeedsReviewError(reason): the recording goes to NEEDS_REVIEW (no dead letter: a person decides).
- PermanentError(code): FAILED at once, plus a dead letter (`dlq`) with what is needed to replay it.
- TransientError(code), or anything unexpected: retried with exponential backoff and full jitter until
  STAGE_MAX_ATTEMPTS; then FAILED plus a dead letter. The Celery task does the waiting (Outcome.retry_in).
The FAILED or NEEDS_REVIEW change and its event are written in one transaction with the dead letter.
"""

from __future__ import annotations

import logging
import random
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from opentelemetry import trace
from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.models import DeadLetter, OutboxEvent, Recording, StageRun, utc_now
from sabha_core.outbox import record_transition
from sabha_core.repo import SyncTenantRepo
from sabha_core.stage_runs import finish_stage_run, start_stage_run
from sabha_core.state import ConcurrentTransition, ConsentRequired, RecordingStatus
from sabha_core.storage import artefact_prefix, run_version

log = logging.getLogger("sabha.workers.stage")
tracer = trace.get_tracer("sabha.workers")

DONE_MARKER = "_DONE"
_BACKOFF_BASE_S = 10.0
_BACKOFF_CAP_S = 600.0


class StageError(Exception):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class TransientError(StageError):
    """Worth retrying: a provider timeout, a rate limit, a storage hiccup."""


class PermanentError(StageError):
    """Retrying cannot help: invalid audio, a missing input, a stage not built yet."""


class NeedsReviewError(StageError):
    """A person must decide (unclear roles, too little verified evidence)."""


@dataclass(frozen=True, slots=True)
class StageSpec:
    name: str  # task and artefact name, e.g. "preprocess"
    working: RecordingStatus  # the status while this stage runs
    done_to: RecordingStatus  # the status once it has finished
    entry_from: RecordingStatus | None = None  # moved from here into `working` when the stage starts
    per_run: bool = False  # re-run by re-analysis (P2.8): run n > 1 writes to <version>-run<n>


class ArtefactStore(Protocol):
    def exists(self, key: str) -> bool: ...

    def put(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> None: ...

    def put_file(self, key: str, path: Path, content_type: str) -> None:
        """Upload a file from disk (in parts when large, so it is never held in memory)."""
        ...

    def get(self, key: str) -> bytes:
        """A small artefact's bytes (JSON); FileNotFoundError when it is not there."""
        ...

    def download(self, key: str, path: Path) -> None:
        """A large artefact to disk; FileNotFoundError when it is not there."""
        ...


class S3Artefacts:
    """The artefacts bucket through a boto3 client."""

    def __init__(self, s3: Any, bucket: str) -> None:
        self._s3 = s3
        self._bucket = bucket

    def exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
        except self._s3.exceptions.ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
        return True

    def put(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> None:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=body, ContentType=content_type)

    def put_file(self, key: str, path: Path, content_type: str) -> None:
        self._s3.upload_file(str(path), self._bucket, key, ExtraArgs={"ContentType": content_type})

    def get(self, key: str) -> bytes:
        try:
            body: bytes = self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except self._s3.exceptions.NoSuchKey as exc:
            raise FileNotFoundError(key) from exc
        return body

    def download(self, key: str, path: Path) -> None:
        try:
            self._s3.download_file(self._bucket, key, str(path))
        except self._s3.exceptions.ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                raise FileNotFoundError(key) from exc
            raise


@dataclass(frozen=True, slots=True)
class StageContext:
    tenant_id: str
    recording: Recording
    prefix: str  # {tenant_id}/{recording_id}/{stage}@{version}/: write this stage's outputs here
    artefacts: ArtefactStore
    attempt: int


Work = Callable[[StageContext], dict[str, Any] | None]


@dataclass(frozen=True, slots=True)
class Outcome:
    result: Literal["done", "work_skipped", "already_done", "missing", "stopped", "retry", "failed", "needs_review"]
    retry_in: float | None = None


class StageRunner:
    def __init__(
        self,
        *,
        db: Database[dict[str, Any]],
        artefacts: ArtefactStore,
        versions: dict[str, str],
        worker: str,
        max_attempts: int = 6,
        heartbeat_s: float = 60.0,
        now: Callable[[], datetime] = utc_now,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._db = db
        self._client: MongoClient[dict[str, Any]] = db.client
        self._artefacts = artefacts
        self._versions = versions
        self._worker = worker
        self._max_attempts = max_attempts
        self._heartbeat_s = heartbeat_s
        self._now = now
        self._jitter = jitter

    def run(self, spec: StageSpec, work: Work, tenant_id: str, recording_id: str, *, attempt: int) -> Outcome:
        with tracer.start_as_current_span(f"stage.{spec.name}") as span:
            span.set_attributes(
                {"sabha.tenant_id": tenant_id, "sabha.recording_id": recording_id, "stage.attempt": attempt}
            )
            outcome = self._run(spec, work, tenant_id, recording_id, attempt)
            span.set_attribute("stage.result", outcome.result)
            return outcome

    def _repo[T: Any](self, collection: str, tenant_id: str, model: type[T]) -> SyncTenantRepo[T]:
        return SyncTenantRepo(self._db, collection, tenant_id, model)

    def _run(self, spec: StageSpec, work: Work, tenant_id: str, recording_id: str, attempt: int) -> Outcome:
        recordings = self._repo("recordings", tenant_id, Recording)
        recording = recordings.find_one({"_id": recording_id})
        if recording is None:
            log.warning("recording not found; nothing to do", extra={"recording_id": recording_id, "stage": spec.name})
            return Outcome("missing")
        if recording.status in (RecordingStatus.FAILED, RecordingStatus.NEEDS_REVIEW):
            return Outcome("stopped")
        if spec.entry_from is not None and recording.status is spec.entry_from:
            try:
                self._move(tenant_id, recording_id, spec.entry_from, spec.working, f"{spec.name}_started")
            except (ConcurrentTransition, ConsentRequired) as exc:
                log.info("could not start the stage", extra={"recording_id": recording_id, "reason": str(exc)})
            recording = recordings.find_one({"_id": recording_id})
            if recording is None:
                return Outcome("missing")
        if recording.status is not spec.working:
            return Outcome("already_done" if recording.status is not spec.entry_from else "stopped")

        runs = self._repo("stage_runs", tenant_id, StageRun)
        version = self._versions[spec.name]
        rerun = spec.per_run and recording.analysis_run > 1
        if rerun:
            version = run_version(version, recording.analysis_run)
        run = start_stage_run(runs, recording_id, spec.name, version, worker=self._worker, now=self._now())
        prefix = artefact_prefix(tenant_id, recording_id, spec.name, version)
        try:
            with self._heartbeat(runs, run):
                if self._artefacts.exists(prefix + DONE_MARKER):
                    meta: dict[str, Any] = {"work_skipped": True}
                else:
                    meta = work(StageContext(tenant_id, recording, prefix, self._artefacts, attempt)) or {}
                    self._artefacts.put(prefix + DONE_MARKER, b"", "text/plain")
            # A re-analysis ends quietly: the event says so, and the relay sends neither emails nor metering.
            done_meta = {"reanalysis": True, "analysis_run": recording.analysis_run} if rerun else None
            try:
                self._move(tenant_id, recording_id, spec.working, spec.done_to, f"{spec.name}_done", meta=done_meta)
            except ConcurrentTransition:
                log.info("another worker finished this stage", extra={"recording_id": recording_id})
            finish_stage_run(runs, run, succeeded=True, meta=meta, now=self._now())
            return Outcome("work_skipped" if meta.get("work_skipped") else "done")
        except NeedsReviewError as exc:
            finish_stage_run(runs, run, succeeded=False, error_code=exc.code, error_detail=exc.detail, now=self._now())
            self._stop(tenant_id, recording_id, spec, RecordingStatus.NEEDS_REVIEW, exc.code, None)
            return Outcome("needs_review")
        except PermanentError as exc:
            finish_stage_run(runs, run, succeeded=False, error_code=exc.code, error_detail=exc.detail, now=self._now())
            self._stop(tenant_id, recording_id, spec, RecordingStatus.FAILED, exc.code, (exc.detail, attempt))
            return Outcome("failed")
        except Exception as exc:  # TransientError and anything unexpected are retried
            code = exc.code if isinstance(exc, StageError) else f"unexpected_{type(exc).__name__}"
            detail = exc.detail if isinstance(exc, StageError) else str(exc)[:2000]
            finish_stage_run(runs, run, succeeded=False, error_code=code, error_detail=detail, now=self._now())
            if attempt < self._max_attempts:
                log.warning("stage failed; will retry", extra={"recording_id": recording_id, "code": code})
                return Outcome("retry", self._jitter() * min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * 2 ** (attempt - 1)))
            self._stop(tenant_id, recording_id, spec, RecordingStatus.FAILED, code, (detail, attempt))
            return Outcome("failed")

    def _move(
        self, tenant_id: str, recording_id: str, src: RecordingStatus, dst: RecordingStatus, reason: str,
        meta: dict[str, Any] | None = None,
    ) -> None:  # fmt: skip
        recordings = self._repo("recordings", tenant_id, Recording)
        outbox = self._repo("outbox", tenant_id, OutboxEvent)
        with self._client.start_session() as session, session.start_transaction():
            record_transition(recordings, outbox, recording_id, src, dst, session=session, reason=reason, meta=meta)

    def _stop(
        self,
        tenant_id: str,
        recording_id: str,
        spec: StageSpec,
        status: RecordingStatus,
        code: str,
        dead_letter: tuple[str | None, int] | None,
    ) -> None:
        """Move to FAILED or NEEDS_REVIEW with its event and, for FAILED, a dead letter: all or nothing."""
        recordings = self._repo("recordings", tenant_id, Recording)
        outbox = self._repo("outbox", tenant_id, OutboxEvent)
        dlq = self._repo("dlq", tenant_id, DeadLetter)
        with self._client.start_session() as session, session.start_transaction():
            try:
                record_transition(
                    recordings, outbox, recording_id, spec.working, status, session=session, reason=code,
                    meta={"stage": spec.name},
                )  # fmt: skip
            except ConcurrentTransition:
                log.info("recording moved on before it could be stopped", extra={"recording_id": recording_id})
                return
            if dead_letter is not None:
                detail, attempts = dead_letter
                dlq.insert_one(
                    DeadLetter(
                        recording_id=recording_id,
                        stage=spec.name,
                        task=f"sabha.{spec.name}",
                        error_code=code,
                        error_detail=detail[:2000] if detail else None,
                        attempts=attempts,
                        args={"tenant_id": tenant_id, "recording_id": recording_id},
                    ),
                    session=session,
                )

    @contextmanager
    def _heartbeat(self, runs: SyncTenantRepo[StageRun], run: StageRun) -> Iterator[None]:
        stop = threading.Event()

        def beat() -> None:
            while not stop.wait(self._heartbeat_s):
                runs.update_one({"_id": run.id, "status": "running"}, {"$set": {"heartbeat_at": self._now()}})

        thread = threading.Thread(target=beat, name=f"heartbeat-{run.id}", daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=5)
