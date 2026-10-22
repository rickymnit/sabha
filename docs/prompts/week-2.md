# Week 2 — Orchestration and the first half of the audio pipeline

Goal: an upload flows automatically through cleaning and speaker detection, and the dashboard shows it live.

---

## P2.6 · Live status over Server-Sent Events

Plan task 2.6.

```text
Add GET /v1/events (SSE). Authenticated; subscribes to Redis channel events:{tenant_id}; filters events
to what the caller may see (staff: only their own person_id's recordings); sends heartbeats every 15 s;
supports Last-Event-ID by replaying the last 5 minutes from the outbox.
Web: a useLiveEvents() hook that updates TanStack Query caches for recording lists and detail; reconnects
with backoff; falls back to polling every 5 s if SSE fails.
Tests: a staff user does not receive another person's events; reconnect replays missed events.
```

Done when: the recordings list updates without a refresh as a job moves.

---

## P1.7 · Organisation profiles and label dictionary

> **Status (2026-10-17).** Already built: profile defaults for school, college and company (sabha_core/profiles.py) and `Tenant.from_profile` (P1.6). Remaining: `POST /v1/admin/tenants`, `PATCH /v1/settings`, `useLabels()` in the web app, and blocking uploads of disabled types.

Plan task 1.7.

```text
Implement organisation profiles.

- packages/core/sabha_core/profiles.py: defaults for school, college and company: enabled_types,
  labels (person, person_plural, recording, recording_plural, unit, manager), default rubric ids per type,
  consent defaults (school strictest), retention_days.
- POST /v1/admin/tenants (internal admin only) creates a tenant from a profile; PATCH /v1/settings lets an
  owner rename labels and toggle enabled types within plan limits.
- The web app reads labels everywhere via useLabels() (from P6.2).
Tests: each profile yields correct defaults; staff cannot change settings; disabling a type blocks new uploads
of that type but keeps old reports readable.
```

Done when: switching a test tenant to `company` changes the UI words to Sales rep, Call, Team.

---

## P1.8 · Audit log

> **Status (2026-10-19).** Partly built: the `AuditEntry` model, `audit_log` collection with its (tenant_id, at) index, and `sabha_api.audit.audit()` used for `recording.create` (P2.1). Remaining: the other actions as their routes land, `GET /v1/audit` (owner/admin, filters, cursor pagination) and the immutability tests.

Plan task 1.8.

```text
Implement an append-only audit_log: {tenant_id, actor_user_id, actor_role, action, target_type, target_id,
at, ip, user_agent, request_id, meta}. Actions: recording.create, recording.play, recording.download,
transcript.view, analysis.view, score.dispute, score.change, export.create, settings.change, user.invite,
data.erase. Helper audit(...) used by services; no update or delete paths exist. GET /v1/audit (owner/admin,
filters, cursor pagination). Add a TTL-free index on (tenant_id, at). Playback is logged when the API issues
a presigned GET URL for audio.
Tests: every listed action writes an entry; staff cannot read the audit log; audit entries cannot be modified.
```

Done when: opening a recording's audio writes an audit entry visible to an admin.

---

## P3.2 · Validate and normalise audio

> **Status (2026-10-20).** Built: `apps/workers/sabha_workers/stages/preprocess.py`. It writes `normalised.wav`, `playback.opus` and `audio.json`, and records `duration_ms` and `audio` on the recording. Checked on a real 21-minute lecture (mp3 with cover art).

Plan task 3.2.

```text
Implement the preprocess stage (apps/workers/tasks/preprocess.py, queue cpu.preprocess), step 1 of 2.

- Download the original from S3 to a temp dir; ffprobe it; reject (PermanentError, code invalid_audio) corrupt
  files, unsupported codecs, duration < 30 s or > 3 h; store duration, codec, sample rate, channels.
- ffmpeg to 16 kHz mono PCM WAV with EBU R128 loudness normalisation and a high-pass filter (~80 Hz); write
  normalised.wav and a 32 kbps Opus playback copy (playback.opus) to {tenant}/{rec}/preprocess@v1/.
- Never modify the original object.
Tests with small fixture files: mp3, m4a, wav, webm with audio, a video mp4 (audio extracted), a corrupt file,
a too-short file.
```

Done when: any supported fixture produces `normalised.wav` and `playback.opus`.

---

## P3.3 · Voice activity detection and segment map

