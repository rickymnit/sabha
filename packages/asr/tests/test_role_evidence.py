"""Evidence-based speaker roles for support calls (sabha_asr.role_evidence, owner's decision 2026-11-04)."""

from __future__ import annotations

from sabha_asr.role_evidence import SUPPORT_PROFILE, judge
from sabha_asr.roles import (
    METHOD_EVIDENCE,
    METHOD_LOW_CONFIDENCE,
    REASON_UNCLEAR_ROLES,
    RoleAssignment,
    SpeakerRole,
    TieBreakRequest,
    assign_roles,
)
from sabha_asr.words import Turn, Word

ROLES = ("support_agent", "customer")
ORGANISATION = ("SchoolLog", "स्कूल लोग")


def call(lines: list[tuple[str, str]], step_ms: int = 4_000) -> tuple[list[Turn], list[Word]]:
    """One turn per line, `step_ms` apart; the line's words spread over its turn."""
    turns, words = [], []
    for i, (speaker, text) in enumerate(lines):
        start = i * step_ms
        turns.append(Turn(speaker, start, start + step_ms - 200))
        tokens = text.split()
        size = (step_ms - 200) // len(tokens)
        words += [Word(t, start + k * size, start + (k + 1) * size, None) for k, t in enumerate(tokens)]
    return turns, words


class Answer:
    """A scripted tie-breaker: names `staff` with `confidence`, and records that it was asked."""

    def __init__(self, staff: str, confidence: float) -> None:
        self.staff, self.confidence = staff, confidence
        self.requests: list[TieBreakRequest] = []

    def __call__(self, request: TieBreakRequest) -> RoleAssignment:
        self.requests.append(request)
        return RoleAssignment({label: SpeakerRole(ROLES[0] if label == self.staff else ROLES[1], self.confidence,
                                                  "llm_tiebreak") for label in request.heuristic.speakers})  # fmt: skip


def test_behaviour_names_the_agent_even_when_the_customer_speaks_first_and_most() -> None:
    turns, words = call([
        ("S0", "हेलो सर एनीडेस्क नंबर लीजिए 193197514"),  # the customer calls, and reads out their AnyDesk ID
        ("S1", "जी बताइए किस स्कूल से बात कर रहे हैं"),
        ("S0", "मैं सनराइज़ स्कूल से बात कर रहा हूँ कंसेशन रिपोर्ट नहीं आ रहा है बहुत लंबी बात है सर"),
        ("S1", "ठीक है रिपोर्ट मॉड्यूल में जाइए फिर क्लिक कीजिए"),
    ])  # fmt: skip
    result = assign_roles(turns, words, "support", ROLES, tenant_name_variants=ORGANISATION)
    assert result.role_by_speaker() == {"S0": "customer", "S1": "support_agent"}
    assert result.needs_review_reason is None and result.speakers["S1"].method == METHOD_EVIDENCE
    assert result.evidence is not None and result.evidence.decision in ("auto", "corroborated")
    cues = {(item.speaker, item.cue) for item in result.evidence.items}
    assert {("S0", "gives_remote_access_id"), ("S0", "introduces_as_school"), ("S1", "asks_which_school"),
            ("S1", "guides_software_steps")} <= cues  # fmt: skip


def test_a_cue_counts_once_however_often_it_is_said() -> None:
    once, words_once = call([("S0", "हेलो"), ("S1", "प्रॉब्लम है")])
    many, words_many = call([("S0", "हेलो"), ("S1", "प्रॉब्लम है"), ("S1", "प्रॉब्लम है"), ("S1", "प्रॉब्लम है")])
    a = judge(once, words_once, SUPPORT_PROFILE, ORGANISATION)
    b = judge(many, words_many, SUPPORT_PROFILE, ORGANISATION)
    assert a is not None and b is not None and a.confidence == b.confidence


