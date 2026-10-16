"""Every error is RFC 9457 problem+json with a stable code and the request id (CLAUDE.md, API conventions)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from sabha_api.errors import PROBLEM_MEDIA_TYPE, ConflictError

PROBLEM_KEYS = {"type", "title", "status", "detail", "code", "request_id"}


def assert_problem(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body: dict[str, Any] = response.json()
    assert set(body) >= PROBLEM_KEYS
    assert body["status"] == status
    assert body["code"] == code
    assert body["type"] == f"urn:sabha:problem:{code}"
    assert body["request_id"] == response.headers["x-request-id"]
    return body


class Thing(BaseModel):
    name: str
    count: int


def add_test_routes(app: object) -> None:
    assert isinstance(app, FastAPI)

    @app.post("/v1/things")
    async def create_thing(thing: Thing) -> Thing:
        return thing

    @app.get("/v1/conflict")
    async def conflict() -> None:
        raise ConflictError("That name is already taken.", extra={"field": "name"})

    @app.get("/v1/boom")
    async def boom() -> None:
        raise RuntimeError("database password is hunter2")


def test_unknown_path_is_a_404_problem(client: TestClient) -> None:
    body = assert_problem(client.get("/v1/nothing-here"), 404, "not_found")
    assert body["title"] == "Not Found"


def test_wrong_method_is_a_405_problem(client: TestClient) -> None:
    assert_problem(client.delete("/health"), 405, "method_not_allowed")


def test_validation_error_lists_fields_without_values(client: TestClient) -> None:
    add_test_routes(client.app)
    response = client.post("/v1/things", json={"name": "a-secret-value", "count": "not-a-number"})
    body = assert_problem(response, 422, "validation_error")
    assert body["errors"] == [
        {
            "loc": ["body", "count"],
            "msg": "Input should be a valid integer, unable to parse string as an integer",
            "type": "int_parsing",
        }
    ]
    assert "not-a-number" not in response.text
    assert "a-secret-value" not in response.text


def test_api_error_keeps_its_code_detail_and_extra_members(client: TestClient) -> None:
    add_test_routes(client.app)
    body = assert_problem(client.get("/v1/conflict"), 409, "conflict")
    assert body["detail"] == "That name is already taken."
    assert body["field"] == "name"


def test_unexpected_error_is_a_generic_500_that_hides_the_exception(client: TestClient) -> None:
    add_test_routes(client.app)
    response = client.get("/v1/boom")
    body = assert_problem(response, 500, "internal_error")
    assert "hunter2" not in response.text
    assert body["detail"] == "Something went wrong on our side."
    assert response.headers["x-content-type-options"] == "nosniff"


def test_openapi_documents_errors_as_problem_json(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "Problem" in schema["components"]["schemas"]
    meta = schema["paths"]["/v1/meta"]["get"]["responses"]
    assert PROBLEM_MEDIA_TYPE in meta["default"]["content"]
    assert "HTTPValidationError" not in schema["components"]["schemas"]
