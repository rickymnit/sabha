"""Reading recordings and results (P5.7b): who sees what in the list, paging, transcript and analysis with their
audit entries, history and trends. The permission matrix (tests/security) covers every route for every caller."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

import httpx
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.database import Database

from sabha_api.resources import open_resources
from sabha_core.indexes import ensure_indexes
from sabha_core.models import (
    Analysis,
    IdentityLink,
    Person,
    Recording,
    Role,
    Score,
    Tenant,
    Transcript,
    Unit,
    User,
    utc_now,
)  # fmt: skip
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
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
    {"key": "teacher_words_per_minute", "value": 120, "unit": "words_per_minute", "definition": "Speaking pace."},
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
    assert item["status"] == "COMPLETED"


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
    assert metrics["teacher_talk_share"]["name"] == "Teacher talk share"  # the tenant's word for a teacher
    assert (metrics["longest_monologue_s"]["unit"], metrics["longest_monologue_s"]["value"]) == ("ms", 95_500)
    assert metrics["teacher_words_per_minute"]["unit"] == "wpm"
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
    assert (body["title"], body["type_label"], body["unit_name"]) == ("r-asha.mp3", "Teaching", "unit-1")
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
