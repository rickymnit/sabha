# ADR 0012: More speech-to-text providers, and comparing them on our own calls

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

Sarvam (ADR 0006) is the only speech-to-text provider, at ₹0.49 per audio minute. The owner finds it costly and
wants to try cheaper models on the same calls and see the difference before switching. The owner chose: OpenAI,
Qwen (Alibaba Cloud), Amazon Transcribe and a self-hosted Whisper.

**Data residency.** Golden rule 12 keeps data in India. On 2026-11-13 the owner decided that, for these calls,
providers outside India are acceptable ("models all over the world would work"). This ADR records that decision.
OpenAI and Qwen's international endpoint (Singapore) process audio outside India. Amazon Transcribe in ap-south-1
(Mumbai) and the self-hosted Whisper keep it in India.

Prices, from each provider's own published figures (checked 2026-11-13, kept in `sabha_asr.pricing` with sources):

| Model | Published price | Word times |
| --- | --- | --- |
| `sarvam/saaras:v4` | ₹0.49 / min | phrases only |
| `openai/gpt-transcribe` | $0.0045 / min | none (text only) |
| `openai/gpt-4o-mini-transcribe` | $0.003 / min (deprecated, shut down 2027-02-26) | none |
| `qwen/qwen3-asr-flash` | $0.000035 / s ($0.0021 / min), international | none |
| `aws/transcribe@ap-south-1` | $0.0001 / s ($0.006 / min), Mumbai | per word |
| `whisper/*` (self-hosted) | no per-minute price; the machine it runs on | per word |

## Decision

1. **Four new providers behind the existing interface** (`packages/asr/sabha_asr/providers/`): `openai`, `qwen`,
   `aws`, `whisper`. Each returns the same `ChunkResult`s, so nothing after the transcribe stage changes. Providers
   without word times spread each chunk's text across it (word_timing "approximate"), as Sarvam's phrases are.
2. **Switching is configuration**: `ASR_PROVIDER` and `ASR_MODEL`, then a restart of the speech worker. Fallbacks stay
   explicit (`ASR_FALLBACKS`, golden rule 7).
3. **Prices keep their currency.** A dollar price becomes rupees only with the configured `USD_INR_RATE`; without it
   the rupee cost is None. AWS is priced for Mumbai only; another region costs None until its price is checked.
4. **A comparison tool, `eval/asr_compare.py`**, sends the same chunks of existing calls to each chosen model, reuses
   Sarvam's saved answers (no second payment), and writes a local HTML report: transcripts side by side, cost, speed,
   and how much each differs from Sarvam. Without human-checked transcripts (the gold set is empty) the difference is
   **not accuracy**: it says where the models disagree, and a person listens to decide who is right. Word error rate
   against a gold transcript is reported only by `eval/wer.py` (golden rule 6).
5. **Self-hosted Whisper is an optional install** (`uv sync --extra whisper`, faster-whisper). It is not part of the
   API or CPU worker images.

## Consequences

- Providers without word times give coarser speaker attribution inside a chunk (as with Sarvam). Amazon Transcribe and
  Whisper give word times.
- Whisper picks one language per chunk; Hindi-English switching is written in the script it chose. Qwen takes one
  language hint or detects it. Sarvam and Amazon Transcribe (with language identification) handle switching inside a
  chunk.
- The comparison report holds call transcripts, so it stays on this machine (`eval/reports/`, not committed) and is
  not published.
- Golden rule 12 in CLAUDE.md still says "data stays in India"; this ADR is the owner's recorded exception for speech
  recognition.
