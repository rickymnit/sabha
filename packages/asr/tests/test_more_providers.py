"""OpenAI, Qwen and Amazon Transcribe adapters (ADR 0012): request shape, response parsing and error mapping against
mocked transports; the registry's provider[:model] choice; prices kept in their own currency."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from sabha_asr.pricing import cost_inr, token_cost_inr
from sabha_asr.provider import AudioChunk, ProviderError, TokenUsage
from sabha_asr.providers import aws, deepgram, gemini, groq, openai, qwen
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
    # "unknown": told to expect Hindi and English, never left to guess Urdu or Bengali (owner, 2026-11-13)
    assert body.count('name="languages[]"') == 2 and "\r\n\r\nhi\r\n" in body and "\r\n\r\nen\r\n" in body
    assert 'name="prompt"' not in body  # a sample prompt was copied into transcripts by gpt-4o-mini-transcribe
    mini = openai.OpenAIProvider("k", model="gpt-4o-mini-transcribe", client=mocked(handler), sleep=no_wait)
    mini.transcribe([CHUNK])
    assert 'name="language"\r\n\r\nhi\r\n' in seen[1].read().decode("latin-1")  # one language: Hindi
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


def test_groq_is_openai_with_groqs_address_words_and_patience() -> None:
    seen: list[httpx.Request] = []
    limited = 3

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) <= limited:  # Groq's per-minute limit: outlasts OpenAI's four waits
            return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})
        return httpx.Response(200, json={"text": "haan ji", "language": "Hindi",
                                         "words": [{"word": "haan", "start": 0.2, "end": 0.5}]})  # fmt: skip

    p = groq.GroqProvider("k", client=mocked(handler), sleep=no_wait)
    limited = 6
    result = p.transcribe([CHUNK])[0]
    body = seen[-1].read().decode("latin-1")
    assert seen[-1].url == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert p.model_id == "groq/whisper-large-v3" and p.word_timing == "word"
    assert 'name="language"\r\n\r\nhi\r\n' in body and "verbose_json" in body
    assert [(w.text, w.start_ms) for w in result.words] == [("haan", 200)]
    s = settings(asr_provider="groq", groq_api_key="k")
    assert build_transcriber(s).primary.model_id == "groq/whisper-large-v3"
    assert cost_inr("groq/whisper-large-v3-turbo", 3_600_000, 100.0) == pytest.approx(4.0)


def test_deepgram_code_switching_words_and_languages() -> None:
    seen: list[httpx.Request] = []
    words = [{"word": "device", "punctuated_word": "Device", "start": 0.1, "end": 0.5, "confidence": 0.9,
              "language": "en"},
             {"word": "की", "start": 0.5, "end": 0.7, "confidence": 0.8, "language": "hi"},
             {"word": "बात", "punctuated_word": "बात।", "start": 0.7, "end": 99.0, "language": "hi"}]  # fmt: skip

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(401, json={"err_code": "INVALID_AUTH", "err_msg": "bad key"})
        return httpx.Response(200, json={"results": {"channels": [{"alternatives": [{"words": words}]}]}})

    p = deepgram.DeepgramProvider("k", client=mocked(handler), sleep=no_wait)
    with pytest.raises(ProviderError) as bad:
        p.transcribe([CHUNK])
    assert not bad.value.retryable and "INVALID_AUTH" in bad.value.reason
    result = p.transcribe([CHUNK])[0]
    query = seen[-1].url.params
    assert seen[-1].headers["authorization"] == "Token k" and seen[-1].content == CHUNK.wav
    assert query["language"] == "multi" and query.get_list("language_hint") == ["hi", "en"]
    assert [(w.text, w.start_ms, w.end_ms) for w in result.words] == [("Device", 100, 500), ("की", 500, 700),
                                                                     ("बात।", 700, 10_000)]  # fmt: skip
    assert [(s.language, s.start_ms, s.end_ms) for s in result.languages] == [("en", 0, 500), ("hi", 500, 10_000)]
    assert cost_inr("deepgram/nova-3", 60_000, 100.0) == pytest.approx(0.52)


def gemini_answer(text: str, reason: str = "STOP", usage: tuple[int, int, int] | None = None) -> dict[str, Any]:
    answer: dict[str, Any] = {
        "candidates": [{"finishReason": reason, "content": {"parts": [{"text": json.dumps({"text": text})}]}}]
    }
    if usage is not None:
        prompt, candidates, thoughts = usage
        answer["usageMetadata"] = {"promptTokenCount": prompt, "candidatesTokenCount": candidates,
                                   "thoughtsTokenCount": thoughts}  # fmt: skip
    return answer


def test_gemini_request_answer_and_guard_against_invented_words() -> None:
    seen: list[httpx.Request] = []
    answers = [gemini_answer("एक device की   बात"), gemini_answer("word " * 61), gemini_answer("ठीक है")]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=answers[len(seen) - 1])

    p = gemini.GeminiProvider("k", client=mocked(handler), sleep=no_wait)
    first = p.transcribe([CHUNK])[0]
    sent = json.loads(seen[0].content)
    assert seen[0].url == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent"
    )
    assert seen[0].headers["x-goog-api-key"] == "k" and sent["generationConfig"]["temperature"] == 0
    assert "Never translate" in sent["contents"][0]["parts"][1]["text"]
    assert [w.text for w in first.words] == ["एक", "device", "की", "बात"] and p.word_timing == "approximate"
    # 3.1 Flash-Lite, the default: no thinking
    assert sent["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}
    # 61 words in 10 s cannot have been spoken: asked again, and the second answer is used
    assert [w.text for w in p.transcribe([CHUNK])[0].words] == ["ठीक", "है"] and len(seen) == 3


def test_gemini_refuses_invented_or_blocked_answers() -> None:
    too_long = gemini.GeminiProvider("k", client=mocked(lambda r: httpx.Response(200, json=gemini_answer("a " * 61))),
                                     sleep=no_wait)  # fmt: skip
    with pytest.raises(ProviderError, match="more words than the audio"):
        too_long.transcribe([CHUNK])
    cut = gemini.GeminiProvider("k", client=mocked(lambda r: httpx.Response(200, json=gemini_answer("x", "SAFETY"))),
                                sleep=no_wait)  # fmt: skip
    with pytest.raises(ProviderError, match="SAFETY"):
        cut.transcribe([CHUNK])
    bad_key = {"error": {"code": 403, "message": "no", "status": "PERMISSION_DENIED"}}
    denied = gemini.GeminiProvider("k", client=mocked(lambda r: httpx.Response(403, json=bad_key)), sleep=no_wait)
    with pytest.raises(ProviderError, match="PERMISSION_DENIED") as err:
        denied.transcribe([CHUNK])
    assert not err.value.retryable
    assert cost_inr("gemini/gemini-3.8-flash", 3_600_000, 100.0) == pytest.approx(6.75)


def test_gemini_reports_the_tokens_it_billed_retries_and_thinking_included() -> None:
    answers = [gemini_answer("word " * 61, usage=(300, 400, 900)), gemini_answer("ठीक है", usage=(300, 10, 50))]
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=answers[len(calls) - 1])

    result = gemini.GeminiProvider("k", client=mocked(handler), sleep=no_wait).transcribe([CHUNK])[0]
    # The refused first answer was billed too: both attempts count. Output includes thinking.
    assert result.usage == TokenUsage(input_tokens=600, output_tokens=1_360, thinking_tokens=950)
    no_usage = gemini.GeminiProvider("k", client=mocked(lambda r: httpx.Response(200, json=gemini_answer("ठीक"))),
                                     sleep=no_wait)  # fmt: skip
    assert no_usage.transcribe([CHUNK])[0].usage is None  # never a guessed count


def test_gemini_2_5_flash_thinks_nothing_and_must_answer_itself() -> None:
    seen: list[httpx.Request] = []
    answers = [{**gemini_answer("ठीक है"), "modelVersion": "gemini-2.5-flash"},
               {**gemini_answer("ठीक है"), "modelVersion": "gemini-3.5-flash-lite"}]  # fmt: skip

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=answers[len(seen) - 1])

    p = gemini.GeminiProvider("k", model="gemini-2.5-flash", client=mocked(handler), sleep=no_wait)
    assert [w.text for w in p.transcribe([CHUNK])[0].words] == ["ठीक", "है"]
    assert json.loads(seen[0].content)["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    assert seen[0].url.path.endswith("/gemini-2.5-flash:generateContent")
    # Google routes retired 2.5 Flash to 3.5 Flash-Lite from 2026-12-01: refused, never a silent swap.
    with pytest.raises(ProviderError, match=r"answered by gemini-3\.5-flash-lite"):
        p.transcribe([CHUNK])
    # Other Gemini models keep their own thinking settings.
    three = gemini.GeminiProvider(
        "k", model="gemini-3.8-flash", client=mocked(lambda r: httpx.Response(200, json=gemini_answer("x")))
    )
    assert "thinkingConfig" not in three.body(CHUNK)["generationConfig"]
    assert token_cost_inr("gemini/gemini-2.5-flash", TokenUsage(1_000_000, 1_000_000), 100.0) == pytest.approx(350.0)


def test_token_billed_cost_counts_output_and_thinking() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000, thinking_tokens=600_000)
    # Gemini 3.8 Flash: $0.75 per 1M input and $3.75 per 1M output (thinking included), until 2026-12-31.
    assert token_cost_inr("gemini/gemini-3.8-flash", usage, 100.0) == pytest.approx(450.0)
    assert token_cost_inr("gemini/gemini-3.8-flash", usage, None) is None  # no rate: never converted with a guess
    assert token_cost_inr("sarvam/saaras:v4", usage, 100.0) is None  # not billed by tokens


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
    assert "openai:gpt-4o-mini-transcribe" not in offered  # writes Hindi in other scripts (registry CHOICES)
    chosen = build_transcriber(s, "openai:gpt-transcribe")
    assert chosen.primary.model_id == "openai/gpt-transcribe"
    assert chosen.fallbacks == ()  # the configured fallback is the chosen provider itself: never twice
    assert [f.name for f in build_transcriber(s).fallbacks] == ["openai"]


def test_model_name_reads_transcript_ids_upload_choices_retired_models_and_files() -> None:
    from sabha_asr.registry import model_name

    assert model_name("sarvam/saaras:v4") == "Sarvam Saaras v4"
    assert model_name("deepgram:nova-3") == "Deepgram Nova-3 (Hindi and English)"
    assert model_name("openai/gpt-4o-mini-transcribe") == "OpenAI gpt-4o-mini-transcribe"
    assert model_name("import:google-meet") == "Transcript file"
    assert model_name("mystery") == "mystery"