> **Status (2026-10-20).** Built: `apps/workers/sabha_workers/stages/vad.py` (Silero VAD v6.2.3 through onnxruntime, model pinned by SHA-256 and fetched by `make models`, telemetry forced off: docs/security/findings.md #7). It is step 2 of the preprocess stage and writes `compact.wav` and `segments@v1.json`; a recording with no speech goes to NEEDS_REVIEW (`no_speech`). Every time mapped exactly in both directions on 2 real dev files (a 21-minute lecture and an 18-minute interview). Remaining: 3 more real files for the "done when", and tuning the `VAD_*` settings (unmeasured defaults) on the gold set.

Plan task 3.3. **Tests first** for the time mapping.

```text
Implement preprocess step 2: Silero VAD and the segment map.

- Run Silero VAD on normalised.wav; add 300 ms end padding to each speech region (LIS showed Silero clips
  250–350 ms off utterance ends); merge gaps shorter than 1.5 s; keep params in settings.
- Produce segments@v1.json: [{orig_start_ms, orig_end_ms, compact_start_ms}], plus compact.wav containing
  only speech, and stats {total_ms, speech_ms, silence_ms, longest_silence_ms}.
- sabha_core/timemap.py: compact_to_original(ms) and original_to_compact(ms) with binary search; exact at
  segment boundaries.
- Then transition PREPROCESSING → DIARIZING.

Tests first: mapping round-trips; boundaries; property test with random segment maps; stats add up.
```

Done when: 5 real files have segment maps that round-trip exactly.

---

## P3.4a · Diarization (first pass)

> **Status (2026-10-21).** Built for CPU: `sabha_asr/diarization.py` (pyannote community-1, pinned revision; `ScriptedDiarizer` for tests) and `apps/workers/sabha_workers/stages/diarize.py`, which writes `diarization@v1.json` on both timelines. `make setup-speech` installs pyannote + CPU PyTorch and fetches the model (HF_TOKEN). Measured on this dev machine (CPU, 8 threads): 5 minutes of interview speech took 433 s (1.44x real time), 1.15 GB peak memory at batch size 8, 3 speakers; no network connections (strace). Telemetry off: docs/security/findings.md #7 and #8. Remaining: NeMo Sortformer and the GPU image's CUDA build (Dockerfile.gpu header) once a GPU exists; running on gold-set files.

Plan task 3.4 (continues in week 3).

```text
Implement the diarization stage (apps/workers/tasks/speech.py, queue gpu.speech).

- Behind an interface in sabha_asr/diarization.py with two implementations: pyannote (community model) and
  NVIDIA NeMo Sortformer; one is active via settings. Load the model once per worker process; run on the L4.
- Input compact.wav; output diarization@v1.json: turns [{speaker_label, start_ms, end_ms}] on the COMPACT
  timeline plus the same turns mapped to ORIGINAL time using timemap.
- For teaching recordings, allow many raw speakers; role assignment (P3.6) collapses students later.
- Record GPU time and real-time factor in stage_runs meta.
Tests: interface contract with a fake model; a short fixture with two speakers on GPU-less CI uses the fake.
```

Done when: diarization runs on staging GPU for gold-set files.

---

## P6.3 · Upload screen

Plan task 6.3. Read first: `docs/design/03-upload.png`, `docs/design/source/Upload.dc.html`.

```text
Build /upload matching docs/design/03-upload.png.

- Drag-and-drop zone + "Choose files"; client-side validation (format, size <= 1 GB, duration read via an
  <audio> element where possible); duplicate check by name+size in the current list.
- Per-file: type select (tenant enabled types), person select, status, progress bar, remove/cancel/resume.
- Upload flow: compute SHA-256 in a Web Worker (streamed), POST /v1/recordings with an Idempotency-Key,
  upload parts in parallel (3 at a time) with retry and resume (persist upload state in IndexedDB so a page
  reload resumes), POST /complete.
- Consent checkbox and plan-hours estimate panel as in the design (consent is enforced server-side in P6.9).
- Accessible: keyboard operable, aria-live status updates.
Tests: Vitest for the upload state machine; Playwright uploading a fixture and simulating a dropped connection.
```

Done when: a 1 GB file survives a network drop and resumes.

---

## P6.4a · Overview shell with live status

Plan task 6.4 (finished in week 5 with real numbers).

```text
Build / (Overview) matching docs/design/01-overview.png: metric strip (placeholders), "Processing now"
counts per stage from GET /v1/recordings/stats (implement it: counts by status for the tenant), recent
recordings table from GET /v1/recordings (cursor pagination, filters by type), live updates via
useLiveEvents(). Leave the "Where coaching helps most" panel as an empty state until week 5.
Tests: table renders statuses with the right chips; live event updates a row.
```

Done when: uploads appear and change status live on the overview.

---

## P7.1 · Monitoring and tracing

> **Status (2026-10-17).** Already built: OpenTelemetry tracing set-up for the API (sabha_core/telemetry.py). Remaining: trace propagation through outbox and Celery, Prometheus metrics, Grafana dashboards, Sentry.

Plan task 7.1.

```text
Set up observability for staging.

- OpenTelemetry: API and workers export traces to the otel-collector; the recording_id is set as a span
  attribute and the trace context is propagated through outbox events and Celery headers, so one trace shows a
  recording's whole journey.
- Prometheus metrics: HTTP latency by route, queue depth and age per queue, stage duration, retries, DLQ size,
  GPU utilisation and memory (DCGM exporter on the GPU VM), LLM tokens and cost (from P5.1 later).
- Grafana dashboards as JSON in infra/grafana/: "Pipeline", "API", "GPU", "LLM cost".
- Sentry for API, workers and web with release = git SHA; scrub PII.
Tests: a smoke test that a span carries recording_id across the API → relay → worker hop.
```

Done when: one recording's full journey is visible as a single trace in staging.
