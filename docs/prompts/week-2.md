# Week 2 — Orchestration and the first half of the audio pipeline

Goal: an upload flows automatically through cleaning and speaker detection, and the dashboard shows it live.

---

## P2.4 · Celery queues, retries and dead-letter queue

Plan task 2.4. Read first: `CLAUDE.md` golden rule 3.

```text
Set up the worker system in apps/workers.

- celery_app.py: Redis broker/backend from settings; queues cpu.preprocess, gpu.speech, llm.analyze,
  io.notify, billing.meter; task routes by name prefix; acks_late=True; task_reject_on_worker_lost=True;
  prefetch multiplier 1 for gpu.speech and llm.analyze; per-queue visibility timeouts (gpu long).
- A base task class SabhaStageTask that: loads the recording via TenantRepo; skips if the output artefact
  exists (idempotency); records stage_runs start/finish; classifies exceptions into TransientError (retry with
  exponential backoff + jitter, max 5) and PermanentError (fail now); on final failure transitions to FAILED
  with an error code and pushes the job to a dead-letter collection `dlq` with full context; emits OTel spans
  and Prometheus metrics (queue wait, run time, retries).
- A heartbeat for long tasks; a beat schedule including the stale multipart cleanup from P2.2 and a
  "stuck jobs" sweeper that requeues jobs stuck in a running state past their timeout.
- Docker Compose services: workers-cpu (cpu.preprocess, io.notify, billing.meter, llm.analyze),
  workers-gpu (gpu.speech, concurrency 1), beat.

Tests: a task killed mid-run is redelivered and completes once; transient errors retry; permanent errors land
in dlq with context; existing artefact causes a skip.
```

Done when: killing a worker mid-job loses nothing (demonstrate in a test and manually).

---

## P2.5 · Transactional outbox and change-stream relay

Plan task 2.5.

```text
Make status changes and their events impossible to disagree.

- When transition() runs, write the status update and an outbox document {event_id, tenant_id, type,
  payload, created_at, published_at:null} in ONE MongoDB transaction (helper in sabha_core/outbox.py).
- apps/workers/relay.py: a long-running process that watches the outbox collection via a change stream
  (resume token persisted in Mongo), publishes each event (a) as a Celery task for the next pipeline stage
  per a routing table, and (b) to a Redis pub/sub channel `events:{tenant_id}` for SSE; marks published_at;
  on restart resumes from the token; a fallback poll every 10 s publishes anything unpublished older than 30 s.
- Routing table: UPLOADED→preprocess, PREPROCESSING done→diarize, DIARIZING done→transcribe,
  TRANSCRIBING done→analyze, COMPLETED→notify and meter.
- Wire P2.2's complete endpoint to write the outbox event.

Tests: transaction rollback leaves no event; relay restart does not lose or duplicate dispatch (dispatch is
idempotent by event_id); end-to-end: complete → preprocess task enqueued.
```

Done when: completing an upload automatically starts preprocessing.

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

> **Status (2026-10-17).** Already built: `sabha_core/timemap.py` (segment map, compact/original mapping, stats) with its tests. Remaining: the Silero VAD step that writes `segments@v1.json` and `compact.wav`, and the PREPROCESSING → DIARIZING transition. The 300 ms end padding is an unmeasured default (there is no LIS); tune it on the gold set.

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
