"""The diarize stage (plan task P3.4a) with a scripted diarizer: mapping to the original timeline and the stage."""

from __future__ import annotations

import json
import uuid
import wave
from collections.abc import Iterator
from typing import Any

import pytest
from pymongo import MongoClient
from pymongo.database import Database

from sabha_asr.diarization import ScriptedDiarizer, Turn
from sabha_core.indexes import ensure_indexes
from sabha_core.models import Recording
from sabha_core.profiles import ConversationType
from sabha_core.repo import SyncTenantRepo
from sabha_core.settings import Settings
from sabha_core.state import RecordingStatus
from sabha_core.timemap import Segment, SegmentMap, build_segment_map
from sabha_workers.stages.diarize import make_work, to_original
from sabha_workers.stages.runner import DONE_MARKER, S3Artefacts, StageRunner, StageSpec

S = RecordingStatus
DIARIZE = StageSpec("diarize", working=S.DIARIZING, done_to=S.TRANSCRIBING)
# Original: speech at [1000, 4000) and [9000, 12000); compact: [0, 3000) and [3000, 6000).
MAP = SegmentMap((Segment(1_000, 4_000, 0), Segment(9_000, 12_000, 3_000)))


# --- Mapping to the original timeline ---


def test_turns_inside_a_segment_shift_by_its_offset() -> None:
    assert to_original([Turn("S0", 500, 2_500), Turn("S1", 3_200, 5_000)], MAP) == [
        Turn("S0", 1_500, 3_500),
        Turn("S1", 9_200, 11_000),
    ]


def test_a_turn_across_a_join_is_split_and_never_covers_removed_silence() -> None:
    assert to_original([Turn("S0", 2_000, 4_000)], MAP) == [Turn("S0", 3_000, 4_000), Turn("S0", 9_000, 10_000)]


def test_turns_ending_exactly_at_a_join_stay_in_their_segment() -> None:
    assert to_original([Turn("S0", 0, 3_000)], MAP) == [Turn("S0", 1_000, 4_000)]


def test_mapping_agrees_with_the_segment_map() -> None:
    segment_map = build_segment_map([(500, 2_000), (6_000, 6_400), (20_000, 25_000)], 30_000)
    for start, end in [(0, 50), (1_700, 1_900), (2_000, 2_700), (2_100, 7_000)]:
        for piece in to_original([Turn("S0", start, end)], segment_map):
            compact_start = segment_map.original_to_compact(piece.start_ms)
            assert segment_map.compact_to_original(compact_start) == piece.start_ms


# --- Settings ---


def test_the_scripted_diarizer_is_for_tests_only() -> None:
    values: dict[str, Any] = {
        "mongo_uri": "mongodb://localhost:27017/?replicaSet=rs0", "redis_url": "redis://localhost:6380/0",
        "s3_bucket_audio": "a", "s3_bucket_artefacts": "b", "s3_bucket_backups": "c",
        "oidc_issuer": "https://auth.example.com", "oidc_audience": "https://api.example.com", "oidc_client_id": "w",
    }  # fmt: skip
    assert Settings(_env_file=None, app_env="test", diarizer="fake", **values).diarizer == "fake"  # type: ignore[call-arg]  # pydantic-settings
    with pytest.raises(ValueError, match="DIARIZER=fake is for tests only"):
        Settings(_env_file=None, app_env="local", diarizer="fake", **values)  # type: ignore[call-arg]  # pydantic-settings


# --- The stage (MongoDB, RustFS) ---


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"diar_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield name
    mongo_replica_set.drop_database(name)


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]], shared_db: str) -> Database[dict[str, Any]]:
    database = mongo_replica_set[shared_db]
    for collection in ("recordings", "stage_runs", "outbox", "dlq"):
        database[collection].delete_many({})
    return database


