# ADR 0005: Fair GPU scheduling across tenants

- **Status:** Proposed
- **Date:** 2026-10-16
- **Plan task:** 7.2

## Context

All tenants share the GPU that runs diarization and speech recognition (queue `gpu.speech`, one task at a time per
GPU). Without control, one school uploading a term's worth of lessons would make every other school wait hours,
including for a five-minute front-desk call whose report someone needs today. The goal from the plan: short calls
finish within 5 minutes during a bulk upload from another tenant.

## Decision

1. **Schedule chunks, not recordings.** The GPU works on chunks of about 30 seconds of compact audio (P3.5). A
   three-hour lesson becomes hundreds of chunks that interleave with other work, so nothing waits behind a whole
   recording. This is the precondition for any fairness: with whole recordings as jobs, the worst-case wait is the
   longest recording in the queue.
2. **Two lanes.** Chunks of recordings shorter than 10 minutes go to a short lane, everything else to a normal lane.
   The short lane is served first, but after 3 consecutive short picks the normal lane gets one turn when it has
   work, so long lessons are never starved.
3. **Weighted deficit round robin across tenants within each lane.** Tenants with queued chunks take turns. On its
   turn a tenant's credit grows by `quantum x weight` (quantum 30 s; weight from the tenant's plan, default 1) and it
   sends chunks from the front of its queue while their cost fits. Each backlogged tenant therefore gets GPU time in
   proportion to its weight regardless of backlog size; a tenant that goes idle leaves the round and loses unused
   credit, so it cannot save up a burst. Chunks of one tenant stay in order.
4. **Admission control.** When the `gpu.speech` backlog is old, the upload API still accepts uploads and returns an
   estimated completion time: queued audio ahead plus the recording's own audio, divided by the GPU throughput
   measured from recent `stage_runs`. The throughput is always measured, never assumed.

The algorithm is `apps/workers/sabha_workers/fair_scheduler.py`; the gpu.speech dispatcher (P2.4) owns one
scheduler and feeds the GPU worker one chunk at a time.

## How the 5-minute target follows

For a short call arriving during another tenant's bulk upload, the wait before its first chunk is at most the chunk
in progress plus one normal-lane chunk; its chunks then run back to back, with one normal chunk after every 3. Its
completion time is therefore about `(its chunks x 4/3 + 2) x time per chunk`. Whether that is under 5 minutes depends
on the GPU's measured time per chunk, which the load test (plan task 7.5) measures on the staging L4. No speed is
assumed here. The simulation tests in `apps/workers/tests/test_fair_scheduler.py` check the ordering guarantees.

## Alternatives considered

- **Separate Celery queues per tenant:** many queues to manage, and fairness depends on worker polling order.
- **Plain priority by recording length:** starves long lessons under a steady stream of short calls.
- **Strict round robin by recording:** a long lesson still holds the GPU for its whole duration.

## Consequences

- The dispatcher must persist scheduler state (queues and credits) so a restart does not reorder or lose chunks;
  this belongs to the P2.4 worker design.
- Tenant weights become a plan setting. Changing them changes everyone's share, so changes are audited.
- Per-chunk dispatch adds a little overhead per chunk; the in-process batcher (P3.5) recovers GPU efficiency by
  batching chunks that are dispatched together.
