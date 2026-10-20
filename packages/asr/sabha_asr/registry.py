"""Builds the configured ASR provider and its explicit fallbacks from settings (ADR 0006).

`build_transcriber(settings)` reads ASR_PROVIDER and ASR_FALLBACKS. An unset or unknown provider fails here, when
the speech worker starts, not on the first recording. Adding a provider means one entry in PROVIDERS.
"""

from __future__ import annotations

from collections.abc import Callable

from sabha_asr.provider import AsrProvider
from sabha_asr.transcriber import Transcriber
from sabha_core.settings import Settings


class AsrConfigError(ValueError):
    """The ASR settings cannot produce a working provider."""


def _fake(_: Settings) -> AsrProvider:
    from sabha_asr.providers.fake import FakeProvider

    return FakeProvider()


def _sarvam(settings: Settings) -> AsrProvider:
    from sabha_asr.providers.sarvam import DEFAULT_MODEL, SarvamProvider

    if settings.sarvam_api_key is None:
        raise AsrConfigError("SARVAM_API_KEY is not set")
    return SarvamProvider(
        settings.sarvam_api_key.get_secret_value(),
        model=settings.asr_model or DEFAULT_MODEL,
        language=settings.asr_language,
        base_url=settings.sarvam_base_url,
    )


PROVIDERS: dict[str, Callable[[Settings], AsrProvider]] = {"fake": _fake, "sarvam": _sarvam}


def build_provider(name: str, settings: Settings) -> AsrProvider:
    factory = PROVIDERS.get(name)
    if factory is None:
        raise AsrConfigError(f"unknown ASR provider {name!r}; known: {', '.join(sorted(PROVIDERS))}")
    return factory(settings)


def build_transcriber(settings: Settings) -> Transcriber:
    if not settings.asr_provider:
        raise AsrConfigError("ASR_PROVIDER is not set")
    primary = build_provider(settings.asr_provider, settings)
    fallbacks = [build_provider(name, settings) for name in settings.asr_fallbacks]
    return Transcriber(primary, fallbacks)
