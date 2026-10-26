"""Re-analysis (P2.8, owner's decisions 2026-10-26): scoring a finished recording again from its transcript.

- Owners and admins only. COMPLETED -> ANALYZING with the next analysis run; the transcript is reused (no speech
  recognition), so no audio is metered again and no email is sent when it finishes (the worker's side).
- Open disputes on the old version are closed ("Re-analysed"); reviewers' scores stay with the old version.
- Every version stays readable; trends, the overview and the people page count only the latest.
- Bulk: every finished recording of a type scored with another rubric than the current one, counted first, at most
  100 per request.

The permission matrix (tests/security) covers both routes for every caller.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.database import Database

from sabha_api.resources import open_resources
from sabha_core.indexes import ensure_indexes
from sabha_core.models import (
    Analysis,
    Dispute,
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
CURRENT = "teaching.school.v0.1"  # the school profile's teaching rubric
USERS = {  # subject -> (user id, role, units)
    "owner": ("u-owner", Role.OWNER, []),
    "admin": ("u-admin", Role.ADMIN, []),
    "manager": ("u-manager", Role.MANAGER, ["unit-1"]),
    "asha": ("u-asha", Role.STAFF, ["unit-1"]),
}
REASON = "The rubric was updated after the review."


@dataclass
class Api:
    client: TestClient
    db: Database[dict[str, Any]]
    idp: Any
    s3: Any

    def headers(self, sub: str, key: str | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.idp.token(sub)}", "Idempotency-Key": key or uuid.uuid4().hex}

    def get(self, sub: str, path: str) -> httpx.Response:
        return self.client.get(path, headers={"Authorization": f"Bearer {self.idp.token(sub)}"})

    def reanalyze(self, sub: str, rid: str, key: str | None = None, **body: Any) -> httpx.Response:
        payload = {"reason": REASON, **body}
        return self.client.post(f"/v1/recordings/{rid}/reanalyze", json=payload, headers=self.headers(sub, key))

    def bulk(self, sub: str, **body: Any) -> httpx.Response:
        payload = {"type": "teaching", "reason": REASON, **body}
        return self.client.post("/v1/reanalysis", json=payload, headers=self.headers(sub))


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"rean_{uuid.uuid4().hex[:12]}"
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
    insert(db, "units", Unit(id="unit-1", tenant_id=T, name="Class 1"))
    for sub, (user_id, role, units) in USERS.items():
        insert(db, "users", User(id=user_id, tenant_id=T, email=f"{sub}@example.com", name=sub, role=role,
                                 unit_ids=units, status="active"))  # fmt: skip
        insert(db, "identities", IdentityLink(tenant_id=T, issuer=issuer, subject=sub, email=f"{sub}@example.com",
                                              user_id=user_id))  # fmt: skip
    insert(db, "people", Person(id="p-asha", tenant_id=T, name="Asha", unit_id="unit-1", user_id="u-asha"))
    return Api(client, db, fake_idp, s3_storage.client())


def finished(
    api: Api,
    *,
    rubric: str = CURRENT,
    score: float = 3.6,
    status: RecordingStatus = RecordingStatus.COMPLETED,
    minutes_ago: int = 10,
) -> tuple[str, str]:
    """A finished lesson of Asha's with its transcript and one analysis (run 1); returns (recording, analysis)."""
    rid = f"r-{uuid.uuid4().hex[:8]}"
    when = utc_now() - timedelta(minutes=minutes_ago)
    insert(api.db, "recordings", Recording(id=rid, tenant_id=T, type=ConversationType.TEACHING, status=status,
                                           consent_ref="c", person_id="p-asha", unit_id="unit-1",
                                           file_name=f"{rid}.mp3", created_at=when))  # fmt: skip
    insert(api.db, "transcripts", Transcript(tenant_id=T, recording_id=rid, version="transcript@v1",
                                             storage_key=f"{T}/{rid}/transcribe@v1/transcript@v1.json",
                                             asr_model="fake", word_timing="approximate", word_count=0,
                                             utterance_count=0, roles={"S0": "teacher"}, rubric_id=rubric))  # fmt: skip
    aid = add_analysis(api, rid, version="v1", rubric=rubric, score=score, created_at=when)
    return rid, aid


