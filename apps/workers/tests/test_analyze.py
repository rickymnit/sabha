"""The analyze stage (plan task P5.7) end to end with a scripted fake LLM: a stored, valid report and its scores."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from pymongo import MongoClient
from pymongo.database import Database

from sabha_analytics.report import load_report_schema
from sabha_analytics.rubric import load_rubric
from sabha_analytics.scoring import JudgeResponse, TokenUsage
from sabha_core.indexes import ensure_indexes
from sabha_core.models import Analysis, Person, Recording, Score, Tenant
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.repo import SyncTenantRepo
from sabha_core.state import RecordingStatus
from sabha_core.timemap import Segment, SegmentMap
from sabha_llm.errors import LlmConfigError, ProviderError
from sabha_workers.stages.analyze import AnalyzeDeps, make_work
from sabha_workers.stages.runner import DONE_MARKER, S3Artefacts, StageRunner, StageSpec

pytestmark = pytest.mark.integration
S = RecordingStatus
ANALYZE = StageSpec("analyze", working=S.ANALYZING, done_to=S.COMPLETED)
ROOT = Path(__file__).resolve().parents[3]
RUBRIC = load_rubric(ROOT / "packages/analytics/tests/fixtures/rubrics/teaching.testing.v1.0.yaml")
TENANT = Tenant.from_profile("school", name="Sunrise Public School", plan=Plan.PILOT, id="t1")
ROWS = (  # the analytics package's test lesson; u0002 is a student line with a phone number
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
DURATION_MS = 520_000
MAP = SegmentMap((Segment(0, DURATION_MS, 0),))

CONCEPT: dict[str, Any] = {
    "key": "concept_clarity", "score": 4, "rationale": "The teacher defines photosynthesis and chlorophyll plainly.",
    "evidence": [
        {"quote": "plant sunlight paani aur carbon dioxide se apna khana banata hai", "utterance_id": "u0001",
         "start_ms": 9_000},
        {"quote": "Chlorophyll leaf ka green pigment hai", "utterance_id": "u0003", "start_ms": 34_000},
    ],
}  # fmt: skip
RECAP: dict[str, Any] = {
    "key": "recap_and_closure", "score": 3, "rationale": "The teacher lists what was covered and what comes next.",
    "evidence": [{"quote": "aaj humne photosynthesis aur chlorophyll dono padhe", "utterance_id": "u0004",
                  "start_ms": 500_000}],
}  # fmt: skip
FAKE = {**CONCEPT, "evidence": [CONCEPT["evidence"][0], {"quote": "plants breathe oxygen at night through their roots",
                                                         "utterance_id": "u0003", "start_ms": 34_000}]}  # fmt: skip
SYNTHESIS = {
    "summary": "A clear lesson on photosynthesis with a short recap at the end.",
    "strengths": ["Defines key terms in plain words.", "Links ideas to everyday experience."],
    "gaps": ["Few checks that students understood.", "The recap is brief."],
    "suggestions": [
        {"text": "Ask a student to explain photosynthesis back in their own words.", "utterance_id": "u0001"},
        {"text": "Pause after defining chlorophyll and ask why leaves are green.", "utterance_id": "u0003"},
        {"text": "Let students state the two key ideas in the recap.", "utterance_id": "u0004"},
    ],
}
PHASES = {"phases": [
    {"phase": "introduction", "start_utterance_id": "u0000", "end_utterance_id": "u0000"},
    {"phase": "explanation", "start_utterance_id": "u0001", "end_utterance_id": "u0003"},
    {"phase": "closing", "start_utterance_id": "u0004", "end_utterance_id": "u0004"},
]}  # fmt: skip


@dataclass
class FakeJudge:
    answers: list[object]
    error: Exception | None = None
    model_id: str = "fake-judge@1"
    calls: list[str] = field(default_factory=list)

    def complete_json(self, *, task: str, system: str, messages: Sequence[Mapping[str, str]],
                      json_schema: Mapping[str, Any], cache_prefix: str | None) -> JudgeResponse:  # fmt: skip
        self.calls.append(task)
        if self.error is not None:
            raise self.error
        return JudgeResponse(self.answers.pop(0), self.model_id, TokenUsage(input_tokens=100, output_tokens=20))


def transcript() -> dict[str, Any]:
    utterances: list[dict[str, Any]] = [
        {"role": role, "speaker_label": "S0" if role == "teacher" else "S1", "start_ms": start, "end_ms": end,
         "text": text, "avg_confidence": None, "low_confidence_spans": []}
        for role, start, end, text in ROWS
    ]  # fmt: skip
    words = sum(len(r[3].split()) for r in ROWS)
    return {"version": "transcript@v1", "timeline": "original", "asr_model": "sarvam/saaras:v4",
            "word_timing": "approximate", "word_count": words, "utterances": utterances}  # fmt: skip


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"anl_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield name
    mongo_replica_set.drop_database(name)


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]], shared_db: str) -> Database[dict[str, Any]]:
    database = mongo_replica_set[shared_db]
    for collection in ("recordings", "stage_runs", "outbox", "dlq", "analyses", "scores", "people", "llm_calls"):
        database[collection].delete_many({})
    return database


class Stage:
    def __init__(self, db: Database[dict[str, Any]], s3_storage: Any) -> None:
        self.db = db
        self.artefacts = S3Artefacts(s3_storage.client(), "sabha-artefacts")
        self.runner = StageRunner(db=db, artefacts=self.artefacts, versions={"analyze": "v1"}, worker="test",
                                  jitter=lambda: 0.0)  # fmt: skip
        SyncTenantRepo(db, "people", "t1", Person).insert_one(Person(id="p-asha", name="Asha", unit_id="unit-1"))

    def recording(self, *, with_inputs: bool = True) -> str:
        rec = Recording(type=ConversationType.TEACHING, status=S.ANALYZING, consent_ref="c", person_id="p-asha",
                        unit_id="unit-1", duration_ms=DURATION_MS)  # fmt: skip
        rid = SyncTenantRepo(self.db, "recordings", "t1", Recording).insert_one(rec).id
        if with_inputs:
            self.artefacts.put(f"t1/{rid}/transcribe@v1/transcript@v1.json", json.dumps(transcript()).encode())
            self.artefacts.put(f"t1/{rid}/preprocess@v1/segments@v1.json", MAP.to_json().encode())
        return rid

    def deps(self, judge: FakeJudge) -> AnalyzeDeps:
        def save(tenant_id: str, analysis: Analysis, scores: list[Score]) -> None:
            analyses = SyncTenantRepo(self.db, "analyses", tenant_id, Analysis)
            rows = SyncTenantRepo(self.db, "scores", tenant_id, Score)
            for old in analyses.find({"recording_id": analysis.recording_id, "version": analysis.version}):
                rows.delete_many({"analysis_id": old.id})
            analyses.delete_many({"recording_id": analysis.recording_id, "version": analysis.version})
            analyses.insert_one(analysis)
            rows.insert_many(scores)

        return AnalyzeDeps(
            preprocess_version="v1", transcribe_version="v1", analysis_version="v1", tenant=lambda _: TENANT,
            person=lambda t, p: SyncTenantRepo(self.db, "people", t, Person).find_one({"_id": p}),
            rubric=lambda *_: RUBRIC, judge=lambda *_: judge, save=save, llm_cost=lambda *_: None,
        )  # fmt: skip

    def run(self, rid: str, judge: FakeJudge) -> str:
        return self.runner.run(ANALYZE, make_work(self.deps(judge)), "t1", rid, attempt=1).result

    def doc(self, rid: str) -> dict[str, Any]:
        found = self.db.recordings.find_one({"_id": rid})
        assert found is not None
        return found


@pytest.fixture
def stage(db: Database[dict[str, Any]], s3_storage: Any) -> Stage:
    return Stage(db, s3_storage)


def good_judge() -> FakeJudge:
    return FakeJudge([{"dimensions": [CONCEPT, RECAP]}, SYNTHESIS, PHASES])


def test_a_lesson_is_scored_stored_and_completed(stage: Stage) -> None:
    rid = stage.recording()
    judge = good_judge()
    assert stage.run(rid, judge) == "done"

    assert stage.doc(rid)["status"] == "COMPLETED"  # the outbox event starts notify and meter
    report = json.loads(stage.artefacts.get(f"t1/{rid}/analyze@v1/analysis@v1.json"))
    jsonschema.validate(report, load_report_schema())
    assert report["overall"]["score"] == 3.6  # 0.6 * 4 + 0.4 * 3, computed in code
    assert "9876543210" not in json.dumps(report)  # golden rule 8

    (analysis,) = stage.db.analyses.find({"recording_id": rid})
    assert (analysis["status"], analysis["overall_score"], analysis["person_id"]) == ("COMPLETED", 3.6, "p-asha")
    assert (analysis["rubric_id"], analysis["version"]) == ("teaching.testing.v1.0", "v1")
    assert analysis["usage"]["input_tokens"] == 300 and analysis["model_ids"] == ["fake-judge@1"]
    assert set(analysis["prompt_hashes"]) >= {"scoring.system", "synthesis.system"}
    scores = {s["dimension"]: s for s in stage.db.scores.find({"analysis_id": analysis["_id"]})}
    assert {k: s["score"] for k, s in scores.items()} == {"concept_clarity": 4, "recap_and_closure": 3}
    assert all(s["person_id"] == "p-asha" and s["verified"] for s in scores.values())
    assert scores["concept_clarity"]["evidence"][0]["utterance_id"] == "u0001"
    assert stage.artefacts.exists(f"t1/{rid}/analyze@v1/{DONE_MARKER}")
    (run,) = stage.db.stage_runs.find({"recording_id": rid})
    assert run["meta"]["dimensions_verified"] == 2 and run["meta"]["llm_calls"] == 3


def test_a_rerun_replaces_its_own_analysis(stage: Stage) -> None:
    rid = stage.recording()
    work = make_work(stage.deps(good_judge()))
    from sabha_workers.stages.runner import StageContext

    recording = Recording.model_validate(stage.doc(rid))
    ctx = StageContext("t1", recording, f"t1/{rid}/analyze@v1/", stage.artefacts, 1)
    work(ctx)
    make_work(stage.deps(good_judge()))(ctx)
    assert stage.db.analyses.count_documents({"recording_id": rid}) == 1
    assert stage.db.scores.count_documents({"recording_id": rid}) == 2


def test_too_little_verified_evidence_is_stored_and_asks_for_review(stage: Stage) -> None:
    rid = stage.recording()
    judge = FakeJudge([{"dimensions": [FAKE, RECAP]}, {"dimensions": [FAKE]}, PHASES])  # the fake quote twice
    assert stage.run(rid, judge) == "needs_review"
    assert (stage.doc(rid)["status"], stage.doc(rid)["status_reason"]) == ("NEEDS_REVIEW", "low_verification")
    (analysis,) = stage.db.analyses.find({"recording_id": rid})
    assert analysis["status"] == "NEEDS_REVIEW" and analysis["overall_score"] is None
    concept = stage.db.scores.find_one({"recording_id": rid, "dimension": "concept_clarity"})
    assert concept is not None and concept["score"] is None and concept["evidence"] == []  # never a fake quote
    assert "plants breathe oxygen" not in json.dumps(list(stage.db.scores.find({"recording_id": rid})), default=str)


@pytest.mark.parametrize(
    ("error", "result", "code"),
    [
        (ProviderError("openai", "HTTP 429", retryable=True), "retry", "llm_unavailable"),
        (ProviderError("openai", "HTTP 401", retryable=False), "failed", "analysis_failed"),
        (LlmConfigError("no LLM provider is configured"), "failed", "analysis_failed"),
    ],
)
def test_llm_failures(stage: Stage, error: Exception, result: str, code: str) -> None:
    rid = stage.recording()
    assert stage.run(rid, FakeJudge([], error=error)) == result
    (run,) = stage.db.stage_runs.find({"recording_id": rid})
    assert run["error_code"] == code
    assert stage.db.analyses.count_documents({"recording_id": rid}) == 0


def test_missing_transcript_fails_for_a_replay(stage: Stage) -> None:
    rid = stage.recording(with_inputs=False)
    assert stage.run(rid, good_judge()) == "failed"
    assert stage.doc(rid)["status_reason"] == "missing_input"
