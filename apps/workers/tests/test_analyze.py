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
from sabha_workers.stages.analyze import AnalyzeDeps, make_work, store_analysis
from sabha_workers.stages.runner import DONE_MARKER, S3Artefacts, StageRunner, StageSpec

pytestmark = pytest.mark.integration
S = RecordingStatus
ANALYZE = StageSpec("analyze", working=S.ANALYZING, done_to=S.COMPLETED, per_run=True)
ROOT = Path(__file__).resolve().parents[3]
RUBRIC = load_rubric(ROOT / "packages/analytics/tests/fixtures/rubrics/teaching.testing.v1.0.yaml")
MEETING_RUBRIC = load_rubric(ROOT / "packages/analytics/tests/fixtures/rubrics/meeting.testing.v1.0.yaml")
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
        self.rubric_asked: list[str | None] = []

    def recording(self, *, with_inputs: bool = True, kind: ConversationType = ConversationType.TEACHING,
                  document: dict[str, Any] | None = None) -> str:  # fmt: skip
        rec = Recording(type=kind, status=S.ANALYZING, consent_ref="c", person_id="p-asha",
                        unit_id="unit-1", duration_ms=DURATION_MS)  # fmt: skip
        rid = SyncTenantRepo(self.db, "recordings", "t1", Recording).insert_one(rec).id
        if with_inputs:
            body = json.dumps(document or transcript()).encode()
            self.artefacts.put(f"t1/{rid}/transcribe@v1/transcript@v1.json", body)
            self.artefacts.put(f"t1/{rid}/preprocess@v1/segments@v1.json", MAP.to_json().encode())
        return rid

    def deps(self, judge: FakeJudge, rubric: Any = RUBRIC) -> AnalyzeDeps:
        def pick(tenant: Tenant, kind: ConversationType, rubric_id: str | None) -> Any:
            self.rubric_asked.append(rubric_id)
            return rubric

        return AnalyzeDeps(
            preprocess_version="v1", transcribe_version="v1", analysis_version="v1", tenant=lambda _: TENANT,
            person=lambda t, p: SyncTenantRepo(self.db, "people", t, Person).find_one({"_id": p}),
            rubric=pick, judge=lambda *_: judge, save=lambda t, a, s: store_analysis(self.db, t, a, s),
            llm_cost=lambda *_: None,
        )  # fmt: skip

    def run(self, rid: str, judge: FakeJudge, rubric: Any = RUBRIC) -> str:
        return self.runner.run(ANALYZE, make_work(self.deps(judge, rubric)), "t1", rid, attempt=1).result

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


def meeting_transcript() -> dict[str, Any]:
    rows = (("S0", 0, 8_000, "Aaj ka agenda budget aur vendor issue hai, dono pe decision chahiye."),
            ("S1", 9_000, 20_000, "Toh decide karte hain budget do lakh rahega, sirf Instagram pe."),
            ("S2", 21_000, 30_000, "Vendor ko main kal baarah baje tak call kar dungi, pakka."))  # fmt: skip
    return {"version": "transcript@v1", "timeline": "original", "asr_model": "sarvam/saaras:v4",
            "word_timing": "approximate", "word_count": sum(len(r[3].split()) for r in rows),
            "utterances": [{"role": "participant", "speaker_label": v, "start_ms": a, "end_ms": b, "text": t,
                            "avg_confidence": None, "low_confidence_spans": []} for v, a, b, t in rows]}  # fmt: skip


