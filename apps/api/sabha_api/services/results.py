"""Reading recordings and their results: list, detail, transcript, analysis, history and trends (plan task P5.7b).

Who sees what (decided 2026-10-19 and in P5.7b):

- owners and admins: every recording and person in their tenant;
- managers and reviewers: recordings and people in their units;
- staff: only recordings of their own person.

Anything outside that is 404, never 403, so a recording's existence is not revealed. The rule lives in
`visible_filter` and every read goes through it.

The API never touches audio (golden rule 2): playback is a short-lived presigned URL to playback.opus, and
issuing one is audited as `recording.play`. Reading a report is audited as `analysis.view` (CLAUDE.md). Evidence
quotes are shown as stored: redacted for everyone (decided 2026-10-19), so no un-redaction happens here.

Lists use cursor pagination (newest first): the cursor is an opaque token for the last item's (created_at, id).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from sabha_api.auth import Principal, Role
from sabha_api.errors import BadRequestError, NotFoundError
from sabha_core.models import Analysis, Person, Recording, Score, Transcript
from sabha_core.repo import TenantRepo
from sabha_core.settings import Settings
from sabha_core.storage import artefact_prefix

VIEW_ALL = frozenset({Role.OWNER, Role.ADMIN})
UNIT_SCOPED = frozenset({Role.MANAGER, Role.REVIEWER})
MAX_LIMIT = 100
NOTHING: dict[str, Any] = {"_id": {"$in": []}}


class ArtefactReader:
    """The artefacts bucket: small JSON documents and presigned playback URLs (never audio bytes)."""

    def __init__(self, s3: Any, settings: Settings) -> None:
        self._s3 = s3
        self._bucket = settings.s3_bucket_artefacts
        self._expiry = settings.playback_url_expiry_s

    async def json(self, key: str) -> Any:
        try:
            response = await asyncio.to_thread(self._s3.get_object, Bucket=self._bucket, Key=key)
        except self._s3.exceptions.NoSuchKey:
            return None
        body = await asyncio.to_thread(response["Body"].read)
        return json.loads(body)

    def playback_url(self, key: str) -> str:
        url: str = self._s3.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=self._expiry
        )
        return url

    @property
    def expiry_s(self) -> int:
        return self._expiry


# --- Visibility ---


async def _own_person(principal: Principal, people: TenantRepo[Person]) -> Person | None:
    return await people.find_one({"user_id": principal.user_id})


async def visible_filter(principal: Principal, people: TenantRepo[Person]) -> dict[str, Any]:
    """The recordings this caller may see, as a MongoDB filter (module docstring)."""
    if principal.role in VIEW_ALL:
        return {}
    if principal.role in UNIT_SCOPED:
        return {"unit_id": {"$in": list(principal.unit_ids)}}
    own = await _own_person(principal, people)
    return NOTHING if own is None else {"person_id": own.id}


async def visible_recording(
    principal: Principal, recording_id: str, recordings: TenantRepo[Recording], people: TenantRepo[Person]
) -> Recording:
    found = await recordings.find_one({"_id": recording_id, **await visible_filter(principal, people)})
    if found is None:
        raise NotFoundError("This recording does not exist or you cannot see it.")
    return found


async def visible_person(principal: Principal, person_id: str, people: TenantRepo[Person]) -> Person:
    person = await people.find_one({"_id": person_id})
    allowed = person is not None and (
        principal.role in VIEW_ALL
        or (principal.role in UNIT_SCOPED and person.unit_id in principal.unit_ids)
        or (principal.role is Role.STAFF and person.user_id == principal.user_id)
    )
    if not allowed or person is None:
        raise NotFoundError("This person does not exist or you cannot see them.")
    return person


# --- Cursor pagination ---


def encode_cursor(created_at: datetime, item_id: str) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{item_id}".encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        stamp, item_id = raw.split("|", 1)
        return datetime.fromisoformat(stamp), item_id
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise BadRequestError("The cursor is not valid; start again without it.") from exc


def after_cursor(cursor: str | None) -> dict[str, Any]:
    if not cursor:
        return {}
    created_at, item_id = decode_cursor(cursor)
    return {"$or": [{"created_at": {"$lt": created_at}}, {"created_at": created_at, "_id": {"$lt": item_id}}]}


# --- Output shapes ---


class PersonRef(BaseModel):
    id: str
    name: str


class RecordingOut(BaseModel):
    id: str
    type: str
    status: str
    status_reason: str | None
    person: PersonRef | None
    unit_id: str | None
    file_name: str | None
    duration_ms: int | None
    created_at: datetime
    status_changed_at: datetime | None
    completed_at: datetime | None
    overall_score: float | None  # the latest analysis, when there is one


class RecordingPage(BaseModel):
    items: list[RecordingOut]
    next_cursor: str | None


class TranscriptOut(BaseModel):
    recording_id: str
    transcript: dict[str, Any]
    roles: dict[str, str]
    roles_need_review: bool
    language_mix: dict[str, float]
    playback_url: str
    playback_expires_in_s: int


class AnalysisSummary(BaseModel):
    id: str
    version: str
    status: str
    overall_score: float | None
    verified_share: float
    review_reasons: list[str]
    rubric_id: str
    rubric_version: str
    model_ids: list[str]
    created_at: datetime


class AnalysisOut(BaseModel):
    recording_id: str
    analysis: AnalysisSummary
    report: dict[str, Any]


class TrendPoint(BaseModel):
    recording_id: str
    analysis_id: str
    created_at: datetime
    score: float | None
    verified: bool


class TrendOut(BaseModel):
    person_id: str
    dimension: str | None  # None: the overall score
    points: list[TrendPoint]


def summary(analysis: Analysis) -> AnalysisSummary:
    return AnalysisSummary(
        id=analysis.id, version=analysis.version, status=analysis.status, overall_score=analysis.overall_score,
        verified_share=analysis.verified_share, review_reasons=analysis.review_reasons, rubric_id=analysis.rubric_id,
        rubric_version=analysis.rubric_version, model_ids=analysis.model_ids, created_at=analysis.created_at,
    )  # fmt: skip


async def _latest_analyses(analyses: TenantRepo[Analysis], recording_ids: list[str]) -> dict[str, Analysis]:
    latest: dict[str, Analysis] = {}
    for item in await analyses.find({"recording_id": {"$in": recording_ids}}, sort=[("created_at", 1)]):
        latest[item.recording_id] = item  # ascending, so the newest wins
    return latest


async def recording_out(
    recordings: list[Recording], people: TenantRepo[Person], analyses: TenantRepo[Analysis]
) -> list[RecordingOut]:
    person_ids = sorted({r.person_id for r in recordings if r.person_id})
    names = {p.id: p.name for p in await people.find({"_id": {"$in": person_ids}})} if person_ids else {}
    latest = await _latest_analyses(analyses, [r.id for r in recordings]) if recordings else {}
    return [
        RecordingOut(
            id=r.id, type=r.type.value, status=r.status.value, status_reason=r.status_reason,
            person=PersonRef(id=r.person_id, name=names[r.person_id]) if r.person_id in names else None,
            unit_id=r.unit_id, file_name=r.file_name, duration_ms=r.duration_ms, created_at=r.created_at,
            status_changed_at=r.status_changed_at, completed_at=r.completed_at,
            overall_score=latest[r.id].overall_score if r.id in latest else None,
        )
        for r in recordings
    ]  # fmt: skip


# --- Reads ---


async def list_recordings(
    principal: Principal,
    *,
    cursor: str | None,
    limit: int,
    recordings: TenantRepo[Recording],
    people: TenantRepo[Person],
    analyses: TenantRepo[Analysis],
) -> RecordingPage:
    query = {**await visible_filter(principal, people)}
    page_filter = after_cursor(cursor)
    found = await recordings.find({"$and": [query, page_filter]} if page_filter else query,
                                  sort=[("created_at", -1), ("_id", -1)], limit=limit + 1)  # fmt: skip
    items, more = found[:limit], len(found) > limit
    next_cursor = encode_cursor(items[-1].created_at, items[-1].id) if more and items else None
    return RecordingPage(items=await recording_out(items, people, analyses), next_cursor=next_cursor)


async def transcript_for(
    recording: Recording, settings: Settings, transcripts: TenantRepo[Transcript], reader: ArtefactReader
) -> TranscriptOut:
    doc = await transcripts.find_one({"recording_id": recording.id})
    content = None if doc is None else await reader.json(doc.storage_key)
    if doc is None or content is None:
        raise NotFoundError("This recording has no transcript yet.")
    playback = artefact_prefix(recording.tenant_id, recording.id, "preprocess", settings.artefact_version_preprocess)
    return TranscriptOut(
        recording_id=recording.id, transcript=content, roles=doc.roles, roles_need_review=doc.roles_need_review,
        language_mix=doc.language_mix, playback_url=reader.playback_url(playback + "playback.opus"),
        playback_expires_in_s=reader.expiry_s,
    )  # fmt: skip


async def latest_analysis(recording: Recording, analyses: TenantRepo[Analysis], reader: ArtefactReader) -> AnalysisOut:
    found = await analyses.find({"recording_id": recording.id}, sort=[("created_at", -1)], limit=1)
    report = None if not found else await reader.json(found[0].report_key)
    if not found or report is None:
        raise NotFoundError("This recording has no analysis yet.")
    return AnalysisOut(recording_id=recording.id, analysis=summary(found[0]), report=report)


async def analysis_history(recording: Recording, analyses: TenantRepo[Analysis]) -> list[AnalysisSummary]:
    return [summary(a) for a in await analyses.find({"recording_id": recording.id}, sort=[("created_at", -1)])]


async def trend(
    person: Person,
    dimension: str | None,
    *,
    limit: int,
    analyses: TenantRepo[Analysis],
    scores: TenantRepo[Score],
) -> TrendOut:
    if dimension is None:
        rows = await analyses.find({"person_id": person.id, "status": "COMPLETED"}, sort=[("created_at", -1)],
                                   limit=limit)  # fmt: skip
        points = [TrendPoint(recording_id=a.recording_id, analysis_id=a.id, created_at=a.created_at,
                             score=a.overall_score, verified=a.overall_score is not None) for a in rows]  # fmt: skip
    else:
        found = await scores.find({"person_id": person.id, "dimension": dimension}, sort=[("created_at", -1)],
                                  limit=limit)  # fmt: skip
        points = [TrendPoint(recording_id=s.recording_id, analysis_id=s.analysis_id, created_at=s.created_at,
                             score=s.score, verified=s.verified) for s in found]  # fmt: skip
    return TrendOut(person_id=person.id, dimension=dimension, points=list(reversed(points)))  # oldest first
