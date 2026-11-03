"""Reading recordings and their results (plan task P5.7b; P3.7's transcript endpoint).

Logic and the visibility rule in sabha_api.services.results.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse

from sabha_api.audit import audit
from sabha_api.auth import Principal, current_principal
from sabha_api.auth.directory import Directory, directory
from sabha_api.deps import Transactions, tenant_repo, transactions
from sabha_api.errors import NotReadyError
from sabha_api.idempotency import HEADER, idempotent
from sabha_api.services import disputes, export, voices
from sabha_api.services import recording_filters as filters
from sabha_api.services import results as service
from sabha_api.services import share as share_service
from sabha_core.models import (
    Analysis,
    AuditEntry,
    DeadLetter,
    Dispute,
    IdempotencyRecord,
    OutboxEvent,
    Person,
    Recording,
    Score,
    Transcript,
    Unit,
    User,
)
from sabha_core.repo import TenantRepo

recordings_router = APIRouter(prefix="/v1/recordings", tags=["recordings"])
people_router = APIRouter(prefix="/v1/people", tags=["people"])

Caller = Annotated[Principal, Depends(current_principal)]
Recordings = Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))]
People = Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))]
Analyses = Annotated[TenantRepo[Analysis], Depends(tenant_repo("analyses", Analysis))]
Scores = Annotated[TenantRepo[Score], Depends(tenant_repo("scores", Score))]
Transcripts = Annotated[TenantRepo[Transcript], Depends(tenant_repo("transcripts", Transcript))]
Entries = Annotated[TenantRepo[AuditEntry], Depends(tenant_repo("audit_log", AuditEntry))]
Units = Annotated[TenantRepo[Unit], Depends(tenant_repo("units", Unit))]
Found = Annotated[Directory, Depends(directory)]
Disputes = Annotated[TenantRepo[Dispute], Depends(tenant_repo("disputes", Dispute))]
Filter = Annotated[filters.ListFilter, Depends(filters.list_filter)]
Users = Annotated[TenantRepo[User], Depends(tenant_repo("users", User))]
Letters = Annotated[TenantRepo[DeadLetter], Depends(tenant_repo("dlq", DeadLetter))]
Outbox = Annotated[TenantRepo[OutboxEvent], Depends(tenant_repo("outbox", OutboxEvent))]
Records = Annotated[TenantRepo[IdempotencyRecord], Depends(tenant_repo("idempotency_keys", IdempotencyRecord))]
Txn = Annotated[Transactions, Depends(transactions)]
Key = Annotated[str | None, Header(alias=HEADER)]
Limit = Annotated[int, Query(ge=1, le=service.MAX_LIMIT)]


def artefact_reader(request: Request) -> service.ArtefactReader:
    s3 = request.app.state.resources.s3
    if s3 is None:
        raise NotReadyError("Storage is not available.")
    return service.ArtefactReader(s3, request.app.state.settings)


Reader = Annotated[service.ArtefactReader, Depends(artefact_reader)]


@recordings_router.get("", response_model=service.RecordingPage)
async def list_recordings(
    principal: Caller, recordings: Recordings, people: People, analyses: Analyses, transcripts: Transcripts,
    units: Units, dlq: Letters, dispute_repo: Disputes, f: Filter,
    cursor: str | None = None, limit: Limit = 20,
) -> service.RecordingPage:  # fmt: skip
    """The recordings you may see, newest first, with each one's status, latest overall score and "who spoke when"
    strip. The filters (person, type, unit and the units under it, score band, recorded dates, the "decision" tab)
    narrow the list; they never show more than you may see."""
    extra = await filters.filter_conditions(f, units=units, analyses=analyses, dlq=dlq, disputes=dispute_repo)
    return await service.list_recordings(principal, cursor=cursor, limit=limit, recordings=recordings, people=people,
                                         analyses=analyses, transcripts=transcripts, extra=extra,
                                         dlq=dlq)  # fmt: skip


@recordings_router.get("/counts", response_model=service.RecordingCounts)
async def count_recordings(
    principal: Caller, recordings: Recordings, people: People, analyses: Analyses, dlq: Letters,
    dispute_repo: Disputes,
) -> service.RecordingCounts:  # fmt: skip
    """How many recordings of each type you may see (the same recordings the list shows), and how many need a
    decision or scored below 3: the Recordings page's tabs. Declared before /{recording_id}, so "counts" is never
    read as an id."""
    tabs = {
        "needs_decision": await filters.decision_condition(dlq, dispute_repo),
        "below_3": {"_id": {"$in": await filters.scored_ids(analyses, "below_3")}},
    }
    return await service.count_recordings(principal, recordings=recordings, people=people, tabs=tabs)


@recordings_router.get("/export.csv", response_class=Response,
                       responses={200: {"content": {"text/csv": {}}, "description": "The list as CSV"}})  # fmt: skip
async def export_recordings(
    request: Request, principal: Caller, recordings: Recordings, people: People, analyses: Analyses, units: Units,
    dlq: Letters, dispute_repo: Disputes, entries: Entries, found: Found, f: Filter,
) -> Response:  # fmt: skip
    """The list with the same filters as CSV, newest first, at most 5,000 rows (Excel opens it). Audited as
    recordings.export."""
    extra = await filters.filter_conditions(f, units=units, analyses=analyses, dlq=dlq, disputes=dispute_repo)
    page = await service.list_recordings(principal, cursor=None, limit=export.MAX_ROWS, recordings=recordings,
                                         people=people, analyses=analyses, extra=extra)  # fmt: skip
    all_units = await units.find({})
    by_id = {u.id: u for u in all_units}
    names = {u.id: " · ".join(n for n in ((by_id[u.parent_id].name if u.parent_id in by_id else None), u.name) if n)
             for u in all_units}  # fmt: skip
    tenant = await found.tenant(principal.tenant_id)
    type_names = {t.value: t.value.capitalize() for t in (tenant.enabled_types if tenant else [])}
    await audit(entries, principal, request, action="recordings.export", target_type="recording", target_id="list",
                meta={"rows": len(page.items), "filters": f.model_dump(mode="json", exclude_none=True)})  # fmt: skip
    return Response(export.to_csv(page.items, names, type_names), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="recordings.csv"'})  # fmt: skip


@recordings_router.post("/share", response_model=share_service.ShareOut)
async def share_recordings(
    body: share_service.ShareIn, request: Request, principal: Caller, recordings: Recordings, people: People,
    outbox: Outbox, entries: Entries, records: Records, txn: Txn, idempotency_key: Key = None,
) -> JSONResponse:  # fmt: skip
    """Share reports with the people analysed: emails each person a link and shows them your note. Does not
    change who may see a report. Managers, reviewers and administrators; at most 100 at once."""

    async def handler() -> tuple[int, dict[str, object]]:
        out = await share_service.share(principal, body, request, recordings=recordings, people=people,
                                        outbox=outbox, entries=entries, transactions=txn)  # fmt: skip
        return 200, out.model_dump(mode="json")

    return await idempotent(records, key=idempotency_key, route=share_service.SHARE_ROUTE, body=body,
                            handler=handler)  # fmt: skip


@recordings_router.put("/{recording_id}/voices", response_model=voices.VoicesOut)
async def name_voices(
    recording_id: str, body: voices.VoicesIn, request: Request, principal: Caller, recordings: Recordings,
    people: People, transcripts: Transcripts, entries: Entries,
) -> voices.VoicesOut:  # fmt: skip
    """Meetings: names for the anonymous voices ("S1" -> "Riya"), for display only. Replaces all names; an empty
    name removes one. Audited."""
    return await voices.name_voices(principal, recording_id, body, request, recordings=recordings, people=people,
                                    transcripts=transcripts, entries=entries)  # fmt: skip


@recordings_router.get("/{recording_id}", response_model=service.RecordingDetail)
async def get_recording(
    recording_id: str, request: Request, principal: Caller, recordings: Recordings, people: People,
    analyses: Analyses, units: Units, transcripts: Transcripts, reader: Reader, users: Users, dlq: Letters,
) -> service.RecordingDetail:  # fmt: skip
    """One recording: status, person, latest overall score, and what the report header needs (speech length,
    languages, the silence removed on the original timeline, who shared it and their note) once the pipeline has
    produced it."""
    recording = await service.visible_recording(principal, recording_id, recordings, people)
    (base,) = await service.recording_out([recording], people, analyses, dlq=dlq)
    sharer = await users.find_one({"_id": recording.shared_by}) if recording.shared_by else None
    return await service.recording_detail(recording, base, settings=request.app.state.settings, units=units,
                                          transcripts=transcripts, reader=reader,
                                          shared_by_name=sharer.name if sharer else None)  # fmt: skip


@recordings_router.get("/{recording_id}/transcript", response_model=service.TranscriptOut)
async def get_transcript(
    recording_id: str, request: Request, principal: Caller, recordings: Recordings, people: People,
    transcripts: Transcripts, reader: Reader, entries: Entries,
) -> service.TranscriptOut:  # fmt: skip
    """The transcript on the original timeline and a short-lived playback URL (audited as recording.play); no URL
    once retention deleted the audio."""
    recording = await service.visible_recording(principal, recording_id, recordings, people)
    out = await service.transcript_for(recording, request.app.state.settings, transcripts, reader)
    if out.playback_url is not None:
        await audit(entries, principal, request, action="recording.play", target_type="recording",
                    target_id=recording.id)  # fmt: skip
    return out


@recordings_router.get("/{recording_id}/analysis", response_model=dict[str, Any])
async def get_analysis(
    recording_id: str, request: Request, principal: Caller, found: Found, recordings: Recordings, people: People,
    analyses: Analyses, scores: Scores, dispute_repo: Disputes, reader: Reader, entries: Entries,
    analysis_id: str | None = None,
) -> dict[str, Any]:  # fmt: skip
    """Everything the report page shows, in one payload for the recording's state: processing (with the stage),
    failed or needs_review (with plain-language reasons), or completed/partial (verified dimensions with their
    quotes, metrics computed in code, synthesis, phases, model info). Viewing a report is audited (analysis.view).
    The shape is apps/web/src/features/report/types.ts AnalysisPayload, field for field."""
    recording = await service.visible_recording(principal, recording_id, recordings, people)
    tenant = await found.tenant(principal.tenant_id)
    person_label = tenant.labels.person if tenant is not None else "Staff"
    payload, analysis = await service.analysis_payload(recording, analyses, reader, person_label=person_label,
                                                       analysis_id=analysis_id)  # fmt: skip
    payload = await disputes.annotate_report(payload, principal, recording, analysis, scores=scores,
                                             disputes=dispute_repo)  # fmt: skip
    if analysis is not None and payload["status"] in ("completed", "partial"):
        await audit(entries, principal, request, action="analysis.view", target_type="recording",
                    target_id=recording.id, meta={"analysis_id": analysis.id})  # fmt: skip
    return payload


@recordings_router.get("/{recording_id}/analyses", response_model=list[service.AnalysisSummary])
async def list_analyses(
    recording_id: str, principal: Caller, recordings: Recordings, people: People, analyses: Analyses
) -> list[service.AnalysisSummary]:
    """Every analysis of this recording, newest first (re-analysis history)."""
    recording = await service.visible_recording(principal, recording_id, recordings, people)
    return await service.analysis_history(recording, analyses)


@people_router.get("", response_model=list[service.PersonOut])
async def list_people(principal: Caller, people: People) -> list[service.PersonOut]:
    """The people you may see and upload for, by name: everyone (owners, admins), your units (managers, reviewers)
    or yourself (staff)."""
    return await service.visible_people(principal, people)


@people_router.get("/summary", response_model=list[service.PersonSummary])
async def people_summary(principal: Caller, people: People, analyses: Analyses) -> list[service.PersonSummary]:
    """The People page: the people you may see (as GET /v1/people), each with their number of analysed recordings
    and recent overall scores, oldest first."""
    return await service.people_summary(principal, people, analyses)


@people_router.get("/{person_id}/trend", response_model=service.TrendOut)
async def person_trend(
    person_id: str, principal: Caller, people: People, analyses: Analyses, scores: Scores,
    dimension: str | None = None, limit: Limit = 50,
) -> service.TrendOut:  # fmt: skip
    """A person's scores over time, oldest first: one rubric dimension, or the overall score without `dimension`."""
    person = await service.visible_person(principal, person_id, people)
    return await service.trend(person, dimension, limit=limit, analyses=analyses, scores=scores)
