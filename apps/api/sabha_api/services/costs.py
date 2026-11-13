"""Expected and actual cost of a recording, in rupees (owner's request, 2026-10-28: every role sees it).

Only Sabha's AI services are priced: speech-to-text and the LLM. Our own processing (normalising, silence and
speaker detection on our servers) has no per-recording price, so it is left out and the page says so. Every figure
comes from a published price or from measured usage (golden rule 6); what is missing is None, never guessed:

- speech-to-text: the provider's published price per minute (sabha_asr.pricing) times the audio sent;
- LLM: the cost the gateway recorded for each call from the published price table (llm_calls.cost_usd), in
  dollars, converted with USD_INR_RATE when it is set;
- the estimate at upload: the length the browser measured, times the expected share of speech (the median of this
  organisation's recent recordings of the type, or all of it without history), times the speech-to-text price,
  plus the median LLM cost per audio minute of those recordings. It is frozen on the recording when the upload is
  created, so the comparison afterwards is with what was shown then.
"""

from __future__ import annotations

from datetime import timedelta
from statistics import median

from pydantic import BaseModel

from sabha_api.auth import Principal
from sabha_api.services.results import visible_recording
from sabha_asr.pricing import cost_inr, price_for
from sabha_asr.registry import AsrConfigError, choices, model_id_for, parse_spec
from sabha_core.models import Analysis, CostEstimate, LlmCall, Person, Recording, Transcript, utc_now
from sabha_core.profiles import ConversationType
from sabha_core.repo import TenantRepo
from sabha_core.settings import Settings
from sabha_core.state import RecordingStatus

HISTORY_DAYS = 90
HISTORY_LIMIT = 200


class Sources(BaseModel):
    asr_model: str | None
    asr_inr_per_minute: float | None
    asr_price_source: str | None
    usd_inr_rate: float | None
    usd_inr_source: str | None


class Actual(BaseModel):
    asr_audio_minutes: float | None  # audio sent to speech-to-text, chunk overlaps included
    asr_inr: float | None
    llm_calls: int
    llm_unpriced_calls: int
    llm_usd: float | None
    llm_inr: float | None
    total_inr: float | None  # None unless both parts are known
    inr_per_minute: float | None  # total over the recording's length
    final: bool  # the recording is finished; until then the actual cost may still grow


class CostOut(BaseModel):
    recording_id: str
    duration_ms: int | None
    estimate: CostEstimate | None
    actual: Actual
    sources: Sources


class EstimateOut(BaseModel):
    estimate: CostEstimate
    inr_per_minute: float | None
    sources: Sources


def asr_model_id(settings: Settings, spec: str | None = None) -> str | None:
    """The speech-to-text model a recording is sent to, as sabha_asr names it ("sarvam/saaras:v4"): the one chosen
    at upload (`spec`, "provider:model"), else the configured one."""
    name, model = parse_spec(spec) if spec else (settings.asr_provider, None)
    if not name:
        return None
    try:
        return model_id_for(name, settings, model)
    except AsrConfigError:
        return None


class SpeechModelOut(BaseModel):
    id: str  # "provider:model", sent back as `asr_model` when creating a recording
    name: str
    available: bool  # set up on this server; the others are shown but cannot be chosen
    default: bool
    inr_per_hour: float | None  # None: no per-minute price (self-hosted) or no USD_INR_RATE


def speech_models(settings: Settings) -> list[SpeechModelOut]:
    """The speech-to-text models an upload may choose, with their published price per audio hour."""
    out = []
    for choice in choices(settings):
        model = asr_model_id(settings, choice.spec)
        price = price_for(model) if model else None
        per_minute = price.inr_per_minute(settings.usd_inr_rate) if price else None
        out.append(SpeechModelOut(id=choice.spec, name=choice.name, available=choice.available, default=choice.default,
                                  inr_per_hour=None if per_minute is None else round(per_minute * 60, 2)))  # fmt: skip
    return out


