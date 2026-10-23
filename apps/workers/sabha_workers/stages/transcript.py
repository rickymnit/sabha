"""The end of the transcribe stage: speaker roles (plan task P3.6) and the canonical transcript (P3.7).

`finish_transcript(ctx, asr, deps)` runs after speech recognition:

1. Reads the diarize stage's turns (compact timeline). Missing: PermanentError `missing_input`.
2. Finds the recording's rubric (sabha_workers.rubrics; none: PermanentError `no_rubric`). Its first two roles are
   (staff, other): teacher/students or receptionist/caller.
3. Assigns roles with sabha_asr.roles (heuristics; the tenant's name is the reception greeting to look for). When
   the heuristics are unsure it asks the LLM tie-breaker if one is configured (sabha_workers.stages.roles_llm).
   Writes `roles@v1.json`.
4. Assembles `transcript@v1.json` with sabha_asr.assembly: utterances with role, speaker label, text and times on
   the ORIGINAL recording timeline (golden rule 4), and saves a `transcripts` document pointing at it.
5. Roles still unclear: the transcript is kept (with the best guess, for the reviewer) and NeedsReviewError
   `unclear_roles` stops the pipeline. A guess is never analysed (golden rule 5).

When a reviewer has confirmed the roles (`recording.confirmed_roles`, ADR 0007), step 3 uses them as they are
(method "reviewer", confidence 1) and asks neither the heuristics nor the LLM. Confirmed roles that do not fit the
speakers or the rubric go back for review rather than being guessed around.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from sabha_analytics.rubric import Rubric
from sabha_asr.assembly import WordTiming, assemble_transcript
from sabha_asr.roles import RoleAssignment, RoleTieBreaker, SpeakerRole, assign_roles
from sabha_asr.words import Turn, Word
from sabha_core.models import Tenant, Transcript
from sabha_core.profiles import ConversationType
from sabha_core.storage import artefact_prefix
from sabha_core.timemap import SegmentMap
from sabha_workers.rubrics import NoRubric
from sabha_workers.stages.runner import NeedsReviewError, PermanentError, StageContext


@dataclass(frozen=True)
class TranscriptDeps:
    diarize_version: str
    tenant: Callable[[str], Tenant | None]
    rubric: Callable[[Tenant, ConversationType], tuple[Rubric, str]]
    tie_breaker: Callable[[str, str], RoleTieBreaker | None]  # (tenant_id, recording_id) -> tie-breaker or None
    save: Callable[[str, Transcript], None]  # (tenant_id, transcript)


@dataclass(frozen=True)
class AsrOutput:
    words: Sequence[Word]
    model: str
    word_timing: WordTiming
    languages: Sequence[dict[str, Any]]  # {start_ms, end_ms, language} on the compact timeline
    segment_map: SegmentMap


def language_mix(spans: Sequence[dict[str, Any]]) -> dict[str, float]:
    """Share of the transcribed audio per detected language ("unknown" when the provider did not say)."""
    totals: dict[str, int] = {}
    for span in spans:
        name = span["language"] or "unknown"
        totals[name] = totals.get(name, 0) + span["end_ms"] - span["start_ms"]
    whole = sum(totals.values())
    return {name: round(ms / whole, 4) for name, ms in sorted(totals.items())} if whole else {}


def confirmed_assignment(confirmed: dict[str, str], turns: Sequence[Turn], roles: tuple[str, str]) -> RoleAssignment:
    """A reviewer's roles as an assignment, or NeedsReviewError when they do not fit: every speaker must have one of
    the rubric's two roles, and exactly one speaker the staff role (roles[0])."""
    labels = {turn.speaker_label for turn in turns}
    staff = [label for label, role in confirmed.items() if role == roles[0]]
    if set(confirmed) != labels or not set(confirmed.values()) <= set(roles) or len(staff) != 1:
        raise NeedsReviewError(
            "unclear_roles", f"the confirmed roles {confirmed} do not fit speakers {sorted(labels)} and roles {roles}"
        )
    return RoleAssignment({label: SpeakerRole(role, 1.0, "reviewer") for label, role in confirmed.items()})


def finish_transcript(ctx: StageContext, asr: AsrOutput, deps: TranscriptDeps) -> dict[str, Any]:
    recording = ctx.recording
    source = artefact_prefix(ctx.tenant_id, recording.id, "diarize", deps.diarize_version)
    try:
        diarization = json.loads(ctx.artefacts.get(source + "diarization@v1.json"))
    except FileNotFoundError as exc:
        raise PermanentError("missing_input", f"diarization output not found: {exc}") from exc
    turns = [Turn(t["speaker_label"], t["start_ms"], t["end_ms"]) for t in diarization["compact"]]

    tenant = deps.tenant(ctx.tenant_id)
    if tenant is None:
        raise PermanentError("missing_input", "the recording's tenant was not found")
    try:
        rubric, _ = deps.rubric(tenant, recording.type)
    except NoRubric as exc:
        raise PermanentError("no_rubric", str(exc)) from exc
    if len(rubric.roles) < 2:
        raise PermanentError("no_rubric", f"rubric {rubric.id} names fewer than two roles")

    if recording.confirmed_roles is not None:
        assignment = confirmed_assignment(recording.confirmed_roles, turns, (rubric.roles[0], rubric.roles[1]))
    else:
        assignment = assign_roles(
            turns, asr.words, recording.type.value, rubric.roles[:2], tenant_name_variants=[tenant.name],
            tie_breaker=deps.tie_breaker(ctx.tenant_id, recording.id),
        )  # fmt: skip
    ctx.artefacts.put(ctx.prefix + "roles@v1.json", assignment.to_json().encode(), "application/json")

    roles = assignment.role_by_speaker()
    transcript = assemble_transcript(asr.words, turns, roles, asr.segment_map, asr_model=asr.model,
                                     word_timing=asr.word_timing)  # fmt: skip
    key = ctx.prefix + "transcript@v1.json"
    ctx.artefacts.put(key, json.dumps(transcript, ensure_ascii=False).encode(), "application/json")
    methods = sorted({speaker.method for speaker in assignment.speakers.values()})
    deps.save(
        ctx.tenant_id,
        Transcript(
            recording_id=recording.id, version=transcript["version"], storage_key=key, asr_model=asr.model,
            word_timing=asr.word_timing, word_count=transcript["word_count"],
            utterance_count=len(transcript["utterances"]), language_mix=language_mix(asr.languages),
            roles=roles, roles_method=",".join(methods), rubric_id=rubric.id, role_choices=list(rubric.roles[:2]),
            roles_need_review=assignment.needs_review_reason is not None,
        )
    )  # fmt: skip
    if assignment.needs_review_reason is not None:
        raise NeedsReviewError(assignment.needs_review_reason, "speaker roles are unclear; a person must confirm them")
    return {
        "speakers": len(roles),
        "roles_method": ",".join(methods),
        "utterances": len(transcript["utterances"]),
        "rubric": rubric.id,
    }
