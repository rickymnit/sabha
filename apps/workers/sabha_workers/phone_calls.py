"""Phone calls from MyOperator (ADR 0017): copying call details in, and fetching a call's audio when asked.

Two jobs:

- `sync_calls` (beat, every MYOPERATOR_SYNC_EVERY_S): asks MyOperator's Search Logs API for calls since the newest
  one already copied (less an overlap, as late calls appear), or MYOPERATOR_BACKFILL_DAYS back on the first run,
  and keeps the answered, recorded ones in `phone_calls` (one document per call id; a second run changes nothing
  but the details). Only call details are copied; the customer's number is kept as its last four digits.
- `import_audio` (task `sabha.phone_call_import`, started by the relay on a `phone_call.import` event that the API
  writes when someone presses Analyse): gets a fresh recording link from MyOperator, downloads the MP3 into the
  audio bucket at the recording's original key, then moves the recording CREATED -> UPLOADED with its outbox event
  in one transaction, so the pipeline starts as for a browser upload. The API never touches the audio (golden rule
  2). Idempotent: a recording no longer CREATED is left alone (golden rule 3).

MyOperator's API (Postman collection "MyOperator API Document", checked 2026-11-20): the token goes in the request
as `token`, not a header. Search Logs is POST /search/search (`from`, `to` in Unix seconds, `log_from` offset,
`page_size` at most 100), newest first. The recording link is GET /recordings/link?file=..., valid 24 hours. In the
answers: `event` 1 is incoming and 2 outgoing; `status` 1 answered and 2 missed; each leg's `action` is received,
missed or transferred, with the agent in `received_by`.
"""

from __future__ import annotations

import hashlib
import logging
import re
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
from pymongo.database import Database

from sabha_core.models import OutboxEvent, Person, PhoneAgent, PhoneCall, Recording, new_id, utc_now
from sabha_core.outbox import record_transition
from sabha_core.repo import SyncTenantRepo
from sabha_core.state import RecordingStatus

log = logging.getLogger("sabha.workers.phone_calls")

PAGE_SIZE = 100  # MyOperator's maximum
MAX_PAGES = 300  # one run reads at most 30 000 calls; the next run carries on from the newest copied
OVERLAP = timedelta(hours=2)  # calls are listed a little after they end; read the last two hours again
TIMEOUT_S = 30.0
DOWNLOAD_TIMEOUT_S = 300.0


class MyOperatorError(Exception):
    """MyOperator refused or failed a request. `retryable`: worth trying again later (network, 429, 5xx)."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class MyOperatorClient:
    """The few MyOperator calls Sabha needs. The token never appears in errors or logs (sabha_core.logging masks
    `token=` in URLs as well)."""

    def __init__(self, token: str, base_url: str, *, http: httpx.Client | None = None) -> None:
        self._token = token
        self._base = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=TIMEOUT_S)

    def _answer(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 429 or response.status_code >= 500:
            raise MyOperatorError(f"MyOperator answered HTTP {response.status_code}", retryable=True)
        try:
            body = response.json()
        except ValueError as exc:
            raise MyOperatorError(
                f"MyOperator answered HTTP {response.status_code} without JSON", retryable=False
            ) from exc
        if response.status_code != 200 or body.get("status") != "success":
            reason = str(body.get("error") or body.get("message") or f"HTTP {response.status_code}")[:200]
            raise MyOperatorError(f"MyOperator refused the request: {reason}", retryable=False)
        return dict(body)

    def search(self, start: datetime, end: datetime, offset: int) -> tuple[list[dict[str, Any]], int]:
        """One page of call logs between `start` and `end`, newest first, and how many there are in all."""
        try:
            response = self._http.post(
                f"{self._base}/search/search",
                data={
                    "token": self._token,
                    "from": int(start.timestamp()),
                    "to": int(end.timestamp()),
                    "log_from": offset,
                    "page_size": PAGE_SIZE,
                },
            )
        except httpx.HTTPError as exc:
            raise MyOperatorError(f"could not reach MyOperator ({type(exc).__name__})", retryable=True) from exc
        data = self._answer(response).get("data") or {}
        return list(data.get("hits") or []), int(data.get("total") or 0)

    def recording_url(self, file: str) -> str:
        """A link to the recording's MP3, valid for 24 hours."""
        try:
            response = self._http.get(f"{self._base}/recordings/link", params={"token": self._token, "file": file})
        except httpx.HTTPError as exc:
            raise MyOperatorError(f"could not reach MyOperator ({type(exc).__name__})", retryable=True) from exc
        url = self._answer(response).get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise MyOperatorError("MyOperator gave no recording link for this call", retryable=False)
        return url

    def download(self, url: str) -> Iterator[bytes]:
        """The recording's bytes, in pieces."""
        try:
            with self._http.stream("GET", url, timeout=DOWNLOAD_TIMEOUT_S) as response:
                if response.status_code != 200:
                    raise MyOperatorError(
                        f"the recording link answered HTTP {response.status_code}",
                        retryable=response.status_code >= 500,
                    )
                yield from response.iter_bytes(1024 * 1024)
        except httpx.HTTPError as exc:
            raise MyOperatorError(f"the recording download failed ({type(exc).__name__})", retryable=True) from exc


