"""Speaker roles on a support call transferred during the call (sabha_asr.transfer), written before the module."""

from __future__ import annotations

from sabha_asr.roles import METHOD_LOW_CONFIDENCE, REASON_UNCLEAR_ROLES
from sabha_asr.transfer import METHOD_TRANSFER, assign_transfer_roles
from sabha_asr.words import Turn, Word

ROLES = ("support_agent", "customer")
ORG = ("SchoolLog",)
S = 1_000


def said(text: str, start_ms: int, end_ms: int) -> list[Word]:
    parts = text.split()
    step = (end_ms - start_ms) // len(parts)
    return [Word(w, start_ms + i * step, start_ms + (i + 1) * step, None) for i, w in enumerate(parts)]


def call_4() -> tuple[list[Turn], list[Word]]:
    """Like call 4: agent 1 (A) with the customer (C), a briefing of agent 2 (B), then B with C; one stray of A."""
    script = [
        ("A", 0, 10, "नमस्कार SchoolLog support से अनिल बोल रहा हूँ बताइए सर"),
        ("C", 10, 40, "सर स्कूल ईआरपी लॉगिन नहीं हो रहा है verify नहीं हो रहा"),
        ("A", 40, 60, "आप अपना anydesk id बताइए मैं चेक कर लेता हूँ"),
        ("C", 60, 70, "जी 1267146230"),
        ("A", 70, 200, "मैं history clear कर देता हूँ chrome download कर लेते हैं"),
        ("C", 200, 230, "ठीक है सर कर दीजिए"),
        ("A", 230, 260, "ये windows 7 है 32 bit वाला system है cloudflare वाली error आ रही है"),
        ("B", 260, 280, "मेरे को anydesk पे connect करवा दो मैं check कर लेता हूँ"),
        ("B", 280, 300, "anydesk id बताइए मैं चेक कर लेता हूँ"),
        ("C", 300, 320, "जी 1267146230"),
        ("A", 320, 325, "ठीक"),  # the diarizer's stray: agent 1 has left
        ("B", 325, 400, "मैं team से check करवा लेता हूँ आप on call रहिए"),
        ("C", 400, 420, "ओके सर"),
        ("B", 420, 450, "मैं आपको इसी number पे call back कर दूँगा"),
        ("C", 450, 460, "ठीक है ठीक है"),
    ]
    turns = [Turn(label, a * S, b * S) for label, a, b, _ in script]
    words = [w for label, a, b, text in script for w in said(text, a * S, b * S)]
    return turns, words


def test_a_warm_transfer_finds_both_agents_the_customer_and_the_handover() -> None:
    turns, words = call_4()
    found = assign_transfer_roles(turns, words, ROLES, ORG)
    assert (found.agent_1, found.agent_2, found.customer) == ("A", "B", "C")
    assert found.handover_ms == 260 * S  # agent 2's first words
    assert found.assignment.needs_review_reason is None
    assert found.assignment.role_by_speaker() == {"A": "support_agent", "B": "support_agent", "C": "customer"}
    assert {s.method for s in found.assignment.speakers.values()} == {METHOD_TRANSFER}
    assert 0.9 <= found.purity < 1  # the 5 s stray of agent 1 after the handover


def test_labels_are_not_assumed_to_be_in_order() -> None:
    turns, words = call_4()
    rename = {"A": "S2", "B": "S0", "C": "S1"}
    turns = [Turn(rename[t.speaker_label], t.start_ms, t.end_ms) for t in turns]
    found = assign_transfer_roles(turns, words, ROLES, ORG)
    assert (found.agent_1, found.agent_2, found.customer) == ("S2", "S0", "S1")


def test_agents_whose_talk_is_mixed_on_both_sides_go_to_review() -> None:
    # The two "agents" take turns all through the call: no clean handover, a reviewer decides.
    script = [("A", 0, 10), ("C", 10, 40), ("B", 40, 100), ("C", 100, 110), ("A", 110, 170), ("C", 170, 190),
              ("B", 190, 250), ("C", 250, 270), ("A", 270, 330), ("C", 330, 340)]  # fmt: skip
    turns = [Turn(label, a * S, b * S) for label, a, b in script]
    words = [w for label, a, b in script for w in said("मैं चेक कर लेता हूँ" if label != "C" else "ठीक है", a * S, b * S)]
    found = assign_transfer_roles(turns, words, ROLES, ORG)
    assert found.assignment.needs_review_reason == REASON_UNCLEAR_ROLES
    assert {s.method for s in found.assignment.speakers.values()} == {METHOD_LOW_CONFIDENCE}


def test_behaviour_that_points_to_the_customer_as_the_agent_goes_to_review() -> None:
    # The voice heard on both sides (C, by structure the customer) greets with the company and asks for the AnyDesk
    # ID; the one-sided voices give the ID and describe the problem. Structure and behaviour disagree.
    script = [
        ("C", 0, 10, "नमस्कार SchoolLog support से अनिल बोल रहा हूँ बताइए सर"),
        ("A", 10, 40, "सर स्कूल ईआरपी लॉगिन नहीं हो रहा है verify नहीं हो रहा"),
        ("C", 40, 60, "आप अपना anydesk id बताइए मैं चेक कर लेता हूँ"),
        ("A", 60, 120, "जी 1267146230"),
        ("B", 120, 140, "हेलो सर मेरा भी login नहीं हो रहा मेरा anydesk 5551234567 है"),
        ("C", 140, 200, "मैं चेक कर लेता हूँ आप on call रहिए"),
        ("B", 200, 260, "ठीक है सर"),
    ]
    turns = [Turn(label, a * S, b * S) for label, a, b, _ in script]
    words = [w for label, a, b, text in script for w in said(text, a * S, b * S)]
    found = assign_transfer_roles(turns, words, ROLES, ORG)
    assert found.assignment.needs_review_reason == REASON_UNCLEAR_ROLES


def test_anything_but_three_voices_goes_to_review() -> None:
    turns, words = call_4()
    two = [Turn("A" if t.speaker_label == "B" else t.speaker_label, t.start_ms, t.end_ms) for t in turns]
    found = assign_transfer_roles(two, words, ROLES, ORG)
    assert found.assignment.needs_review_reason == REASON_UNCLEAR_ROLES
    assert found.agent_1 is None and set(found.assignment.speakers) == {"A", "C"}
