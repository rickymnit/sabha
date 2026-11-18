"""The end of the transcribe stage: speaker roles (plan task P3.6) and the canonical transcript (P3.7).

`finish_transcript(ctx, asr, deps)` runs after speech recognition:

1. Reads the diarize stage's turns (compact timeline). Missing: PermanentError `missing_input`.
2. Finds the recording's rubric (sabha_workers.rubrics; none: PermanentError `no_rubric`). Its first two roles are
   (staff, other): teacher/students or receptionist/caller.
3. Assigns roles with sabha_asr.roles (heuristics; the tenant's name and its `name_variants` are what a receptionist
   greets with and a sales rep introduces). When
   the heuristics are unsure it asks the LLM tie-breaker if one is configured (sabha_workers.stages.roles_llm).
   Types with an evidence profile (support calls) are judged by behaviour (sabha_asr.role_evidence). Roles are
   judged on the same turns the words are given to speakers by (`AsrOutput.word_turns`). Writes `roles@v1.json`,
   and the automatic decision twice more, never overwritten by a reviewer's: `roles_auto@v1.json` (the roles) and,
   when there is any, `role_evidence@v1.json` (what the evidence and the tie-breaker found). Reviewer corrections are
   measured against them (eval/role_corrections.py).
4. Assembles `transcript@v1.json` with sabha_asr.assembly: utterances with role, speaker label, text and times on
   the ORIGINAL recording timeline (golden rule 4), and saves a `transcripts` document pointing at it, with the
   list rows' "who spoke when" strip (`speaker_strip`).
   A support call transferred during the call (Recording.transfer_person_id) has two agents and the customer:
   sabha_asr.transfer finds them and the handover, writes `transfer@v1.json`, and the transcript document maps each
   agent's speaker label to their person (`agents`) with the handover on the original timeline (`handover_ms`).
   When the uploader asked for the Gemini speaker check (Recording.speaker_model "gemini") and the roles are settled,
   sabha_asr.speaker_check moves lines Gemini hears from the other side before the transcript is assembled. It reads
   the preprocess stage's normalised.wav (original timeline), masks each line's PII first (golden rule 8), writes
   `speaker_check@v1.json`, and adds its cost to the speech cost. Asked for but not configured (no GEMINI_API_KEY),
   or Gemini failing: the stage fails (`speaker_check_unavailable`, retried, or `speaker_check_failed`), never a
   transcript without the check (golden rule 7). Meetings and roles waiting for a reviewer are not checked.
   Meetings have no one to find: every voice is a "participant" (method "all_participants"), never reviewed.
5. Roles still unclear: the transcript is kept (with the best guess, for the reviewer) and NeedsReviewError
   `unclear_roles` stops the pipeline. A guess is never analysed (golden rule 5).

When a reviewer has confirmed the roles (`recording.confirmed_roles`, ADR 0007), step 3 uses them as they are
(method "reviewer", confidence 1) and asks neither the heuristics nor the LLM. Confirmed roles that do not fit the
speakers or the rubric go back for review rather than being guessed around.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from sabha_analytics.rubric import Rubric
from sabha_asr.assembly import WordTiming, assemble_transcript
from sabha_asr.pricing import TOKEN_PRICES, cost_inr, token_cost_inr
from sabha_asr.provider import ProviderError, TokenUsage
from sabha_asr.roles import RoleAssignment, RoleTieBreaker, SpeakerRole, assign_roles
from sabha_asr.speaker_check import MODEL_ID as CHECK_MODEL
from sabha_asr.speaker_check import WINDOW_MS, WINDOW_TAIL_MS, Verdict, lines_of, relabel
from sabha_asr.transfer import TransferRoles, assign_transfer_roles, from_confirmed
from sabha_asr.words import Turn, Word, assign_words_to_turns
from sabha_core.models import SpeakerCheck, SpeakerSpan, Tenant, Transcript
from sabha_core.profiles import ConversationType
from sabha_core.storage import artefact_prefix
from sabha_core.timemap import SegmentMap
from sabha_llm.redact import redact
from sabha_workers.rubrics import NoRubric
from sabha_workers.stages.preprocess import Runner, ffmpeg_timeout_s, run_tool
from sabha_workers.stages.runner import NeedsReviewError, PermanentError, StageContext, TransientError

ALL_PARTICIPANTS = "all_participants"  # roles method for meetings: every voice is a participant
STRIP_MAX_SPANS = 60  # a list row's strip is about 140px wide; more spans would only blur and bloat the list
STRIP_MERGE_GAP_MS = 1_000  # turns of one side this close together are drawn as one span
STRIP_MIN_SPEECH = 0.25  # a time slot with less speech than this share is drawn as silence


@dataclass(frozen=True)
class TranscriptDeps:
    diarize_version: str
    tenant: Callable[[str], Tenant | None]
    rubric: Callable[[Tenant, ConversationType], tuple[Rubric, str]]
    tie_breaker: Callable[[str, str], RoleTieBreaker | None]  # (tenant_id, recording_id) -> tie-breaker or None
    save: Callable[[str, Transcript], None]  # (tenant_id, transcript)
    usd_inr_rate: float | None = None  # rupees for an ASR model priced in dollars (USD_INR_RATE)
    # The Gemini speaker check (sabha_asr.speaker_check.GeminiSpeakerAsker), None when GEMINI_API_KEY is not set;
    # the preprocess version whose normalised.wav it listens to; ffmpeg for cutting its windows.
    speaker_checker: Callable[[], SpeakerAsker | None] = lambda: None
    preprocess_version: str = "v1"
    run: Runner = run_tool


class SpeakerAsker(Protocol):
    def __call__(
        self, wav: bytes, window_start_s: float, numbered: Sequence[tuple[int, float, str]], staff_word: str
    ) -> tuple[dict[int, Verdict], TokenUsage | None]: ...


@dataclass(frozen=True)
class AsrOutput:
    words: Sequence[Word]
    model: str
    word_timing: WordTiming
    languages: Sequence[dict[str, Any]]  # {start_ms, end_ms, language} on the compact timeline
    segment_map: SegmentMap
    billed_ms: Mapping[str, int] = field(default_factory=dict)  # audio sent per ASR model id, overlaps included
    # The turns words are given to speakers by (sabha_asr.chunking.chunk_turns); None: the diarization turns.
    word_turns: Sequence[Turn] | None = None
    # Token-billed models (Gemini): the tokens every answer reported (transcribe.billed_tokens); a token-billed model
    # missing here has an unknown cost.
    usage: Mapping[str, TokenUsage] = field(default_factory=dict)


def language_mix(spans: Sequence[dict[str, Any]]) -> dict[str, float]:
    """Share of the transcribed audio per detected language ("unknown" when the provider did not say)."""
    totals: dict[str, int] = {}
    for span in spans:
        name = span["language"] or "unknown"
        totals[name] = totals.get(name, 0) + span["end_ms"] - span["start_ms"]
    whole = sum(totals.values())
    return {name: round(ms / whole, 4) for name, ms in sorted(totals.items())} if whole else {}


def speaker_strip(
    utterances: Sequence[Mapping[str, Any]], staff_role: str | None, duration_ms: int | None
) -> list[SpeakerSpan]:
    """The "who spoke when" strip for list rows: utterances (ORIGINAL timeline) as staff or other, at most
    STRIP_MAX_SPANS spans. Neighbouring turns of one side less than STRIP_MERGE_GAP_MS apart become one span. If that
    still leaves too many, the recording is cut into STRIP_MAX_SPANS equal slots, each drawn as the side that spoke
    most in it (silence when under STRIP_MIN_SPEECH of the slot), and equal neighbours are joined. `staff_role` None
    (meetings: nobody is analysed) makes everyone "other"."""
    turns = sorted(
        (int(u["start_ms"]), int(u["end_ms"]), "staff" if u["role"] == staff_role else "other")
        for u in utterances
        if u["end_ms"] > u["start_ms"]
    )
    spans: list[list[Any]] = []
    for start, end, kind in turns:
        last = spans[-1] if spans else None
        if last is not None and last[2] == kind and start - last[1] <= STRIP_MERGE_GAP_MS:
            last[1] = max(last[1], end)
        else:
            spans.append([start, end, kind])
    if len(spans) > STRIP_MAX_SPANS:
        spans = _slotted(turns, duration_ms or max(end for _, end, _ in turns))
    return [SpeakerSpan(start_ms=a, end_ms=b, speaker=k) for a, b, k in spans]


def _slotted(turns: Sequence[tuple[int, int, str]], duration_ms: int) -> list[list[Any]]:
    width = duration_ms / STRIP_MAX_SPANS
    spans: list[list[Any]] = []
    for i in range(STRIP_MAX_SPANS):
        lo, hi = i * width, (i + 1) * width
        talk = {"staff": 0.0, "other": 0.0}
        for start, end, kind in turns:
            talk[kind] += max(0.0, min(end, hi) - max(start, lo))
        kind = max(talk, key=lambda k: talk[k])
        if talk["staff"] + talk["other"] < STRIP_MIN_SPEECH * width:
            continue
        a, b = round(lo), round(hi)
        if spans and spans[-1][2] == kind and spans[-1][1] == a:
            spans[-1][1] = b
        else:
            spans.append([a, b, kind])
    return spans


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


def _asr_cost(model: str, audio_ms: int, asr: AsrOutput, usd_inr_rate: float | None) -> float | None:
    """A token-billed model's cost from the tokens it billed (None when they are not all known); any other model's
    from the audio sent."""
    if model in TOKEN_PRICES:
        usage = asr.usage.get(model)
        return None if usage is None else token_cost_inr(model, usage, usd_inr_rate)
    return cost_inr(model, audio_ms, usd_inr_rate)


STAFF_WORDS = {"sales_rep": "sales rep", "support_agent": "support agent", "receptionist": "receptionist",
               "teacher": "teacher"}  # fmt: skip


def _speaker_check(
    ctx: StageContext,
    asr: AsrOutput,
    deps: TranscriptDeps,
    word_turns: Sequence[Turn],
    roles: Mapping[str, str],
    rubric: Rubric,
    transfer: TransferRoles | None,
) -> tuple[list[Turn], SpeakerCheck]:
    """The Gemini speaker check (module docstring, step 3): the turns to assemble with, and what the check did."""
    asker = deps.speaker_checker()
    if asker is None:
        raise PermanentError("speaker_check_unavailable", "the Gemini speaker check was asked for but GEMINI_API_KEY "
                             "is not set")  # fmt: skip
    staff_role = rubric.roles[0]
    words = list(asr.words)
    labels = [turn.speaker_label for turn in assign_words_to_turns(words, word_turns)]
    lines = lines_of(words, labels)
    starts = [asr.segment_map.compact_to_original(line.start_ms) for line in lines]
    verdicts: dict[int, Verdict] = {}
    usage: TokenUsage | None = TokenUsage(0, 0, 0)
    source = artefact_prefix(ctx.tenant_id, ctx.recording.id, "preprocess", deps.preprocess_version)
    with tempfile.TemporaryDirectory(prefix="sabha-speakers-") as tmp:
        audio = Path(tmp) / "normalised.wav"
        try:
            ctx.artefacts.download(source + "normalised.wav", audio)
        except FileNotFoundError as exc:
            raise PermanentError("missing_input", f"preprocess audio not found: {exc}") from exc
        for window in range(0, max(starts) + 1, WINDOW_MS):
            inside = [i for i, start in enumerate(starts) if window <= start < window + WINDOW_MS]
            if not inside:
                continue
            numbered = [(n + 1, starts[i] / 1000, redact(lines[i].text).redacted_text) for n, i in enumerate(inside)]
            wav = _cut_wav(audio, window, WINDOW_MS + WINDOW_TAIL_MS, deps.run)
            try:
                answer, billed = asker(wav, window / 1000, numbered, STAFF_WORDS.get(staff_role, staff_role))
            except ProviderError as exc:
                error = TransientError if exc.retryable else PermanentError
                code = "speaker_check_unavailable" if exc.retryable else "speaker_check_failed"
                raise error(code, f"{exc.provider}: {exc.reason}") from exc
            verdicts.update({inside[n - 1]: verdict for n, verdict in answer.items() if 1 <= n <= len(inside)})
            usage = None if usage is None or billed is None else usage + billed
    agents = (transfer.agent_1, transfer.agent_2) if transfer and transfer.agent_1 and transfer.agent_2 else None
    new_labels, changes = relabel(lines, verdicts, labels, roles, staff_role, agents=agents,
                                  handover_ms=transfer.handover_ms if transfer else None)  # fmt: skip
    cost = None if usage is None else token_cost_inr(CHECK_MODEL, usage, deps.usd_inr_rate)
    unsure = sum(1 for v in verdicts.values() if v == "unsure")
    found = {
        "version": "speaker_check@v1", "model": CHECK_MODEL, "timeline": "original", "lines": len(lines),
        "unsure": unsure,
        "usage": None if usage is None else usage.to_record(), "cost_inr": cost,
        "changed": [{"start_ms": asr.segment_map.compact_to_original(c.start_ms), "from": roles.get(c.from_label),
                     "to": roles.get(c.to_label), "from_label": c.from_label, "to_label": c.to_label}
                    for c in changes],
    }  # fmt: skip
    ctx.artefacts.put(ctx.prefix + "speaker_check@v1.json", json.dumps(found, ensure_ascii=False).encode(),
                      "application/json")  # fmt: skip
    summary = SpeakerCheck(model=CHECK_MODEL, lines=len(lines), changed=len(changes), unsure=unsure,
                           cost_inr=None if cost is None else round(cost, 4))  # fmt: skip
    return _runs(words, new_labels), summary


def _runs(words: Sequence[Word], labels: Sequence[str]) -> list[Turn]:
    """Turns from per-word labels: one turn per run of consecutive words with the same label."""
    turns: list[Turn] = []
    for word, label in zip(words, labels, strict=True):
        end = max(word.end_ms, word.start_ms + 1)
        if turns and turns[-1].speaker_label == label:
            turns[-1] = Turn(label, turns[-1].start_ms, max(turns[-1].end_ms, end))
        else:
            start = max(word.start_ms, turns[-1].end_ms) if turns else word.start_ms
            turns.append(Turn(label, start, max(end, start + 1)))
    return turns


def _cut_wav(audio: Path, start_ms: int, length_ms: int, run: Runner) -> bytes:
    """`length_ms` of 16 kHz mono WAV from `start_ms` (shorter at the end of the recording)."""
    out = audio.with_name(f"window-{start_ms}.wav")
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", "-ss", f"{start_ms / 1000:.3f}",
            "-t", f"{length_ms / 1000:.3f}", "-i", str(audio), "-ac", "1", "-ar", "16000", str(out)]  # fmt: skip
    run(args, ffmpeg_timeout_s(length_ms))
    data = out.read_bytes()
    out.unlink()
    return data


def _original(compact_ms: int | None, asr: AsrOutput) -> int | None:
    return None if compact_ms is None else asr.segment_map.compact_to_original(compact_ms)


def _agents(transfer: TransferRoles | None, agent_1: str | None, agent_2: str | None) -> dict[str, str]:
    """Speaker label -> person id for both agents of a transferred call; empty when they are not known."""
    if transfer is None or transfer.agent_1 is None or transfer.agent_2 is None or not agent_1 or not agent_2:
        return {}
    return {transfer.agent_1: agent_1, transfer.agent_2: agent_2}


def finish_transcript(
    ctx: StageContext, asr: AsrOutput, deps: TranscriptDeps, turns: Sequence[Turn] | None = None
) -> dict[str, Any]:
    """Steps 1-5 above. `turns` are given for an imported transcript (ADR 0009), which has no diarization."""
    recording = ctx.recording
    if turns is None:
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
    meeting = recording.type is ConversationType.MEETING
    if len(rubric.roles) < (1 if meeting else 2):
        raise PermanentError("no_rubric", f"rubric {rubric.id} names too few roles")

    transfer: TransferRoles | None = None
    names = [tenant.name, *tenant.name_variants]
    if meeting:  # everyone is a participant and the meeting is analysed: nobody to find, nothing to review
        labels = sorted({turn.speaker_label for turn in turns})
        assignment = RoleAssignment({label: SpeakerRole(rubric.roles[0], 1.0, ALL_PARTICIPANTS) for label in labels})
    elif recording.transfer_person_id and recording.type is ConversationType.SUPPORT:
        if recording.confirmed_roles is not None:
            transfer = from_confirmed(recording.confirmed_roles, turns, rubric.roles[:2])
            if transfer is None:
                raise NeedsReviewError("unclear_roles", f"the confirmed roles {recording.confirmed_roles} do not fit "
                                       "a transferred call: two agents and one customer")  # fmt: skip
        else:
            transfer = assign_transfer_roles(asr.word_turns or turns, asr.words, rubric.roles[:2], names)
            ctx.artefacts.put(ctx.prefix + "roles_auto@v1.json", transfer.assignment.to_json().encode(),
                              "application/json")  # fmt: skip
        assignment = transfer.assignment
        record = {**transfer.to_record(), "handover_original_ms": _original(transfer.handover_ms, asr)}
        ctx.artefacts.put(ctx.prefix + "transfer@v1.json", json.dumps(record, ensure_ascii=False).encode(),
                          "application/json")  # fmt: skip
    elif recording.confirmed_roles is not None:
        assignment = confirmed_assignment(recording.confirmed_roles, turns, (rubric.roles[0], rubric.roles[1]))
    else:
        assignment = assign_roles(
            asr.word_turns or turns, asr.words, recording.type.value, rubric.roles[:2], tenant_name_variants=names,
            tie_breaker=deps.tie_breaker(ctx.tenant_id, recording.id),
        )  # fmt: skip
        ctx.artefacts.put(ctx.prefix + "roles_auto@v1.json", assignment.to_json().encode(), "application/json")
        if assignment.evidence is not None or assignment.ai_evidence:
            found = {
                "version": "role_evidence@v1",
                "timeline": "compact",
                "evidence": None if assignment.evidence is None else assignment.evidence.to_record(),
                "ai_evidence": list(assignment.ai_evidence),
                "needs_review_reason": assignment.needs_review_reason,
            }
            ctx.artefacts.put(ctx.prefix + "role_evidence@v1.json", json.dumps(found, ensure_ascii=False).encode(),
                              "application/json")  # fmt: skip
    ctx.artefacts.put(ctx.prefix + "roles@v1.json", assignment.to_json().encode(), "application/json")

    roles = assignment.role_by_speaker()
    word_turns: Sequence[Turn] = asr.word_turns or turns
    check: SpeakerCheck | None = None
    if recording.speaker_model == "gemini" and not meeting and assignment.needs_review_reason is None and asr.words:
        word_turns, check = _speaker_check(ctx, asr, deps, word_turns, roles, rubric, transfer)
    transcript = assemble_transcript(asr.words, word_turns, roles, asr.segment_map, asr_model=asr.model,
                                     word_timing=asr.word_timing)  # fmt: skip
    key = ctx.prefix + "transcript@v1.json"
    ctx.artefacts.put(key, json.dumps(transcript, ensure_ascii=False).encode(), "application/json")
    methods = sorted({speaker.method for speaker in assignment.speakers.values()})
    costs = [_asr_cost(model, ms, asr, deps.usd_inr_rate) for model, ms in asr.billed_ms.items()]
    if check is not None:
        costs.append(check.cost_inr)
    asr_cost = None if not costs or any(c is None for c in costs) else round(sum(c for c in costs if c), 4)
    deps.save(
        ctx.tenant_id,
        Transcript(
            recording_id=recording.id, version=transcript["version"], storage_key=key, asr_model=asr.model,
            word_timing=asr.word_timing, word_count=transcript["word_count"],
            utterance_count=len(transcript["utterances"]), language_mix=language_mix(asr.languages),
            roles=roles, roles_method=",".join(methods), rubric_id=rubric.id, role_choices=list(rubric.roles[:2]),
            speaker_strip=speaker_strip(transcript["utterances"], None if meeting else rubric.roles[0],
                                        recording.duration_ms),
            roles_need_review=assignment.needs_review_reason is not None,
            asr_billed_ms=sum(asr.billed_ms.values()) or None, asr_cost_inr=asr_cost,
            agents=_agents(transfer, recording.person_id, recording.transfer_person_id),
            handover_ms=None if transfer is None else _original(transfer.handover_ms, asr),
            speaker_check=check,
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