def test_conflicting_evidence_goes_to_a_reviewer_without_asking_the_ai() -> None:
    turns, words = call([
        ("S0", "गुड आफ्टरनून स्कूल लोग से बोल रहा हूँ एनीडेस्क नंबर बताइए"),  # agent cues ...
        ("S1", "मॉड्यूल में जाइए फिर क्लिक कीजिए"),  # ... and agent cues from the other speaker too
        ("S0", "रिपोर्ट मॉड्यूल में स्क्रीनशॉट भेजिए डेवलपर टिकट"),
        ("S1", "स्क्रीनशॉट भेजिए अब चेक कीजिए डेवलपर टिकट"),
    ])  # fmt: skip
    ai = Answer("S0", 0.99)
    result = assign_roles(turns, words, "support", ROLES, tenant_name_variants=ORGANISATION, tie_breaker=ai)
    assert result.needs_review_reason == REASON_UNCLEAR_ROLES
    assert result.evidence is not None and result.evidence.decision == "conflict"
    assert ai.requests == []


def test_weak_evidence_asks_the_ai_with_guidance_and_needs_it_ninety_percent_sure() -> None:
    turns, words = call([("S0", "हेलो"), ("S1", "हेलो जी"), ("S0", "हाँ जी")])  # nothing to go on
    sure, unsure = Answer("S1", 0.93), Answer("S1", 0.85)
    accepted = assign_roles(turns, words, "support", ROLES, tenant_name_variants=ORGANISATION, tie_breaker=sure)
    assert accepted.role_by_speaker() == {"S0": "customer", "S1": "support_agent"}
    assert accepted.needs_review_reason is None and accepted.evidence is not None
    assert "AnyDesk" in sure.requests[0].guidance and sure.requests[0].organisation == ORGANISATION
    refused = assign_roles(turns, words, "support", ROLES, tenant_name_variants=ORGANISATION, tie_breaker=unsure)
    assert refused.needs_review_reason == REASON_UNCLEAR_ROLES  # 85% is enough elsewhere, not on a support call
    assert {s.method for s in refused.speakers.values()} == {METHOD_LOW_CONFIDENCE}


def test_the_ai_may_not_overrule_evidence_that_leans_the_other_way() -> None:
    turns, words = call([
        ("S0", "मैं सनराइज़ स्कूल से बात कर रहा हूँ"),  # leans: S0 is the customer, so S1 the agent
        ("S1", "हाँ जी"),
        ("S0", "हाँ"),
    ])  # fmt: skip
    evidence = judge(turns, words, SUPPORT_PROFILE, ORGANISATION)
    assert evidence is not None and evidence.staff == "S1" and evidence.decision == "weak"
    contrary = Answer("S0", 0.97)
    result = assign_roles(turns, words, "support", ROLES, tenant_name_variants=ORGANISATION, tie_breaker=contrary)
    assert evidence.confidence == 0.625  # 3 for S1 (S0 names a school) against 0.5 for S0 (spoke first): a lean
    assert result.needs_review_reason == REASON_UNCLEAR_ROLES


def test_other_types_keep_their_rules() -> None:
    turns, words = call([("S0", "नमस्ते सनराइज़ स्कूल से प्रिया बोल रही हूँ"), ("S1", "जी फीस के बारे में")])
    result = assign_roles(turns, words, "reception", ("receptionist", "caller"), tenant_name_variants=("सनराइज़ स्कूल",))
    assert result.evidence is None and result.role_by_speaker()["S0"] == "receptionist"


def test_the_agent_offering_to_act_is_not_the_customer_asking() -> None:
    # The agent restates the problem as they offer to fix it; on 2026-11-04 that counted for the customer.
    turns, words = call([
        ("S0", "हेलो मैं वैष्णव पब्लिक स्कूल से बोल रही हूँ"),
        ("S1", "आपकी फीस नहीं आ रही है ना तो वो मैं देख लेता हूँ"),
        ("S1", "कंसेशन ऐड करवा देता हूं आपको बता देता हूं कैसे करना है"),
    ])  # fmt: skip
    evidence = judge(turns, words, SUPPORT_PROFILE, ORGANISATION)
    assert evidence is not None and evidence.staff == "S1"
    s1 = {item.cue for item in evidence.items if item.speaker == "S1"}
    assert s1 == {"offers_to_do_it"}  # not describes_a_problem, requests_a_change or asks_how_to