class Stage:
    def __init__(self, db: Database[dict[str, Any]], s3_storage: Any, tmp: Any) -> None:
        self.db = db
        self.artefacts = S3Artefacts(s3_storage.client(), "sabha-artefacts")
        self.tmp = tmp
        self.runner = StageRunner(db=db, artefacts=self.artefacts, versions={"diarize": "v1"}, worker="test")

    def recording(self, *, with_inputs: bool = True) -> str:
        recording = Recording(type=ConversationType.TEACHING, status=S.DIARIZING, consent_ref="c")
        rid = SyncTenantRepo(self.db, "recordings", "t1", Recording).insert_one(recording).id
        if with_inputs:
            compact = self.tmp / f"{rid}.wav"
            with wave.open(str(compact), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(16_000)
                out.writeframes(b"\x00\x00" * 16 * MAP.compact_length_ms)
            self.artefacts.put_file(f"t1/{rid}/preprocess@v1/compact.wav", compact, "audio/wav")
            self.artefacts.put(f"t1/{rid}/preprocess@v1/segments@v1.json", MAP.to_json().encode())
        return rid

    def run(self, rid: str, diarizer: ScriptedDiarizer) -> str:
        work = make_work(lambda: diarizer, preprocess_version="v1", device="cpu")
        return self.runner.run(DIARIZE, work, "t1", rid, attempt=1).result

    def doc(self, rid: str) -> dict[str, Any]:
        found = self.db.recordings.find_one({"_id": rid})
        assert found is not None
        return found


@pytest.fixture
def stage(db: Database[dict[str, Any]], s3_storage: Any, tmp_path: Any) -> Stage:
    return Stage(db, s3_storage, tmp_path)


@pytest.mark.integration
def test_the_stage_writes_both_timelines_and_moves_on(stage: Stage) -> None:
    rid = stage.recording()
    diarizer = ScriptedDiarizer([("teacher", 0, 2_000), ("student", 2_000, 3_500), ("teacher", 3_500, 6_000)])
    assert stage.run(rid, diarizer) == "done"

    assert stage.doc(rid)["status"] == "TRANSCRIBING"
    output = json.loads(stage.artefacts.get(f"t1/{rid}/diarize@v1/diarization@v1.json"))
    assert output["version"] == "diarization@v1" and output["model"] == "scripted-diarizer@1"
    assert output["speakers"] == ["S0", "S1"]
    assert output["compact"][1] == {"speaker_label": "S1", "start_ms": 2_000, "end_ms": 3_500}
    # The student's turn crosses the join at compact 3000, so it is two pieces in original time.
    assert [t for t in output["original"] if t["speaker_label"] == "S1"] == [
        {"speaker_label": "S1", "start_ms": 3_000, "end_ms": 4_000},
        {"speaker_label": "S1", "start_ms": 9_000, "end_ms": 9_500},
    ]
    assert stage.artefacts.exists(f"t1/{rid}/diarize@v1/{DONE_MARKER}")
    (run,) = stage.db.stage_runs.find({"recording_id": rid})
    assert run["meta"]["speakers"] == 2 and run["meta"]["audio_s"] == 6.0 and run["meta"]["device"] == "cpu"
    assert run["meta"]["real_time_factor"] is not None


@pytest.mark.integration
def test_missing_preprocess_output_fails_for_a_replay(stage: Stage) -> None:
    rid = stage.recording(with_inputs=False)
    assert stage.run(rid, ScriptedDiarizer([])) == "failed"
    assert (stage.doc(rid)["status"], stage.doc(rid)["status_reason"]) == ("FAILED", "missing_input")
    assert stage.db.dlq.count_documents({"recording_id": rid}) == 1


@pytest.mark.integration
def test_no_speaker_turns_asks_for_review(stage: Stage) -> None:
    rid = stage.recording()
    assert stage.run(rid, ScriptedDiarizer([])) == "needs_review"
    assert (stage.doc(rid)["status"], stage.doc(rid)["status_reason"]) == ("NEEDS_REVIEW", "no_speakers")
