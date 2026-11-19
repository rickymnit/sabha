"""Speaker roles on a support call a colleague helped on: agent 1, the colleague (agent 2) and the customer.

Owner's decision (2026-11-18, meaning corrected 2026-11-19): agent 1 can hand the phone to a colleague sitting beside
them for part of the call (Recording.transferred), and the diarizer is then asked for exactly three voices. The call
stays agent 1's: both agent voices get the staff role, so every score and metric is agent 1's.
Call 4 (NiaLabs demo) is a warm transfer: agent 1 talks with the customer, briefs agent 2 while the customer waits,
and leaves; agent 2 carries on with the customer. `assign_transfer_roles` works in three steps:

1. Structure. For every choice of (agent 1, agent 2) among the three voices and every turn start T as the handover,
   the purity is the share of the two agents' talk that is on their own side: agent 1 before T, agent 2 from T. The
   customer is the remaining voice and must talk on both sides (at least CUSTOMER_SIDE_MS before and after T). The
   highest purity wins; the handover is the earliest T that reaches it.
2. Behaviour. The support evidence (sabha_asr.role_evidence) is judged twice: on agent 1 and the customer before T,
   and on agent 2 and the customer from T. Neither may lean (confidence >= LEAN) to the customer as the agent. Weak
   or mixed evidence does not block: the structure is the stronger evidence here, because only the customer is
   heard on both sides of a transfer. On call 4 the evidence was weak before the handover and mixed after it (a
   cue misfired on "anydesk pe connect kar lijiye"), while the structure was clear (purity 0.92).
3. Confident when the purity is at least MIN_PURITY and step 2 holds: both agents get the rubric's staff role and the
   customer the other role, method "transfer", confidence the purity. Otherwise the best guess is kept for a
   reviewer, method "heuristic_low_confidence" and `unclear_roles` (sabha_asr.roles.next_status). Anything but three
   voices goes to a reviewer too, and so does a 3-way call where agent 1 stays on (agent 1's talk after the handover
   lowers the purity). Nothing here calls an LLM, and a guess is never analysed (golden rule 5).

A reviewer's roles (`from_confirmed`, ADR 0007): two speakers with the staff role and one with the other; agent 1 is
the agent who speaks first, and the handover is agent 2's first turn.

Talk the diarizer gave an agent on the wrong side of the handover (call 4: about 10 s of "agent 1" after he left)
stays as the diarizer gave it; the purity says how much there is. MIN_PURITY and CUSTOMER_SIDE_MS are starting
values, not measured: check them against reviewer corrections (eval/role_corrections.py).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import permutations

from sabha_asr.role_evidence import LEAN, PROFILES, RoleEvidence, judge
from sabha_asr.roles import METHOD_LOW_CONFIDENCE, REASON_UNCLEAR_ROLES, RoleAssignment, SpeakerRole
from sabha_asr.words import Turn, Word, assign_words_to_turns

METHOD_TRANSFER = "transfer"
MIN_PURITY = 0.9
"""At least this share of the two agents' talk on their own side of the handover (module docstring, step 3)."""
CUSTOMER_SIDE_MS = 5_000
"""The customer talks at least this long on each side of the handover."""
VOICES = 3


@dataclass(frozen=True, slots=True)
class TransferRoles:
    """The roles of a transferred call. The agents and the handover (compact timeline) are None without 3 voices."""

    assignment: RoleAssignment
    agent_1: str | None
    agent_2: str | None
    customer: str | None
    handover_ms: int | None
    purity: float
    evidence_before: RoleEvidence | None = None
    evidence_after: RoleEvidence | None = None

    def to_record(self) -> dict[str, object]:
        """transfer@v1.json: who is who, where the handover is (compact timeline) and why."""
        return {
            "version": "transfer@v1",
            "timeline": "compact",
            "agent_1": self.agent_1,
            "agent_2": self.agent_2,
            "customer": self.customer,
            "handover_ms": self.handover_ms,
            "purity": self.purity,
            "needs_review_reason": self.assignment.needs_review_reason,
            "evidence_before": None if self.evidence_before is None else self.evidence_before.to_record(),
            "evidence_after": None if self.evidence_after is None else self.evidence_after.to_record(),
        }


def _key(turn: Turn) -> tuple[str, int, int]:
    return (turn.speaker_label, turn.start_ms, turn.end_ms)


