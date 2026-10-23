"""The transcribe stage (plan task P3.5) with fake providers: chunking, resume, errors, fallback, output."""

from __future__ import annotations

import json
import uuid
import wave
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from pymongo import MongoClient
from pymongo.database import Database

from sabha_asr.chunking import plan_chunks
from sabha_asr.provider import AudioChunk, ChunkResult, ProviderError
from sabha_asr.providers.fake import FakeProvider
from sabha_asr.transcriber import Transcriber
from sabha_core.indexes import ensure_indexes
from sabha_core.models import Recording, Tenant, Transcript
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.repo import SyncTenantRepo
from sabha_core.state import RecordingStatus
from sabha_core.timemap import Segment, SegmentMap
from sabha_workers.rubrics import rubric_for
from sabha_workers.stages.runner import DONE_MARKER, S3Artefacts, StageRunner, StageSpec
from sabha_workers.stages.transcribe import BATCH_SIZE, make_work, plan_key
from sabha_workers.stages.transcript import TranscriptDeps

S = RecordingStatus
TRANSCRIBE = StageSpec("transcribe", working=S.TRANSCRIBING, done_to=S.ANALYZING)
# Compact: a 40 s stretch of talk, then (after a removed silence) 10 s more.
MAP = SegmentMap((Segment(2_000, 42_000, 0), Segment(60_000, 70_000, 40_000)))
RUBRICS = Path(__file__).resolve().parents[3] / "rubrics"
TENANT = Tenant.from_profile("school", name="Sunrise Public School", plan=Plan.PILOT, id="t1")


class FlakyProvider(FakeProvider):
    """Fails with `error` on call number `fail_on` (1-based), answers otherwise."""

    def __init__(self, error: ProviderError, fail_on: int, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.error, self.fail_on = error, fail_on

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[ChunkResult]:
        if len(self.calls) + 1 == self.fail_on:
            self.calls.append([c.chunk_id for c in chunks])
            raise self.error
        return super().transcribe(chunks)


class SilentProvider(FakeProvider):
    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[ChunkResult]:
        self.calls.append([c.chunk_id for c in chunks])
        return [ChunkResult(c.chunk_id, "", (), ()) for c in chunks]


def test_a_different_chunk_plan_never_reuses_saved_parts() -> None:
    plan_a = plan_chunks(50_000, [40_000], max_chunk_ms=30_000)
    plan_b = plan_chunks(50_000, [40_000], max_chunk_ms=20_000)
    assert plan_key(plan_a) == plan_key(plan_chunks(50_000, [40_000], max_chunk_ms=30_000))
    assert plan_key(plan_a) != plan_key(plan_b)


# --- The stage (MongoDB, RustFS) ---


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"asr_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield name
    mongo_replica_set.drop_database(name)


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]], shared_db: str) -> Database[dict[str, Any]]:
    database = mongo_replica_set[shared_db]
    for collection in ("recordings", "stage_runs", "outbox", "dlq"):
        database[collection].delete_many({})
    return database


