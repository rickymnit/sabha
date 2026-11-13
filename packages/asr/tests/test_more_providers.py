"""OpenAI, Qwen and Amazon Transcribe adapters (ADR 0012): request shape, response parsing and error mapping against
mocked transports; the registry's provider[:model] choice; prices kept in their own currency."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from sabha_asr.pricing import cost_inr
from sabha_asr.provider import AudioChunk, ProviderError
from sabha_asr.providers import aws, openai, qwen
from sabha_asr.registry import (
    AsrConfigError,
    build_provider,
    build_transcriber,
    choices,
    chosen_spec,
    model_id_for,
    parse_spec,
)
from sabha_core.settings import Settings

CHUNK = AudioChunk("rec1-c003", b"RIFF....WAVEfmt fake audio", 10_000)


def no_wait(seconds: float) -> None:
    """Rate-limit waits take no time in tests."""


def mocked(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- OpenAI ---


def test_openai_sends_the_model_and_spreads_the_text() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"text": "haan ji bataiye", "languages": ["hi"]})

    result = openai.OpenAIProvider("k", client=mocked(handler), sleep=no_wait).transcribe([CHUNK])[0]
    body = seen[0].read().decode("latin-1")
    assert seen[0].url == "https://api.openai.com/v1/audio/transcriptions"
    assert seen[0].headers["authorization"] == "Bearer k"
    assert 'name="model"\r\n\r\ngpt-transcribe' in body
    assert "language" not in body.replace('name="file"', "")  # "unknown": no hint, the model detects it
    assert [w.text for w in result.words] == ["haan", "ji", "bataiye"]
    assert result.words[0].start_ms == 0 and result.words[-1].end_ms == CHUNK.duration_ms
    assert result.languages[0].language == "hi"


def test_openai_whisper1_asks_for_word_times() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.read().decode("latin-1"))
        return httpx.Response(200, json={"text": "haan ji", "language": "hindi",
                                         "words": [{"word": "haan", "start": 0.2, "end": 0.5},
                                                   {"word": " ji", "start": 0.5, "end": 99.0}]})  # fmt: skip

    p = openai.OpenAIProvider("k", model="whisper-1", client=mocked(handler), sleep=no_wait)
    result = p.transcribe([CHUNK])[0]
    assert p.word_timing == "word"
    assert "verbose_json" in seen[0] and "timestamp_granularities[]" in seen[0]
    assert [(w.text, w.start_ms, w.end_ms) for w in result.words] == [("haan", 200, 500), ("ji", 500, 10_000)]


@pytest.mark.parametrize(("status", "code", "retryable"), [
    (429, "insufficient_quota", False), (429, "rate_limit_exceeded", True), (401, "invalid_api_key", False),
    (503, "server_error", True),
])  # fmt: skip
def test_openai_errors(status: int, code: str, retryable: bool) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(status, json={"error": {"code": code, "message": "secret text never logged"}})

    with pytest.raises(ProviderError) as caught:
        openai.OpenAIProvider("k", client=mocked(handler), sleep=no_wait).transcribe([CHUNK])
    assert caught.value.retryable is retryable
    assert "secret" not in str(caught.value)
    assert len(calls) == (5 if (status, retryable) == (429, True) else 1)  # rate limits are waited out 4 times


# --- Qwen ---


def test_qwen_request_and_answer() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.read()))
        return httpx.Response(200, json={"choices": [{"message": {
            "content": "नमस्ते sir", "annotations": [{"type": "audio_info", "language": "hi"}]}}],
            "usage": {"seconds": 10}})  # fmt: skip

    p = qwen.QwenProvider("k", language="hi-IN", client=mocked(handler), sleep=no_wait)
    result = p.transcribe([CHUNK])[0]
    sent = seen[0]
    assert sent["model"] == "qwen3-asr-flash" and sent["asr_options"] == {"enable_itn": False, "language": "hi"}
    audio = sent["messages"][0]["content"][0]["input_audio"]["data"]
    assert audio.startswith("data:audio/wav;base64,")
    assert result.text == "नमस्ते sir" and result.languages[0].language == "hi"


def test_qwen_unreadable_answer_is_not_retried() -> None:
    handler = lambda request: httpx.Response(200, json={"choices": []})  # noqa: E731
    with pytest.raises(ProviderError) as caught:
        qwen.QwenProvider("k", client=mocked(handler), sleep=no_wait).transcribe([CHUNK])
    assert not caught.value.retryable


# --- Amazon Transcribe ---


def test_aws_words_punctuation_and_confidence() -> None:
    body = {"results": {"items": [
        {"type": "pronunciation", "start_time": "0.1", "end_time": "0.4",
         "alternatives": [{"content": "Hello", "confidence": "0.98"}]},
        {"type": "punctuation", "alternatives": [{"content": ","}]},
        {"type": "pronunciation", "start_time": "0.5", "end_time": "11.0",
         "alternatives": [{"content": "sir", "confidence": ""}]},
    ]}}  # fmt: skip
    result = aws.parse(CHUNK, body, "en-IN")
    assert [(w.text, w.start_ms, w.end_ms, w.confidence) for w in result.words] == [
        ("Hello,", 100, 400, 0.98), ("sir", 500, 10_000, None)]  # fmt: skip
    assert result.languages[0].language == "en-IN"


# --- Registry and prices ---


def settings(**values: Any) -> Settings:
    base = {"app_env": "test", "mongo_uri": "mongodb://localhost:27017/?replicaSet=rs0",
            "redis_url": "redis://localhost:6380/0", "s3_bucket_audio": "a", "s3_bucket_artefacts": "b",
            "s3_bucket_backups": "c", "oidc_issuer": "https://auth.example.com",
            "oidc_audience": "https://api.example.com", "oidc_client_id": "c"}  # fmt: skip
    return Settings(_env_file=None, **(base | values))  # type: ignore[call-arg]  # settings option mypy cannot see


def test_spec_and_model_choice() -> None:
    s = settings(asr_provider="openai", asr_model="gpt-4o-mini-transcribe", openai_api_key="k")
    assert parse_spec("openai:gpt-transcribe") == ("openai", "gpt-transcribe")
    assert parse_spec("qwen") == ("qwen", None)
    assert model_id_for("openai", s) == "openai/gpt-4o-mini-transcribe"  # ASR_MODEL for the configured provider
    assert model_id_for("openai", s, "gpt-transcribe") == "openai/gpt-transcribe"  # an explicit model wins
    assert model_id_for("aws", s) == "aws/transcribe@ap-south-1"
    assert build_provider("openai", s, "gpt-transcribe").model_id == "openai/gpt-transcribe"
    with pytest.raises(AsrConfigError, match="DASHSCOPE_API_KEY"):
        build_provider("qwen", s)


def test_dollar_prices_need_the_configured_rate() -> None:
    minute = 60_000
    assert cost_inr("sarvam/saaras:v4", minute) == pytest.approx(0.49)
    assert cost_inr("openai/gpt-transcribe", minute) is None  # no rate: never converted with a guess
    assert cost_inr("openai/gpt-transcribe", minute, 90.0) == pytest.approx(0.405)
    assert cost_inr("aws/transcribe@us-east-1", minute, 90.0) is None  # only Mumbai's price was checked
    assert cost_inr("whisper/large-v3-turbo", minute, 90.0) is None  # self-hosted: no per-minute price


# --- Choosing a model per upload ---


def test_upload_choices_and_what_a_chosen_model_builds() -> None:
    s = settings(asr_provider="sarvam", sarvam_api_key="k", openai_api_key="k", asr_fallbacks="openai")
    offered = {c.spec: c for c in choices(s)}
    assert next(iter(offered)) == "sarvam:saaras:v4" and offered["sarvam:saaras:v4"].default
    assert offered["openai:gpt-transcribe"].available and not offered["qwen:qwen3-asr-flash"].available
    assert chosen_spec("openai", s) == "openai:gpt-transcribe"  # a bare provider means its default model
    with pytest.raises(AsrConfigError, match="not set up"):
        chosen_spec("qwen:qwen3-asr-flash", s)  # listed, but no DASHSCOPE_API_KEY
    with pytest.raises(AsrConfigError, match="not one of"):
        chosen_spec("openai:gpt-9", s)
    chosen = build_transcriber(s, "openai:gpt-4o-mini-transcribe")
    assert chosen.primary.model_id == "openai/gpt-4o-mini-transcribe"
    assert chosen.fallbacks == ()  # the configured fallback is the chosen provider itself: never twice
    assert [f.name for f in build_transcriber(s).fallbacks] == ["openai"]
