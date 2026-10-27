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
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from sabha_api.auth import Principal, Role
from sabha_api.errors import BadRequestError, NotFoundError
from sabha_core.models import Analysis, Person, Recording, Score, Transcript, Unit
from sabha_core.profiles import ConversationType
from sabha_core.reasons import explain
from sabha_core.repo import TenantRepo
from sabha_core.settings import Settings
from sabha_core.state import RecordingStatus
from sabha_core.storage import artefact_prefix
from sabha_core.timemap import SegmentMap

VIEW_ALL = frozenset({Role.OWNER, Role.ADMIN})
LATEST: dict[str, Any] = {"superseded": {"$ne": True}}  # an analysis or score not replaced by a re-analysis
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


class PersonOut(BaseModel):
    id: str
    name: str
    unit_id: str | None


async def visible_people(principal: Principal, people: TenantRepo[Person]) -> list[PersonOut]:
    """The people this caller may see and upload for: all (owners, admins), their units (managers, reviewers) or
    only themselves (staff), by name."""
    if principal.role in VIEW_ALL:
        query: dict[str, Any] = {}
    elif principal.role in UNIT_SCOPED:
        query = {"unit_id": {"$in": list(principal.unit_ids)}}
    else:
        query = {"user_id": principal.user_id}
    found = await people.find(query, sort=[("name", 1)])
    return [PersonOut(id=p.id, name=p.name, unit_id=p.unit_id) for p in found]


RECENT_SCORES = 10


class PersonSummary(PersonOut):
    """A row of the People page: real counts and scores only (golden rule 6), nothing estimated."""

    analysed: int  # recordings with a completed analysis
    latest_score: float | None  # the overall score of the most recently analysed recording
    recent_scores: list[float]  # overall scores of the last RECENT_SCORES analysed recordings, oldest first
    last_analysed_at: datetime | None


async def people_summary(
    principal: Principal, people: TenantRepo[Person], analyses: TenantRepo[Analysis]
) -> list[PersonSummary]:
    """visible_people, each with how many of their recordings are analysed and their recent overall scores. A
    re-analysed recording counts once, with its newest result."""
    visible = await visible_people(principal, people)
    ids = [p.id for p in visible]
    found = (
        await analyses.find({"person_id": {"$in": ids}, "status": "COMPLETED"}, sort=[("created_at", 1)]) if ids else []
    )
    newest: dict[str, dict[str, Analysis]] = {}  # person -> recording -> its newest analysis
    for analysis in found:
        newest.setdefault(analysis.person_id or "", {})[analysis.recording_id] = analysis
    out = []
    for person in visible:
        mine = sorted(newest.get(person.id, {}).values(), key=lambda a: a.created_at)
        scored = [a.overall_score for a in mine if a.overall_score is not None]
        out.append(PersonSummary(
            **person.model_dump(), analysed=len(mine), latest_score=scored[-1] if scored else None,
            recent_scores=scored[-RECENT_SCORES:], last_analysed_at=mine[-1].created_at if mine else None,
        ))  # fmt: skip
    return out


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


def recording_title(file_name: str | None, recording_id: str) -> str:
    """What people call the recording: its file name without the extension ("Class 7B.mp3" -> "Class 7B")."""
    if not file_name:
        return recording_id
    stem, dot, extension = file_name.rpartition(".")
    return stem if dot and stem.strip() and extension.isalnum() and len(extension) <= 5 else file_name


class RecordingOut(BaseModel):
    id: str
    title: str
    type: str
    status: str
    status_reason: str | None
    status_note: str | None  # why it failed or needs review, in plain words (sabha_core.reasons); else None
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
    superseded: bool  # a newer analysis of the recording exists (re-analysis)
    created_at: datetime


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
        rubric_version=analysis.rubric_version, model_ids=analysis.model_ids, superseded=analysis.superseded,
        created_at=analysis.created_at,
    )  # fmt: skip


def status_note(recording: Recording) -> str | None:
    if recording.status.value not in ("FAILED", "NEEDS_REVIEW"):
        return None
    return explain(recording.status_reason)


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
            id=r.id, title=recording_title(r.file_name, r.id), type=r.type.value, status=r.status.value,
            status_reason=r.status_reason, status_note=status_note(r),
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
    person_id: str | None = None,
    type: ConversationType | None = None,
    status: RecordingStatus | None = None,
) -> RecordingPage:
    # Every condition is AND-ed with the visibility filter, so the narrowing filters can never widen it.
    conditions: list[dict[str, Any]] = [await visible_filter(principal, people), after_cursor(cursor)]
    if person_id is not None:
        conditions.append({"person_id": person_id})
    if type is not None:
        conditions.append({"type": type.value})
    if status is not None:
        conditions.append({"status": status.value})
    kept = [c for c in conditions if c]  # owners see everything: their visibility filter is {}
    query = {"$and": kept} if kept else {}
    found = await recordings.find(query, sort=[("created_at", -1), ("_id", -1)], limit=limit + 1)
    items, more = found[:limit], len(found) > limit
    next_cursor = encode_cursor(items[-1].created_at, items[-1].id) if more and items else None
    return RecordingPage(items=await recording_out(items, people, analyses), next_cursor=next_cursor)


