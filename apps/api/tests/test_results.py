"""Reading recordings and results (P5.7b): who sees what in the list, paging, transcript and analysis with their
audit entries, history and trends. The permission matrix (tests/security) covers every route for every caller."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.database import Database

from sabha_api.resources import open_resources
from sabha_api.services.results import metric_name, recording_title, shown_ticket, without_ids
from sabha_core.indexes import ensure_indexes
from sabha_core.models import (
    Analysis,
    IdentityLink,
    Person,
    Recording,
    Role,
    Score,
    SpeakerSpan,
    Tenant,
    Transcript,
    Unit,
    User,
    utc_now,
)  # fmt: skip
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.reasons import explain
from sabha_core.repo import COLLECTIONS
from sabha_core.state import RecordingStatus

pytestmark = pytest.mark.integration
T = "tenant-a"
USERS = {  # subject -> (user id, role, units)
    "owner": ("u-owner", Role.OWNER, []),
    "manager": ("u-manager", Role.MANAGER, ["unit-1"]),
    "asha": ("u-asha", Role.STAFF, []),
    "nobody": ("u-nobody", Role.STAFF, []),  # no person linked
}


@dataclass
class Api:
    client: TestClient
    db: Database[dict[str, Any]]
    idp: Any
    s3: Any

    def get(self, sub: str, path: str) -> httpx.Response:
        return self.client.get(path, headers={"Authorization": f"Bearer {self.idp.token(sub)}"})

    def post(self, sub: str, path: str, body: dict[str, Any]) -> httpx.Response:
        return self.client.post(path, json=body, headers={"Authorization": f"Bearer {self.idp.token(sub)}"})


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"res_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield name
    mongo_replica_set.drop_database(name)


def insert(db: Database[dict[str, Any]], collection: str, doc: Any) -> None:
    db[collection].insert_one(doc.model_dump(by_alias=True))


@pytest.fixture
def api(make_client: Any, mongo_uri: str, mongo_replica_set: MongoClient[dict[str, Any]], shared_db: str,
        fake_idp: Any, s3_storage: Any) -> Api:  # fmt: skip
    db = mongo_replica_set[shared_db]
    for collection in COLLECTIONS:
        db[collection].delete_many({})
    client = make_client(
        resources=open_resources, token_verifier=fake_idp.verifier(), mongo_uri=f"{mongo_uri}&replicaSet=rs0",
        mongo_db=shared_db, redis_url="redis://127.0.0.1:1/0", s3_endpoint_url=s3_storage.endpoint_url,
        s3_access_key_id=s3_storage.access_key_id, s3_secret_access_key=s3_storage.secret_access_key,
    )  # fmt: skip
    issuer = client.app.state.settings.oidc_issuer
    insert(db, "tenants", Tenant.from_profile("school", name="Sunrise", plan=Plan.PILOT, id=T))
    for unit in ("unit-1", "unit-2"):
        insert(db, "units", Unit(id=unit, tenant_id=T, name=unit))
    for sub, (user_id, role, units) in USERS.items():
        insert(db, "users", User(id=user_id, tenant_id=T, email=f"{sub}@example.com", name=sub, role=role,
                                 unit_ids=units, status="active"))  # fmt: skip
        insert(db, "identities", IdentityLink(tenant_id=T, issuer=issuer, subject=sub, email=f"{sub}@example.com",
                                              user_id=user_id))  # fmt: skip
    insert(db, "people", Person(id="p-asha", tenant_id=T, name="Asha", unit_id="unit-1", user_id="u-asha"))
    insert(db, "people", Person(id="p-ravi", tenant_id=T, name="Ravi", unit_id="unit-2"))
    return Api(client, db, fake_idp, s3_storage.client())


def recording(api: Api, rid: str, person: str, unit: str, minutes_ago: int,
              status: RecordingStatus = RecordingStatus.COMPLETED) -> None:  # fmt: skip
    insert(api.db, "recordings", Recording(
        id=rid, tenant_id=T, type=ConversationType.TEACHING, status=status, consent_ref="c", person_id=person,
        unit_id=unit, file_name=f"{rid}.mp3", created_at=utc_now() - timedelta(minutes=minutes_ago),
    ))  # fmt: skip


DIMENSIONS: list[dict[str, Any]] = [
    {"key": "concept_clarity", "name": "Concept clarity", "weight": 0.6, "verified": True, "score": 4,
     "rationale": "Defines terms plainly.", "attempts": 1, "failure_reasons": [],
     "evidence": [{"quote": "Chlorophyll leaf ka green pigment hai", "utterance_id": "u0003", "start_ms": 34_000,
                   "end_ms": 40_000}]},
    {"key": "recap_and_closure", "name": "Recap and closure", "weight": 0.4, "verified": True, "score": 3,
     "rationale": "Lists what was covered.", "attempts": 1, "failure_reasons": [],
     "evidence": [{"quote": "aaj humne dono padhe", "utterance_id": "u0004", "start_ms": 500_000, "end_ms": 510_000}]},
]  # fmt: skip
METRICS = [
    {"key": "teacher_talk_share", "value": 0.82, "unit": "ratio", "definition": "Share of talk time."},
    {"key": "longest_monologue_s", "value": 95.5, "unit": "s", "definition": "Longest stretch of talk."},
    {"key": "words_per_minute", "value": 120, "unit": "words/min", "definition": "Speaking pace."},
]
SYNTHESIS = {"summary": "A clear lesson.", "strengths": ["Plain words."], "gaps": ["Few checks."],
             "suggestions": [{"text": "Ask a student to explain.", "utterance_id": "u0001", "start_ms": 9_000,
                              "end_ms": 30_000}]}  # fmt: skip


def analysis(api: Api, rid: str, version: str, score: float, minutes_ago: int, person: str = "p-asha",
             dimensions: list[dict[str, Any]] | None = None,
             status: Literal["COMPLETED", "NEEDS_REVIEW"] = "COMPLETED") -> str:  # fmt: skip
    key = f"{T}/{rid}/analyze@{version}/analysis@v1.json"
    report = {"version": "analysis@v1", "overall": {"score": score}, "dimensions": dimensions or DIMENSIONS,
              "metrics": METRICS, "synthesis": SYNTHESIS,
              "phases": [{"phase": "introduction", "start_utterance_id": "u0000", "end_utterance_id": "u0000",
                          "start_ms": 0, "end_ms": 8_000}]}  # fmt: skip
    api.s3.put_object(Bucket="sabha-artefacts", Key=key, Body=json.dumps(report).encode())
    doc = Analysis(tenant_id=T, recording_id=rid, version=version, person_id=person, unit_id="unit-1",
                   conversation_type=ConversationType.TEACHING, rubric_id="teaching.school.v0.1", rubric_version="0.1",
                   rubric_hash="h", report_key=key, status=status, overall_score=score, verified_share=1.0,
                   model_ids=["openai:o3-mini"], prompt_hashes={"scoring.system": "abc"},
                   created_at=utc_now() - timedelta(minutes=minutes_ago))  # fmt: skip
    insert(api.db, "analyses", doc)
    insert(api.db, "scores", Score(tenant_id=T, analysis_id=doc.id, recording_id=rid, person_id=person,
                                   dimension="concept_clarity", name="Concept clarity", weight=0.6,
                                   score=round(score), verified=True, created_at=doc.created_at))  # fmt: skip
    return doc.id


def ids(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


# --- The list ---


def test_each_caller_lists_only_what_they_may_see(api: Api) -> None:
    recording(api, "r-asha", "p-asha", "unit-1", 3)
    recording(api, "r-ravi", "p-ravi", "unit-2", 2)
    assert ids(api.get("owner", "/v1/recordings")) == ["r-ravi", "r-asha"]  # newest first
    assert ids(api.get("manager", "/v1/recordings")) == ["r-asha"]  # unit-1 only
    assert ids(api.get("asha", "/v1/recordings")) == ["r-asha"]  # her own
    assert ids(api.get("nobody", "/v1/recordings")) == []  # no person: nothing, not an error


def test_the_list_narrows_by_person_and_type_but_never_widens(api: Api) -> None:
    recording(api, "r-asha", "p-asha", "unit-1", 3)
    recording(api, "r-ravi", "p-ravi", "unit-2", 2)
    assert ids(api.get("owner", "/v1/recordings?person_id=p-ravi")) == ["r-ravi"]
    assert ids(api.get("owner", "/v1/recordings?type=teaching")) == ["r-ravi", "r-asha"]
    assert ids(api.get("owner", "/v1/recordings?type=reception")) == []
    assert ids(api.get("manager", "/v1/recordings?person_id=p-ravi")) == []  # not in the manager's unit
    assert ids(api.get("asha", "/v1/recordings?person_id=p-ravi")) == []  # not her own
    assert api.get("owner", "/v1/recordings?type=karaoke").status_code == 422


def test_the_list_pages_with_a_cursor(api: Api) -> None:
    for minutes in range(5):
        recording(api, f"r{minutes}", "p-asha", "unit-1", minutes)
    first = api.get("owner", "/v1/recordings?limit=2").json()
    assert [i["id"] for i in first["items"]] == ["r0", "r1"] and first["next_cursor"]
    second = api.get("owner", f"/v1/recordings?limit=2&cursor={first['next_cursor']}").json()
    third = api.get("owner", f"/v1/recordings?limit=2&cursor={second['next_cursor']}").json()
    assert [i["id"] for i in second["items"] + third["items"]] == ["r2", "r3", "r4"]
    assert third["next_cursor"] is None
    assert api.get("owner", "/v1/recordings?cursor=not-a-cursor").json()["code"] == "bad_request"
    assert api.get("owner", "/v1/recordings?limit=500").status_code == 422


def test_the_list_shows_the_person_and_latest_score(api: Api) -> None:
    recording(api, "r-asha", "p-asha", "unit-1", 30)
    analysis(api, "r-asha", "v1", 3.1, 20)
    analysis(api, "r-asha", "v2", 3.8, 10)  # a re-analysis
    (item,) = api.get("owner", "/v1/recordings").json()["items"]
    assert item["person"] == {"id": "p-asha", "name": "Asha"} and item["overall_score"] == 3.8
    assert item["status"] == "COMPLETED" and item["status_note"] is None
    assert item["title"] == "r-asha"


def test_the_list_shows_who_spoke_when_but_never_a_guess_awaiting_review(api: Api) -> None:
    recording(api, "r-sure", "p-asha", "unit-1", 30)
    recording(api, "r-guess", "p-asha", "unit-1", 20)
    strip = [SpeakerSpan(start_ms=0, end_ms=9_000, speaker="staff"), SpeakerSpan(start_ms=9_000, end_ms=12_000,
                                                                                  speaker="other")]  # fmt: skip
    for rid, guess in (("r-sure", False), ("r-guess", True)):
        insert(api.db, "transcripts", Transcript(
            tenant_id=T, recording_id=rid, version="transcript@v1", storage_key=f"{T}/{rid}/t.json",
            asr_model="sarvam/saaras:v4", word_timing="approximate", word_count=10, utterance_count=2,
            roles_need_review=guess, speaker_strip=strip, rubric_id="teaching.school.v0.1",
        ))  # fmt: skip
    strips = {i["id"]: i["speaker_strip"] for i in api.get("owner", "/v1/recordings").json()["items"]}
    assert strips["r-sure"] == [s.model_dump() for s in strip]
    assert strips["r-guess"] is None


def test_search_finds_names_only_among_what_the_caller_may_see(api: Api) -> None:
    recording(api, "asha-fractions", "p-asha", "unit-1", 30)
    recording(api, "ravi-fractions", "p-ravi", "unit-2", 20)
    insert(api.db, "people", Person(id="p-asha-b", tenant_id="tenant-b", name="Asha B", unit_id="unit-1"))

    def found(sub: str, q: str) -> tuple[list[str], list[str]]:
        body = api.get(sub, f"/v1/search?q={q}").json()
        return [p["id"] for p in body["people"]], [r["id"] for r in body["recordings"]]

    assert found("owner", "FRACTIONS") == ([], ["ravi-fractions", "asha-fractions"])  # any case, newest first
    assert found("owner", "ash") == (["p-asha"], ["asha-fractions"])  # never tenant-b's Asha
    assert found("manager", "fractions") == ([], ["asha-fractions"])  # unit-1 only
    assert found("asha", "as") == (["p-asha"], ["asha-fractions"])
    assert found("asha", "ravi") == ([], [])  # staff see only their own
    assert found("owner", ".*") == ([], [])  # the text is escaped, never read as a pattern
    assert api.get("owner", "/v1/search?q=a").status_code == 422  # at least two characters


def test_the_list_says_in_plain_words_why_a_recording_stopped(api: Api) -> None:
    recording(api, "r-1", "p-asha", "unit-1", 30, RecordingStatus.FAILED)
    api.db.recordings.update_one({"_id": "r-1"}, {"$set": {"status_reason": "no_speech"}})
    recording(api, "r-2", "p-asha", "unit-1", 20, RecordingStatus.FAILED)
    api.db.recordings.update_one({"_id": "r-2"}, {"$set": {"status_reason": "unexpected_ValueError"}})
    notes = {i["id"]: i["status_note"] for i in api.get("owner", "/v1/recordings").json()["items"]}
    assert notes == {"r-1": "No speech was found in the recording.", "r-2": explain("unexpected_ValueError")}


def test_the_people_summary_counts_real_analyses_for_the_people_you_may_see(api: Api) -> None:
    for rid, minutes in (("r-1", 50), ("r-2", 40), ("r-3", 30)):
        recording(api, rid, "p-asha", "unit-1", minutes)
    analysis(api, "r-1", "v1", 2.5, 45)
    analysis(api, "r-2", "v1", 3.0, 35)
    analysis(api, "r-2", "v2", 3.4, 25)  # a re-analysis replaces r-2's score, it is not a new recording
    analysis(api, "r-3", "v1", 4.9, 20, status="NEEDS_REVIEW")  # never shown (golden rule 5)
    rows = {p["id"]: p for p in api.get("owner", "/v1/people/summary").json()}
    assert set(rows) == {"p-asha", "p-ravi"}
    asha = rows["p-asha"]
    assert (asha["analysed"], asha["latest_score"], asha["recent_scores"]) == (2, 3.4, [2.5, 3.4])
    assert asha["last_analysed_at"] is not None
    assert (rows["p-ravi"]["analysed"], rows["p-ravi"]["latest_score"], rows["p-ravi"]["recent_scores"]) == (
        0,
        None,
        [],
    )
    assert [p["id"] for p in api.get("manager", "/v1/people/summary").json()] == ["p-asha"]  # unit-1 only
    assert [p["id"] for p in api.get("asha", "/v1/people/summary").json()] == ["p-asha"]  # herself


# --- Overview ---


def overview(api: Api, who: str, days: int = 7) -> dict[str, Any]:
    end = utc_now() + timedelta(minutes=1)
    params = {"from": (end - timedelta(days=days)).isoformat(), "to": end.isoformat()}
    response = api.get(who, f"/v1/overview?{urlencode(params)}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_the_overview_counts_real_results_once_each(api: Api) -> None:
    recording(api, "r-1", "p-asha", "unit-1", 60)
    recording(api, "r-2", "p-asha", "unit-1", 50)
    recording(api, "r-ravi", "p-ravi", "unit-2", 40)
    recording(api, "r-busy", "p-asha", "unit-1", 5, RecordingStatus.TRANSCRIBING)
    recording(api, "r-stuck", "p-asha", "unit-1", 5, RecordingStatus.NEEDS_REVIEW)
    api.db.recordings.update_many({"_id": {"$in": ["r-1", "r-2", "r-ravi"]}}, {"$set": {"duration_ms": 1_800_000}})
    analysis(api, "r-1", "v1", 2.0, 55)
    analysis(api, "r-1", "v2", 3.0, 30)  # re-analysed: r-1 counts once, with 3.0
    analysis(api, "r-2", "v1", 4.0, 45)
    analysis(api, "r-ravi", "v1", 5.0, 35, person="p-ravi")
    analysis(api, "r-busy", "v1", 1.0, 3, status="NEEDS_REVIEW")  # never counted (golden rule 5)

    owner = overview(api, "owner")
    assert (owner["recordings_analysed"], owner["audio_hours"]) == (3, 1.5)
    assert owner["median_overall_by_type"] == [{"type": "teaching", "median": 4.0, "n": 3}]
    (clarity,) = owner["coaching"]  # concept_clarity, round(score) of each newest analysis: 3, 4, 5
    assert (clarity["dimension_key"], clarity["median"], clarity["n"]) == ("concept_clarity", 4.0, 3)
    assert {s["stage"]: s["n"] for s in owner["in_progress"]} == {"transcribing": 1, "needs_review": 1}

    manager = overview(api, "manager")  # unit-1 only: Ravi's recording is not theirs
    assert (manager["recordings_analysed"], manager["median_overall_by_type"][0]["median"]) == (2, 3.5)
    assert overview(api, "asha")["recordings_analysed"] == 2  # her own


def test_the_overview_period_is_checked(api: Api) -> None:
    assert overview(api, "owner", days=1)["recordings_analysed"] == 0  # an empty period is not an error
    end = utc_now()
    bad = [{"from": end.isoformat(), "to": (end - timedelta(days=1)).isoformat()},
           {"from": (end - timedelta(days=400)).isoformat(), "to": end.isoformat()}]  # fmt: skip
    for params in bad:
        assert api.get("owner", f"/v1/overview?{urlencode(params)}").status_code == 400


# --- Reviews (ADR 0007) ---


def in_review(api: Api, rid: str, reason: str = "unclear_roles", person: str = "p-asha", unit: str = "unit-1") -> None:
    """A recording waiting for review, with a two-speaker transcript where Sabha guessed S0 is the teacher."""
    recording(api, rid, person, unit, 5, RecordingStatus.NEEDS_REVIEW)
    api.db.recordings.update_one({"_id": rid}, {"$set": {"status_reason": reason}})
    key = f"{T}/{rid}/transcribe@v1/transcript@v1.json"
    utterances = [
        {"speaker_label": "S0", "role": "teacher", "start_ms": 0, "end_ms": 9_000, "text": "Aaj fractions padhenge."},
        {"speaker_label": "S1", "role": "students", "start_ms": 9_500, "end_ms": 21_000, "text": "Ma'am, " * 60},
        {"speaker_label": "S0", "role": "teacher", "start_ms": 22_000, "end_ms": 24_000, "text": "Haan, batao."},
    ]  # fmt: skip
    api.s3.put_object(Bucket="sabha-artefacts", Key=key,
                      Body=json.dumps({"version": "transcript@v1", "utterances": utterances}).encode())  # fmt: skip
    insert(api.db, "transcripts", Transcript(
        tenant_id=T, recording_id=rid, version="transcript@v1", storage_key=key, asr_model="sarvam/saaras:v4",
        word_timing="approximate", word_count=40, utterance_count=3, roles={"S0": "teacher", "S1": "students"},
        roles_need_review=True, role_choices=["teacher", "students"], rubric_id="teaching.school.v0.1",
    ))  # fmt: skip


def test_the_review_queue_is_needs_review_only_for_those_who_resolve(api: Api) -> None:
    in_review(api, "r-review")
    in_review(api, "r-ravi", person="p-ravi", unit="unit-2")
    recording(api, "r-done", "p-asha", "unit-1", 3)
    assert ids(api.get("owner", "/v1/reviews")) == ["r-ravi", "r-review"]
    assert ids(api.get("manager", "/v1/reviews")) == ["r-review"]  # their unit only
    (item,) = api.get("manager", "/v1/reviews").json()["items"]
    assert item["status_note"] == "We could not tell the speakers apart reliably."
    assert api.get("asha", "/v1/reviews").status_code == 403  # staff never resolve their own


def test_speakers_show_talk_time_guess_and_samples(api: Api) -> None:
    in_review(api, "r-review")
    body = api.get("manager", "/v1/recordings/r-review/speakers").json()
    assert (body["reason"], body["choices"]) == ("unclear_roles", ["teacher", "students"])
    first, second = body["speakers"]
    assert (first["label"], first["guess"], first["talk_ms"]) == ("S1", "students", 11_500)  # most talk first
    assert second["label"] == "S0" and [s["start_ms"] for s in second["samples"]] == [0, 22_000]  # time order
    assert len(first["samples"][0]["text"]) <= 240 and first["samples"][0]["text"].endswith("…")
    assert api.get("asha", "/v1/recordings/r-review/speakers").status_code == 403


def test_confirming_the_teacher_rebuilds_the_transcript_then_scores(api: Api) -> None:
    in_review(api, "r-review")
    response = api.post("manager", "/v1/recordings/r-review/review", {"action": "confirm_roles", "staff_speaker": "S1"})
    assert response.json() == {"recording_id": "r-review", "status": "TRANSCRIBING"}
    saved = api.db.recordings.find_one({"_id": "r-review"})
    assert saved is not None
    assert (saved["status"], saved["status_reason"]) == ("TRANSCRIBING", "roles_confirmed")
    assert saved["confirmed_roles"] == {"S0": "students", "S1": "teacher"}  # the reviewer overrode the guess
    (event,) = api.db.outbox.find({"payload.recording_id": "r-review"})
    assert event["type"] == "recording.transcribing"  # the relay starts the transcribe stage again
    (entry,) = api.db.audit_log.find({"action": "recording.review"})
    assert (entry["actor_user_id"], entry["meta"]["decision"]) == ("u-manager", "confirm_roles")
    again = api.post("owner", "/v1/recordings/r-review/review", {"action": "confirm_roles", "staff_speaker": "S0"})
    assert (again.status_code, again.json()["code"]) == (409, "not_in_review")


def test_roles_can_be_confirmed_only_for_unclear_roles_and_known_speakers(api: Api) -> None:
    in_review(api, "r-quotes", reason="low_verification")
    wrong = api.post("owner", "/v1/recordings/r-quotes/review", {"action": "confirm_roles", "staff_speaker": "S0"})
    assert (wrong.status_code, wrong.json()["code"]) == (409, "not_a_roles_review")
    in_review(api, "r-roles")
    nobody = api.post("owner", "/v1/recordings/r-roles/review", {"action": "confirm_roles", "staff_speaker": "S9"})
    assert (nobody.status_code, nobody.json()["code"]) == (400, "unknown_speaker")
    assert api.db.recordings.find_one({"_id": "r-roles"})["status"] == "NEEDS_REVIEW"  # type: ignore[index]


def test_closing_needs_a_note_and_says_why_in_plain_words(api: Api) -> None:
    in_review(api, "r-review", reason="no_speech")
    assert api.post("manager", "/v1/recordings/r-review/review", {"action": "close"}).status_code == 400
    closed = api.post("manager", "/v1/recordings/r-review/review", {"action": "close", "note": "Blank recording"})
    assert closed.json()["status"] == "FAILED"
    (item,) = api.get("owner", "/v1/recordings").json()["items"]
    assert item["status_note"] == "A reviewer closed this recording as not usable."
    (entry,) = api.db.audit_log.find({"action": "recording.review"})
    assert entry["meta"] == {"decision": "close", "note": "Blank recording", "review_reason": "no_speech"}


def test_who_may_resolve(api: Api) -> None:
    in_review(api, "r-ravi", person="p-ravi", unit="unit-2")
    body = {"action": "close", "note": "x"}
    assert api.post("manager", "/v1/recordings/r-ravi/review", body).status_code == 404  # not their unit
    in_review(api, "r-asha")
    assert api.post("asha", "/v1/recordings/r-asha/review", body).status_code == 403  # her own: never


# --- Meetings: naming the voices ---


def meeting(api: Api, rid: str) -> None:
    recording(api, rid, "p-asha", "unit-1", 5)
    api.db.recordings.update_one({"_id": rid}, {"$set": {"type": "meeting"}})
    insert(api.db, "transcripts", Transcript(
        tenant_id=T, recording_id=rid, version="transcript@v1", storage_key=f"{T}/{rid}/t.json", asr_model="m",
        word_timing="approximate", word_count=10, utterance_count=3, roles={"S0": "participant", "S1": "participant"},
        role_choices=["participant"], rubric_id="meeting.company.v0.1",
    ))  # fmt: skip


def test_voices_in_a_meeting_can_be_named_and_the_names_come_back_with_the_recording(api: Api) -> None:
    meeting(api, "r-meet")
    response = api.client.put("/v1/recordings/r-meet/voices", json={"names": {"S0": " Riya ", "S1": ""}},
                              headers={"Authorization": f"Bearer {api.idp.token('manager')}"})  # fmt: skip
    assert response.json() == {"recording_id": "r-meet", "voice_names": {"S0": "Riya"}}  # empty removes; trimmed
    assert api.get("owner", "/v1/recordings/r-meet").json()["voice_names"] == {"S0": "Riya"}
    (entry,) = api.db.audit_log.find({"action": "recording.voices"})
    assert entry["meta"] == {"voices": ["S0"]}


def test_only_meeting_voices_that_spoke_can_be_named(api: Api) -> None:
    meeting(api, "r-meet")
    headers = {"Authorization": f"Bearer {api.idp.token('owner')}"}
    ghost = api.client.put("/v1/recordings/r-meet/voices", json={"names": {"S7": "Nobody"}}, headers=headers)
    assert (ghost.status_code, ghost.json()["code"]) == (400, "unknown_voice")
    recording(api, "r-lesson", "p-asha", "unit-1", 5)
    lesson = api.client.put("/v1/recordings/r-lesson/voices", json={"names": {"S0": "Asha"}}, headers=headers)
    assert (lesson.status_code, lesson.json()["code"]) == (409, "not_a_meeting")  # students are never named


# --- Transcript and analysis ---


def test_the_transcript_comes_with_a_playback_url_and_is_audited(api: Api) -> None:
    recording(api, "r-asha", "p-asha", "unit-1", 5)
    key = f"{T}/r-asha/transcribe@v1/transcript@v1.json"
    api.s3.put_object(Bucket="sabha-artefacts", Key=key, Body=b'{"version": "transcript@v1", "utterances": []}')
    doc = Transcript(
        tenant_id=T, recording_id="r-asha", version="transcript@v1", storage_key=key, asr_model="sarvam/saaras:v4",
        word_timing="approximate", word_count=0, utterance_count=0, roles={"S0": "teacher"},
        language_mix={"hi-IN": 1.0}, rubric_id="teaching.school.v0.1",
    )  # fmt: skip
    insert(api.db, "transcripts", doc)
    response = api.get("asha", "/v1/recordings/r-asha/transcript")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transcript"]["version"] == "transcript@v1" and body["roles"] == {"S0": "teacher"}
    url = body["playback_url"].replace("%40", "@")
    assert f"{T}/r-asha/preprocess@v1/playback.opus" in url and "X-Amz-Expires=900" in url
    (entry,) = api.db.audit_log.find({"action": "recording.play"})
    assert (entry["actor_user_id"], entry["target_id"]) == ("u-asha", "r-asha")


def test_no_transcript_yet_is_404_and_the_analysis_says_processing(api: Api) -> None:
    recording(api, "r-busy", "p-asha", "unit-1", 1, status=RecordingStatus.TRANSCRIBING)
    assert api.get("owner", "/v1/recordings/r-busy/transcript").json()["code"] == "not_found"
    assert api.get("owner", "/v1/recordings/r-busy/analysis").json()["status"] == "processing"
    assert api.get("owner", "/v1/recordings/r-busy").json()["status"] == "TRANSCRIBING"


def test_the_report_payload_for_a_completed_lesson(api: Api) -> None:
    recording(api, "r-old", "p-asha", "unit-1", 60)
    analysis(api, "r-old", "v1", 2.9, 50)
    recording(api, "r-asha", "p-asha", "unit-1", 30)
    analysis(api, "r-asha", "v1", 3.1, 20)
    newest = analysis(api, "r-asha", "v2", 3.6, 10)  # a re-analysis: the latest one is shown
    body = api.get("manager", "/v1/recordings/r-asha/analysis").json()

    assert (body["status"], body["reasons"], body["analysis_id"]) == ("completed", [], newest)
    assert body["overall"] == 3.6 and body["rubric"] == {"id": "teaching.school.v0.1", "version": "0.1",
                                                         "name": "Teaching"}  # fmt: skip
    assert body["model"] == {"ids": ["openai:o3-mini"], "prompt_hash": "abc"}
    assert body["person_history"] == {"count": 1, "min": 2.9, "max": 2.9}  # her other lesson, real data only
    assert body["comparison"] is None
    metrics = {m["key"]: m for m in body["metrics"]}
    assert metrics["teacher_talk_share"]["name"] == "Teacher talk time"  # the tenant's word for a teacher
    assert (metrics["longest_monologue_s"]["unit"], metrics["longest_monologue_s"]["value"]) == ("ms", 95_500)
    assert metrics["words_per_minute"]["unit"] == "wpm"
    assert body["dimensions"][0]["evidence"][0] == DIMENSIONS[0]["evidence"][0]
    assert body["suggestions"] == [{"text": "Ask a student to explain.", "utterance_id": "u0001", "start_ms": 9_000}]
    assert body["phases"] == [{"name": "introduction", "start_ms": 0, "end_ms": 8_000}]
    (entry,) = api.db.audit_log.find({"action": "analysis.view"})
    assert entry["meta"]["analysis_id"] == newest
    history = api.get("manager", "/v1/recordings/r-asha/analyses").json()
    assert [h["version"] for h in history] == ["v2", "v1"]


def test_unverified_dimensions_show_nothing_but_their_name(api: Api) -> None:
    tampered = {**DIMENSIONS[1], "verified": False, "score": 5, "rationale": "should never be shown"}
    not_applicable = {"key": "escalation", "name": "Escalation", "weight": 0.2, "verified": True, "score": None,
                      "not_applicable": True, "rationale": "Nothing to escalate.", "attempts": 1,
                      "failure_reasons": [], "evidence": DIMENSIONS[0]["evidence"]}  # fmt: skip
    recording(api, "r-asha", "p-asha", "unit-1", 30)
    analysis(api, "r-asha", "v1", 4.0, 20, dimensions=[DIMENSIONS[0], tampered, not_applicable])
    body = api.get("owner", "/v1/recordings/r-asha/analysis").json()
    assert body["status"] == "partial" and body["reasons"][0]["code"] == "unverified_dimensions"
    assert body["dimensions"][1] == {"key": "recap_and_closure", "name": "Recap and closure", "weight": 0.4,
                                     "verified": False}  # fmt: skip
    assert "should never be shown" not in json.dumps(body)
    assert body["dimensions"][2]["not_applicable"] is True and body["dimensions"][2]["score"] is None


@pytest.mark.parametrize(
    ("status", "reason", "expected"),
    [
        (RecordingStatus.TRANSCRIBING, None, {"status": "processing", "stage": "transcribing"}),
        (RecordingStatus.FAILED, "invalid_audio", {"status": "failed"}),
        (RecordingStatus.NEEDS_REVIEW, "unclear_roles", {"status": "needs_review"}),
    ],
)
def test_the_report_payload_before_there_is_a_report(api: Api, status: RecordingStatus, reason: str | None,
                                                     expected: dict[str, str]) -> None:  # fmt: skip
    recording(api, "r-x", "p-asha", "unit-1", 5, status=status)
    api.db.recordings.update_one({"_id": "r-x"}, {"$set": {"status_reason": reason}})
    body = api.get("owner", "/v1/recordings/r-x/analysis").json()
    assert body == {**body, **expected} and body["recording_id"] == "r-x"
    if reason:
        assert body["reasons"][0]["code"] == reason and body["reasons"][0]["message"]
    assert api.db.audit_log.count_documents({"action": "analysis.view"}) == 0


def test_the_recording_detail_has_what_the_report_header_needs(api: Api) -> None:
    recording(api, "r-asha", "p-asha", "unit-1", 30)
    api.db.recordings.update_one({"_id": "r-asha"}, {"$set": {"duration_ms": 70_000}})
    segments = [{"orig_start_ms": 1_000, "orig_end_ms": 31_000, "compact_start_ms": 0},
                {"orig_start_ms": 40_000, "orig_end_ms": 65_000, "compact_start_ms": 30_000}]  # fmt: skip
    api.s3.put_object(Bucket="sabha-artefacts", Key=f"{T}/r-asha/preprocess@v1/segments@v1.json",
                      Body=json.dumps(segments).encode())  # fmt: skip
    doc = Transcript(
        tenant_id=T, recording_id="r-asha", version="transcript@v1", storage_key="k", asr_model="m",
        word_timing="approximate", word_count=0, utterance_count=0, language_mix={"hi-IN": 0.7, "en-IN": 0.3},
        rubric_id="teaching.school.v0.1",
    )  # fmt: skip
    insert(api.db, "transcripts", doc)
    body = api.get("asha", "/v1/recordings/r-asha").json()
    assert (body["title"], body["type_label"], body["unit_name"]) == ("r-asha", "Teaching", "unit-1")
    assert body["speech_ms"] == 55_000 and body["languages"] == ["English", "Hindi"]
    assert body["removed_silence"] == [{"start_ms": 0, "end_ms": 1_000}, {"start_ms": 31_000, "end_ms": 40_000},
                                       {"start_ms": 65_000, "end_ms": 70_000}]  # fmt: skip


# --- Trends ---


def test_a_trend_of_the_overall_score_and_of_one_dimension(api: Api) -> None:
    for i, score in enumerate([2.9, 3.4, 3.8]):
        recording(api, f"r{i}", "p-asha", "unit-1", 100 - i)
        analysis(api, f"r{i}", "v1", score, 90 - i * 10)
    overall = api.get("asha", "/v1/people/p-asha/trend").json()
    assert overall["dimension"] is None and [p["score"] for p in overall["points"]] == [2.9, 3.4, 3.8]  # oldest first
    one = api.get("manager", "/v1/people/p-asha/trend?dimension=concept_clarity&limit=2").json()
    assert [p["score"] for p in one["points"]] == [3, 4]  # the latest two, oldest first
    assert api.get("asha", "/v1/people/p-ravi/trend").json()["code"] == "not_found"  # not her


def test_people_lists_whom_each_caller_may_upload_for(api: Api) -> None:
    def names(sub: str) -> list[str]:
        response = api.get(sub, "/v1/people")
        assert response.status_code == 200, response.text
        return [p["name"] for p in response.json()]

    assert names("owner") == ["Asha", "Ravi"]
    assert names("manager") == ["Asha"]  # unit-1 only
    assert names("asha") == ["Asha"]  # staff upload only for themselves
    assert names("nobody") == []


@pytest.mark.parametrize(
    ("file_name", "title"),
    [
        ("Class 7B.mp3", "Class 7B"),
        ("Fractions, 13 Oct.final.m4a", "Fractions, 13 Oct.final"),
        ("no extension", "no extension"),
        (".mp3", ".mp3"),
        ("Talk by Dr. A. Rao", "Talk by Dr. A. Rao"),  # " Rao" is not an extension
        (None, "r-1"),
    ],
)
def test_the_title_is_the_file_name_without_its_extension(file_name: str | None, title: str) -> None:
    assert recording_title(file_name, "r-1") == title


@pytest.mark.parametrize(
    ("key", "person", "name"),
    [
        ("teacher_talk_share", "Faculty member", "Faculty member talk time"),
        ("students_talk_share", "Teacher", "Student talk time"),
        ("teacher_question_count", "Teacher", "Questions asked by teacher"),
        ("receptionist_talk_share", "Receptionist", "Receptionist talk time"),
        ("caller_talk_share", "Receptionist", "Caller talk time"),
        ("visitor_talk_share", "Sales rep", "Visitor talk time"),
        ("receptionist_talk_share", "Sales rep", "Sales rep talk time"),  # the tenant's word for its staff
        ("longest_silence_s", "Teacher", "Longest silence"),
        ("longest_monologue_s", "Teacher", "Longest uninterrupted talk"),
        ("words_per_minute", "Teacher", "Speaking pace"),
        ("new_thing_ms", "Teacher", "New thing"),  # a metric added later: its key without the unit
    ],
)
def test_metric_names_are_plain_words(key: str, person: str, name: str) -> None:
    assert metric_name(key, person) == name


@pytest.mark.parametrize(
    ("text", "clean"),
    [
        ("At utterance u0000, try pausing longer.", "Try pausing longer."),
        ("In utterance u0003 the analogy works well.", "The analogy works well."),
        ("Ask three students before the worksheet.", "Ask three students before the worksheet."),
    ],
)
def test_old_reports_lose_utterance_ids(text: str, clean: str) -> None:
    assert without_ids(text) == clean


def test_a_ticket_is_shown_only_with_its_verified_quotes() -> None:
    quote = {"quote": "mujhe Mr. Mehta se milna hai", "utterance_id": "u0000", "start_ms": 0, "end_ms": 3_000}
    ticket = {"category": "appointment_or_meeting", "status": "resolved", "follow_up": None,
              "summary": "A visitor came for a meeting and was handed over.",
              "evidence": {"need": quote, "outcome": quote}}  # fmt: skip
    assert shown_ticket(ticket) == ticket
    old = {k: v for k, v in ticket.items() if k != "evidence"}  # stored before quotes were asked for
    assert shown_ticket(old) is None
    assert shown_ticket(None) is None
