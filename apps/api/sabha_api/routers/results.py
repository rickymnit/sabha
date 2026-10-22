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
from sabha_api.services import results as service
from sabha_core.models import Analysis, AuditEntry, Person, Recording, Score, Transcript, Unit
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
Limit = Annotated[int, Query(ge=1, le=service.MAX_LIMIT)]


def artefact_reader(request: Request) -> service.ArtefactReader:
    s3 = request.app.state.resources.s3
    if s3 is None:
        raise NotReadyError("Storage is not available.")
    return service.ArtefactReader(s3, request.app.state.settings)


Reader = Annotated[service.ArtefactReader, Depends(artefact_reader)]


@recordings_router.get("", response_model=service.RecordingPage)
async def list_recordings(
    principal: Caller, recordings: Recordings, people: People, analyses: Analyses,
    cursor: str | None = None, limit: Limit = 20,
) -> service.RecordingPage:  # fmt: skip
    """The recordings you may see, newest first, with each one's status and latest overall score."""
    return await service.list_recordings(principal, cursor=cursor, limit=limit, recordings=recordings, people=people,
                                         analyses=analyses)  # fmt: skip


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
    """The transcript on the original timeline and a short-lived playback URL (audited as recording.play)."""
    recording = await service.visible_recording(principal, recording_id, recordings, people)
    out = await service.transcript_for(recording, request.app.state.settings, transcripts, reader)
    await audit(entries, principal, request, action="recording.play", target_type="recording", target_id=recording.id)
    return out


@recordings_router.get("/{recording_id}/analysis", response_model=dict[str, Any])
async def get_analysis(
    recording_id: str, request: Request, principal: Caller, found: Found, recordings: Recordings, people: People,
    analyses: Analyses, reader: Reader, entries: Entries,
) -> dict[str, Any]:  # fmt: skip
    """Everything the report page shows, in one payload for the recording's state: processing (with the stage),
    failed or needs_review (with plain-language reasons), or completed/partial (verified dimensions with their
    quotes, metrics computed in code, synthesis, phases, model info). Viewing a report is audited (analysis.view).
    The shape is apps/web/src/features/report/types.ts AnalysisPayload, field for field."""
    recording = await service.visible_recording(principal, recording_id, recordings, people)
    tenant = await found.tenant(principal.tenant_id)
    person_label = tenant.labels.person if tenant is not None else "Staff"
    payload, analysis = await service.analysis_payload(recording, analyses, reader, person_label=person_label)
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


@people_router.get("/{person_id}/trend", response_model=service.TrendOut)
async def person_trend(
    person_id: str, principal: Caller, people: People, analyses: Analyses, scores: Scores,
    dimension: str | None = None, limit: Limit = 50,
) -> service.TrendOut:  # fmt: skip
    """A person's scores over time, oldest first: one rubric dimension, or the overall score without `dimension`."""
    person = await service.visible_person(principal, person_id, people)
    return await service.trend(person, dimension, limit=limit, analyses=analyses, scores=scores)
