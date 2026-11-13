"""Builds the configured ASR provider and its explicit fallbacks from settings (ADR 0006, ADR 0012).

`build_transcriber(settings)` reads ASR_PROVIDER and ASR_FALLBACKS. An unset or unknown provider, or one without its
key, fails here, when the speech worker starts, not on the first recording. Adding a provider means one entry in
PROVIDERS and one in DEFAULT_MODELS.

`build_provider(name, settings, model)` builds one provider; `model` overrides ASR_MODEL, so a comparison
(eval/asr_compare.py) can run several models of one provider side by side. `parse_spec("openai:gpt-transcribe")`
splits such a "provider[:model]" spec.

Switching the pipeline to another provider is a configuration change: ASR_PROVIDER (and ASR_MODEL), then restart the
speech worker. Nothing is swapped on error unless ASR_FALLBACKS names it (golden rule 7).

An owner or admin may also choose the model per upload (`choices`, `chosen_spec`); the recording keeps the spec and
the speech worker builds that model for it (`build_transcriber(settings, spec)`).
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass

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


def build_transcriber(settings: Settings, spec: str | None = None) -> Transcriber:
    """The configured provider, or the model a recording was uploaded with (`spec`, "provider[:model]"). The
    configured fallbacks apply either way, except one naming the chosen provider (golden rule 7: never implicit)."""
    if spec:
        name, model = parse_spec(spec)
    elif settings.asr_provider:
        name, model = settings.asr_provider, None
    else:
        raise AsrConfigError("ASR_PROVIDER is not set")
    primary = build_provider(name, settings, model)
    fallbacks = [build_provider(other, settings) for other in settings.asr_fallbacks if other != name]
    return Transcriber(primary, fallbacks)


# --- Choosing a model per upload (owner, 2026-11-13) ---


@dataclass(frozen=True, slots=True)
class Choice:
    spec: str  # "provider:model", what an upload sends and a recording keeps
    name: str  # shown to people
    available: bool  # its key (or install) is in place, so the speech worker can use it
    default: bool  # the configured ASR_PROVIDER/ASR_MODEL


# The models offered on the upload page: provider, model, name. Not gpt-4o-mini-transcribe: on a Hindi support call it
# wrote 18 of 44 pieces in Urdu or Telugu script even when told the language is Hindi (owner's rule, 2026-11-13:
# transcripts only in English, Hindi and Hinglish). It stays usable in eval/asr_compare.py.
CHOICES: tuple[tuple[str, str, str], ...] = (
    ("sarvam", "saaras:v4", "Sarvam Saaras v4"),
    ("openai", "gpt-transcribe", "OpenAI Transcribe"),
    ("qwen", "qwen3-asr-flash", "Qwen3 ASR Flash"),
    ("aws", "transcribe", "Amazon (Mumbai)"),
    ("whisper", "large-v3-turbo", "Whisper (own server)"),
)


def is_set_up(name: str, settings: Settings) -> bool:
    """The provider's key (or, for Whisper, its optional install) is in place. Nothing is called."""
    if name == "sarvam":
        return settings.sarvam_api_key is not None
    if name == "openai":
        return settings.openai_api_key is not None
    if name == "qwen":
        return settings.dashscope_api_key is not None
    if name == "aws":
        return bool(settings.aws_transcribe_bucket)
    if name == "whisper":
        return importlib.util.find_spec("faster_whisper") is not None
    return name == "fake"


def choices(settings: Settings) -> list[Choice]:
    """The models an upload may choose, the configured one first and marked default."""
    configured = (
        f"{settings.asr_provider}:{model_for(settings.asr_provider, settings)}" if settings.asr_provider else None
    )
    found = [Choice(f"{p}:{m}", n, is_set_up(p, settings), f"{p}:{m}" == configured) for p, m, n in CHOICES]
    if configured and not any(c.default for c in found):  # e.g. "fake" in tests, or a model not listed
        found.append(Choice(configured, configured, True, True))
    return sorted(found, key=lambda c: not c.default)


def chosen_spec(spec: str, settings: Settings) -> str:
    """`spec` normalised to "provider:model" if it is offered and set up; AsrConfigError otherwise."""
    name, model = parse_spec(spec)
    full = f"{name}:{model_for(name, settings, model)}" if name in DEFAULT_MODELS else spec
    for choice in choices(settings):
        if choice.spec == full:
            if not choice.available:
                raise AsrConfigError(f"{choice.name} is not set up on this server")
            return full
    raise AsrConfigError(f"{spec!r} is not one of the speech-to-text models offered")
