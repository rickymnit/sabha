"""The Gemini speaker check (sabha_asr.speaker_check), written before the module."""

from __future__ import annotations

import json
from typing import Any

import httpx

from sabha_asr.provider import TokenUsage
from sabha_asr.speaker_check import (
    MIN_WORDS,
    GeminiSpeakerAsker,
    Line,
    Verdict,
    lines_of,
    relabel,
)
from sabha_asr.words import Word

ROLES = {"S0": "customer", "S1": "sales_rep"}


def ws(*runs: tuple[int, str]) -> list[Word]:
    """(start_ms, text): each word 400 ms long, one after another from start_ms."""
    out = []
    for start, text in runs:
        for i, w in enumerate(text.split()):
            out.append(Word(w, start + i * 400, start + i * 400 + 400, None))
    return out


def test_lines_follow_the_speaker_and_end_at_sentence_ends() -> None:
    words = ws((0, "हेलो। नमस्कार सर, क्या हाल है?"), (5_000, "बढ़िया सर एकदम। बताइए सर।"))
    labels = ["S0"] * 6 + ["S0", "S0", "S0", "S1", "S1"]
    lines = lines_of(words, labels)
    assert [(line.text, line.label) for line in lines] == [
        ("हेलो।", "S0"), ("नमस्कार सर, क्या हाल है?", "S0"), ("बढ़िया सर एकदम।", "S0"), ("बताइए सर।", "S1"),
    ]  # fmt: skip
    assert lines[2].word_ids == (6, 7, 8) and (lines[2].start_ms, lines[2].end_ms) == (5_000, 6_200)


def test_a_line_gemini_gives_to_the_other_side_moves_but_short_and_unsure_lines_stay() -> None:
    words = ws((0, "हाँ सर मैं निया लैब से बात कर रहा हूँ।"), (5_000, "ओके।"), (6_000, "सर मुझे बायोमेट्रिक चाहिए थी।"))
    labels = ["S0"] * 16
    lines = lines_of(words, labels)
    staff: dict[int, Verdict] = {
        0: "staff",
        1: "staff",
        2: "unsure",
    }  # line 1 is "ओके।": too short to move on Gemini's word alone
    new, changes = relabel(lines, staff, labels, ROLES, "sales_rep")
    assert new[:10] == ["S1"] * 10 and new[10:] == ["S0"] * 6
    assert [(c.index, c.from_label, c.to_label) for c in changes] == [(0, "S0", "S1")]
    assert MIN_WORDS == 3


def test_with_more_than_one_customer_voice_the_nearest_one_takes_the_line() -> None:
    roles = {"S0": "customer", "S1": "sales_rep", "S2": "customer"}
    words = ws((0, "price kitna hai sir"), (3_000, "ek minute main batata hoon"), (60_000, "aur discount milega kya"),
               (63_000, "haan bilkul mil jayega sir"))  # fmt: skip
    labels = ["S0"] * 4 + ["S1"] * 5 + ["S2"] * 4 + ["S1"] * 5
    lines = lines_of(words, labels)
    new, _ = relabel(lines, {3: "customer"}, labels, roles, "sales_rep")
    assert new[13:] == ["S2"] * 5  # the customer voice heard near 63 s, not S0 from the start


def test_on_a_transferred_call_a_staff_line_goes_to_the_agent_of_that_side() -> None:
    roles = {"S0": "support_agent", "S1": "customer", "S2": "support_agent"}
    words = ws((0, "mera login nahi ho raha।"), (100_000, "anydesk id bataiye main dekhta hoon"))
    labels = ["S1"] * 5 + ["S1"] * 6
    lines = lines_of(words, labels)
    new, _ = relabel(
        lines, {0: "customer", 1: "staff"}, labels, roles, "support_agent", agents=("S0", "S2"), handover_ms=50_000
    )
    assert new[5:] == ["S2"] * 6  # after the handover: agent 2


def test_lines_are_never_split_across_labels_even_when_unchanged() -> None:
    lines = [Line(0, 0, 400, "x", "S0", (0,))]
    new, changes = relabel(lines, {}, ["S0"], ROLES, "sales_rep")
    assert new == ["S0"] and changes == []


def test_gemini_is_asked_with_little_thinking_and_answers_with_line_numbers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        parts = [{"text": json.dumps({"staff": [2], "unsure": [3]})}]
        usage = {"promptTokenCount": 5000, "candidatesTokenCount": 12, "thoughtsTokenCount": 0}
        answer = {"candidates": [{"finishReason": "STOP", "content": {"parts": parts}}], "usageMetadata": usage}
        return httpx.Response(200, json=answer)

    asker = GeminiSpeakerAsker("k", client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None)
    verdicts, usage = asker(b"RIFF", 0.0, [(1, 0.0, "हेलो।"), (2, 1.0, "मेरा नाम रोशन है।"), (3, 2.0, "ठीक")],
                            "sales rep")  # fmt: skip
    sent: dict[str, Any] = json.loads(seen[0].content)
    assert sent["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    assert sent["generationConfig"]["temperature"] == 0
    assert "2. [1s] मेरा नाम रोशन है।" in sent["contents"][0]["parts"][1]["text"]
    assert verdicts == {1: "customer", 2: "staff", 3: "unsure"}
    assert usage == TokenUsage(5000, 12, 0)