class RecordingCounts(BaseModel):
    by_type: dict[str, int]  # only types with at least one recording


async def count_recordings(
    principal: Principal, *, recordings: TenantRepo[Recording], people: TenantRepo[Person]
) -> RecordingCounts:
    """Per type, the recordings `list_recordings` would show this caller (the same visibility filter)."""
    visible = await visible_filter(principal, people)
    rows = await recordings.aggregate([{"$match": visible}, {"$group": {"_id": "$type", "n": {"$sum": 1}}}])
    return RecordingCounts(by_type={row["_id"]: row["n"] for row in sorted(rows, key=lambda r: str(r["_id"]))})


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
        rows = await analyses.find({"person_id": person.id, "status": "COMPLETED", **LATEST}, sort=[("created_at", -1)],
                                   limit=limit)  # fmt: skip
        points = [TrendPoint(recording_id=a.recording_id, analysis_id=a.id, created_at=a.created_at,
                             score=a.overall_score, verified=a.overall_score is not None) for a in rows]  # fmt: skip
    else:
        found = await scores.find({"person_id": person.id, "dimension": dimension, **LATEST},
                                  sort=[("created_at", -1)], limit=limit)  # fmt: skip
        points = [TrendPoint(recording_id=s.recording_id, analysis_id=s.analysis_id, created_at=s.created_at,
                             score=s.shown_score, verified=s.verified) for s in found]  # fmt: skip
    return TrendOut(person_id=person.id, dimension=dimension, points=list(reversed(points)))  # oldest first


# --- The report page's payloads (apps/web/src/features/report/types.ts, field for field) ---

PROCESSING_STAGES = {
    "CREATED": "uploaded", "UPLOADED": "uploaded", "PREPROCESSING": "preprocessing", "DIARIZING": "diarizing",
    "TRANSCRIBING": "transcribing", "ANALYZING": "analyzing",
}  # fmt: skip
LANGUAGE_NAMES = {"hi": "Hindi", "en": "English", "mr": "Marathi", "ta": "Tamil", "te": "Telugu", "bn": "Bengali",
                  "gu": "Gujarati", "kn": "Kannada", "ml": "Malayalam", "pa": "Punjabi", "or": "Odia"}  # fmt: skip
STAFF_ROLE_WORDS = frozenset({"teacher", "receptionist", "sales_rep"})


def _reasons(codes: list[str]) -> list[dict[str, str]]:
    return [{"code": code, "message": explain(code)} for code in codes]


# Display names for the computed metrics (sabha_analytics.metrics). "{person}" is the tenant's word for the staff
# member ("Teacher", "Receptionist" in a school; "Sales rep" in a company); other roles are named as below.
METRIC_NAMES = {
    "duration_s": "Length",
    "call_duration_s": "Call length",
    "silence_share": "Silence",
    "longest_silence_s": "Longest silence",
    "long_silence_count": "Long pauses or holds",
    "hold_gap_count": "Holds",
    "open_question_count": "Open questions asked",
    "open_question_ratio": "Open questions",
    "words_per_minute": "Speaking pace",
    "longest_monologue_s": "Longest uninterrupted talk",
    "voice_count": "Voices",
    "top_voice_share": "Largest share of talk",
    "quiet_voice_count": "Voices hardly heard",
}
ROLE_METRIC_NAMES = {"talk_share": "{role} talk time", "turn_count": "Turns by {role_lower}",
                     "question_count": "Questions asked by {role_lower}"}  # fmt: skip
OTHER_ROLE_WORDS = {"students": "Student", "caller": "Caller", "customer": "Customer", "visitor": "Visitor"}


def metric_name(key: str, person_label: str) -> str:
    """A metric's name in plain words: "teacher_talk_share" -> "Teacher talk time" (in the tenant's own word)."""
    if key in METRIC_NAMES:
        return METRIC_NAMES[key]
    for suffix, pattern in ROLE_METRIC_NAMES.items():
        role = key.removesuffix("_" + suffix)
        if role != key:
            word = person_label if role in STAFF_ROLE_WORDS else OTHER_ROLE_WORDS.get(role, role.replace("_", " "))
            word = word[:1].upper() + word[1:]
            return pattern.format(role=word, role_lower=word.lower())
    words = [w for w in key.split("_") if w not in ("s", "ms")]  # a metric added later: its key, minus the unit
    name = " ".join(person_label if w in STAFF_ROLE_WORDS else w for w in words)
    return name[:1].upper() + name[1:]