# --- Reading a call log ---

_DIGITS = re.compile(r"\D+")
DIRECTIONS: dict[object, Literal["incoming", "outgoing"]] = {1: "incoming", 2: "outgoing"}


def mask_number(number: object) -> str:
    """The last four digits only ("+919876543210" -> "••••3210"); "Unknown" when there are none."""
    digits = _DIGITS.sub("", str(number or ""))
    return f"••••{digits[-4:]}" if len(digits) >= 4 else "Unknown"


def _seconds(duration: object) -> int | None:
    """ "00:04:30" -> 270."""
    parts = str(duration or "").split(":")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    hours, minutes, seconds = (int(p) for p in parts)
    return hours * 3600 + minutes * 60 + seconds


def _time(value: object) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(str(value)), UTC) if value not in (None, "", 0) else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def agents_of(source: dict[str, Any]) -> list[PhoneAgent]:
    """Everyone who answered, in the order they did: the agent of each leg that was not missed."""
    found: dict[str, PhoneAgent] = {}
    for leg in source.get("log_details") or []:
        if leg.get("action") == "missed":
            continue
        for person in leg.get("received_by") or []:
            user_id = str(person.get("user_id") or "").strip()
            if user_id and user_id not in found:
                extension = str(person.get("extension") or "").strip() or None
                found[user_id] = PhoneAgent(
                    user_id=user_id, name=str(person.get("name") or "").strip() or "Unknown", extension=extension
                )
    return list(found.values())


def parse_call(hit: dict[str, Any]) -> PhoneCall | None:
    """The call in one Search Logs hit, or None when it is not an answered, recorded call."""
    source = hit.get("_source") or {}
    call_id = str(source.get("allcaller_id") or hit.get("user_id") or "").strip()
    recording_file = str(source.get("filename") or "").strip()
    direction = DIRECTIONS.get(source.get("event"))
    started = _time(source.get("start_time"))
    agents = agents_of(source)
    if not call_id or not recording_file or direction is None or started is None or not agents:
        return None
    ended = _time(source.get("end_time"))
    duration = _seconds(source.get("duration"))
    if duration is None:
        duration = max(0, int((ended - started).total_seconds())) if ended else 0
    return PhoneCall(
        call_id=call_id,
        direction=direction,
        started_at=started,
        ended_at=ended,
        duration_s=duration,
        department=str(source.get("department_name") or "").strip() or None,
        customer=mask_number(source.get("caller_number")),
        agents=agents,
        recording_file=recording_file,
    )


# --- Copying calls in ---


@dataclass(frozen=True)
class SyncResult:
    read: int  # call logs read from MyOperator
    kept: int  # answered, recorded calls written (new or updated)


def _agent_people(people: SyncTenantRepo[Person]) -> dict[str, Person]:
    """MyOperator user id -> the person matched to it."""
    return {agent: p for p in people.find({"phone_agent_ids": {"$ne": []}}) for agent in p.phone_agent_ids}


def save_call(calls: SyncTenantRepo[PhoneCall], call: PhoneCall, matched: dict[str, Person]) -> None:
    """Insert the call, or refresh its details; never touches whether it was analysed."""
    details = call.model_dump(
        by_alias=True,
        include={
            "provider",
            "direction",
            "started_at",
            "ended_at",
            "duration_s",
            "department",
            "customer",
            "agents",
            "recording_file",
            "synced_at",
        },
    )
    person = matched.get(call.agents[0].user_id)
    if person is not None:
        details |= {"person_id": person.id, "unit_id": person.unit_id}
    calls.update_one(
        {"call_id": call.call_id},
        {"$set": details, "$setOnInsert": {"_id": new_id(), "created_at": utc_now()}},
        upsert=True,
    )


