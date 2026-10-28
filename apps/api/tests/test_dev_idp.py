"""The local dev sign-in (sabha_api.auth.dev_idp; decided 2026-10-22): local only, and nothing is bypassed."""

from __future__ import annotations

import importlib.util
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from pymongo import MongoClient

from sabha_api.auth.password import hash_password, verify_password
from sabha_api.resources import open_resources
from sabha_core.indexes import ensure_indexes
from sabha_core.repo import COLLECTIONS
from sabha_core.settings import AppEnv, Settings

ISSUER = "http://localhost:8000/dev-idp"
BASE: dict[str, Any] = {
    "mongo_uri": "mongodb://localhost:27017/?replicaSet=rs0", "redis_url": "redis://localhost:6380/0",
    "s3_bucket_audio": "a", "s3_bucket_artefacts": "b", "s3_bucket_backups": "c", "oidc_issuer": ISSUER,
    "oidc_audience": "sabha-local", "oidc_client_id": "sabha-web",
}  # fmt: skip


def _seed_module() -> Any:
    path = Path(__file__).resolve().parents[3] / "scripts" / "admin" / "dev_seed.py"
    spec = importlib.util.spec_from_file_location("dev_seed", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["dev_seed"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("env", ["test", "staging", "production"])
def test_dev_login_is_refused_outside_local(env: AppEnv) -> None:
    extra = {"s3_region": "ap-south-1"} if env != "test" else {}
    with pytest.raises(ValidationError, match="DEV_LOGIN is for local development only"):
        Settings(_env_file=None, app_env=env, dev_login=True, **{**BASE, **extra})  # type: ignore[call-arg]


def test_without_dev_login_the_routes_do_not_exist(make_client: Any) -> None:
    client = make_client()
    assert client.get("/dev-idp/users").status_code == 404
    assert client.post("/dev-idp/token", json={"subject": "dev-owner"}).status_code == 404


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"dev_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield name
    mongo_replica_set.drop_database(name)


@pytest.mark.integration
def test_local_sign_in_end_to_end(make_client: Any, mongo_uri: str, mongo_replica_set: MongoClient[dict[str, Any]],
                                  shared_db: str, s3_storage: Any) -> None:  # fmt: skip
    db = mongo_replica_set[shared_db]
    for collection in COLLECTIONS:
        db[collection].delete_many({})
    seed = _seed_module()
    assert seed.seed(db, ISSUER) > 0
    assert seed.seed(db, ISSUER) == 0  # running it again changes nothing
    old_style = {"$set": {"name": "Asha Rao (Teacher, Class 6)"}, "$unset": {"title": ""}}
    db.users.update_one({"_id": "u-dev-asha"}, old_style)
    assert seed.seed(db, ISSUER) == 1  # an older seed's name is split into name and job title

    client = make_client(
        resources=open_resources, app_env="local", dev_login=True, oidc_issuer=ISSUER, oidc_audience="sabha-local",
        mongo_uri=f"{mongo_uri}&replicaSet=rs0", mongo_db=shared_db, redis_url="redis://127.0.0.1:1/0",
        s3_endpoint_url=s3_storage.endpoint_url, s3_access_key_id=s3_storage.access_key_id,
        s3_secret_access_key=s3_storage.secret_access_key,
    )  # fmt: skip
    people = client.get("/dev-idp/users").json()
    listed = {f"dev-{u[0]}" for u in (*seed.USERS, *seed.COMPANY_USERS)}
    assert {p["subject"] for p in people} == listed  # E2E School is not listed
    assert {p["tenant_name"] for p in people} == {"Demo School", "Brightpath Software"}
    company = db.tenants.find_one({"_id": "demo-company"})
    assert (
        company is not None
        and company["profile"] == "company"
        and set(company["enabled_types"]) == {"reception", "meeting", "sales"}
    )
    assert "ब्राइट पाथ सॉफ्टवेयर" in company["name_variants"]  # how the recogniser writes it inside Hindi
    assert {(p["name"], p["title"]) for p in people if p["subject"] == "dev-asha"} == {("Asha Rao", "Teacher, Class 6")}

    token = client.post("/dev-idp/token", json={"subject": "dev-asha"}).json()["access_token"]
    me = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    assert me.json()["user"]["role"] == "staff"  # role and tenant come from our own records, as with Auth0
    assert me.json()["user"]["title"] == "Teacher, Class 6"
    assert me.json()["tenant"]["units"] == [{"id": "unit-6", "name": "Class 6"}, {"id": "unit-7", "name": "Class 7"}]
    assert client.post("/dev-idp/token", json={"subject": "dev-nobody"}).status_code == 404
    hidden = client.post("/dev-idp/token", json={"subject": "e2e-teacher"}).json()["access_token"]
    e2e_me = client.get("/v1/me", headers={"Authorization": f"Bearer {hidden}"}).json()  # still signs in by subject
    assert (e2e_me["tenant"]["id"], e2e_me["user"]["name"]) == ("e2e-school", "Test Teacher")
    forged = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    assert not any(path.startswith("/dev-idp") for path in client.get("/openapi.json").json()["paths"])


# --- Local password sign-in (owner's choice, 2026-10-28) ---

LOGIN = {"login_username": "tester", "login_as": "owner@demo-school.example"}
PASSWORD = "made-up-for-tests"  # pragma: allowlist secret  (a test value, not anyone's password)


def test_password_hashes_check_and_never_hold_the_password() -> None:
    stored = hash_password(PASSWORD)
    assert PASSWORD not in stored and stored != hash_password(PASSWORD)  # salted
    assert verify_password(PASSWORD, stored)
    assert not verify_password(PASSWORD.upper(), stored)
    assert not verify_password(PASSWORD, "not-a-hash")


@pytest.mark.parametrize(
    ("env", "extra", "message"),
    [
        ("staging", {"s3_region": "ap-south-1"}, "for local use only"),
        ("local", {"dev_login": True}, "not both"),
        ("local", {"login_as": None}, "set together"),
    ],
)
def test_password_login_is_local_only_and_never_beside_the_dev_list(
    env: AppEnv, extra: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        fields = {**BASE, **LOGIN, "login_password_hash": "scrypt$x", **extra}  # pragma: allowlist secret
        Settings(_env_file=None, app_env=env, **fields)  # type: ignore[call-arg]  # _env_file: pydantic-settings


@pytest.mark.integration
def test_password_sign_in_end_to_end(make_client: Any, mongo_uri: str, mongo_replica_set: MongoClient[dict[str, Any]],
                                     shared_db: str, s3_storage: Any) -> None:  # fmt: skip
    db = mongo_replica_set[shared_db]
    for collection in COLLECTIONS:
        db[collection].delete_many({})
    _seed_module().seed(db, ISSUER)
    client = make_client(
        resources=open_resources, app_env="local", oidc_issuer=ISSUER, oidc_audience="sabha-local",
        login_password_hash=hash_password(PASSWORD), **LOGIN,
        mongo_uri=f"{mongo_uri}&replicaSet=rs0", mongo_db=shared_db, redis_url="redis://127.0.0.1:1/0",
        s3_endpoint_url=s3_storage.endpoint_url, s3_access_key_id=s3_storage.access_key_id,
        s3_secret_access_key=s3_storage.secret_access_key,
    )  # fmt: skip
    assert client.get("/dev-idp/users").status_code == 404  # the list that skips the password is not mounted

    wrong_password = {
        "username": "tester",
        "password": "nope",  # pragma: allowlist secret  (a deliberately wrong test value)
    }
    for wrong in (wrong_password, {"username": "Tester", "password": PASSWORD}):
        refused = client.post("/auth/login", json=wrong)
        assert (refused.status_code, refused.json()["code"]) == (401, "unauthorized")
        assert refused.json()["detail"] == "The username or password is wrong."  # never says which

    token = client.post("/auth/login", json={"username": "tester", "password": PASSWORD}).json()["access_token"]
    me = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert (me["user"]["email"], me["user"]["role"]) == ("owner@demo-school.example", "owner")
