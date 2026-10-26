"""Disputes (P6.7, owner's decisions 2026-10-26): raising one, the reviewer's queue and the decision.

- Raise: the person analysed, the managers of their unit, owners and admins; one open dispute per score; meetings
  (nobody analysed) by managers, owners and admins only.
- Resolve: reviewers and managers for their units, owners and admins for all, never a dispute you raised yourself.
- Accepted: the reviewer's score replaces the AI's in the report, the overall score and the trend; the AI score is
  kept as history. Every decision is audited, kept as a calibration record and starts the notification.

The permission matrix (tests/security) covers every route for every caller; these tests cover the rules.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.database import Database

from sabha_api.resources import open_resources
from sabha_core.indexes import ensure_indexes
from sabha_core.models import Analysis, IdentityLink, Person, Recording, Role, Score, Tenant, Unit, User
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.repo import COLLECTIONS
from sabha_core.state import RecordingStatus

pytestmark = pytest.mark.integration
T = "tenant-a"
USERS = {  # subject -> (user id, role, units)
    "owner": ("u-owner", Role.OWNER, []),
    "manager": ("u-manager", Role.MANAGER, ["unit-1"]),
    "manager2": ("u-manager2", Role.MANAGER, ["unit-1"]),
    "other_manager": ("u-other-manager", Role.MANAGER, ["unit-2"]),
    "reviewer": ("u-reviewer", Role.REVIEWER, ["unit-1"]),
    "asha": ("u-asha", Role.STAFF, ["unit-1"]),
    "bina": ("u-bina", Role.STAFF, ["unit-1"]),
}
COMMENT = "Both terms were defined and checked with the class."
NOTE = "The quotes show both terms defined."


@dataclass
class Api:
    client: TestClient
    db: Database[dict[str, Any]]
    idp: Any
    s3: Any

    def get(self, sub: str, path: str) -> httpx.Response:
        return self.client.get(path, headers={"Authorization": f"Bearer {self.idp.token(sub)}"})

    def post(self, sub: str, path: str, body: dict[str, Any], *, key: str | None = None) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.idp.token(sub)}"}
        if key is not None:
            headers["Idempotency-Key"] = key
        return self.client.post(path, json=body, headers=headers)

    def dispute(self, sub: str, analysis_id: str, **change: Any) -> httpx.Response:
        body = {"dimension_key": "concept_clarity", "proposed_score": 5, "comment": COMMENT, **change}
        return self.post(sub, f"/v1/analyses/{analysis_id}/disputes", body, key=uuid.uuid4().hex)

    def resolve(self, sub: str, dispute_id: str, **body: Any) -> httpx.Response:
        return self.post(sub, f"/v1/disputes/{dispute_id}/resolve", body)


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"disp_{uuid.uuid4().hex[:12]}"
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
        insert(db, "units", Unit(id=unit, tenant_id=T, name=f"Class {unit[-1]}"))
    for sub, (user_id, role, units) in USERS.items():
        insert(db, "users", User(id=user_id, tenant_id=T, email=f"{sub}@example.com", name=sub, role=role,
                                 unit_ids=units, status="active"))  # fmt: skip
        insert(db, "identities", IdentityLink(tenant_id=T, issuer=issuer, subject=sub, email=f"{sub}@example.com",
                                              user_id=user_id))  # fmt: skip
    insert(db, "people", Person(id="p-asha", tenant_id=T, name="Asha", unit_id="unit-1", user_id="u-asha"))
    insert(db, "people", Person(id="p-bina", tenant_id=T, name="Bina", unit_id="unit-1", user_id="u-bina"))
    return Api(client, db, fake_idp, s3_storage.client())


EVIDENCE = [{"quote": "Chlorophyll leaf ka green pigment hai", "utterance_id": "u0003", "start_ms": 34_000,
             "end_ms": 40_000}]  # fmt: skip
DIMENSIONS: list[dict[str, Any]] = [
    {"key": "concept_clarity", "name": "Concept clarity", "weight": 0.6, "verified": True, "score": 4,
     "rationale": "Defines terms plainly.", "attempts": 1, "failure_reasons": [], "evidence": EVIDENCE},
    {"key": "recap_and_closure", "name": "Recap and closure", "weight": 0.4, "verified": True, "score": 3,
     "rationale": "Lists what was covered.", "attempts": 1, "failure_reasons": [],
     "evidence": [{"quote": "aaj humne dono padhe", "utterance_id": "u0004", "start_ms": 500_000, "end_ms": 510_000}]},
    {"key": "checks_for_understanding", "name": "Checks for understanding", "weight": 0.0, "verified": False,
     "score": None, "rationale": None, "attempts": 2, "failure_reasons": ["quote_not_found"], "evidence": []},
]  # fmt: skip


def scored(api: Api, *, person: str | None = "p-asha", kind: ConversationType = ConversationType.TEACHING,
           created_by: str = "u-asha") -> str:  # fmt: skip
    """A finished recording with an analysis: concept clarity 4 (weight 0.6), recap 3 (0.4), one unverified."""
    rid = f"r-{uuid.uuid4().hex[:8]}"
    aid = f"an-{rid}"
    insert(api.db, "recordings", Recording(id=rid, tenant_id=T, type=kind, status=RecordingStatus.COMPLETED,
                                           consent_ref="c", person_id=person, unit_id="unit-1", file_name=f"{rid}.mp3",
                                           created_by=created_by))  # fmt: skip
    key = f"{T}/{rid}/analyze@v1/analysis@v1.json"
    report = {"version": "analysis@v1", "overall": {"score": 3.6}, "dimensions": DIMENSIONS, "metrics": [],
              "synthesis": {"summary": "A clear lesson.", "strengths": [], "gaps": [], "suggestions": []}}  # fmt: skip
    api.s3.put_object(Bucket="sabha-artefacts", Key=key, Body=json.dumps(report).encode())
    rubric = "teaching.school.v0.1" if kind is ConversationType.TEACHING else "meeting.company.v0.1"
    insert(api.db, "analyses", Analysis(id=aid, tenant_id=T, recording_id=rid, version="v1", person_id=person,
                                        unit_id="unit-1", conversation_type=kind, rubric_id=rubric,
                                        rubric_version="0.1", rubric_hash="h", report_key=key, status="COMPLETED",
                                        overall_score=3.6, verified_share=1.0))  # fmt: skip
    for d in DIMENSIONS:
        insert(api.db, "scores", Score(tenant_id=T, analysis_id=aid, recording_id=rid, person_id=person,
                                       dimension=d["key"], name=d["name"], weight=d["weight"], score=d["score"],
                                       verified=d["verified"], evidence=d["evidence"]))  # fmt: skip
    return aid


def body(response: httpx.Response, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status, response.text
    out: dict[str, Any] = response.json()
    return out


def one(api: Api, collection: str, query: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] | None = api.db[collection].find_one(query)
    assert found is not None, f"no {collection} document matches {query}"
    return found


def code(response: httpx.Response) -> str:
    return str(response.json().get("code"))


def report_of(api: Api, sub: str, analysis_id: str) -> dict[str, Any]:
    rid = analysis_id.removeprefix("an-")
    return body(api.get(sub, f"/v1/recordings/{rid}/analysis"))


# --- Raising a dispute ---


def test_the_person_analysed_disputes_her_own_score(api: Api) -> None:
    aid = scored(api)
    dispute = body(api.dispute("asha", aid), 201)
    assert dispute["status"] == "open"
    assert (dispute["dimension_key"], dispute["ai_score"], dispute["proposed_score"]) == ("concept_clarity", 4, 5)
    assert dispute["comment"] == COMMENT
    entry = api.db.audit_log.find_one({"action": "dispute.create"})
    assert entry is not None and entry["target_id"] == dispute["id"] and entry["actor_user_id"] == "u-asha"
    assert one(api, "disputes", {"_id": dispute["id"]})["tenant_id"] == T


def test_a_replayed_create_returns_the_same_dispute(api: Api) -> None:
    aid = scored(api)
    path, payload = f"/v1/analyses/{aid}/disputes", {"dimension_key": "concept_clarity", "proposed_score": 5,
                                                     "comment": COMMENT}  # fmt: skip
    first = body(api.post("asha", path, payload, key="k-1"), 201)
    again = body(api.post("asha", path, payload, key="k-1"), 201)
    assert again["id"] == first["id"] and api.db.disputes.count_documents({}) == 1


def test_one_open_dispute_per_score(api: Api) -> None:
    aid = scored(api)
    body(api.dispute("asha", aid), 201)
    second = api.dispute("manager", aid, proposed_score=3)
    assert second.status_code == 409 and code(second) == "dispute_open"
    body(api.dispute("manager", aid, dimension_key="recap_and_closure", proposed_score=4), 201)  # another score


@pytest.mark.parametrize(
    ("change", "status", "error"),
    [
        ({"dimension_key": "pacing"}, 400, "not_disputable"),  # not in this analysis
        ({"dimension_key": "checks_for_understanding"}, 400, "not_disputable"),  # unverified: never shown
        ({"proposed_score": 4}, 400, "same_score"),  # what it already is
        ({"proposed_score": 6}, 422, "validation_error"),
        ({"comment": "too short"}, 422, "validation_error"),
    ],
)
def test_a_dispute_must_be_about_a_shown_score_and_say_why(api: Api, change: dict[str, Any], status: int,
                                                           error: str) -> None:  # fmt: skip
    response = api.dispute("asha", scored(api), **change)
    assert response.status_code == status and code(response) == error, response.text


def test_reviewers_and_colleagues_do_not_raise_disputes(api: Api) -> None:
    aid = scored(api)
    assert api.dispute("reviewer", aid).status_code == 403
    assert api.dispute("bina", aid).status_code == 404  # not hers: she cannot see it
    assert api.dispute("other_manager", aid).status_code == 404


def test_a_meeting_is_disputed_by_managers_not_by_staff(api: Api) -> None:
    aid = scored(api, kind=ConversationType.MEETING)
    assert api.dispute("asha", aid).status_code == 403  # nobody is analysed in a meeting
    body(api.dispute("manager", aid), 201)


# --- The queue ---


def test_the_queue_shows_open_disputes_of_the_callers_units(api: Api) -> None:
    dispute = body(api.dispute("asha", scored(api)), 201)
    items = body(api.get("reviewer", "/v1/disputes"))["items"]
    assert [i["id"] for i in items] == [dispute["id"]]
    item = items[0]
    assert item["kind"] == "dispute" and item["person_name"] == "Asha" and item["unit"] == "Class 1"
    assert (item["dimension_name"], item["ai_score"], item["proposed_score"]) == ("Concept clarity", 4, 5)
    assert item["evidence"] == [{"quote": "Chlorophyll leaf ka green pigment hai", "start_ms": 34_000}]
    assert body(api.get("other_manager", "/v1/disputes"))["items"] == []
    assert api.get("asha", "/v1/disputes").status_code == 403
    assert body(api.get("owner", "/v1/disputes?status=accepted"))["items"] == []


# --- Resolving ---


def test_an_accepted_dispute_changes_the_score_the_overall_and_the_trend(api: Api) -> None:
    aid = scored(api)
    dispute = body(api.dispute("asha", aid, proposed_score=2), 201)
    done = body(api.resolve("reviewer", dispute["id"], decision="accepted", final_score=2, note=NOTE))
    assert done["status"] == "accepted" and done["final_score"] == 2

    report = report_of(api, "asha", aid)
    clarity = next(d for d in report["dimensions"] if d["key"] == "concept_clarity")
    assert clarity["score"] == 4  # the AI score stays, as history
    assert clarity["override"]["score"] == 2 and clarity["override"]["reviewer_role"] == "reviewer"
    assert clarity["override"]["note"] == NOTE and clarity["override"]["resolved_at"]
    assert report["overall"] == 2.4  # 0.6 * 2 + 0.4 * 3, with the reviewer's score

    analysis = one(api, "analyses", {"_id": aid})
    assert (analysis["overall_score"], analysis["ai_overall_score"]) == (2.4, 3.6)
    score = one(api, "scores", {"analysis_id": aid, "dimension": "concept_clarity"})
    assert (score["score"], score["human_score"]) == (4, 2)
    overall = body(api.get("manager", "/v1/people/p-asha/trend"))["points"]
    assert [p["score"] for p in overall if p["analysis_id"] == aid] == [2.4]
    clarity_trend = body(api.get("manager", "/v1/people/p-asha/trend?dimension=concept_clarity"))["points"]
    assert [p["score"] for p in clarity_trend if p["analysis_id"] == aid] == [2]


def test_every_decision_is_audited_kept_for_calibration_and_announced(api: Api) -> None:
    aid = scored(api)
    dispute = body(api.dispute("asha", aid), 201)
    body(api.resolve("manager", dispute["id"], decision="rejected", note=NOTE))
    stored = one(api, "disputes", {"_id": dispute["id"]})
    assert stored["status"] == "rejected" and stored["resolved_by"] == "u-manager"
    # A calibration record: a person's score next to the AI's (the AI's when the dispute is rejected).
    assert stored["calibration"] == {"source": "dispute", "rubric_id": "teaching.school.v0.1",
                                     "rubric_version": "0.1", "dimension": "concept_clarity", "ai_score": 4,
                                     "human_score": 4}  # fmt: skip
    entry = api.db.audit_log.find_one({"action": "dispute.resolve"})
    assert entry is not None and entry["meta"]["decision"] == "rejected"
    event = api.db.outbox.find_one({"type": "dispute.resolved"})
    assert event is not None and event["payload"]["dispute_id"] == dispute["id"]
    assert one(api, "analyses", {"_id": aid})["overall_score"] == 3.6  # unchanged


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"decision": "accepted", "note": NOTE}, "final_score_required"),
        ({"decision": "accepted", "final_score": 4, "note": NOTE}, "same_score"),  # that is a rejection
    ],
)
def test_an_acceptance_needs_a_new_final_score(api: Api, payload: dict[str, Any], error: str) -> None:
    dispute = body(api.dispute("asha", scored(api)), 201)
    response = api.resolve("reviewer", dispute["id"], **payload)
    assert response.status_code == 400 and code(response) == error


def test_a_note_is_required(api: Api) -> None:
    dispute = body(api.dispute("asha", scored(api)), 201)
    assert api.resolve("reviewer", dispute["id"], decision="rejected", note="").status_code == 422


def test_a_dispute_is_decided_once(api: Api) -> None:
    dispute = body(api.dispute("asha", scored(api)), 201)
    body(api.resolve("reviewer", dispute["id"], decision="rejected", note=NOTE))
    again = api.resolve("owner", dispute["id"], decision="accepted", final_score=5, note=NOTE)
    assert again.status_code == 409 and code(again) == "dispute_closed"


def test_nobody_decides_a_dispute_they_raised(api: Api) -> None:
    dispute = body(api.dispute("manager", scored(api)), 201)
    own = api.resolve("manager", dispute["id"], decision="accepted", final_score=5, note=NOTE)
    assert own.status_code == 403 and code(own) == "own_dispute"
    body(api.resolve("manager2", dispute["id"], decision="accepted", final_score=5, note=NOTE))


def test_after_an_accepted_dispute_the_next_one_starts_from_the_reviewers_score(api: Api) -> None:
    aid = scored(api)
    first = body(api.dispute("asha", aid, proposed_score=5), 201)
    body(api.resolve("reviewer", first["id"], decision="accepted", final_score=5, note=NOTE))
    assert code(api.dispute("asha", aid, proposed_score=5)) == "same_score"  # 5 is what is shown now
    second = body(api.dispute("manager", aid, proposed_score=3), 201)
    assert second["current_score"] == 5 and second["ai_score"] == 4


# --- What the report tells the viewer ---


def test_the_report_says_who_may_dispute_and_which_scores_are_open(api: Api) -> None:
    aid = scored(api)
    assert report_of(api, "asha", aid)["can_dispute"] is True
    assert report_of(api, "manager", aid)["can_dispute"] is True
    assert report_of(api, "reviewer", aid)["can_dispute"] is False
    body(api.dispute("asha", aid), 201)
    dims = {d["key"]: d for d in report_of(api, "asha", aid)["dimensions"]}
    assert dims["concept_clarity"]["dispute_open"] is True and dims["recap_and_closure"]["dispute_open"] is False
