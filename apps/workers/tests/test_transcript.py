"""Speaker roles (P3.6) and the canonical transcript (P3.7) at the end of the transcribe stage, plus the LLM
tie-breaker. No services: artefacts live in memory and the LLM gateway is a fake."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from sabha_asr.roles import TieBreakRequest
from sabha_asr.words import Word
from sabha_core.models import Recording, Tenant, Transcript
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.timemap import Segment, SegmentMap
from sabha_llm.errors import ProviderError
from sabha_llm.types import CompletionResult, Usage
from sabha_workers.rubrics import NoRubric, rubric_for
from sabha_workers.stages.roles_llm import LlmRoleTieBreaker
from sabha_workers.stages.runner import NeedsReviewError, PermanentError, StageContext
from sabha_workers.stages.transcript import AsrOutput, TranscriptDeps, finish_transcript, language_mix

RUBRICS = Path(__file__).resolve().parents[3] / "rubrics"
TENANT = Tenant.from_profile("school", name="Sunrise Public School", plan=Plan.PILOT, id="t1")
# Original: speech [1000, 31000) and [40000, 70000); compact [0, 30000) and [30000, 60000).
MAP = SegmentMap((Segment(1_000, 31_000, 0), Segment(40_000, 70_000, 30_000)))


class Memory:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def exists(self, key: str) -> bool:
        return key in self.files

    def put(self, key: str, body: bytes, content_type: str = "") -> None:
        self.files[key] = body

    def put_file(self, key: str, path: Path, content_type: str) -> None:
        self.files[key] = path.read_bytes()

    def get(self, key: str) -> bytes:
        if key not in self.files:
            raise FileNotFoundError(key)
        return self.files[key]

    def download(self, key: str, path: Path) -> None:
        path.write_bytes(self.get(key))


def words(*runs: tuple[int, int, str]) -> list[Word]:
    """(start_ms, end_ms, text) -> words spread evenly over each run."""
    out = []
    for start, end, text in runs:
        parts = text.split()
        step = (end - start) // len(parts)
        out += [Word(p, start + i * step, start + (i + 1) * step, None) for i, p in enumerate(parts)]
    return out


@dataclass
class Setup:
    turns: list[tuple[str, int, int]]
    kind: ConversationType = ConversationType.TEACHING
    tie_breaker: Any = None
    confirmed_roles: dict[str, str] | None = None  # a reviewer's answer (ADR 0007)
    saved: list[Transcript] = field(default_factory=list)
    store: Memory = field(default_factory=Memory)

    def run(self, asr_words: list[Word]) -> dict[str, Any]:
        diarization = {"compact": [{"speaker_label": s, "start_ms": a, "end_ms": b} for s, a, b in self.turns]}
        self.store.put("t1/r1/diarize@v1/diarization@v1.json", json.dumps(diarization).encode())
        deps = TranscriptDeps(
            diarize_version="v1", tenant=lambda _: TENANT, rubric=lambda t, k: rubric_for(t, k, RUBRICS),
            tie_breaker=lambda *_: self.tie_breaker, save=lambda _, doc: self.saved.append(doc),
        )  # fmt: skip
        recording = Recording(id="r1", tenant_id="t1", type=self.kind, confirmed_roles=self.confirmed_roles)
        ctx = StageContext("t1", recording, "t1/r1/transcribe@v1/", self.store, 1)
        spans = [{"start_ms": 0, "end_ms": 45_000, "language": "hi-IN"},
                 {"start_ms": 45_000, "end_ms": 60_000, "language": "en-IN"}]  # fmt: skip
        return finish_transcript(ctx, AsrOutput(asr_words, "sarvam/saaras:v4", "approximate", spans, MAP), deps)

    def transcript(self) -> dict[str, Any]:
        data: dict[str, Any] = json.loads(self.store.get("t1/r1/transcribe@v1/transcript@v1.json"))
        return data


LECTURE = words((0, 28_000, "aaj hum photosynthesis padhenge " * 6), (30_000, 50_000, "chlorophyll green hai " * 5),
                (50_500, 52_000, "ma'am kyun"), (52_500, 60_000, "kyunki sunlight absorb karta hai"))  # fmt: skip


def test_a_clear_teacher_gets_roles_and_an_original_time_transcript() -> None:
    setup = Setup([("S0", 0, 50_000), ("S1", 50_500, 52_000), ("S0", 52_500, 60_000)])
    meta = setup.run(LECTURE)

    roles = json.loads(setup.store.get("t1/r1/transcribe@v1/roles@v1.json"))
    assert {label: r["role"] for label, r in roles.items()} == {"S0": "teacher", "S1": "students"}
    assert roles["S0"]["method"] == "heuristic"
    utterances = setup.transcript()["utterances"]
    # Compact 30000 is the join: the teacher's speech after it starts at original 40000, never in the gap.
    assert utterances[0]["start_ms"] == 1_000
    assert any(u["start_ms"] == 40_000 for u in utterances)
    assert all(not (31_000 < u["start_ms"] < 40_000) for u in utterances)
    assert [u["role"] for u in utterances].count("students") == 1
    (doc,) = setup.saved
    assert (doc.roles, doc.roles_need_review, doc.rubric_id) == ({"S0": "teacher", "S1": "students"}, False,
                                                                 "teaching.school.v0.1")  # fmt: skip
    assert doc.language_mix == {"en-IN": 0.25, "hi-IN": 0.75} and doc.word_count == len(LECTURE)
    assert meta["speakers"] == 2 and meta["rubric"] == "teaching.school.v0.1"


def even_split() -> Setup:
    # Two adults talk equally in short turns: neither heuristic can tell who teaches.
    turns = [("S0" if i % 2 == 0 else "S1", i * 5_000, i * 5_000 + 4_500) for i in range(12)]
    return Setup(turns)


def test_unclear_roles_keep_the_transcript_and_ask_for_review() -> None:
    setup = even_split()
    with pytest.raises(NeedsReviewError) as caught:
        setup.run(LECTURE)
    assert caught.value.code == "unclear_roles"
    assert setup.saved[0].roles_need_review is True  # stored for the reviewer, with the best guess
    assert setup.saved[0].role_choices == ["teacher", "students"]  # what the reviewer chooses between
    assert setup.transcript()["utterances"]


def test_roles_a_reviewer_confirmed_are_used_without_guessing() -> None:
    setup = even_split()
    setup.confirmed_roles = {"S0": "students", "S1": "teacher"}
    setup.tie_breaker = lambda _: pytest.fail("the tie-breaker must not be asked")
    meta = setup.run(LECTURE)  # no NeedsReviewError: the reviewer settled it
    roles = json.loads(setup.store.get("t1/r1/transcribe@v1/roles@v1.json"))
    assert roles == {"S0": {"role": "students", "confidence": 1.0, "method": "reviewer"},
                     "S1": {"role": "teacher", "confidence": 1.0, "method": "reviewer"}}  # fmt: skip
    (doc,) = setup.saved
    assert (doc.roles, doc.roles_method, doc.roles_need_review) == (setup.confirmed_roles, "reviewer", False)
    assert meta["roles_method"] == "reviewer"


@pytest.mark.parametrize(
    "confirmed",
    [
        {"S0": "teacher"},  # a speaker left out
        {"S0": "teacher", "S1": "teacher"},  # nobody is the students
        {"S0": "teacher", "S1": "principal"},  # not a role of this rubric
    ],
)
def test_confirmed_roles_that_do_not_fit_send_it_back_for_review(confirmed: dict[str, str]) -> None:
    setup = even_split()
    setup.confirmed_roles = confirmed
    with pytest.raises(NeedsReviewError) as caught:
        setup.run(LECTURE)
    assert caught.value.code == "unclear_roles"


def test_a_confident_tie_break_settles_unclear_roles() -> None:
    gateway = FakeGateway({"staff_speaker": "S1", "confidence": 0.9})
    setup = even_split()
    setup.tie_breaker = LlmRoleTieBreaker(gateway, "t1", "r1")  # type: ignore[arg-type]  # a fake gateway
    setup.run(LECTURE)
    assert setup.saved[0].roles == {"S0": "students", "S1": "teacher"} and setup.saved[0].roles_method == "llm_tiebreak"
    assert gateway.calls[0]["task"] == "roles.tiebreak"


def test_reception_finds_the_receptionist_by_the_school_greeting() -> None:
    call = words((0, 6_000, "namaste sunrise public school main pooja bol rahi hoon"),
                 (6_500, 12_000, "haan ji admission ke baare mein poochna tha"),
                 (12_500, 30_000, "ji bilkul form office se mil jayega aap kal aa jaiye"))  # fmt: skip
    setup = Setup([("S0", 0, 6_000), ("S1", 6_500, 12_000), ("S0", 12_500, 30_000)], ConversationType.RECEPTION)
    setup.run(call)
    assert setup.saved[0].roles == {"S0": "receptionist", "S1": "caller"}
    assert setup.saved[0].rubric_id == "reception.school.v0.2"  # the approved pilot version


def test_a_type_without_a_rubric_fails_for_a_replay() -> None:
    setup = Setup([("S0", 0, 60_000)], ConversationType.COUNSELLING)
    with pytest.raises(PermanentError) as caught:
        setup.run(LECTURE)
    assert caught.value.code == "no_rubric"
    with pytest.raises(NoRubric):
        rubric_for(TENANT, ConversationType.COUNSELLING, RUBRICS)


def test_missing_diarization_fails_for_a_replay() -> None:
    setup = Setup([])
    ctx = StageContext("t1", Recording(id="r1", tenant_id="t1", type=ConversationType.TEACHING), "p/", Memory(), 1)
    deps = TranscriptDeps("v1", lambda _: TENANT, lambda t, k: rubric_for(t, k, RUBRICS), lambda *_: None,
                          lambda _, doc: setup.saved.append(doc))  # fmt: skip
    with pytest.raises(PermanentError, match="diarization output not found"):
        finish_transcript(ctx, AsrOutput(LECTURE, "m", "approximate", [], MAP), deps)


def test_language_mix_shares() -> None:
    spans: list[dict[str, Any]] = [
        {"start_ms": 0, "end_ms": 300, "language": None},
        {"start_ms": 300, "end_ms": 1_000, "language": "hi-IN"},
    ]
    assert language_mix(spans) == {"hi-IN": 0.7, "unknown": 0.3}
    assert language_mix([]) == {}


# --- The LLM tie-breaker ---


class FakeGateway:
    def __init__(self, answer: Any = None, error: Exception | None = None) -> None:
        self.answer, self.error = answer, error
        self.calls: list[dict[str, Any]] = []

    def complete(self, **kwargs: Any) -> CompletionResult:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return CompletionResult("roles.tiebreak", "fake:small", json.dumps(self.answer), self.answer, Usage(10, 2),
                                None, 5, "h")  # fmt: skip


def request() -> TieBreakRequest:
    from sabha_asr.roles import RoleAssignment, SpeakerRole

    low = "heuristic_low_confidence"
    speakers = {"S0": SpeakerRole("teacher", 0.5, low), "S1": SpeakerRole("students", 0.5, low)}
    heuristic = RoleAssignment(speakers, "unclear_roles")
    return TieBreakRequest("teaching", ("teacher", "students"), heuristic, (("S0", "aaj hum padhenge"), ("S1", "ji")))


def tie_break(gateway: FakeGateway) -> Any:
    return LlmRoleTieBreaker(gateway, "t1", "r1")(request())  # type: ignore[arg-type]  # a fake gateway


def test_the_tie_breaker_names_one_staff_member() -> None:
    gateway = FakeGateway({"staff_speaker": "S0", "confidence": 0.85})
    answer = tie_break(gateway)
    assert answer.role_by_speaker() == {"S0": "teacher", "S1": "students"}
    call = gateway.calls[0]
    assert call["json_schema"]["properties"]["staff_speaker"]["enum"] == ["S0", "S1", "unsure"]
    assert call["tenant_id"] == "t1" and call["recording_id"] == "r1"
    assert "S0: aaj hum padhenge" in call["messages"][1].content


@pytest.mark.parametrize(
    "gateway",
    [
        FakeGateway({"staff_speaker": "unsure", "confidence": 0.2}),
        FakeGateway({"staff_speaker": "S9", "confidence": 0.9}),
        FakeGateway(error=ProviderError("openai", "HTTP 503", retryable=True)),
    ],
    ids=["unsure", "unknown speaker", "call failed"],
)
def test_the_tie_breaker_never_guesses(gateway: FakeGateway) -> None:
    assert tie_break(gateway) is None