def sync_calls(
    db: Database[dict[str, Any]], client: MyOperatorClient, tenant_id: str, *, now: datetime, backfill_days: int
) -> SyncResult:
    """Copy in the answered, recorded calls since the newest one already here (module docstring)."""
    calls = SyncTenantRepo(db, "phone_calls", tenant_id, PhoneCall)
    newest = calls.find({}, sort=[("started_at", -1)], limit=1)
    start = newest[0].started_at - OVERLAP if newest else now - timedelta(days=backfill_days)
    matched = _agent_people(SyncTenantRepo(db, "people", tenant_id, Person))
    read = kept = 0
    for page in range(MAX_PAGES):
        hits, total = client.search(start, now, offset=page * PAGE_SIZE)
        read += len(hits)
        for hit in hits:
            call = parse_call(hit)
            if call is not None:
                save_call(calls, call, matched)
                kept += 1
        if len(hits) < PAGE_SIZE or read >= total:
            break
    else:
        log.warning(
            "phone call sync stopped at its page limit; the next run carries on",
            extra={"tenant_id": tenant_id, "read": read},
        )
    log.info("phone calls synced", extra={"tenant_id": tenant_id, "read": read, "kept": kept})
    return SyncResult(read=read, kept=kept)


# --- Fetching a call's audio ---

CONTENT_TYPE = "audio/mpeg"


def import_audio(
    db: Database[dict[str, Any]],
    s3: Any,
    client: MyOperatorClient,
    *,
    bucket: str,
    tenant_id: str,
    recording_id: str,
    max_bytes: int,
) -> str:
    """Copy the call's MP3 into storage and release the recording for processing. Returns what happened.

    Raises MyOperatorError; the task retries a retryable one and records a permanent one with `record_failure`.
    """
    recordings = SyncTenantRepo(db, "recordings", tenant_id, Recording)
    recording = recordings.find_one({"_id": recording_id})
    if recording is None or recording.phone_call_id is None or recording.storage_key is None:
        return "not_a_phone_call"
    if recording.status is not RecordingStatus.CREATED:
        return "already_imported"
    calls = SyncTenantRepo(db, "phone_calls", tenant_id, PhoneCall)
    call = calls.find_one({"_id": recording.phone_call_id})
    if call is None:
        raise MyOperatorError("the phone call this recording came from no longer exists", retryable=False)

    url = client.recording_url(call.recording_file)
    digest, size = hashlib.sha256(), 0
    with tempfile.TemporaryFile() as spool:
        for piece in client.download(url):
            size += len(piece)
            if size > max_bytes:
                raise MyOperatorError(f"the recording is larger than {max_bytes} bytes", retryable=False)
            digest.update(piece)
            spool.write(piece)
        if size == 0:
            raise MyOperatorError("MyOperator sent an empty recording", retryable=False)
        spool.seek(0)
        s3.upload_fileobj(spool, bucket, recording.storage_key, ExtraArgs={"ContentType": CONTENT_TYPE})

    outbox = SyncTenantRepo(db, "outbox", tenant_id, OutboxEvent)
    with db.client.start_session() as session, session.start_transaction():
        record_transition(
            recordings,
            outbox,
            recording_id,
            RecordingStatus.CREATED,
            RecordingStatus.UPLOADED,
            reason="phone_call_imported",
            meta={"size_bytes": size, "duplicate_of": None, "ready": True},
            session=session,
        )
        recordings.update_one(
            {"_id": recording_id},
            {
                "$set": {
                    "sha256": digest.hexdigest(),
                    "size_bytes": size,
                    "awaiting_consent": False,
                    "completed_at": utc_now(),
                    "status_reason": None,
                }
            },
            session=session,
        )
        calls.update_one({"_id": call.id}, {"$set": {"import_error": None}}, session=session)
    log.info("phone call audio imported", extra={"recording_id": recording_id, "size_bytes": size})
    return "imported"


def record_failure(db: Database[dict[str, Any]], *, tenant_id: str, recording_id: str, reason: str) -> None:
    """The audio could not be fetched: say so on the call (the page offers Analyse again) and on the recording."""
    recordings = SyncTenantRepo(db, "recordings", tenant_id, Recording)
    recording = recordings.find_one({"_id": recording_id})
    if recording is None or recording.status is not RecordingStatus.CREATED:
        return
    recordings.update_one({"_id": recording_id}, {"$set": {"status_reason": "phone_call_download_failed"}})
    if recording.phone_call_id:
        SyncTenantRepo(db, "phone_calls", tenant_id, PhoneCall).update_one(
            {"_id": recording.phone_call_id}, {"$set": {"import_error": reason[:300]}}
        )
    log.warning("phone call audio could not be fetched", extra={"recording_id": recording_id, "reason": reason})
