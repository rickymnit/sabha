# ADR 0006: Sarvam AI for speech recognition, with approximate word timing

- **Status:** Accepted
- **Date:** 2026-10-17
- **Plan task:** 3.1

## Context

The plan expected to port an ASR layer from an earlier "LIS" codebase. That codebase does not exist (ADR 0001
correction), so `packages/asr` builds its provider layer from scratch. The owner chose Sarvam AI's hosted
speech-to-text as the first provider: it targets Indian languages and Hindi-English switching, needs no GPU, and
Sarvam says it processes data in India (golden rule 12).

Sarvam's REST API (docs.sarvam.ai, read 2026-10-17) differs from what the pipeline assumed:

| The pipeline assumed | Sarvam's `POST /speech-to-text` |
| --- | --- |
| A start and end time per word | `timestamps` = parallel lists `words`, `start_time_seconds`, `end_time_seconds`, where each "word" is a phrase or sentence |
| A confidence per word | No confidence |
| Chunks of about 30 s | At most 30 s per request (the Batch API takes 2 h, also phrase-level, and is asynchronous) |

## Decision

1. **Sarvam's REST API, one request per chunk.** Chunks stay under 29.5 s. Model `saaras:v4` by default
   (`ASR_MODEL` overrides; `saaras:v3` gets `mode=transcribe`). `language_code=unknown` detects the language unless
   `ASR_LANGUAGE` sets one.
2. **Approximate word timing.** Each phrase is split on whitespace and its time is shared among its words in
   proportion to their length (`sabha_asr.provider.spread_words`). Transcripts record `word_timing: "approximate"`.
3. **Word confidence is optional.** `Word.confidence` and `avg_confidence` may be null. Words without confidence are
   never marked low-confidence, so the transcript view shows no "unclear" highlighting for Sarvam transcripts.
4. **One provider, explicit fallbacks only.** `ASR_PROVIDER` picks one; `ASR_FALLBACKS` (empty by default) lists
   others to try in order. Every fallback use is logged with the reason and recorded in the outcome
   (golden rule 7). The fake provider is refused in staging and production.
5. **Retries** follow Sarvam's error guide: 429 (except `insufficient_quota_error`), 500 and 503, timeouts and
   network errors are retryable; 400, 403, 413, 422 and out-of-credits are not. Retrying belongs to the stage.

## Consequences

- **Speaker attribution is phrase-accurate, not word-accurate.** Words are given to speakers by their times. A
  phrase in which the speaker changes is split approximately, which affects talk share, question counts and quote
  timestamps. We measure speaker-attribution error on the gold set (P4.3 roles eval) before trusting these numbers.
  If it is too high, the next step is a self-hosted forced aligner on the GPU worker for real word times.
- **Playback positions** for quotes are accurate to the phrase, not the word.
- **Before any real recording is sent:** confirm in writing Sarvam's data location, retention (zero-day retention
  is offered on request) and that inputs are not used for training. Their public pages and third-party summaries
  disagree on training terms. Until then, use only test audio.
- **Cost and speed** are unknown until measured: the transcriber records audio and compute milliseconds per batch
  (real-time factor), and stage runs keep them for cost reports. No figures are assumed here (golden rule 6).
- **Dependencies:** `httpx` in `sabha-asr` (sync HTTP for the Celery worker).
- Adding another provider (for example a self-hosted model chosen by a bake-off) is one adapter, one registry entry
  and the shared contract tests in `packages/asr/tests/test_provider.py`.