def metric_out(metric: dict[str, Any], person_label: str) -> dict[str, Any]:
    """analysis@v1 metric -> the UI's Metric: display name in the tenant's words, and units the UI formats."""
    name = metric_name(metric["key"], person_label)
    value, unit = metric["value"], metric["unit"]
    if unit == "s":
        value, unit = (None if value is None else round(value * 1000)), "ms"
    unit = {"words/min": "wpm", "words_per_minute": "wpm"}.get(unit, unit)
    if unit not in ("ratio", "count", "wpm", "ms"):
        unit = "count"
    return {"key": metric["key"], "name": name, "value": value, "unit": unit,
            "definition": metric["definition"]}  # fmt: skip


# Analyses made before synthesis prompt v2 can name utterance ids ("At utterance u0000, try ..."). The id means
# nothing to a reader and the time is shown next to the text, so the phrase is dropped when the report is served.
_UTTERANCE_REF = re.compile(r"\b(?:at|in)?\s*(?:utterance|line)\s+u\d{4,}\b[,:]?\s*", re.IGNORECASE)


def without_ids(text: str) -> str:
    cleaned = _UTTERANCE_REF.sub(" ", text).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned[:1].upper() + cleaned[1:] if cleaned != text else text


def dimension_out(d: dict[str, Any]) -> dict[str, Any]:
    base = {"key": d["key"], "name": d["name"], "weight": d["weight"]}
    if not d["verified"]:
        return {**base, "verified": False}  # nothing else from an unverified dimension (golden rule 5)
    evidence = [{k: e[k] for k in ("quote", "utterance_id", "start_ms", "end_ms")} for e in d["evidence"]]
    out = {**base, "verified": True, "score": d["score"], "rationale": d["rationale"], "evidence": evidence}
    if d.get("not_applicable"):
        out["not_applicable"] = True
    return out


def report_payload(
    recording: Recording, analysis: Analysis | None, report: dict[str, Any] | None, *, person_label: str,
    history: list[float],
) -> dict[str, Any]:  # fmt: skip
    """The AnalysisPayload for the recording's current state (processing, failed, needs_review, completed, partial)."""
    status = recording.status.value
    if status in PROCESSING_STAGES:
        updated = recording.status_changed_at or recording.created_at
        return {"status": "processing", "reasons": [], "recording_id": recording.id,
                "stage": PROCESSING_STAGES[status], "progress": None, "updated_at": updated.isoformat()}  # fmt: skip
    if status == "FAILED":
        return {"status": "failed", "reasons": _reasons([recording.status_reason or "unknown"]),
                "recording_id": recording.id, "reference": recording.id}  # fmt: skip
    if status == "NEEDS_REVIEW" or analysis is None or report is None:
        codes = analysis.review_reasons if analysis is not None and analysis.review_reasons else []
        return {"status": "needs_review", "reasons": _reasons(codes or [recording.status_reason or "unknown"]),
                "recording_id": recording.id}  # fmt: skip
    dimensions = [dimension_out(d) for d in report["dimensions"]]
    partial = any(not d["verified"] for d in dimensions)
    synthesis = report.get("synthesis") or {}
    return {
        "status": "partial" if partial else "completed",
        "reasons": _reasons(["unverified_dimensions"]) if partial else [],
        "analysis_id": analysis.id,
        "recording_id": recording.id,
        "created_at": analysis.created_at.isoformat(),
        "rubric": {
            "id": analysis.rubric_id,
            "version": analysis.rubric_version,
            "name": recording.type.value.capitalize(),
        },
        "model": {"ids": analysis.model_ids, "prompt_hash": analysis.prompt_hashes.get("scoring.system")},
        "overall": report["overall"]["score"],
        "comparison": None,  # never invented (golden rule 6); needs real data across the tenant
        "person_history": {"count": len(history), "min": min(history), "max": max(history)} if history else None,
        "dimensions": dimensions,
        "metrics": [metric_out(m, person_label) for m in report["metrics"]],
        "summary": without_ids(synthesis.get("summary", "")),
        "strengths": synthesis.get("strengths", []),
        "gaps": synthesis.get("gaps", []),
        "suggestions": [
            {"text": without_ids(s["text"]), "utterance_id": s["utterance_id"], "start_ms": s["start_ms"]}
            for s in synthesis.get("suggestions", [])
        ],
        "phases": [
            {"name": p["phase"], "start_ms": p["start_ms"], "end_ms": p["end_ms"]} for p in report.get("phases") or []
        ]
        or None,
        "ticket": shown_ticket(report.get("ticket")),
        "deal_card": report.get("deal_card"),  # sales meetings: verified items only (sabha_analytics.sales)
        "meeting_notes": report.get("meeting_notes"),  # meetings: verified items only (sabha_analytics.meetings)
    }


