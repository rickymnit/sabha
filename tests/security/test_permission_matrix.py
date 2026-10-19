"""The permission matrix (tests/security/permissions.yaml, plan task P7.4) stays complete.

These checks run now. The tests that call every route as every caller are written once the owner has reviewed
the matrix, and then fail on any difference between the matrix and the API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from sabha_api.main import create_app
from sabha_core.settings import Settings

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