def add_analysis(api: Api, rid: str, *, version: str, rubric: str = CURRENT, score: float = 3.6,
                 superseded: bool = False, created_at: Any = None) -> str:  # fmt: skip
    key = f"{T}/{rid}/analyze@{version}/analysis@v1.json"
    report = {"version": "analysis@v1", "overall": {"score": score}, "metrics": [],
              "dimensions": [{"key": "concept_clarity", "name": "Concept clarity", "weight": 1.0, "verified": True,
                              "score": round(score), "rationale": "Plain words.", "attempts": 1,
                              "failure_reasons": [], "evidence": [{"quote": "Chlorophyll leaf ka green pigment hai",
                              "utterance_id": "u0003", "start_ms": 34_000, "end_ms": 40_000}]}],
              "synthesis": {"summary": f"Version {version}.", "strengths": [], "gaps": [],
                            "suggestions": []}}  # fmt: skip
    api.s3.put_object(Bucket="sabha-artefacts", Key=key, Body=json.dumps(report).encode())
    analysis = Analysis(tenant_id=T, recording_id=rid, version=version, person_id="p-asha", unit_id="unit-1",
                        conversation_type=ConversationType.TEACHING, rubric_id=rubric, rubric_version=rubric[-3:],
                        rubric_hash="h", report_key=key, status="COMPLETED", overall_score=score, verified_share=1.0,
                        superseded=superseded, created_at=created_at or utc_now())  # fmt: skip
    insert(api.db, "analyses", analysis)
    insert(api.db, "scores", Score(tenant_id=T, analysis_id=analysis.id, recording_id=rid, person_id="p-asha",
                                   dimension="concept_clarity", name="Concept clarity", weight=1.0,
                                   score=round(score), verified=True, superseded=superseded,
                                   created_at=analysis.created_at))  # fmt: skip
    return analysis.id


