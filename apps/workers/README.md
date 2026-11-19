# apps/workers

The Celery 5 workers that run the processing pipeline on Redis queues (`cpu.preprocess`, `gpu.speech`, `llm.analyze`, `io.notify`, `billing.meter`), the outbox relay (`make relay`) and the scheduler (`make beat`). Each task (preprocess, speech, analyze, notify, meter, relay) is idempotent: it checks for its output artefact at `{tenant_id}/{recording_id}/{stage}@{version}/` before doing work, runs with `acks_late=True`, and moves recordings only through the state machine in `sabha_core/state.py`.

## Preprocess (P3.2, P3.3)

`sabha_workers/stages/preprocess.py` checks the upload, normalises it with ffmpeg and finds the speech with Silero
VAD. It writes `normalised.wav`, `playback.opus`, `compact.wav` (speech only), `segments@v1.json` (the map back to
the original timeline) and `audio.json` under `{tenant}/{recording}/preprocess@{version}/`.

It needs:

- `ffmpeg` and `ffprobe` on the PATH (installed in the worker images; `apt install ffmpeg` on a dev machine);
- the Silero VAD model file. Run `make models` once. It downloads the pinned file (`sabha_workers/stages/vad.py`:
  URL and SHA-256) to `~/.cache/sabha/models/`. The CPU worker image fetches it at build time and sets
  `VAD_MODEL_PATH`. The model is never downloaded while a recording is being processed.

The VAD settings (`VAD_*` in `.env.example`) are unmeasured starting values; tune them on the gold set.

## Diarization (P3.4)

`sabha_workers/stages/diarize.py` runs speaker diarization on `compact.wav` and writes `diarization@v1.json` under
`{tenant}/{recording}/diarize@{version}/`: the turns on the compact timeline and the same turns on the original
recording timeline. The model sits behind `sabha_asr/diarization.py`.

On a dev machine (CPU):

1. Create a free Hugging Face account, accept the conditions of
   [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) and
   [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0), and put a read token in `.env` as
   `HF_TOKEN`.
2. `make setup-speech`: installs pyannote.audio and CPU-only PyTorch (the optional `speech` extra) and fetches the
   pinned model to `~/.cache/sabha/models/`. A later plain `uv sync` or `make setup` removes the extra again; run
   `make setup-speech` after it.

The token is used only to download the model. While a recording is processed, the model loads from the local
folder with the Hugging Face hub offline, and pyannote's own usage telemetry is switched off
(`docs/security/findings.md` #8).

How many speakers are asked for: the number set at upload, else 3 for a support call a colleague helped on, else
the type's default (support: 2), else pyannote decides (`speaker_count` in `diarize.py`; ADR 0014, ADR 0015).

Model attribution: speaker diarization uses
[pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) by
pyannoteAI, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), with
[pyannote.audio](https://github.com/pyannote/pyannote-audio) (MIT).

## Transcribe and the transcript (P3.5 to P3.7)

`stages/transcribe.py` sends `compact.wav` in chunks to the speech-to-text model chosen at upload
(`Recording.asr_choice`) or the configured one, and stores each chunk's words (and, for Gemini, the tokens billed).
`stages/transcript.py` then builds `transcript@v1.json` on the original timeline:

1. Speaker roles from what each speaker does (ADR 0011), or, for a support call a colleague helped on, the two agent
   voices and the customer (`sabha_asr/transfer.py`, `transfer@v1.json`; ADR 0015). Unclear roles send the
   recording to review.
2. If the uploader chose it, the Gemini speaker check (`sabha_asr/speaker_check.py`, `speaker_check@v1.json`;
   ADR 0014). It needs `GEMINI_API_KEY`; if Gemini fails the stage fails (`speaker_check_unavailable` is retried,
   `speaker_check_failed` is not).
3. The speech-to-text cost in rupees (by minute, or by tokens for Gemini, plus the speaker check).

## Analyze (P5.4 to P5.8)

`stages/analyze.py` computes the numbers in code (`sabha_analytics.metrics`), asks the LLM through `sabha_llm`
(PII masked first) to judge each rubric point with quotes, keeps only quotes the grounding check finds in the
transcript, and writes the scores, the summary and, for sales and support, the plus and drawback list (ADR 0013).

## Scheduled jobs (`make beat`)

| Task | Every | What it does |
| --- | --- | --- |
| `sabha.maintenance.abort_stale_uploads` | hour | Cancels uploads never completed |
| `sabha.maintenance.requeue_stuck` | 5 minutes | Sends again any stage whose worker died |
| `sabha.maintenance.expire_audio` | day | Deletes audio past the workspace's retention (`docs/runbook.md`) |
| `sabha.maintenance.backup` | day | Exports the database to the backups bucket (`docs/runbook.md`) |
