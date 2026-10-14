# apps/workers

The Celery 5 workers that run the processing pipeline on Redis queues (`cpu.preprocess`, `gpu.speech`, `llm.analyze`, `io.notify`, `billing.meter`) plus the outbox relay. Each task (preprocess, speech, analyze, notify, meter, relay) is idempotent: it checks for its output artefact at `{tenant_id}/{recording_id}/{stage}@{version}/` before doing work, runs with `acks_late=True`, and moves recordings only through the state machine in `sabha_core/state.py`.
