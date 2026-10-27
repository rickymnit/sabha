"""Reading recordings and their results (plan task P5.7b; P3.7's transcript endpoint).

Logic and the visibility rule in sabha_api.services.results.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from sabha_api.audit import audit
from sabha_api.auth import Principal, current_principal
from sabha_api.auth.directory import Directory, directory
from sabha_api.deps import tenant_repo
from sabha_api.errors import NotReadyError
from sabha_api.services import disputes, voices
from sabha_api.services import results as service
from sabha_core.models import Analysis, AuditEntry, Dispute, Person, Recording, Score, Transcript, Unit
from sabha_core.profiles import ConversationType
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
    cursor: str | None = None, limit: Limit = 20, person_id: str | None = None, type: ConversationType | None = None,
) -> service.RecordingPage:  # fmt: skip
    """The recordings you may see, newest first, with each one's status, latest overall score and "who spoke when"
    strip. `person_id` and `type` narrow the list; they never show more than you may see."""
    return await service.list_recordings(principal, cursor=cursor, limit=limit, recordings=recordings, people=people,
                                         analyses=analyses, person_id=person_id, type=type,
                                         transcripts=transcripts)  # fmt: skip


@recordings_router.get("/counts", response_model=service.RecordingCounts)
async def count_recordings(principal: Caller, recordings: Recordings, people: People) -> service.RecordingCounts:
    """How many recordings of each type you may see: the same recordings the list shows. Declared before
    /{recording_id}, so "counts" is never read as an id."""
    return await service.count_recordings(principal, recordings=recordings, people=people)


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
    analyses: Analyses, units: Units, transcripts: Transcripts, reader: Reader,
) -> service.RecordingDetail:  # fmt: skip
    """One recording: status, person, latest overall score, and what the report header needs (speech length,
    languages, the silence removed on the original timeline) once the pipeline has produced it."""
    recording = await service.visible_recording(principal, recording_id, recordings, people)
    (base,) = await service.recording_out([recording], people, analyses)
    return await service.recording_detail(recording, base, settings=request.app.state.settings, units=units,
                                          transcripts=transcripts, reader=reader)  # fmt: skip


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
