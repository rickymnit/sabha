"""The provider contract (every registered provider), spread_words, transcriber fallback rules and the registry."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from itertools import pairwise
from typing import Any

import httpx
import pytest

from sabha_asr.provider import AsrProvider, AudioChunk, ProviderError, spread_words
from sabha_asr.providers.fake import FakeProvider
from sabha_asr.providers.sarvam import SarvamProvider
from sabha_asr.registry import AsrConfigError, build_transcriber
from sabha_asr.transcriber import Transcriber
from sabha_asr.words import Word
from sabha_core.settings import Settings

CHUNKS = [AudioChunk("c1", b"RIFF-fake-1", 4_000), AudioChunk("c2", b"RIFF-fake-2", 12_000)]

# --- spread_words ---


def test_spread_words_tiles_the_phrase_by_length() -> None:
    words = spread_words("aaj hum padhenge", 1_000, 2_400)
    assert [(w.text, w.start_ms, w.end_ms) for w in words] == [
        ("aaj", 1_000, 1_300),
        ("hum", 1_300, 1_600),
        ("padhenge", 1_600, 2_400),
    ]
    assert all(w.confidence is None for w in words)


def test_spread_words_counts_devanagari_by_code_point() -> None:
    words = spread_words("नमस्ते आज", 0, 900)
    assert [w.text for w in words] == ["नमस्ते", "आज"]
    assert words[0].end_ms == words[1].start_ms and words[-1].end_ms == 900


def test_spread_words_never_leaves_gaps_or_overruns() -> None:
    words = spread_words("a bb ccc dddd eeeee", 7, 20)
    assert words[0].start_ms == 7 and words[-1].end_ms == 20
    assert all(a.end_ms == b.start_ms for a, b in pairwise(words))


def test_spread_words_in_a_zero_length_phrase_gives_zero_length_words() -> None:
    assert [(w.start_ms, w.end_ms) for w in spread_words("ek do", 500, 500)] == [(500, 500), (500, 500)]


def test_spread_words_of_blank_text_is_empty() -> None:
    assert spread_words("   ", 0, 100) == []


def test_spread_words_rejects_bad_times() -> None:
    with pytest.raises(ValueError):
        spread_words("ek", 200, 100)


# --- Contract: every provider produces the same shapes ---


def sarvam_ok() -> SarvamProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"request_id": "r", "transcript": "aaj hum", "language_code": "hi-IN"})

    return SarvamProvider("test-key", client=httpx.Client(transport=httpx.MockTransport(handler)))


PROVIDER_FACTORIES: dict[str, Callable[[], AsrProvider]] = {"fake": FakeProvider, "sarvam": sarvam_ok}


@pytest.fixture(params=sorted(PROVIDER_FACTORIES))
def provider(request: pytest.FixtureRequest) -> Iterator[AsrProvider]:
    yield PROVIDER_FACTORIES[request.param]()


def test_every_registered_provider_is_covered_by_the_contract() -> None:
    from sabha_asr.registry import PROVIDERS

    assert set(PROVIDERS) == set(PROVIDER_FACTORIES)


def test_contract_one_result_per_chunk_in_order(provider: AsrProvider) -> None:
    results = provider.transcribe(CHUNKS)
    assert [r.chunk_id for r in results] == ["c1", "c2"]


def test_contract_words_are_ordered_and_inside_the_chunk(provider: AsrProvider) -> None:
    for chunk, result in zip(CHUNKS, provider.transcribe(CHUNKS), strict=True):
        assert result.words, "the canned responses all contain speech"
        assert all(isinstance(w, Word) for w in result.words)
        assert all(0 <= w.start_ms <= w.end_ms <= chunk.duration_ms for w in result.words)
        assert [w.start_ms for w in result.words] == sorted(w.start_ms for w in result.words)
        assert result.text == " ".join(w.text for w in result.words)


def test_contract_languages_cover_the_chunk(provider: AsrProvider) -> None:
    for chunk, result in zip(CHUNKS, provider.transcribe(CHUNKS), strict=True):
        assert result.languages
        assert result.languages[0].start_ms == 0 and result.languages[-1].end_ms == chunk.duration_ms


def test_contract_identity(provider: AsrProvider) -> None:
    assert provider.model_id.startswith(f"{provider.name}/")
    assert provider.word_timing in ("word", "approximate")
    assert 0 < provider.max_chunk_ms <= 30_000


# --- Transcriber: no silent fallback (golden rule 7) ---


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.5  # each read advances half a second: one transcribe call takes 0.5 s
        return self.now


DOWN = ProviderError("primary", "HTTP 503 rate_limit_exceeded_error", retryable=True)


def test_primary_answers_without_fallback() -> None:
    outcome = Transcriber(FakeProvider(), clock=Clock()).transcribe(CHUNKS)
    assert outcome.provider == "fake" and outcome.fallback_reason is None
    assert outcome.audio_ms == 16_000 and outcome.compute_ms == 500
    assert outcome.real_time_factor == pytest.approx(500 / 16_000)


def test_without_configured_fallbacks_the_error_is_raised_unchanged() -> None:
    primary = FakeProvider(name="primary", failure=DOWN)
    with pytest.raises(ProviderError) as raised:
        Transcriber(primary).transcribe(CHUNKS)
    assert raised.value is DOWN


def test_configured_fallback_is_used_logged_and_recorded(caplog: pytest.LogCaptureFixture) -> None:
    primary = FakeProvider(name="primary", failure=DOWN)
    backup = FakeProvider(name="backup")
    with caplog.at_level(logging.WARNING, logger="sabha.asr"):
        outcome = Transcriber(primary, [backup]).transcribe(CHUNKS)
    assert outcome.provider == "backup" and outcome.model_id == "backup/canned"
    assert outcome.fallback_reason == "primary: HTTP 503 rate_limit_exceeded_error"
    (record,) = caplog.records
    assert record.__dict__["failed_provider"] == "primary"
    assert record.__dict__["fallback_provider"] == "backup"
    assert record.__dict__["reason"] == "HTTP 503 rate_limit_exceeded_error"


def test_every_failure_is_recorded_and_the_last_raised_when_all_fail() -> None:
    second = ProviderError("second", "HTTP 500 internal_server_error", retryable=True)
    third = FakeProvider(name="third")
    outcome = Transcriber(
        FakeProvider(name="primary", failure=DOWN), [FakeProvider(name="second", failure=second), third]
    ).transcribe(CHUNKS)
    assert (
        outcome.fallback_reason == "primary: HTTP 503 rate_limit_exceeded_error; second: HTTP 500 internal_server_error"
    )

    with pytest.raises(ProviderError) as raised:
        Transcriber(
            FakeProvider(name="primary", failure=DOWN), [FakeProvider(name="second", failure=second)]
        ).transcribe(CHUNKS)
    assert raised.value is second


def test_bugs_are_never_handled_by_a_fallback() -> None:
    class Broken(FakeProvider):
        def transcribe(self, chunks: Any) -> Any:
            raise KeyError("bug")

    backup = FakeProvider(name="backup")
    with pytest.raises(KeyError):
        Transcriber(Broken(name="primary"), [backup]).transcribe(CHUNKS)
    assert backup.calls == []


def test_chunks_over_a_providers_limit_are_refused_before_calling_it() -> None:
    short = FakeProvider(max_chunk_ms=10_000)
    with pytest.raises(ValueError, match="limit"):
        Transcriber(short).transcribe(CHUNKS)
    assert short.calls == []


def test_mismatched_results_are_a_bug() -> None:
    class Shuffled(FakeProvider):
        def transcribe(self, chunks: Any) -> Any:
            return list(reversed(super().transcribe(chunks)))

    with pytest.raises(RuntimeError, match="do not match"):
        Transcriber(Shuffled()).transcribe(CHUNKS)


def test_a_provider_may_appear_only_once() -> None:
    with pytest.raises(ValueError, match="once"):
        Transcriber(FakeProvider(), [FakeProvider()])


def test_empty_batch_is_refused() -> None:
    with pytest.raises(ValueError):
        Transcriber(FakeProvider()).transcribe([])


# --- Registry and settings ---

BASE: dict[str, Any] = {
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


def settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **{**BASE, **overrides})  # type: ignore[call-arg]


def test_registry_builds_the_configured_provider_and_fallbacks() -> None:
    transcriber = build_transcriber(settings(asr_provider="sarvam", asr_fallbacks="fake", sarvam_api_key="k"))
    assert transcriber.primary.name == "sarvam" and transcriber.primary.model_id == "sarvam/saaras:v4"
    assert [f.name for f in transcriber.fallbacks] == ["fake"]


def test_registry_uses_the_configured_model() -> None:
    transcriber = build_transcriber(settings(asr_provider="sarvam", asr_model="saaras:v3", sarvam_api_key="k"))
    assert transcriber.primary.model_id == "sarvam/saaras:v3"


def test_no_fallback_unless_configured() -> None:
    assert build_transcriber(settings(asr_provider="fake")).fallbacks == ()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({}, "ASR_PROVIDER is not set"),
        ({"asr_provider": "whisper"}, "unknown ASR provider 'whisper'"),
        ({"asr_provider": "fake", "asr_fallbacks": "nope"}, "unknown ASR provider 'nope'"),
    ],
)
def test_registry_refuses_bad_configuration(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(AsrConfigError, match=message):
        build_transcriber(settings(**overrides))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"asr_provider": "sarvam"}, "SARVAM_API_KEY is required"),
        ({"asr_provider": "fake", "asr_fallbacks": "sarvam"}, "SARVAM_API_KEY is required"),
        ({"asr_provider": "fake", "asr_fallbacks": "fake"}, "must not repeat"),
        ({"asr_provider": "sarvam", "asr_fallbacks": "fake,fake", "sarvam_api_key": "k"}, "twice"),
    ],
)
def test_settings_refuse_inconsistent_asr_configuration(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        settings(**overrides)


def test_settings_refuse_the_fake_provider_when_deployed() -> None:
    deployed = {
        "app_env": "staging",
        "oidc_issuer": "https://auth.example.com",
        "s3_endpoint_url": None,
        "asr_provider": "fake",
    }
    with pytest.raises(ValueError, match="fake ASR provider"):
        settings(**deployed)
