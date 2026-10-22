"""Reading recordings and their results (plan task P5.7b; P3.7's transcript endpoint).

Logic and the visibility rule in sabha_api.services.results.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from sabha_api.audit import audit
from sabha_api.auth import Principal, current_principal
from sabha_api.deps import tenant_repo
from sabha_api.errors import NotReadyError
from sabha_api.services import results as service
from sabha_core.models import Analysis, AuditEntry, Person, Recording, Score, Transcript
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


@recordings_router.get("/{recording_id}", response_model=service.RecordingOut)
async def get_recording(
    recording_id: str, principal: Caller, recordings: Recordings, people: People, analyses: Analyses
) -> service.RecordingOut:
    """One recording's status, person and latest overall score."""
    recording = await service.visible_recording(principal, recording_id, recordings, people)
    (out,) = await service.recording_out([recording], people, analyses)
    return out


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


@recordings_router.get("/{recording_id}/analysis", response_model=service.AnalysisOut)
async def get_analysis(
    recording_id: str, request: Request, principal: Caller, recordings: Recordings, people: People,
    analyses: Analyses, reader: Reader, entries: Entries,
) -> service.AnalysisOut:  # fmt: skip
    """The latest analysis: verified dimensions with evidence, metrics, synthesis and model info (audited)."""
    recording = await service.visible_recording(principal, recording_id, recordings, people)
    out = await service.latest_analysis(recording, analyses, reader)
    await audit(entries, principal, request, action="analysis.view", target_type="recording", target_id=recording.id,
                meta={"analysis_id": out.analysis.id})  # fmt: skip
    return out


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