class Stage:
    def __init__(self, db: Database[dict[str, Any]], s3_storage: Any, tmp: Any) -> None:
        self.db = db
        self.artefacts = S3Artefacts(s3_storage.client(), "sabha-artefacts")
        self.tmp = tmp
        self.saved: list[Transcript] = []
        self.transcript_deps = TranscriptDeps(
            diarize_version="v1", tenant=lambda _: TENANT, rubric=lambda t, k: rubric_for(t, k, RUBRICS),
            tie_breaker=lambda *_: None, save=self.save_transcript,
        )  # fmt: skip
        self.runner = StageRunner(db=db, artefacts=self.artefacts, versions={"transcribe": "v1"}, worker="test",
                                  jitter=lambda: 0.0)  # fmt: skip

    def save_transcript(self, tenant_id: str, document: Transcript) -> None:
        # Through the real tenant-scoped repository: a missing tenant id must fail here, as in the worker.
        transcripts = SyncTenantRepo(self.db, "transcripts", tenant_id, Transcript)
        transcripts.insert_one(document)
        self.saved.append(document)

    def recording(self, segment_map: SegmentMap = MAP, *, with_inputs: bool = True) -> str:
        recording = Recording(type=ConversationType.TEACHING, status=S.TRANSCRIBING, consent_ref="c")
        rid = SyncTenantRepo(self.db, "recordings", "t1", Recording).insert_one(recording).id
        if with_inputs:
            compact = self.tmp / f"{rid}.wav"
            with wave.open(str(compact), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(16_000)
                out.writeframes(b"\x01\x00" * 16 * segment_map.compact_length_ms)
            self.artefacts.put_file(f"t1/{rid}/preprocess@v1/compact.wav", compact, "audio/wav")
            self.artefacts.put(f"t1/{rid}/preprocess@v1/segments@v1.json", segment_map.to_json().encode())
            # One teacher talking throughout: roles are clear, so the stage ends in ANALYZING.
            turns = [{"speaker_label": "S0", "start_ms": 0, "end_ms": segment_map.compact_length_ms}]
            self.artefacts.put(f"t1/{rid}/diarize@v1/diarization@v1.json", json.dumps({"compact": turns}).encode())
        return rid

    def run(self, rid: str, transcriber: Transcriber, attempt: int = 1) -> str:
        work = make_work(lambda: transcriber, "v1", self.transcript_deps)
        return self.runner.run(TRANSCRIBE, work, "t1", rid, attempt=attempt).result

    def doc(self, rid: str) -> dict[str, Any]:
        found = self.db.recordings.find_one({"_id": rid})
        assert found is not None
        return found

    def output(self, rid: str) -> dict[str, Any]:
        data: dict[str, Any] = json.loads(self.artefacts.get(f"t1/{rid}/transcribe@v1/asr@v1.json"))
        return data


@pytest.fixture
def stage(db: Database[dict[str, Any]], s3_storage: Any, tmp_path: Any) -> Stage:
    return Stage(db, s3_storage, tmp_path)


@pytest.mark.integration
def test_the_stage_writes_compact_words_and_cost_inputs(stage: Stage) -> None:
    rid = stage.recording()
    provider = FakeProvider(max_chunk_ms=30_000)
    assert stage.run(rid, Transcriber(provider)) == "done"

    assert stage.doc(rid)["status"] == "ANALYZING"
    # 40 s of talk is split in two (with overlap); the 10 s after the join is its own chunk.
    assert [len(call) for call in provider.calls] == [3]
    output = stage.output(rid)
    assert (output["version"], output["timeline"], output["provider"]) == ("asr@v1", "compact", "fake")
    assert output["fallback_reasons"] == [] and output["chunks"] == 3
    starts = [w["start_ms"] for w in output["words"]]
    assert starts == sorted(starts) and all(w["end_ms"] <= MAP.compact_length_ms for w in output["words"])
    assert {span["language"] for span in output["languages"]} == {"hi-IN"}
    assert stage.artefacts.exists(f"t1/{rid}/transcribe@v1/{DONE_MARKER}")
    (run,) = stage.db.stage_runs.find({"recording_id": rid})
    meta = run["meta"]
    assert (meta["requests"], meta["audio_s"], meta["provider"], meta["fallback"]) == (3, 50.0, "fake", False)
    assert meta["sent_audio_s"] == 50.5  # the 0.5 s overlap at the split is sent twice
    # P3.6/P3.7: roles and the transcript on the original timeline, then ANALYZING.
    assert stage.artefacts.exists(f"t1/{rid}/transcribe@v1/transcript@v1.json")
    (doc,) = stage.saved
    assert doc.roles == {"S0": "teacher"} and doc.storage_key.endswith("transcript@v1.json")
    assert meta["speakers"] == 1
    stored = stage.db.transcripts.find_one({"recording_id": rid})
    assert stored is not None and stored["tenant_id"] == "t1"


@pytest.mark.integration
def test_a_retry_resumes_after_the_batches_already_done(stage: Stage) -> None:
    # 40 chunks of <= 1 s (0.5 s overlaps): four batches of 10. 20 s of one voice is also a clear teacher.
    long_map = SegmentMap((Segment(0, 20_000, 0),))
    rid = stage.recording(long_map)
    flaky = FlakyProvider(ProviderError("fake", "HTTP 503", retryable=True), fail_on=2, max_chunk_ms=1_000)
    assert stage.run(rid, Transcriber(flaky), attempt=1) == "retry"
    assert stage.doc(rid)["status"] == "TRANSCRIBING"

    again = FakeProvider(max_chunk_ms=1_000)
    assert stage.run(rid, Transcriber(again), attempt=2) == "done"
    # Batch 1 was saved before batch 2 failed: the retry sends batches 2, 3 and 4 only.
    assert [len(call) for call in again.calls] == [BATCH_SIZE] * 3
    runs = sorted(stage.db.stage_runs.find({"recording_id": rid}), key=lambda r: r["attempt"])
    assert runs[0]["error_code"] == "asr_unavailable" and runs[1]["meta"]["batches_resumed"] == 1


@pytest.mark.integration
def test_a_permanent_provider_failure_fails_with_a_dead_letter(stage: Stage) -> None:
    rid = stage.recording()
    bad_key = FakeProvider(failure=ProviderError("fake", "HTTP 403 invalid_api_key_error", retryable=False))
    assert stage.run(rid, Transcriber(bad_key)) == "failed"
    assert (stage.doc(rid)["status"], stage.doc(rid)["status_reason"]) == ("FAILED", "asr_failed")
    (letter,) = stage.db.dlq.find({"recording_id": rid})
    assert "invalid_api_key_error" in letter["error_detail"]


@pytest.mark.integration
def test_a_configured_fallback_answers_and_is_recorded(stage: Stage) -> None:
    rid = stage.recording()
    down = FakeProvider(name="primary", failure=ProviderError("primary", "HTTP 503", retryable=True))
    backup = FakeProvider(name="backup")
    assert stage.run(rid, Transcriber(down, [backup])) == "done"
    output = stage.output(rid)
    assert output["provider"] == "backup" and output["fallback_reasons"] == ["primary: HTTP 503"]


@pytest.mark.integration
def test_no_words_at_all_asks_for_review(stage: Stage) -> None:
    rid = stage.recording()
    assert stage.run(rid, Transcriber(SilentProvider())) == "needs_review"
    assert (stage.doc(rid)["status"], stage.doc(rid)["status_reason"]) == ("NEEDS_REVIEW", "no_transcript")


@pytest.mark.integration
def test_missing_preprocess_output_fails_for_a_replay(stage: Stage) -> None:
    rid = stage.recording(with_inputs=False)
    assert stage.run(rid, Transcriber(FakeProvider())) == "failed"
    assert stage.doc(rid)["status_reason"] == "missing_input"
