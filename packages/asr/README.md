# packages/asr

`sabha_asr`, the multi-provider speech-recognition layer, plus diarisation, speaker roles and transcript assembly.
Configuration picks one active provider per deployment, and owners and admins may choose another model per upload.
Any fallback must be configured explicitly and is logged with its reason, never applied silently (golden rule 7).
Decision records: [ADR 0006](../../docs/adr/0006-asr-sarvam.md) (Sarvam), [ADR 0012](../../docs/adr/0012-more-asr-providers.md)
(other providers), [ADR 0011](../../docs/adr/0011-evidence-based-speaker-roles.md) (roles),
[ADR 0014](../../docs/adr/0014-speaker-count-and-gemini-speaker-check.md) (speaker check),
[ADR 0015](../../docs/adr/0015-colleague-helped-calls.md) (colleague-helped calls).

| Module | What it does |
| --- | --- |
| `provider.py` | The `AsrProvider` interface, its output (`ChunkResult`: words, language spans, tokens billed), `TokenUsage`, `ProviderError`, and `spread_words` for providers that time phrases only |
| `transcriber.py` | Runs the chosen provider and, only if configured, its fallbacks; records which provider answered, why, and the real-time factor |
| `registry.py` | Builds the transcriber from `ASR_PROVIDER` / `ASR_MODEL` / `ASR_FALLBACKS`; `CHOICES` is the upload page's model list |
| `pricing.py` | Published prices: per minute (`PRICES`) and per token (`TOKEN_PRICES`, Gemini), with source and date |
| `providers/` | `sarvam`, `gemini`, `deepgram`, `openai`, `groq`, `qwen`, `aws`, `whisper` (self-hosted), and `fake` (tests and local only, refused in staging and production) |
| `chunking.py`, `batcher.py` | Chunk planning at VAD joins with overlap and de-duplication; the request batcher (P3.5) |
| `diarization.py` | pyannote behind one interface; asked for an exact number of speakers when one is known |
| `words.py`, `roles.py`, `role_evidence.py` | Words and turns; speaker roles from what each speaker does |
| `transfer.py` | Support calls a colleague helped on: the two agent voices, the customer and the handover point |
| `speaker_check.py` | The Gemini speaker check: lines, the question per 3-minute window, and moving lines between speakers |
| `assembly.py`, `imported.py` | transcript@v1 on the original timeline; transcripts uploaded as text (ADR 0009) |

## On the upload page

Sarvam Saaras v4, OpenAI Transcribe, Whisper Large v3 and Whisper Turbo (Groq), Deepgram Nova-3, Gemini 3.8 Flash,
Gemini 3.1 Flash-Lite, Gemini Flash-Lite and Whisper (own server). A model whose key is missing shows "not set up".
Qwen and Amazon Transcribe are left off (2026-11-19) but still work with `ASR_PROVIDER` and in
`eval/asr_compare.py`. Gemini 2.5 Flash and 2.5 Flash-Lite cannot be used: Google refuses them to our account.

## Settings

`ASR_PROVIDER`, `ASR_MODEL`, `ASR_FALLBACKS`, `ASR_LANGUAGE`, and each provider's key: `SARVAM_API_KEY`,
`GEMINI_API_KEY` (also needed for the speaker check), `DEEPGRAM_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`,
`DASHSCOPE_API_KEY` (Qwen), `AWS_TRANSCRIBE_*`. See `.env.example`.

## Trying a provider by hand

```
ffmpeg -i sample.m4a -ar 16000 -ac 1 -c:a pcm_s16le sample.wav
uv run sabha-asr-transcribe sample.wav > words.jsonl
```

Use only audio you may send to the provider: real recordings need consent, and Gemini, Deepgram,
OpenAI, Groq and Qwen are outside India (ADR 0012).

## Adding a provider

Write an adapter that satisfies `AsrProvider` in `providers/`, add a factory to `registry.PROVIDERS`
and its default model to `DEFAULT_MODELS`, its price to `pricing.py` (with the source and the date checked), and, to
offer it at upload, a row in `registry.CHOICES`. Try it on a real call with `eval/asr_compare.py` before offering it.