def body(response: httpx.Response, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status, response.text
    out: dict[str, Any] = response.json()
    return out


def one(api: Api, collection: str, query: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] | None = api.db[collection].find_one(query)
    assert found is not None, f"no {collection} document matches {query}"
    return found


# --- One recording ---


def test_an_owner_reanalyses_a_finished_recording_from_its_transcript(api: Api) -> None:
    rid, _ = finished(api)
    out = body(api.reanalyze("owner", rid))
    assert (out["recording_id"], out["status"], out["analysis_run"]) == (rid, "ANALYZING", 2)
    recording = one(api, "recordings", {"_id": rid})
    assert (recording["status"], recording["analysis_run"]) == ("ANALYZING", 2)
    # The analyze stage starts again; the transcript is reused (no transcribe or preprocess event).
    events = [e["type"] for e in api.db.outbox.find({"payload.recording_id": rid})]
    assert events == ["recording.analyzing"]
    assert one(api, "outbox", {"type": "recording.analyzing"})["payload"]["meta"]["reanalysis"] is True
    entry = one(api, "audit_log", {"action": "recording.reanalyze"})
    assert entry["target_id"] == rid and entry["meta"]["reason"] == REASON and entry["meta"]["analysis_run"] == 2


def test_a_replayed_request_starts_one_run(api: Api) -> None:
    rid, _ = finished(api)
    first = body(api.reanalyze("admin", rid, key="same-key"))
    again = body(api.reanalyze("admin", rid, key="same-key"))
    assert first == again and one(api, "recordings", {"_id": rid})["analysis_run"] == 2


def test_another_rubric_version_of_the_same_type_can_be_chosen(api: Api) -> None:
    rid, _ = finished(api)
    body(api.reanalyze("owner", rid, rubric_id="teaching.school.v0.1"))
    assert one(api, "recordings", {"_id": rid})["rubric_id"] == "teaching.school.v0.1"


@pytest.mark.parametrize("rubric_id", ["teaching.school.v9.9", "reception.school.v0.2", "../etc/passwd"])
def test_an_unknown_or_other_type_rubric_is_refused(api: Api, rubric_id: str) -> None:
    rid, _ = finished(api)
    response = api.reanalyze("owner", rid, rubric_id=rubric_id)
    assert response.status_code == 400 and response.json()["code"] == "unknown_rubric"
    assert one(api, "recordings", {"_id": rid})["status"] == "COMPLETED"


def test_only_a_finished_recording_with_a_transcript_is_reanalysed(api: Api) -> None:
    rid, _ = finished(api, status=RecordingStatus.NEEDS_REVIEW)
    response = api.reanalyze("owner", rid)
    assert response.status_code == 409 and response.json()["code"] == "not_completed"
    rid, _ = finished(api)
    api.db.transcripts.delete_many({"recording_id": rid})
    response = api.reanalyze("owner", rid)
    assert response.status_code == 409 and response.json()["code"] == "no_transcript"


def test_a_reason_is_required(api: Api) -> None:
    rid, _ = finished(api)
    assert api.reanalyze("owner", rid, reason="").status_code == 422


def test_managers_and_staff_do_not_reanalyse(api: Api) -> None:
    rid, _ = finished(api)
    assert api.reanalyze("manager", rid).status_code == 403
    assert api.reanalyze("asha", rid).status_code == 403


def test_open_disputes_on_the_old_version_are_closed(api: Api) -> None:
    rid, aid = finished(api)
    common: dict[str, Any] = {
        "tenant_id": T, "analysis_id": aid, "recording_id": rid, "person_id": "p-asha", "unit_id": "unit-1",
        "dimension": "concept_clarity", "dimension_name": "Concept clarity", "ai_score": 4, "current_score": 4,
        "proposed_score": 5, "comment": "Both terms were defined.", "raised_by": "u-asha",
    }  # fmt: skip
    insert(api.db, "disputes", Dispute(id="d-open", **common))
    insert(api.db, "disputes", Dispute(id="d-done", status="accepted", final_score=5, **common))
    body(api.reanalyze("owner", rid))
    closed = one(api, "disputes", {"_id": "d-open"})
    assert (closed["status"], closed["resolution_note"]) == ("closed", "Re-analysed")
    assert closed["calibration"] is None  # nobody judged it
    assert one(api, "disputes", {"_id": "d-done"})["status"] == "accepted"  # stays with the old version


# --- Versions ---


def test_every_version_stays_readable_and_the_latest_is_shown(api: Api) -> None:
    rid, old = finished(api, score=2.0)
    new = add_analysis(api, rid, version="v1-run2", score=4.0)
    api.db.analyses.update_one({"_id": old}, {"$set": {"superseded": True}})
    latest = body(api.get("manager", f"/v1/recordings/{rid}/analysis"))
    assert (latest["analysis_id"], latest["overall"], latest["is_latest"]) == (new, 4.0, True)
    earlier = body(api.get("manager", f"/v1/recordings/{rid}/analysis?analysis_id={old}"))
    assert (earlier["analysis_id"], earlier["overall"], earlier["is_latest"]) == (old, 2.0, False)
    assert earlier["can_dispute"] is False  # only the latest version can be disputed
    listed = api.get("manager", f"/v1/recordings/{rid}/analyses")
    history: list[dict[str, Any]] = listed.json()
    assert [(h["id"], h["superseded"]) for h in history] == [(new, False), (old, True)]
    _, other = finished(api)
    assert api.get("manager", f"/v1/recordings/{rid}/analysis?analysis_id={other}").status_code == 404


def test_numbers_count_only_the_latest_version(api: Api) -> None:
    rid, old = finished(api, score=2.0)
    add_analysis(api, rid, version="v1-run2", score=4.0)
    api.db.analyses.update_one({"_id": old}, {"$set": {"superseded": True}})
    api.db.scores.update_many({"analysis_id": old}, {"$set": {"superseded": True}})
    overall = body(api.get("manager", "/v1/people/p-asha/trend"))["points"]
    assert [p["score"] for p in overall] == [4.0]
    clarity = body(api.get("manager", "/v1/people/p-asha/trend?dimension=concept_clarity"))["points"]
    assert [p["score"] for p in clarity] == [4]
    summary = api.get("owner", "/v1/people/summary")
    assert summary.status_code == 200
    asha = next(p for p in summary.json() if p["id"] == "p-asha")
    assert (asha["analysed"], asha["latest_score"], asha["recent_scores"]) == (1, 4.0, [4.0])


# --- Many recordings ---


def test_bulk_counts_first_then_starts_at_most_a_hundred(api: Api) -> None:
    older = [finished(api, rubric="teaching.school.v0.0")[0] for _ in range(3)]
    current, _ = finished(api)
    counted = body(api.bulk("admin", dry_run=True))
    assert (counted["matching"], counted["started"], counted["rubric_id"]) == (3, 0, CURRENT)
    assert all(one(api, "recordings", {"_id": r})["status"] == "COMPLETED" for r in older)

    started = body(api.bulk("admin", limit=2))
    assert (started["matching"], started["started"], started["remaining"]) == (3, 2, 1)
    statuses = sorted(one(api, "recordings", {"_id": r})["status"] for r in older)
    assert statuses == ["ANALYZING", "ANALYZING", "COMPLETED"]
    assert one(api, "recordings", {"_id": current})["status"] == "COMPLETED"  # already on the current rubric
    assert api.db.audit_log.count_documents({"action": "recording.reanalyze"}) == 2
    assert body(api.bulk("admin"))["started"] == 1  # the rest; the running ones are not counted again


def test_bulk_is_capped_and_for_owners_and_admins(api: Api) -> None:
    assert api.bulk("admin", limit=101).status_code == 422
    assert api.bulk("manager", dry_run=True).status_code == 403
