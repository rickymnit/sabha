"""The Sarvam adapter against a mocked HTTP transport: request shape, response parsing and error mapping."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from sabha_asr.provider import AudioChunk, ProviderError
from sabha_asr.providers.sarvam import MAX_CHUNK_MS, SarvamProvider

CHUNK = AudioChunk("rec1-c003", b"RIFF....WAVEfmt fake audio", 10_000)
Handler = Callable[[httpx.Request], httpx.Response]


def provider(handler: Handler, **kwargs: Any) -> SarvamProvider:
    return SarvamProvider("secret-key-123", client=httpx.Client(transport=httpx.MockTransport(handler)), **kwargs)


def respond(body: Any, status: int = 200) -> Handler:
    return lambda request: httpx.Response(status, json=body)


def form_fields(request: httpx.Request) -> dict[str, str]:
    """Plain form fields of a multipart request (the file part excluded)."""
    content = request.read().decode("latin-1")
    boundary = request.headers["content-type"].split("boundary=")[1]
    fields = {}
    for part in content.split(f"--{boundary}"):
        if 'name="' in part and "filename=" not in part:
            name = part.split('name="')[1].split('"')[0]
            fields[name] = part.split("\r\n\r\n", 1)[1].rsplit("\r\n", 1)[0]
    return fields


# --- Request ---


def test_request_shape() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"transcript": "haan", "language_code": "hi-IN"})

    provider(handler, base_url="https://sarvam.test/", language="hi-IN").transcribe([CHUNK])
    (request,) = seen
    assert request.method == "POST" and str(request.url) == "https://sarvam.test/speech-to-text"
    assert request.headers["api-subscription-key"] == "secret-key-123"
    assert form_fields(request) == {"model": "saaras:v4", "language_code": "hi-IN", "with_timestamps": "true"}
    assert b'filename="rec1-c003.wav"' in request.content and b"fake audio" in request.content


def test_saaras_v3_sends_transcribe_mode() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"transcript": "haan", "language_code": None})

    provider(handler, model="saaras:v3").transcribe([CHUNK])
    assert form_fields(seen[0])["mode"] == "transcribe"


def test_one_request_per_chunk_in_order() -> None:
    order: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        order.append(request.read().split(b'filename="')[1].split(b'"')[0].decode())
        return httpx.Response(200, json={"transcript": "haan", "language_code": "hi-IN"})

    chunks = [AudioChunk(f"c{i}", b"x", 1_000) for i in range(3)]
    results = provider(handler).transcribe(chunks)
    assert order == ["c0.wav", "c1.wav", "c2.wav"]
    assert [r.chunk_id for r in results] == ["c0", "c1", "c2"]


def test_chunks_over_the_rest_limit_are_refused_before_sending() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    with pytest.raises(ValueError, match="limit"):
        provider(handler).transcribe([AudioChunk("long", b"x", MAX_CHUNK_MS + 1)])
    assert calls == []


# --- Response ---


def test_phrases_become_approximately_timed_words() -> None:
    body = {
        "request_id": "r1",
        "transcript": "aaj hum fractions padhenge. Ready?",
        "language_code": "hi-IN",
        "timestamps": {
            "words": ["aaj hum fractions padhenge.", "Ready?"],
            "start_time_seconds": [0.5, 6.0],
            "end_time_seconds": [4.1, 6.6],
        },
    }
    (result,) = provider(respond(body)).transcribe([CHUNK])
    assert [w.text for w in result.words] == ["aaj", "hum", "fractions", "padhenge.", "Ready?"]
    assert result.words[0].start_ms == 500 and result.words[3].end_ms == 4_100
    assert (result.words[4].start_ms, result.words[4].end_ms) == (6_000, 6_600)
    assert all(w.confidence is None for w in result.words)
    assert result.text == "aaj hum fractions padhenge. Ready?"
    assert [(s.start_ms, s.end_ms, s.language) for s in result.languages] == [(0, 10_000, "hi-IN")]


def test_phrases_out_of_order_are_sorted_and_clamped_to_the_chunk() -> None:
    body = {
        "transcript": "do ek",
        "language_code": "hi-IN",
        "timestamps": {"words": ["do", "ek"], "start_time_seconds": [5.0, -0.2], "end_time_seconds": [11.0, 1.0]},
    }
    (result,) = provider(respond(body)).transcribe([CHUNK])
    assert [(w.text, w.start_ms, w.end_ms) for w in result.words] == [("ek", 0, 1_000), ("do", 5_000, 10_000)]


@pytest.mark.parametrize("timestamps", [None, {}])
def test_without_timestamps_the_transcript_is_spread_over_the_chunk(timestamps: Any) -> None:
    body = {"transcript": "namaste sir", "language_code": None, "timestamps": timestamps}
    (result,) = provider(respond(body)).transcribe([CHUNK])
    assert [w.text for w in result.words] == ["namaste", "sir"]
    assert result.words[0].start_ms == 0 and result.words[-1].end_ms == 10_000
    assert result.languages[0].language is None


def test_silence_gives_no_words() -> None:
    (result,) = provider(respond({"transcript": "", "language_code": None})).transcribe([CHUNK])
    assert result.words == () and result.text == ""


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"language_code": "hi-IN"},
        {"transcript": 5},
        {"transcript": "x", "language_code": 7},
        {"transcript": "x", "timestamps": "soon"},
        {"transcript": "x", "timestamps": {"words": ["x"]}},
        {"transcript": "x", "timestamps": {"words": ["x"], "start_time_seconds": [0], "end_time_seconds": []}},
        {"transcript": "x", "timestamps": {"words": [1], "start_time_seconds": [0], "end_time_seconds": [1]}},
        {"transcript": "x", "timestamps": {"words": ["x"], "start_time_seconds": ["0"], "end_time_seconds": [1]}},
    ],
)
def test_unreadable_responses_are_provider_errors(body: Any) -> None:
    with pytest.raises(ProviderError) as raised:
        provider(respond(body)).transcribe([CHUNK])
    assert raised.value.retryable is False


def test_non_json_response_is_a_provider_error() -> None:
    with pytest.raises(ProviderError, match="not JSON"):
        provider(lambda r: httpx.Response(200, text="<html>")).transcribe([CHUNK])


# --- Errors (Sarvam's error guide) ---


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (429, "rate_limit_exceeded_error", True),
        (503, "rate_limit_exceeded_error", True),
        (500, "internal_server_error", True),
        (429, "insufficient_quota_error", False),
        (403, "invalid_api_key_error", False),
        (400, "invalid_request_error", False),
        (422, "unprocessable_entity_error", False),
    ],
)
def test_http_errors_map_to_retryable_or_not(status: int, code: str, retryable: bool) -> None:
    body = {"error": {"message": "details that may echo input", "code": code, "request_id": "r"}}
    with pytest.raises(ProviderError) as raised:
        provider(respond(body, status)).transcribe([CHUNK])
    assert raised.value.retryable is retryable
    assert raised.value.reason == f"HTTP {status} {code}"
    assert raised.value.provider == "sarvam"


def test_error_without_a_json_body() -> None:
    with pytest.raises(ProviderError) as raised:
        provider(lambda r: httpx.Response(502, text="Bad Gateway")).transcribe([CHUNK])
    assert raised.value.reason == "HTTP 502 unknown" and raised.value.retryable is True


@pytest.mark.parametrize(
    "error", [httpx.ConnectTimeout("slow"), httpx.ReadTimeout("slow"), httpx.ConnectError("refused")]
)
def test_network_failures_are_retryable(error: Exception) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    with pytest.raises(ProviderError) as raised:
        provider(handler).transcribe([CHUNK])
    assert raised.value.retryable is True


def test_error_reasons_never_hold_the_key_or_the_message() -> None:
    body = {"error": {"message": "secret-key-123 aaj hum", "code": "invalid_request_error"}}
    with pytest.raises(ProviderError) as raised:
        provider(respond(body, 400)).transcribe([CHUNK])
    assert "secret-key-123" not in str(raised.value) and "aaj hum" not in str(raised.value)


def test_an_empty_key_is_refused() -> None:
    with pytest.raises(ValueError):
        SarvamProvider("")


def test_identity() -> None:
    sarvam = provider(respond({}))
    assert (sarvam.name, sarvam.model_id, sarvam.word_timing) == ("sarvam", "sarvam/saaras:v4", "approximate")
    assert json.dumps(sarvam.max_chunk_ms) == "29500"
