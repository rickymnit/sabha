"""The permission matrix (tests/security/permissions.yaml, plan task P7.4) stays complete.

The completeness checks need no services. `test_the_api_follows_the_matrix` calls every route as every caller
against a real API (MongoDB, RustFS, a fake identity provider) and fails on any difference.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from pymongo import MongoClient

from sabha_api.main import create_app
from sabha_api.resources import open_resources
from sabha_core.indexes import ensure_indexes
from sabha_core.models import Analysis, IdentityLink, Person, Recording, Role, Score, Tenant, Transcript, Unit, User
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.settings import Settings
from sabha_core.state import RecordingStatus

MATRIX_FILE = Path(__file__).with_name("permissions.yaml")
STATUSES = {200, 201, 401, 403, 404, 422, 503}


def matrix() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(MATRIX_FILE.read_text())
    return data


def api_routes() -> set[str]:
    values: dict[str, Any] = {
        "app_env": "test",
        "mongo_uri": "mongodb://localhost:27017/?replicaSet=rs0",
        "redis_url": "redis://localhost:6380/0",
        "s3_bucket_audio": "a",
        "s3_bucket_artefacts": "b",
        "s3_bucket_backups": "c",
        "oidc_issuer": "https://auth.example.com",
        "oidc_audience": "https://api.example.com",
        "oidc_client_id": "web",
    }
    settings = Settings(_env_file=None, **values)  # type: ignore[call-arg]  # pydantic-settings
    spec = create_app(settings).openapi()
    return {f"{method.upper()} {path}" for path, item in spec["paths"].items() for method in item}


def route_of(entry: str) -> str:
    """'POST /v1/users/invites (admin inviting an admin)' -> 'POST /v1/users/invites'."""
    return entry.split(" (", 1)[0]


def test_every_route_is_in_the_matrix() -> None:
    covered = {route_of(entry) for entry in matrix()["routes"]}
    missing = sorted(api_routes() - covered)
    assert not missing, f"add these routes to {MATRIX_FILE.name}: {missing}"


def test_the_matrix_names_no_route_the_api_lacks() -> None:
    stale = sorted({route_of(entry) for entry in matrix()["routes"]} - api_routes())
    assert not stale, f"remove or rename in {MATRIX_FILE.name}: {stale}"


@pytest.mark.parametrize("entry", sorted(matrix()["routes"]))
def test_every_caller_has_an_expected_status(entry: str) -> None:
    callers = set(matrix()["callers"])
    rules = matrix()["routes"][entry]
    if "all" in rules:
        assert set(rules) == {"all"}, f"{entry}: 'all' cannot be combined with other keys"
        expected = rules["all"]
        assert all(s in STATUSES for s in (expected if isinstance(expected, list) else [expected]))
        return
    named = set(rules) - {"others"}
    assert named <= callers, f"{entry}: unknown callers {sorted(named - callers)}"
    assert "others" in rules or named == callers, f"{entry}: no status for {sorted(callers - named)}"
    for status in rules.values():
        assert status in STATUSES, f"{entry}: unexpected status {status}"


# --- Every route, called as every caller (integration) ---

CALLERS: dict[str, tuple[str, Role, list[str]]] = {  # caller -> (tenant, role, units)
    "owner": ("tenant-a", Role.OWNER, []),
    "admin": ("tenant-a", Role.ADMIN, []),
    "manager_unit": ("tenant-a", Role.MANAGER, ["unit-1"]),
    "manager_other_unit": ("tenant-a", Role.MANAGER, ["unit-2"]),
    "reviewer_unit": ("tenant-a", Role.REVIEWER, ["unit-1"]),
    "staff_uploader": ("tenant-a", Role.STAFF, ["unit-1"]),
    "staff_colleague": ("tenant-a", Role.STAFF, ["unit-1"]),
    "other_tenant": ("tenant-b", Role.OWNER, []),
}
ISSUER = "https://auth.example.com"
FILE = b"0123456789"
DONE = "rec-done"
TRANSCRIPT_KEY = f"tenant-a/{DONE}/transcribe@v1/transcript@v1.json"
REPORT_KEY = f"tenant-a/{DONE}/analyze@v1/analysis@v1.json"


@pytest.fixture(scope="module")
def seeded_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"perm_{uuid.uuid4().hex[:12]}"
    db = mongo_replica_set[name]
    ensure_indexes(db)
    for tenant_id in ("tenant-a", "tenant-b"):
        tenant = Tenant.from_profile("school", name=tenant_id, plan=Plan.PILOT, id=tenant_id)
        db.tenants.insert_one(tenant.model_dump(by_alias=True))
    for unit in ("unit-1", "unit-2"):
        db.units.insert_one(Unit(id=unit, tenant_id="tenant-a", name=unit).model_dump(by_alias=True))
    for caller, (tenant_id, role, units) in CALLERS.items():
        email = f"{caller}@example.com"
        user = User(id=f"u-{caller}", tenant_id=tenant_id, email=email, name=caller, role=role, unit_ids=units,
                    status="active")  # fmt: skip
        link = IdentityLink(tenant_id=tenant_id, issuer=ISSUER, subject=caller, email=email, user_id=user.id)
        db.users.insert_one(user.model_dump(by_alias=True))
        db.identities.insert_one(link.model_dump(by_alias=True))
    for person in (
        Person(id="p-asha", tenant_id="tenant-a", name="Asha", unit_id="unit-1", user_id="u-staff_uploader"),
        Person(id="p-colleague", tenant_id="tenant-a", name="Bina", unit_id="unit-1", user_id="u-staff_colleague"),
    ):
        db.people.insert_one(person.model_dump(by_alias=True))
    # A finished recording of Asha with its transcript and analysis, for the read routes (P5.7b).
    for doc in (
        Recording(id=DONE, tenant_id="tenant-a", type=ConversationType.TEACHING, status=RecordingStatus.COMPLETED,
                  consent_ref="c", person_id="p-asha", unit_id="unit-1", created_by="u-staff_uploader"),
        Transcript(tenant_id="tenant-a", recording_id=DONE, version="transcript@v1", storage_key=TRANSCRIPT_KEY,
                   asr_model="fake", word_timing="approximate", word_count=0, utterance_count=0,
                   roles={"S0": "teacher"}, rubric_id="teaching.school.v0.1"),
        Analysis(id="an-done", tenant_id="tenant-a", recording_id=DONE, version="v1", person_id="p-asha",
                 unit_id="unit-1", conversation_type=ConversationType.TEACHING, rubric_id="teaching.school.v0.1",
                 rubric_version="0.1", rubric_hash="h", report_key=REPORT_KEY, status="COMPLETED", overall_score=3.6,
                 verified_share=1.0),
        Score(tenant_id="tenant-a", analysis_id="an-done", recording_id=DONE, person_id="p-asha",
              dimension="concept_clarity", name="Concept clarity", weight=0.6, score=4, verified=True),
    ):  # fmt: skip
        db[{"Recording": "recordings", "Transcript": "transcripts", "Analysis": "analyses",
            "Score": "scores"}[type(doc).__name__]].insert_one(doc.model_dump(by_alias=True))  # fmt: skip
    yield name
    mongo_replica_set.drop_database(name)


@dataclass
class Api:
    client: TestClient
    idp: Any  # conftest.FakeIdp
    db: Any  # the seeded database, for routes that change a recording (a fresh one per call)

    def headers(self, caller: str, *, create: bool = False) -> dict[str, str]:
        out = {} if caller == "anonymous" else {"Authorization": f"Bearer {self.idp.token(caller)}"}
        if create:
            out["Idempotency-Key"] = uuid.uuid4().hex
        return out


@pytest.fixture
def api(mongo_uri: str, seeded_db: str, fake_idp: Any, s3_storage: Any,
        mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[Api]:  # fmt: skip
    values: dict[str, Any] = {
        "app_env": "test",
        "mongo_uri": f"{mongo_uri}&replicaSet=rs0",
        "mongo_db": seeded_db,
        "redis_url": "redis://127.0.0.1:1/0",
        "s3_endpoint_url": s3_storage.endpoint_url,
        "s3_access_key_id": s3_storage.access_key_id,
        "s3_secret_access_key": s3_storage.secret_access_key,
        "s3_bucket_audio": "sabha-audio",
        "s3_bucket_artefacts": "sabha-artefacts",
        "s3_bucket_backups": "sabha-backups",
        "oidc_issuer": ISSUER,
        "oidc_audience": "https://api.example.com",
        "oidc_client_id": "web",
    }
    settings = Settings(_env_file=None, **values)  # type: ignore[call-arg]  # pydantic-settings
    app = create_app(settings, resources=open_resources, token_verifier=fake_idp.verifier())
    artefacts = s3_storage.client()
    artefacts.put_object(Bucket="sabha-artefacts", Key=TRANSCRIPT_KEY, Body=b'{"utterances": []}')
    report = (
        b'{"version": "analysis@v1", "overall": {"score": 3.6}, "dimensions": [], "metrics": [], "synthesis": null}'
    )
    artefacts.put_object(Bucket="sabha-artefacts", Key=REPORT_KEY, Body=report)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield Api(test_client, fake_idp, mongo_replica_set[seeded_db])


def new_upload(api: Api) -> dict[str, Any]:
    """A recording of Asha, uploaded (parts sent, not completed) by staff_uploader."""
    body = {"type": "teaching", "person_id": "p-asha", "file_name": "lesson.mp3", "size_bytes": len(FILE),
            "content_type": "audio/mpeg"}  # fmt: skip
    created = api.client.post("/v1/recordings", json=body, headers=api.headers("staff_uploader", create=True))
    assert created.status_code == 201, created.text
    out: dict[str, Any] = created.json()
    put = httpx.put(out["parts"][0]["url"], content=FILE)
    assert put.status_code == 200
    out["etag"] = put.headers["etag"]
    return out


def invite(role: str) -> Callable[[Api, str], httpx.Response]:
    def call(api: Api, caller: str) -> httpx.Response:
        body = {"email": f"{uuid.uuid4().hex[:10]}@example.com", "name": "New", "role": role}
        return api.client.post("/v1/users/invites", json=body, headers=api.headers(caller, create=True))

    return call


def create_recording(api: Api, caller: str) -> httpx.Response:
    body = {"type": "teaching", "person_id": "p-asha", "file_name": "lesson.mp3", "size_bytes": len(FILE),
            "content_type": "audio/mpeg"}  # fmt: skip
    return api.client.post("/v1/recordings", json=body, headers=api.headers(caller, create=True))


def parts(api: Api, caller: str) -> httpx.Response:
    upload = new_upload(api)
    path = f"/v1/recordings/{upload['recording_id']}/parts"
    return api.client.post(path, json={"part_numbers": [1]}, headers=api.headers(caller))


def complete(api: Api, caller: str) -> httpx.Response:
    upload = new_upload(api)
    body = {"parts": [{"part_number": 1, "etag": upload["etag"]}], "sha256": hashlib.sha256(FILE).hexdigest(),
            "force": True}  # fmt: skip
    path = f"/v1/recordings/{upload['recording_id']}/complete"
    return api.client.post(path, json=body, headers=api.headers(caller))


def review(api: Api, caller: str) -> httpx.Response:
    """Confirms the teacher of a fresh recording of Asha that needs review (unclear roles)."""
    rid = f"rec-review-{uuid.uuid4().hex[:8]}"
    for collection, doc in (
        ("recordings", Recording(id=rid, tenant_id="tenant-a", type=ConversationType.TEACHING, consent_ref="c",
                                 status=RecordingStatus.NEEDS_REVIEW, status_reason="unclear_roles",
                                 person_id="p-asha", unit_id="unit-1", created_by="u-staff_uploader")),
        ("transcripts", Transcript(tenant_id="tenant-a", recording_id=rid, version="transcript@v1",
                                   storage_key=TRANSCRIPT_KEY, asr_model="fake", word_timing="approximate",
                                   word_count=0, utterance_count=0, roles={"S0": "teacher", "S1": "students"},
                                   role_choices=["teacher", "students"], rubric_id="teaching.school.v0.1")),
    ):  # fmt: skip
        api.db[collection].insert_one(doc.model_dump(by_alias=True))
    body = {"action": "confirm_roles", "staff_speaker": "S0"}
    return api.client.post(f"/v1/recordings/{rid}/review", json=body, headers=api.headers(caller))


CALLS: dict[str, Callable[[Api, str], httpx.Response]] = {
    "GET /health": lambda a, who: a.client.get("/health", headers=a.headers(who)),
    "GET /ready": lambda a, who: a.client.get("/ready", headers=a.headers(who)),
    "GET /v1/meta": lambda a, who: a.client.get("/v1/meta", headers=a.headers(who)),
    "GET /v1/me": lambda a, who: a.client.get("/v1/me", headers=a.headers(who)),
    "POST /v1/users/invites": invite("staff"),
    "POST /v1/users/invites (admin inviting an admin)": invite("admin"),
    "POST /v1/recordings": create_recording,
    "POST /v1/recordings/{recording_id}/parts": parts,
    "POST /v1/recordings/{recording_id}/complete": complete,
    "GET /v1/recordings": lambda a, who: a.client.get("/v1/recordings", headers=a.headers(who)),
    "GET /v1/recordings/{recording_id}": lambda a, who: a.client.get(f"/v1/recordings/{DONE}", headers=a.headers(who)),
    "GET /v1/recordings/{recording_id}/transcript": lambda a, who: a.client.get(
        f"/v1/recordings/{DONE}/transcript", headers=a.headers(who)
    ),
    "GET /v1/recordings/{recording_id}/analysis": lambda a, who: a.client.get(
        f"/v1/recordings/{DONE}/analysis", headers=a.headers(who)
    ),
    "GET /v1/recordings/{recording_id}/analyses": lambda a, who: a.client.get(
        f"/v1/recordings/{DONE}/analyses", headers=a.headers(who)
    ),
    "GET /v1/people": lambda a, who: a.client.get("/v1/people", headers=a.headers(who)),
    "GET /v1/people/summary": lambda a, who: a.client.get("/v1/people/summary", headers=a.headers(who)),
    "GET /v1/reviews": lambda a, who: a.client.get("/v1/reviews", headers=a.headers(who)),
    "GET /v1/recordings/{recording_id}/speakers": lambda a, who: a.client.get(
        f"/v1/recordings/{DONE}/speakers", headers=a.headers(who)
    ),
    "POST /v1/recordings/{recording_id}/review": review,
    "GET /v1/overview": lambda a, who: a.client.get(
        "/v1/overview?from=2026-01-01T00:00:00Z&to=2026-12-31T00:00:00Z", headers=a.headers(who)
    ),
    "GET /v1/people/{person_id}/trend": lambda a, who: a.client.get("/v1/people/p-asha/trend", headers=a.headers(who)),
}


def expected(entry: str, caller: str) -> set[int]:
    rules = matrix()["routes"][entry]
    status = rules.get("all", rules.get(caller, rules.get("others")))
    return set(status) if isinstance(status, list) else {status}


def test_every_matrix_entry_has_a_call() -> None:
    assert set(CALLS) == set(matrix()["routes"])


CASES = [(entry, caller) for entry in sorted(matrix()["routes"]) for caller in matrix()["callers"]]


@pytest.mark.integration
@pytest.mark.parametrize(("entry", "caller"), CASES, ids=[f"{e} as {c}" for e, c in CASES])
def test_the_api_follows_the_matrix(api: Api, entry: str, caller: str) -> None:
    response = CALLS[entry](api, caller)
    assert response.status_code in expected(entry, caller), (
        f"{entry} as {caller}: got {response.status_code}, matrix says {sorted(expected(entry, caller))}: "
        f"{response.text[:300]}"
    )