def _best_split(ordered: Sequence[Turn], labels: Sequence[str]) -> tuple[float, str, str, str, int] | None:
    """(purity, agent 1, agent 2, customer, handover) with the highest purity, or None when no split has the customer
    on both sides."""
    totals = {label: sum(t.end_ms - t.start_ms for t in ordered if t.speaker_label == label) for label in labels}
    best: tuple[float, str, str, str, int] | None = None
    for agent_1, agent_2 in permutations(labels, 2):
        customer = next(label for label in labels if label not in (agent_1, agent_2))
        agents_ms = totals[agent_1] + totals[agent_2]
        if agents_ms == 0:
            continue
        before = {label: 0 for label in labels}  # talk before the candidate handover
        for turn in ordered:
            if turn.speaker_label == agent_2:  # agent 2's turns only can start the handover
                customer_after = totals[customer] - before[customer]
                if before[customer] >= CUSTOMER_SIDE_MS and customer_after >= CUSTOMER_SIDE_MS:
                    purity = (before[agent_1] + totals[agent_2] - before[agent_2]) / agents_ms
                    if best is None or purity > best[0]:
                        best = (purity, agent_1, agent_2, customer, turn.start_ms)
            before[turn.speaker_label] += turn.end_ms - turn.start_ms
    return best


def _half(
    turns: Sequence[Turn], words: Sequence[tuple[Word, Turn]], keep: set[tuple[str, int, int]]
) -> tuple[list[Turn], list[Word]]:
    """The turns in `keep` and the words said in them (each word stays with the turn it was given on the full call)."""
    return [t for t in turns if _key(t) in keep], [w for w, t in words if _key(t) in keep]


def _leans(evidence: RoleEvidence | None) -> str | None:
    return evidence.staff if evidence is not None and evidence.confidence >= LEAN else None


def assign_transfer_roles(
    turns: Sequence[Turn], words: Sequence[Word], rubric_roles: Sequence[str], organisation: Sequence[str] = ()
) -> TransferRoles:
    """Roles for a support call transferred during the call (module docstring). `rubric_roles` is (staff, other)."""
    staff_role, other_role = rubric_roles[0], rubric_roles[1]
    ordered = sorted(turns, key=lambda t: (t.start_ms, t.end_ms))
    labels = sorted({t.speaker_label for t in ordered})

    def unclear(agents: Sequence[str]) -> TransferRoles:
        speakers = {label: SpeakerRole(staff_role if label in agents else other_role, 0.0, METHOD_LOW_CONFIDENCE)
                    for label in labels}  # fmt: skip
        return TransferRoles(RoleAssignment(speakers, REASON_UNCLEAR_ROLES), None, None, None, None, 0.0)

    if len(labels) != VOICES:
        return unclear(labels[:1])
    split = _best_split(ordered, labels)
    if split is None:
        return unclear(labels[:2])
    purity, agent_1, agent_2, customer, handover = split

    ordered_words = sorted(words, key=lambda w: (w.start_ms, w.end_ms))
    owned = list(zip(ordered_words, assign_words_to_turns(ordered_words, ordered), strict=True))
    profile = PROFILES["support"]
    before = {_key(t) for t in ordered if t.start_ms < handover and t.speaker_label in (agent_1, customer)}
    after = {_key(t) for t in ordered if t.start_ms >= handover and t.speaker_label in (agent_2, customer)}
    evidence = [judge(*_half(ordered, owned, keep), profile, organisation) for keep in (before, after)]
    leans = [_leans(evidence[0]), _leans(evidence[1])]
    confident = purity >= MIN_PURITY and customer not in leans
    confidence = round(purity, 3)
    method = METHOD_TRANSFER if confident else METHOD_LOW_CONFIDENCE
    speakers = {label: SpeakerRole(other_role if label == customer else staff_role, confidence, method)
                for label in labels}  # fmt: skip
    assignment = RoleAssignment(speakers, None if confident else REASON_UNCLEAR_ROLES)
    return TransferRoles(assignment, agent_1, agent_2, customer, handover, confidence, evidence[0], evidence[1])


def from_confirmed(
    confirmed: dict[str, str], turns: Sequence[Turn], rubric_roles: Sequence[str]
) -> TransferRoles | None:
    """A reviewer's roles for a transferred call (module docstring), or None when they do not fit: every speaker has
    one of the rubric's two roles, two of three speakers the staff role."""
    staff_role, other_role = rubric_roles[0], rubric_roles[1]
    labels = {t.speaker_label for t in turns}
    agents = [label for label, role in confirmed.items() if role == staff_role]
    customers = [label for label, role in confirmed.items() if role == other_role]
    if set(confirmed) != labels or len(labels) != VOICES or len(agents) != 2 or len(customers) != 1:
        return None
    first = {label: min(t.start_ms for t in turns if t.speaker_label == label) for label in agents}
    agent_1, agent_2 = sorted(agents, key=lambda label: (first[label], label))
    speakers = {label: SpeakerRole(role, 1.0, "reviewer") for label, role in confirmed.items()}
    return TransferRoles(RoleAssignment(speakers), agent_1, agent_2, customers[0], first[agent_2], 1.0)