def test_a_meeting_is_scored_as_a_whole_and_its_scores_belong_to_no_one(stage: Stage) -> None:
    rid = stage.recording(kind=ConversationType.MEETING, document=meeting_transcript())
    scores = {"dimensions": [
        {"key": "decisions_made", "score": 4, "rationale": "The budget decision is said out loud.",
         "evidence": [{"quote": "budget do lakh rahega", "utterance_id": "u0001", "start_ms": 9_000}]},
        {"key": "actions_assigned", "score": 4, "rationale": "The vendor call has an owner and a time.",
         "evidence": [{"quote": "kal baarah baje tak call kar dungi", "utterance_id": "u0002", "start_ms": 21_000}]},
    ]}  # fmt: skip
    synthesis = {
        "summary": "A short meeting that settled the budget and gave out the vendor call.",
        "strengths": ["The budget decision is said clearly.", "The vendor call has a time."],
        "gaps": ["Decisions were not read back.", "No next check-in was set."],
        "suggestions": [{"text": "Read the decision back.", "utterance_id": "u0001"},
                        {"text": "Confirm who owns each action.", "utterance_id": "u0002"},
                        {"text": "Close with the list of actions.", "utterance_id": "u0002"}],
    }  # fmt: skip
    phases = {
        "phases": [
            {"phase": "opening", "start_utterance_id": "u0000", "end_utterance_id": "u0000"},
            {"phase": "decisions", "start_utterance_id": "u0001", "end_utterance_id": "u0002"},
        ]
    }
    notes = {"decisions": [{"decision": "The budget is Rs 2 lakh, on Instagram only.", "quote": "budget do lakh rahega",
                            "start_ms": 9_000, "utterance_id": "u0001"}],
             "action_items": [{"action": "Call the vendor.", "owner": None, "owner_voice": "S2", "due": "tomorrow 12",
                               "quote": "kal baarah baje tak call kar dungi", "start_ms": 21_000,
                               "utterance_id": "u0002"}],
             "open_questions": []}  # fmt: skip
    assert stage.run(rid, FakeJudge([scores, synthesis, phases, notes]), MEETING_RUBRIC) == "done"
    (analysis,) = stage.db.analyses.find({"recording_id": rid})
    assert analysis["person_id"] is None  # nobody is scored, so nobody's trend shows it
    assert all(s["person_id"] is None for s in stage.db.scores.find({"analysis_id": analysis["_id"]}))
    report = json.loads(stage.artefacts.get(f"t1/{rid}/analyze@v1/analysis@v1.json"))
    assert report["meeting_notes"]["action_items"][0]["owner_voice"] == "S2"
    assert {m["key"]: m["value"] for m in report["metrics"]}["voice_count"] == 3


# --- Re-analysis (P2.8) ---


def reanalyse(stage: Stage, rid: str, run: int, rubric_id: str | None = None) -> None:
    """What POST /v1/recordings/{id}/reanalyze does to the recording: back to ANALYZING with the next run."""
    stage.db.recordings.update_one({"_id": rid}, {"$set": {"status": "ANALYZING", "analysis_run": run,
                                                           "rubric_id": rubric_id}})  # fmt: skip


def test_a_reanalysis_stores_a_new_version_and_keeps_the_old(stage: Stage) -> None:
    rid = stage.recording()
    assert stage.run(rid, good_judge()) == "done"
    reanalyse(stage, rid, 2)
    assert stage.run(rid, good_judge()) == "done"  # not skipped: run 2 has its own artefact folder

    assert stage.doc(rid)["status"] == "COMPLETED"
    assert stage.artefacts.exists(f"t1/{rid}/analyze@v1-run2/analysis@v1.json")
    by_version = {a["version"]: a for a in stage.db.analyses.find({"recording_id": rid})}
    assert set(by_version) == {"v1", "v1-run2"}
    assert (by_version["v1"]["superseded"], by_version["v1-run2"]["superseded"]) == (True, False)
    old_scores = list(stage.db.scores.find({"analysis_id": by_version["v1"]["_id"]}))
    new_scores = list(stage.db.scores.find({"analysis_id": by_version["v1-run2"]["_id"]}))
    assert len(old_scores) == len(new_scores) == 2
    assert all(s["superseded"] for s in old_scores) and not any(s["superseded"] for s in new_scores)
    # Finishing a re-analysis is quiet: the event says so, and the relay starts neither notify nor meter.
    done = stage.db.outbox.find_one({"type": "recording.completed", "payload.meta.reanalysis": True})
    assert done is not None and done["payload"]["meta"]["analysis_run"] == 2


def test_a_retried_reanalysis_replaces_only_its_own_version(stage: Stage) -> None:
    rid = stage.recording()
    stage.run(rid, good_judge())
    reanalyse(stage, rid, 2)
    stage.run(rid, good_judge())
    latest = Analysis.model_validate(stage.db.analyses.find_one({"version": "v1-run2"}))
    rows = [Score.model_validate(s) for s in stage.db.scores.find({"recording_id": rid, "superseded": False})]
    store_analysis(stage.db, "t1", latest, rows)  # the same version again, as a retried stage would
    assert stage.db.analyses.count_documents({"recording_id": rid}) == 2
    assert stage.db.analyses.count_documents({"recording_id": rid, "superseded": False}) == 1


def test_a_reanalysis_uses_the_rubric_chosen_for_it(stage: Stage) -> None:
    rid = stage.recording()
    stage.run(rid, good_judge())
    reanalyse(stage, rid, 2, rubric_id="teaching.testing.v1.0")
    stage.run(rid, good_judge())
    assert stage.rubric_asked == [None, "teaching.testing.v1.0"]
