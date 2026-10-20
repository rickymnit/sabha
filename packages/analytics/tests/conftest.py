"""Shared fixtures for the scoring, synthesis and report tests: a scripted fake judge model and a short lesson.

The fake model never calls a provider. It returns the scripted answers in order and records every call, so tests
can assert what was asked (and that no unredacted PII was ever in a prompt).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from sabha_analytics.grounding import PreparedTranscript, prepare_transcript
from sabha_analytics.rubric import Rubric, load_rubric
from sabha_analytics.scoring import JudgeResponse, TokenUsage
from sabha_llm.redact import STUDENT, KnownName

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# (role, start_ms, end_ms, text). u0002 is a student line with a phone number and a student's name: neither may ever
# appear in a prompt (golden rules 8 and 10).
LESSON_ROWS = (
    ("teacher", 0, 8_000, "Aaj hum photosynthesis ke baare mein padhenge, dhyan se suno."),
    (
        "teacher",
        9_000,
        30_000,
        "Photosynthesis matlab plant sunlight paani aur carbon dioxide se apna khana banata hai.",
    ),
    ("students", 31_000, 33_000, "Ma'am Aman ka number 9876543210 hai."),
    ("teacher", 34_000, 40_000, "Chlorophyll leaf ka green pigment hai jo sunlight absorb karta hai."),
    ("teacher", 500_000, 510_000, "Aaj humne photosynthesis aur chlorophyll dono padhe, kal experiment karenge."),
)

FAKE_QUOTE = "plants breathe oxygen at night through their roots"
"""Plausible, on topic, and said nowhere in the lesson."""


def transcript_document(rows: Sequence[tuple[str, int, int, str]] = LESSON_ROWS) -> dict[str, Any]:
    return {
        "version": "transcript@v1",
        "timeline": "original",
        "asr_model": "fake-asr@1",
        "word_count": sum(len(text.split()) for *_, text in rows),
        "utterances": [
            {
                "role": role,
                "speaker_label": "SPEAKER_00" if role == "teacher" else "SPEAKER_01",
                "start_ms": start,
                "end_ms": end,
                "text": text,
                "avg_confidence": 0.9,
                "low_confidence_spans": [],
            }
            for role, start, end, text in rows
        ],
    }


@pytest.fixture
def lesson() -> PreparedTranscript:
    return prepare_transcript(transcript_document(), names=[KnownName("Aman", STUDENT)])


@pytest.fixture
def rubric() -> Rubric:
    rubric, _ = load_rubric(FIXTURES / "rubrics" / "teaching.testing.v1.0.yaml")
    return rubric


NOT_APPLICABLE_WHEN = "The lesson ends early because of an assembly, so there is no time to close it."


@pytest.fixture
def optional_recap_rubric(rubric: Rubric) -> Rubric:
    """The fixture rubric with recap_and_closure allowed to be not applicable (rubric `not_applicable_when`)."""
    concept, recap = rubric.dimensions
    optional = recap.model_copy(update={"not_applicable_when": NOT_APPLICABLE_WHEN})
    return rubric.model_copy(update={"dimensions": (concept, optional)})


@dataclass
class FakeJudge:
    """Returns `answers` in order; records each call's keyword arguments."""

    answers: list[object]
    model_id: str = "fake-judge@1"
    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete_json(
        self,
        *,
        task: str,
        system: str,
        messages: Sequence[Mapping[str, str]],
        json_schema: Mapping[str, Any],
        cache_prefix: str | None,
    ) -> JudgeResponse:
        self.calls.append(
            {"task": task, "system": system, "messages": list(messages), "json_schema": json_schema,
             "cache_prefix": cache_prefix}
        )  # fmt: skip
        if not self.answers:
            raise AssertionError("the fake judge was called more times than scripted")
        return JudgeResponse(self.answers.pop(0), self.model_id, TokenUsage(input_tokens=100, output_tokens=20))

    def prompt_texts(self) -> list[str]:
        return [call["system"] for call in self.calls] + [m["content"] for call in self.calls for m in call["messages"]]


@dataclass(frozen=True)
class Answers:
    """Scripted answers for the lesson above: the good ones pass grounding, the bad one carries FAKE_QUOTE."""

    fake_quote: str = FAKE_QUOTE

    @property
    def good_concept(self) -> dict[str, Any]:
        return {
            "key": "concept_clarity",
            "score": 4,
            "rationale": "The teacher defines photosynthesis and chlorophyll in plain words.",
            "evidence": [
                {"quote": "plant sunlight paani aur carbon dioxide se apna khana banata hai", "utterance_id": "u0001",
                 "start_ms": 9_000},
                {"quote": "Chlorophyll leaf ka green pigment hai", "utterance_id": "u0003", "start_ms": 34_000},
            ],
        }  # fmt: skip

    @property
    def good_recap(self) -> dict[str, Any]:
        return {
            "key": "recap_and_closure",
            "score": 3,
            "rationale": "The teacher lists what was covered and says what comes next.",
            "evidence": [
                {"quote": "aaj humne photosynthesis aur chlorophyll dono padhe", "utterance_id": "u0004",
                 "start_ms": 500_000}
            ],
        }  # fmt: skip

    @property
    def recap_not_applicable(self) -> dict[str, Any]:
        """A null score with one real quote of what the lesson was about."""
        return {
            "key": "recap_and_closure",
            "score": None,
            "rationale": "The lesson was cut short by an assembly, so there was no time for a recap.",
            "evidence": [
                {"quote": "Aaj hum photosynthesis ke baare mein padhenge", "utterance_id": "u0000", "start_ms": 0}
            ],
        }

    @property
    def bad_concept(self) -> dict[str, Any]:
        good = self.good_concept
        fake = {"quote": FAKE_QUOTE, "utterance_id": "u0003", "start_ms": 34_000}
        return {**good, "evidence": [good["evidence"][0], fake]}


@pytest.fixture
def answers() -> Answers:
    return Answers()


@pytest.fixture
def fake_judge() -> type[FakeJudge]:
    return FakeJudge
