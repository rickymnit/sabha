"""Builds the configured ASR provider and its explicit fallbacks from settings (ADR 0006, ADR 0012).

`build_transcriber(settings)` reads ASR_PROVIDER and ASR_FALLBACKS. An unset or unknown provider, or one without its
key, fails here, when the speech worker starts, not on the first recording. Adding a provider means one entry in
PROVIDERS and one in DEFAULT_MODELS.

`build_provider(name, settings, model)` builds one provider; `model` overrides ASR_MODEL, so a comparison
(eval/asr_compare.py) can run several models of one provider side by side. `parse_spec("openai:gpt-transcribe")`
splits such a "provider[:model]" spec.

Switching the pipeline to another provider is a configuration change: ASR_PROVIDER (and ASR_MODEL), then restart the
speech worker. Nothing is swapped on error unless ASR_FALLBACKS names it (golden rule 7).
"""

from __future__ import annotations

from collections.abc import Callable

from sabha_asr.provider import AsrProvider
from sabha_asr.transcriber import Transcriber
from sabha_core.settings import Settings


class AsrConfigError(ValueError):
    """The ASR settings cannot produce a working provider."""


DEFAULT_MODELS: dict[str, str] = {
    "fake": "fake",
    "sarvam": "saaras:v4",
    "openai": "gpt-transcribe",
    "qwen": "qwen3-asr-flash",
    "aws": "transcribe",
    "whisper": "large-v3-turbo",
}


def _fake(_: Settings, __: str) -> AsrProvider:
    from sabha_asr.providers.fake import FakeProvider

    return FakeProvider()


def _sarvam(settings: Settings, model: str) -> AsrProvider:
    from sabha_asr.providers.sarvam import SarvamProvider

    if settings.sarvam_api_key is None:
        raise AsrConfigError("SARVAM_API_KEY is not set")
    return SarvamProvider(settings.sarvam_api_key.get_secret_value(), model=model, language=settings.asr_language,
                          base_url=settings.sarvam_base_url)  # fmt: skip


def _openai(settings: Settings, model: str) -> AsrProvider:
    from sabha_asr.providers.openai import OpenAIProvider

    if settings.openai_api_key is None:
        raise AsrConfigError("OPENAI_API_KEY is not set")
    return OpenAIProvider(settings.openai_api_key.get_secret_value(), model=model, language=settings.asr_language,
                          base_url=settings.openai_base_url)  # fmt: skip


def _qwen(settings: Settings, model: str) -> AsrProvider:
    from sabha_asr.providers.qwen import QwenProvider

    if settings.dashscope_api_key is None:
        raise AsrConfigError("DASHSCOPE_API_KEY is not set")
    return QwenProvider(settings.dashscope_api_key.get_secret_value(), model=model, language=settings.asr_language,
                        base_url=settings.dashscope_base_url)  # fmt: skip


def _aws(settings: Settings, model: str) -> AsrProvider:
    from sabha_asr.providers.aws import DEFAULT_MODEL, AwsTranscribeProvider

    if model != DEFAULT_MODEL:
        raise AsrConfigError(f"Amazon Transcribe has one model, {DEFAULT_MODEL!r}; got {model!r}")
    if not settings.aws_transcribe_bucket:
        raise AsrConfigError("AWS_TRANSCRIBE_BUCKET is not set")
    key, secret = settings.aws_transcribe_access_key_id, settings.aws_transcribe_secret_access_key
    return AwsTranscribeProvider(
        bucket=settings.aws_transcribe_bucket, region=settings.aws_transcribe_region, language=settings.asr_language,
        access_key_id=key.get_secret_value() if key else None,
        secret_access_key=secret.get_secret_value() if secret else None,
    )  # fmt: skip


def _whisper(settings: Settings, model: str) -> AsrProvider:
    from sabha_asr.providers.whisper import WhisperProvider

    return WhisperProvider(model=model, device=settings.whisper_device, compute_type=settings.whisper_compute_type,
                           cpu_threads=settings.whisper_cpu_threads, language=settings.asr_language)  # fmt: skip


PROVIDERS: dict[str, Callable[[Settings, str], AsrProvider]] = {
    "fake": _fake,
    "sarvam": _sarvam,
    "openai": _openai,
    "qwen": _qwen,
    "aws": _aws,
    "whisper": _whisper,
}


def parse_spec(spec: str) -> tuple[str, str | None]:
    """ "openai:gpt-transcribe" -> ("openai", "gpt-transcribe"); "qwen" -> ("qwen", None)."""
    name, _, model = spec.strip().partition(":")
    return name, (model or None)


def model_for(name: str, settings: Settings, model: str | None = None) -> str:
    """The model `build_provider` would use: `model`, else ASR_MODEL for the configured provider, else the default."""
    if name not in DEFAULT_MODELS:
        raise AsrConfigError(f"unknown ASR provider {name!r}; known: {', '.join(sorted(PROVIDERS))}")
    if model:
        return model
    if name == settings.asr_provider and settings.asr_model:
        return settings.asr_model
    return DEFAULT_MODELS[name]


def model_id_for(name: str, settings: Settings, model: str | None = None) -> str:
    """The model id a provider records ("sarvam/saaras:v4", "aws/transcribe@ap-south-1"), without building it."""
    chosen = model_for(name, settings, model)
    suffix = f"@{settings.aws_transcribe_region}" if name == "aws" else ""
    return f"{name}/{chosen}{suffix}"


def build_provider(name: str, settings: Settings, model: str | None = None) -> AsrProvider:
    factory = PROVIDERS.get(name)
    if factory is None:
        raise AsrConfigError(f"unknown ASR provider {name!r}; known: {', '.join(sorted(PROVIDERS))}")
    return factory(settings, model_for(name, settings, model))


def build_transcriber(settings: Settings) -> Transcriber:
    if not settings.asr_provider:
        raise AsrConfigError("ASR_PROVIDER is not set")
    primary = build_provider(settings.asr_provider, settings)
    fallbacks = [build_provider(name, settings) for name in settings.asr_fallbacks]
    return Transcriber(primary, fallbacks)
