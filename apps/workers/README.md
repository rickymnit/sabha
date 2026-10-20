# apps/workers

The Celery 5 workers that run the processing pipeline on Redis queues (`cpu.preprocess`, `gpu.speech`, `llm.analyze`, `io.notify`, `billing.meter`) plus the outbox relay. Each task (preprocess, speech, analyze, notify, meter, relay) is idempotent: it checks for its output artefact at `{tenant_id}/{recording_id}/{stage}@{version}/` before doing work, runs with `acks_late=True`, and moves recordings only through the state machine in `sabha_core/state.py`.

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