def shown_ticket(ticket: dict[str, Any] | None) -> dict[str, Any] | None:
    """Reception: the ticket with its verified quotes. Tickets stored before quotes were asked for (2026-10-26) have
    none, so they are not shown (golden rule 5)."""
    if not ticket or not ticket.get("evidence"):
        return None
    return ticket


async def analysis_payload(
    recording: Recording,
    analyses: TenantRepo[Analysis],
    reader: ArtefactReader,
    *,
    person_label: str,
    analysis_id: str | None = None,
) -> tuple[dict[str, Any], Analysis | None]:
    """The report payload of the recording's latest analysis, or of an earlier version (`analysis_id`, which must
    be one of this recording's; 404 otherwise). `is_latest` says which it is."""
    found = await analyses.find({"recording_id": recording.id}, sort=[("created_at", -1)], limit=1)
    newest = found[0] if found else None
    analysis = newest
    if analysis_id is not None:
        analysis = await analyses.find_one({"_id": analysis_id, "recording_id": recording.id})
        if analysis is None:
            raise NotFoundError("This recording has no such analysis.")
    report = None if analysis is None else await reader.json(analysis.report_key)
    history: list[float] = []
    if analysis is not None and recording.person_id:
        others = {"person_id": recording.person_id, "status": "COMPLETED", "recording_id": {"$ne": recording.id}}
        earlier = await analyses.find(others, sort=[("created_at", -1)], limit=20)
        history = [a.overall_score for a in earlier if a.overall_score is not None]
    payload = report_payload(recording, analysis, report, person_label=person_label, history=history)
    if analysis is not None and "analysis_id" in payload:
        payload["is_latest"] = newest is not None and analysis.id == newest.id
    return payload, analysis


class Range(BaseModel):
    start_ms: int
    end_ms: int


class RecordingDetail(RecordingOut):
    """What the report header needs (ReportRecording in the web app), filled in as the pipeline produces it."""

    type_label: str
    unit_name: str | None
    recorded_at: datetime
    speech_ms: int | None  # after silence removal; None until preprocessing has run
    languages: list[str]  # language names, from the transcript
    removed_silence: list[Range]  # on the original timeline (golden rule 4)
    voice_names: dict[str, str]  # meetings: names given to the anonymous voices ("S1" -> "Riya")


def silence_gaps(segment_map: SegmentMap, duration_ms: int | None) -> list[Range]:
    gaps, cursor = [], 0
    for segment in segment_map.segments:
        if segment.orig_start_ms > cursor:
            gaps.append(Range(start_ms=cursor, end_ms=segment.orig_start_ms))
        cursor = segment.orig_end_ms
    if duration_ms is not None and duration_ms > cursor:
        gaps.append(Range(start_ms=cursor, end_ms=duration_ms))
    return gaps


async def recording_detail(
    recording: Recording, base: RecordingOut, *, settings: Settings, units: TenantRepo[Unit],
    transcripts: TenantRepo[Transcript], reader: ArtefactReader,
) -> RecordingDetail:  # fmt: skip
    unit = await units.find_one({"_id": recording.unit_id}) if recording.unit_id else None
    transcript = await transcripts.find_one({"recording_id": recording.id})
    languages = sorted({LANGUAGE_NAMES.get(code.split("-")[0], code) for code in (transcript.language_mix if transcript
                        else {}) if code != "unknown"})  # fmt: skip
    pre = artefact_prefix(recording.tenant_id, recording.id, "preprocess", settings.artefact_version_preprocess)
    segments = await reader.json(pre + "segments@v1.json")
    segment_map = None if segments is None else SegmentMap.from_records(segments)
    return RecordingDetail(
        **base.model_dump(), type_label=recording.type.value.capitalize(),
        unit_name=unit.name if unit else None, recorded_at=recording.recorded_at or recording.created_at,
        voice_names=recording.voice_names,
        speech_ms=None if segment_map is None else segment_map.compact_length_ms, languages=languages,
        removed_silence=[] if segment_map is None else silence_gaps(segment_map, recording.duration_ms),
    )  # fmt: skip