def sources(settings: Settings, model: str | None = None) -> Sources:
    """Where the prices come from; `model` is the speech-to-text model used (default: the configured one)."""
    model = model or asr_model_id(settings)
    price = price_for(model) if model else None
    return Sources(asr_model=model, asr_inr_per_minute=price.inr_per_minute(settings.usd_inr_rate) if price else None,
                   asr_price_source=price.source if price else None, usd_inr_rate=settings.usd_inr_rate,
                   usd_inr_source=settings.usd_inr_source)  # fmt: skip


async def estimate(
    kind: ConversationType, duration_ms: int, settings: Settings, *, recordings: TenantRepo[Recording],
    analyses: TenantRepo[Analysis], asr_spec: str | None = None,
) -> CostEstimate:  # fmt: skip
    since = utc_now() - timedelta(days=HISTORY_DAYS)
    done = await recordings.find({"type": kind.value, "status": RecordingStatus.COMPLETED.value,
                                  "created_at": {"$gte": since}, "duration_ms": {"$gt": 0}},
                                 sort=[("created_at", -1)], limit=HISTORY_LIMIT)  # fmt: skip
    shares = [min(1.0, r.speech_ms / r.duration_ms) for r in done if r.speech_ms is not None and r.duration_ms]
    lengths = {r.id: r.duration_ms or 0 for r in done}
    found = await analyses.find({"recording_id": {"$in": list(lengths)}, "status": "COMPLETED", "superseded": False,
                                 "cost_usd": {"$ne": None}}) if lengths else []  # fmt: skip
    usd_per_minute = [a.cost_usd / (lengths[a.recording_id] / 60_000) for a in found if a.cost_usd is not None]

    share = median(shares) if shares else 1.0
    model = asr_model_id(settings, asr_spec)
    asr = cost_inr(model, round(duration_ms * share), settings.usd_inr_rate) if model else None
    rate = settings.usd_inr_rate
    llm = median(usd_per_minute) * duration_ms / 60_000 * rate if usd_per_minute and rate else None
    total = asr + llm if asr is not None and llm is not None else None
    return CostEstimate(
        duration_ms=duration_ms, asr_inr=_r(asr), llm_inr=_r(llm), total_inr=_r(total), speech_share=round(share, 4),
        history_n=len(usd_per_minute), usd_inr_rate=rate,
    )  # fmt: skip


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


async def recording_cost(
    principal: Principal, recording_id: str, settings: Settings, *, recordings: TenantRepo[Recording],
    people: TenantRepo[Person], transcripts: TenantRepo[Transcript], llm_calls: TenantRepo[LlmCall],
) -> CostOut:  # fmt: skip
    recording = await visible_recording(principal, recording_id, recordings, people)
    found = await transcripts.find({"recording_id": recording.id}, sort=[("created_at", -1)], limit=1)
    transcript = found[0] if found else None
    calls = await llm_calls.find({"recording_id": recording.id})
    priced = [c.cost_usd for c in calls if c.cost_usd is not None]
    unpriced = len(calls) - len(priced)
    llm_usd = sum(priced) if calls and not unpriced else None  # a partly priced total would understate the cost
    rate = settings.usd_inr_rate
    llm_inr = llm_usd * rate if llm_usd is not None and rate else None
    asr_inr = transcript.asr_cost_inr if transcript else None
    total = asr_inr + llm_inr if asr_inr is not None and llm_inr is not None else None
    minutes = recording.duration_ms / 60_000 if recording.duration_ms else None
    actual = Actual(
        asr_audio_minutes=round(transcript.asr_billed_ms / 60_000, 2) if transcript and transcript.asr_billed_ms
        else None,
        asr_inr=_r(asr_inr), llm_calls=len(calls), llm_unpriced_calls=unpriced, llm_usd=_r(llm_usd),
        llm_inr=_r(llm_inr), total_inr=_r(total), inr_per_minute=_r(total / minutes) if total is not None and minutes
        else None,
        final=recording.status in (RecordingStatus.COMPLETED, RecordingStatus.FAILED),
    )  # fmt: skip
    return CostOut(recording_id=recording.id, duration_ms=recording.duration_ms, estimate=recording.cost_estimate,
                   actual=actual, sources=sources(settings, transcript.asr_model if transcript
                                                  else asr_model_id(settings, recording.asr_choice)))  # fmt: skip
