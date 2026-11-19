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
5. **Owners and admins may choose the model per upload** (added 2026-11-13 at the owner's request). The upload page
   lists the models in `sabha_asr.registry.CHOICES` with their price per audio hour (`GET /v1/speech-models`); ones
   whose key is missing are shown but cannot be chosen. The recording keeps the choice (`asr_choice`, audited on
   create), its cost estimate uses that model's price, and the speech worker builds that model for it. Other roles
   cannot choose (403); without a choice the configured model is used.
6. **Self-hosted Whisper is an optional install** (`uv sync --extra whisper`, faster-whisper). It is not part of the
   API or CPU worker images.

7. **Only English, Hindi and Hinglish in transcripts** (owner, 2026-11-13). Left to detect the language itself,
   OpenAI's models wrote parts of a Hindi call in Urdu and Bengali script. So:
   - With ASR_LANGUAGE "unknown", gpt-transcribe is told to expect Hindi and English (`languages` hi, en) and the
     older OpenAI models are told Hindi.
   - No sample `prompt` is sent. As a test, a Hinglish sample prompt was tried on one support call;
     gpt-4o-mini-transcribe copied it into 12 of 44 pieces, which would put words nobody said in the transcript.
   - The transcribe stage asks again, in Hindi, any chunk written in a script other than Latin and Devanagari, for
     every provider. A chunk still in another script is kept and counted (`still_other_script`), never dropped.
   - On that call: gpt-transcribe gave 0 of 44 pieces in another script. gpt-4o-mini-transcribe gave 18 of 44 in
     Urdu or Telugu script even with `language` hi, so it is no longer offered on the upload page.

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

## Addendum 2026-11-16: Groq

The owner added Groq (Whisper Large v3 and Whisper Large v3 Turbo, hosted by Groq in the US) under the same
residency exception. Groq serves OpenAI's transcription API, so `providers/groq.py` is the OpenAI provider with
Groq's address and models; both models return word times. Groq's published prices (0.111 and 0.04 USD per audio
hour, minimum 10 s billed per request) are in `sabha_asr/pricing.py`. Its per-minute limits are low on the free
plan, so Groq waits out a rate limit longer (8 retries) than OpenAI does.

## Addendum 2026-11-16: Deepgram and Gemini, for Hindi-English code-mix

The owner wants Hindi written in Devanagari and English words in Latin letters, at about Whisper's price. Whisper
cannot do this safely: without a language it translated Hindi into English and wrote Urdu; with a mixed sample prompt
it copied the sample into near-silent pieces. Added under the same residency exception:

- `deepgram` (Nova-3, `language=multi` with hi/en hints): code-mix with word times; 0.0052 USD per minute.
- `gemini` (`gemini-3.8-flash`, `gemini-3.5-flash-lite`): a general model told to transcribe verbatim, never
  translate, and write each word in its own script. No word times. An answer with more than 6 words per second of
  audio is asked again once, then fails the chunk, so invented text never reaches a transcript (golden rule 5).
  Priced on audio input only (25 tokens per second); output tokens cost extra and are not counted.

Which one to use is decided on accuracy against hand-corrected transcripts (eval/wer.py), not on the difference from
Sarvam.

## Addendum 2026-11-19: the upload list, and what Gemini costs per hour

Gemini bills by tokens: audio in, plus the written answer and any "thinking", both billed as output. Since
2026-11-18 every Gemini answer's token counts are stored and priced (`TokenUsage`, `TOKEN_PRICES` in
`sabha_asr/pricing.py`), and Gemini answering with a different model than asked fails the chunk instead of being
used quietly (golden rule 7).

Measured on NiaLabs calls, at the published prices:

| Model | Thinking | Cost per audio hour | Measured on |
| --- | --- | --- | --- |
| Gemini 3.8 Flash | Google's default | about ₹148 (thinking was 88% of it) | 2026-11-18 |
| Gemini 3.8 Flash | low (no thinking tokens used) | about ₹13.3 | 174 s of the Roshan call, 2026-11-19 |
| Gemini 3.1 Flash-Lite | minimal | about ₹11.0 | 2026-11-18 |

The upload page's price list counts audio input only for Gemini, so it shows less than these figures.

The upload list (owner):

- **Gemini 3.8 Flash** is back on the list on 2026-11-19, asked to think "low".
- **Gemini 3.1 Flash-Lite** is Gemini's default model (2026-11-18). Google retires it on 2027-05-07.
- **Gemini 2.5 Flash and 2.5 Flash-Lite** are not offered: Google refuses both to our account (HTTP 404, "no longer
  available to new users", 2026-11-18).
- **Qwen3 ASR Flash and Amazon Transcribe** are off the list on 2026-11-19. Their adapters stay for
  `eval/asr_compare.py`.
