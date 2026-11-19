# Sabha architecture

How a recording travels from the browser to a scored, evidence-backed report. Rules behind each box are in
[CLAUDE.md](CLAUDE.md); decisions are in [docs/adr/](docs/adr/).

## System overview

```mermaid
flowchart LR
    subgraph Client["Browser"]
        WEB["Web app<br/>React + Vite<br/>apps/web"]
    end

    subgraph Auth["Login"]
        AUTH0["Auth0<br/>(OIDC)"]
    end

    subgraph API["API · apps/api (FastAPI)"]
        ROUTERS["Routers /v1/...<br/>recordings, results, reviews,<br/>disputes, users, costs, search"]
        SERVICES["Services<br/>permissions, consent,<br/>idempotency, audit"]
    end

    subgraph Data["Data (India)"]
        MONGO[("MongoDB 7<br/>replica set<br/>tenant-scoped repo")]
        S3[("Object storage<br/>S3 ap-south-1 / RustFS<br/>audio · artefacts · backups")]
        REDIS[("Redis 7<br/>Celery broker")]
    end

    subgraph Workers["Workers · apps/workers (Celery)"]
        RELAY["Outbox relay"]
        BEAT["Beat<br/>(scheduled jobs)"]
        PIPE["Pipeline stages"]
        NOTIFY["Notify<br/>email + webhooks"]
        METER["Meter<br/>usage + cost"]
    end

    subgraph Packages["Shared packages"]
        CORE["sabha_core<br/>settings, repo, models,<br/>state machine, storage"]
        ASR["sabha_asr<br/>speech-to-text providers,<br/>diarisation, speaker check"]
        LLM["sabha_llm<br/>gateway, PII redaction,<br/>budgets, caching"]
        ANA["sabha_analytics<br/>rubrics, metrics, scoring,<br/>grounding"]
    end

    subgraph External["Outside providers"]
        STT["Speech-to-text<br/>Sarvam, OpenAI, Groq,<br/>Deepgram, Gemini"]
        LLMP["LLM<br/>OpenAI"]
    end

    WEB -- "login" --> AUTH0
    WEB -- "JWT + JSON" --> ROUTERS
    WEB -- "audio parts<br/>(presigned URLs)" --> S3
    ROUTERS --> SERVICES --> MONGO
    SERVICES -- "presign only,<br/>never audio bytes" --> S3

    MONGO -- "outbox events" --> RELAY
    RELAY --> REDIS
    BEAT --> REDIS
    REDIS --> PIPE
    REDIS --> NOTIFY
    REDIS --> METER

    PIPE <--> S3
    PIPE <--> MONGO
    PIPE --> ASR --> STT
    PIPE --> ANA --> LLM --> LLMP
    NOTIFY --> MONGO
    METER --> MONGO

    API -.-> CORE
    Workers -.-> CORE
```

## Recording pipeline

Each stage is idempotent: it first looks for its output at `{tenant_id}/{recording_id}/{stage}@{version}/` and exits
if it is there. Status moves only through `sabha_core/state.py`.

```mermaid
flowchart TD
    CREATED(["CREATED<br/>POST /v1/recordings"]) --> UP["Browser uploads parts<br/>straight to storage"]
    UP --> UPLOADED(["UPLOADED<br/>POST .../complete"])
    UPLOADED -- "consent_ref required" --> PRE

    subgraph Q1["queue: cpu.preprocess"]
        PRE["Preprocess<br/>ffmpeg normalise → VAD<br/>compact audio + segment map"]
    end
    subgraph Q2["queue: gpu.speech"]
        DIA["Diarise<br/>pyannote, speaker count"]
        TR["Transcribe<br/>chosen speech-to-text model"]
        TS["Build transcript<br/>speaker roles, colleague-helped calls,<br/>optional Gemini speaker check,<br/>times mapped back to the original"]
    end
    subgraph Q3["queue: llm.analyze"]
        MET["Metrics in code<br/>talk share, questions, pace,<br/>silence, monologues"]
        JUDGE["LLM judges each rubric item<br/>(PII redacted first)"]
        GROUND["Grounding check<br/>every quote found in transcript<br/>(fuzzy ratio ≥ 0.90)"]
        SCORE["Scores + summary"]
    end

    PRE --> DIA --> TR --> TS --> MET --> JUDGE --> GROUND --> SCORE
    SCORE --> DONE(["COMPLETED"])
    GROUND -- "too little verified evidence" --> REVIEW(["NEEDS_REVIEW"])
    TS -- "roles unclear" --> REVIEW
    PRE & DIA & TR & JUDGE -- "error after retries" --> FAILED(["FAILED → dlq"])

    DONE --> N["queue: io.notify<br/>emails, webhooks"]
    DONE --> B["queue: billing.meter<br/>usage_events, cost"]
```

## Scheduled jobs (Celery beat)

| Job | Every | Does |
| --- | --- | --- |
| `abort_stale_uploads` | hour | cancels uploads never completed |
| `requeue_stuck` | 5 min | re-sends stages whose worker died |
| `expire_audio` | day | deletes audio past its retention |
| `backup` | day | exports the database to the backups bucket |
