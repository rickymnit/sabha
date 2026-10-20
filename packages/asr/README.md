# packages/asr

`sabha_asr`, the multi-provider speech-recognition layer. Configuration picks one active provider per deployment; any fallback must be configured explicitly and is logged with its reason, never applied silently (golden rule 7). Decision record: [ADR 0006](../../docs/adr/0006-asr-sarvam.md).

| Module | What it does |
| --- | --- |
| `provider.py` | The `AsrProvider` interface, its standard output (`ChunkResult`: words, language spans), `ProviderError`, and `spread_words` for providers that time phrases only |
| `transcriber.py` | Runs the configured provider and, only if configured, its fallbacks; records which provider answered, why, and the real-time factor |
| `registry.py` | Builds the transcriber from `ASR_PROVIDER` / `ASR_FALLBACKS`; unknown names fail at start-up |
| `providers/sarvam.py` | Sarvam AI REST speech-to-text: chunks under 30 s, phrase timestamps turned into approximate word times, no confidence |
| `providers/fake.py` | Canned words for tests and local development (refused in staging and production) |
| `chunking.py`, `batcher.py` | Chunk planning at VAD joins with overlap and de-duplication; the request batcher (P3.5) |
| `words.py`, `roles.py`, `assembly.py` | Words and turns, speaker roles, transcript@v1 assembly on the original timeline (P3.6, P3.7) |

## Settings

`ASR_PROVIDER` (`sarvam`, or `fake` locally), `ASR_FALLBACKS`, `ASR_MODEL`, `ASR_LANGUAGE`, `SARVAM_API_KEY`, `SARVAM_BASE_URL`. See `.env.example`.

## Trying a provider by hand

```
ffmpeg -i sample.m4a -ar 16000 -ac 1 -c:a pcm_s16le sample.wav
uv run sabha-asr-transcribe sample.wav > words.jsonl
```

Use only audio you may send to the provider: real recordings need consent and Sarvam's data terms confirmed first (ADR 0006).

## Adding a provider

Write an adapter that satisfies `AsrProvider`, add it to `registry.PROVIDERS`, and add a factory to `PROVIDER_FACTORIES` in `tests/test_provider.py`: the shared contract tests then run against it.
