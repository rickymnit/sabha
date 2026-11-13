# Sabha: every command to run it by hand

Copy-paste commands for running Sabha on this machine (WSL 2, Ubuntu, Docker under systemd, repo at `/root/sabha`).
Every command assumes you are in the repo root:

```bash
cd /root/sabha
```

Contents: [Daily quick start](#daily-quick-start) · [First-time setup](#1-first-time-setup-once-per-machine) ·
[Start](#2-start-everything) · [Check](#3-check-that-everything-is-running) · [Logs](#4-logs) ·
[Use the app](#5-use-the-app) · [Stop](#6-stop-everything) · [Restart after code changes](#7-restart-after-changing-code) ·
[Look inside the database](#8-look-inside-the-database-read-only) · [Tests](#9-tests-and-checks) ·
[Admin scripts](#10-admin-scripts) · [Troubleshooting](#11-troubleshooting) · [Reset](#12-reset-or-wipe-local-data)

---

## Daily quick start

Start everything (services plus the five app processes in the background, logs in `/tmp/sabha-logs`):

```bash
cd /root/sabha
systemctl start docker            # only if Docker is not already running
make dev                          # MongoDB, Redis, RustFS + buckets
mkdir -p /tmp/sabha-logs
nohup make api      > /tmp/sabha-logs/api.log     2>&1 &
nohup make relay    > /tmp/sabha-logs/relay.log   2>&1 &
nohup make workers  > /tmp/sabha-logs/workers.log 2>&1 &
nohup make beat     > /tmp/sabha-logs/beat.log    2>&1 &
nohup pnpm -C apps/web dev > /tmp/sabha-logs/web.log 2>&1 &
```

Wait about 15 seconds, then check:

```bash
curl -s http://127.0.0.1:8000/ready; echo
curl -s -o /dev/null -w "web: %{http_code}\n" http://localhost:5180/
```

Open http://localhost:5180 and sign in.

Stop everything at the end of the day:

```bash
pkill -f 'uvicorn sabha_api'; pkill -f 'sabha_workers.relay'; pkill -f 'sabha_workers.worker worker'
pkill -f 'sabha_workers.worker beat'; pkill -f 'apps/web/node_modules/.*vite'
make down
```

---

## 1. First-time setup (once per machine)

### 1.1 Tools

Check what is installed (this machine has uv 0.13, Node 22.23, pnpm 10.33, Docker 29.1, Compose 2.40):

```bash
uv --version; node --version; pnpm --version; docker --version; docker compose version
```

Install anything missing:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # uv (installs to ~/.local/bin; Python 3.12 comes through uv)
corepack enable                                     # pnpm at the version the repo pins
systemctl enable --now docker                       # start Docker now and at every boot
```

### 1.2 Dependencies, models and `.env`

```bash
make setup          # creates .env (if missing), installs Python + web dependencies, git hooks, VAD model
make setup-speech   # pyannote + CPU PyTorch for diarisation and its model (needs HF_TOKEN in .env first)
```

Models land in `~/.cache/sabha/models/` (`silero_vad-v6.2.3.onnx`, `pyannote-community-1-3533c8cf`). Check:

```bash
ls ~/.cache/sabha/models
```

Edit `.env` (`nano .env`). Every setting is explained in `.env.example`. The ones that matter:

| Setting | Value |
| --- | --- |
| `APP_ENV` | `local` |
| `OPENAI_API_KEY` | Your OpenAI key (analysis) |
| `SARVAM_API_KEY` | Your Sarvam key (speech recognition) |
| `HF_TOKEN` | Hugging Face token (only for `make setup-speech`) |
| `USD_INR_RATE` | Optional: shows LLM cost in rupees |

### 1.3 Sign-in: choose one

**Option A: username and password (current setup).**

```bash
uv run python scripts/admin/hash_password.py      # type the password twice; prints a hash
```

In `.env`:

```
DEV_LOGIN=false
LOGIN_USERNAME=SysAdmin
LOGIN_PASSWORD_HASH='<the hash printed above>'
LOGIN_AS=owner@demo-school.example
```

In `apps/web/.env.local`:

```
VITE_AUTH_MODE=password
```

**Option B: pick a seeded user from a list (no password).**

In `.env`:

```
DEV_LOGIN=true
OIDC_ISSUER=http://localhost:8000/dev-idp
OIDC_AUDIENCE=sabha-local
OIDC_CLIENT_ID=sabha-web
```

In `apps/web/.env.local`, remove the `VITE_AUTH_MODE=password` line. After changing `.env`, restart the API; after
changing `apps/web/.env.local`, restart the web app.

### 1.4 Demo data and browser for tests

```bash
make dev                                              # services must be up first
uv run python scripts/admin/dev_seed.py               # Demo School, NiaLabs, users (safe to repeat)
pnpm -C apps/web exec playwright install chromium     # only needed for make e2e
```

---

## 2. Start everything

### 2.1 Services (Docker)

```bash
systemctl status docker --no-pager | head -3     # "active (running)"? If not: systemctl start docker
make dev
```

Expected at the end: `ok sabha-audio`, `ok sabha-artefacts`, `ok sabha-backups`.

### 2.2 App processes: option A, one terminal each (easiest to watch)

Open five terminals (in VS Code: Terminal → New Terminal), `cd /root/sabha` in each, then:

| Terminal | Command | Ready when the log shows |
| --- | --- | --- |
| 1 | `make api` | `Application startup complete.` |
| 2 | `make relay` | `outbox relay started` |
| 3 | `make workers` | `celery@<hostname> ready.` |
| 4 | `make beat` | `beat: Starting...` |
| 5 | `pnpm -C apps/web dev` | `Local: http://localhost:5180/` |

### 2.3 App processes: option B, all in the background

The same as the [daily quick start](#daily-quick-start):

```bash
mkdir -p /tmp/sabha-logs
nohup make api      > /tmp/sabha-logs/api.log     2>&1 &
nohup make relay    > /tmp/sabha-logs/relay.log   2>&1 &
nohup make workers  > /tmp/sabha-logs/workers.log 2>&1 &
nohup make beat     > /tmp/sabha-logs/beat.log    2>&1 &
nohup pnpm -C apps/web dev > /tmp/sabha-logs/web.log 2>&1 &
```

What each one does:

- **api**: the backend on http://localhost:8000. It reloads itself when you edit `apps/api` or `packages/core`.
- **relay**: starts the next pipeline stage when one finishes. Without it, uploads sit at "uploaded" forever.
- **workers**: does the processing (preprocess, diarise, transcribe, analyse, emails).
- **beat**: timed jobs (stuck-job sweeper every 5 min, upload cleanup hourly, nightly retention and backup).
- **web**: the website on http://localhost:5180. It reloads itself when you edit `apps/web`.

---

## 3. Check that everything is running

```bash
curl -s http://127.0.0.1:8000/health; echo     # {"status":"ok"}
curl -s http://127.0.0.1:8000/ready; echo      # mongo, redis, storage, indexes: all "ok"
curl -s -o /dev/null -w "web: %{http_code}\n" http://localhost:5180/     # web: 200
uv run python scripts/check_env.py             # validates .env and every service (run while the API is up)
```

Which app processes are running (each should show at least one line):

```bash
for p in 'uvicorn sabha_api' 'sabha_workers.relay' 'sabha_workers.worker worker' 'sabha_workers.worker beat' 'apps/web/node_modules/.*vite'; do
  printf '%-30s %s\n' "$p" "$(pgrep -f "$p" >/dev/null && echo running || echo STOPPED)"
done
```

Docker services:

```bash
docker ps --format '{{.Names}}  {{.Status}}'   # sabha-dev-mongo-1, -redis-1, -rustfs-1: "Up ... (healthy)"
```

Ports in use (MongoDB 27017, Redis 6380, RustFS 9000/9001, API 8000, web 5180):

```bash
ss -ltnp | grep -E ':(27017|6380|9000|9001|8000|5180) '
```

---

## 4. Logs

Background logs (option B):

```bash
tail -f /tmp/sabha-logs/workers.log            # pipeline progress; Ctrl+C to stop watching
tail -f /tmp/sabha-logs/api.log
tail -n 50 /tmp/sabha-logs/relay.log
```

Errors only:

```bash
grep -h -E '"level": "(ERROR|WARNING)"|Traceback' /tmp/sabha-logs/*.log | tail -n 30
```

Docker services (MongoDB, Redis, RustFS):

```bash
make logs                                       # follow all; Ctrl+C to stop
docker logs --tail 50 sabha-dev-mongo-1
```

The logs are JSON lines. For readable output: `tail -f /tmp/sabha-logs/workers.log | grep -o '"message": "[^"]*"'`.

---

## 5. Use the app

| What | Where |
| --- | --- |
| Website | http://localhost:5180 |
| API endpoint list (try requests in the browser) | http://localhost:8000/docs |
| Storage console (RustFS) | http://localhost:9001: username and password are `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY` in `.env` |
| Demo pages on mock data, no sign-in | http://localhost:5180/dev/components, `/dev/transcript`, `/dev/report`, `/dev/reviews`, `/dev/overview` |

Show the storage console login:

```bash
grep -E '^\s*S3_(ACCESS_KEY_ID|SECRET_ACCESS_KEY)=' .env
```

**Processing a recording:** sign in → Upload → choose the file, teacher and class → tick consent → Upload. The status
moves through uploaded → preprocessing → diarizing → transcribing → analyzing → completed. On this laptop,
diarisation takes about as long as the speech in the recording (a 20-minute lesson: about 20 minutes).

**Retry a failed recording:** open it (Recordings → the failed one) → Retry. Only owners and admins see the button.
It reruns only the stage that failed; earlier stages are not repeated. Retry, don't upload the same file again:
a new upload repeats every stage, including the slow diarisation and the paid speech recognition.

Only upload audio you have consent for. No real school recordings until the providers' data terms are confirmed.

---

## 6. Stop everything

Stop the app processes:

- **Option A (terminals):** Ctrl+C in each of the five terminals.
- **Option B (background):**

```bash
pkill -f 'uvicorn sabha_api'
pkill -f 'sabha_workers.relay'
pkill -f 'sabha_workers.worker worker'
pkill -f 'sabha_workers.worker beat'
pkill -f 'apps/web/node_modules/.*vite'
```

Then the Docker services (your data is kept):

```bash
make down
```

A recording being processed when you stop will continue from its stage on the next start (the stuck-job sweeper
re-sends it after 30 minutes without a heartbeat).

---

## 7. Restart after changing code

The API and the web app reload by themselves. **The workers, relay and beat do not**: after any change to
`packages/` or `apps/workers/`, or after `git pull`, restart them. If you skip this, workers run old code, and a
recording can fail the same way on every retry (for example `unexpected_ValidationError ... Extra inputs are not
permitted`).

Background (option B):

```bash
pkill -f 'sabha_workers.worker worker'; pkill -f 'sabha_workers.worker beat'; pkill -f 'sabha_workers.relay'
sleep 3
nohup make workers > /tmp/sabha-logs/workers.log 2>&1 &
nohup make beat    > /tmp/sabha-logs/beat.log    2>&1 &
nohup make relay   > /tmp/sabha-logs/relay.log   2>&1 &
```

Terminals (option A): Ctrl+C in the workers, beat and relay terminals, then run `make workers`, `make beat` and
`make relay` again.

After `git pull` or a dependency change, first run:

```bash
uv sync && pnpm -C apps/web install
```

After changing `.env`, restart everything: [stop](#6-stop-everything), then [start](#2-start-everything).

---

## 8. Look inside the database (read-only)

Open a MongoDB shell (type `exit` to leave):

```bash
docker exec -it sabha-dev-mongo-1 mongosh sabha
```

Or run one query from your normal shell:

```bash
docker exec sabha-dev-mongo-1 mongosh --quiet sabha --eval '<query>'
```

Useful queries (paste inside `mongosh sabha`):

```js
// The 10 newest recordings with their status
db.recordings.find({}, {file_name: 1, status: 1, status_reason: 1, duration_ms: 1, created_at: 1}).sort({created_at: -1}).limit(10)

// How many recordings are in each status
db.recordings.aggregate([{$group: {_id: {status: "$status", reason: "$status_reason"}, n: {$sum: 1}}}])

// Every stage run of one recording (replace the id): timing, attempts and errors
db.stage_runs.find({recording_id: "<recording id>"}, {stage: 1, attempt: 1, status: 1, duration_ms: 1, error_code: 1, error_detail: 1, meta: 1}).sort({started_at: 1})

// Failed jobs waiting for a retry (dead letters)
db.dlq.find({replayed_at: null}, {recording_id: 1, stage: 1, error_code: 1, error_detail: 1, created_at: 1}).sort({created_at: -1})

// LLM calls and cost for one recording
db.llm_calls.find({recording_id: "<recording id>"}, {task: 1, model: 1, status: 1, error_code: 1, tokens_in: 1, tokens_out: 1, cost_usd: 1, created_at: 1})

// Speech recognition cost per recording (rupees)
db.transcripts.find({}, {recording_id: 1, asr_billed_ms: 1, asr_cost_inr: 1})

// Recordings that look stuck (still processing after 1 hour)
db.recordings.find({status: {$in: ["PREPROCESSING", "DIARIZING", "TRANSCRIBING", "ANALYZING"]}, status_changed_at: {$lt: new Date(Date.now() - 3600e3)}}, {status: 1, status_changed_at: 1})
```

Do not edit data by hand in the shell. Use the app or the admin scripts: every document must keep its
`tenant_id`, and changes must go through the audit log.

---

## 9. Tests and checks

| Command | What it does | Needs |
| --- | --- | --- |
| `make test-fast` | Tests that need no Docker (quick) | Nothing running |
| `make test` | All Python tests (starts its own test containers) and web unit tests | Docker |
| `make test-py` | Python tests only, with coverage in `coverage.xml` | Docker |
| `make test-web` | Web unit tests only | Nothing running |
| `make lint` | ruff, mypy, eslint, prettier, tsc | Nothing running |
| `make fmt` | Fix formatting and simple lint issues | Nothing running |
| `make e2e` | Browser tests in Chromium (reseeds demo data first) | `make dev` and `make api` running |

One Python test file or one test:

```bash
uv run pytest apps/workers/tests/test_stage_runner.py
uv run pytest apps/workers/tests/test_stage_runner.py -k retries -v
```

Failed browser tests leave screenshots and traces in `apps/web/test-results/`.

Evaluation (needs real, human-annotated data):

```bash
make eval-wer HYP_DIR=<folder of transcript@v1 files>
make eval-kappa RUBRIC=<rubric yaml> AI_DIR=<folder of reports> SCORES="<rater json files>"
```

---

## 10. Admin scripts

```bash
uv run python scripts/admin/dev_seed.py               # demo school, demo company and users (local only; repeatable)
uv run python scripts/admin/hash_password.py          # hash for LOGIN_PASSWORD_HASH

uv run python scripts/admin/create_tenant.py --name "Green Valley School" --profile school --plan pilot \
    --owner-email principal@example.com --owner-name "Asha Rao" --audio-hours 100
uv run python scripts/admin/set_plan.py --tenant <tenant id> --plan starter --audio-hours 100

uv run python scripts/admin/backfill.py --dry-run     # see what would be filled in; then run without --dry-run
uv run python scripts/admin/expire_audio.py --dry-run # see what audio retention would delete; then without it
uv run python scripts/admin/restore_drill.py          # restore the latest backup into a scratch database and check it
```

Try speech recognition alone (sends the audio to Sarvam and is billed):

```bash
uv run sabha-asr-transcribe <file.wav>                # 16 kHz mono WAV
```

Each script explains its options at the top of its file, for example `head -30 scripts/admin/set_plan.py`.

---

## 11. Troubleshooting

| What you see | Cause | Fix |
| --- | --- | --- |
| `Cannot connect to the Docker daemon` | Docker is not running | `systemctl start docker` |
| `make dev` hangs or a container is "unhealthy" | A service failed to start | `docker logs sabha-dev-mongo-1` (or `-redis-1`, `-rustfs-1`); then `make down && make dev` |
| `address already in use` on 8000 or 5180 | An old API or web process is still running | `pkill -f 'uvicorn sabha_api'` or `pkill -f 'apps/web/node_modules/.*vite'`, then start again |
| `check_env.py`: OIDC FAIL, connection refused | The API is not running (it is the sign-in issuer locally) | Start `make api`, run the check again |
| `check_env.py`: OIDC FAIL, HTTP 404 | Expected with the username-and-password sign-in (`DEV_LOGIN=false`): the API checks tokens itself and does not serve that address | Nothing to fix. To test sign-in: `curl -s -X POST http://127.0.0.1:8000/auth/login -H 'content-type: application/json' -d '{"username":"x","password":"y"}'` must answer 401, not 404 |
| Sign-in page says the password is wrong | Wrong password, or the hash in `.env` changed | Make a new hash ([1.3](#13-sign-in-choose-one)) and restart the API |
| Recording stays at **Uploaded** | The relay is not running | Start `make relay` |
| Recording stays at **Created** | The upload did not finish in the browser | Upload again; abandoned uploads are cleaned up after 24 h |
| Recording stays at Preprocessing / Diarizing / ... | Workers are not running, or a long diarisation | Check the workers are running ([3](#3-check-that-everything-is-running)) and `tail -f /tmp/sabha-logs/workers.log`; diarisation takes about as long as the speech |
| Failed: `too_short` / `invalid_audio` | The file is too short or cannot be read | Use a longer or a different audio file |
| Failed: `analysis_failed ... model_not_found` | The LLM model in settings no longer exists | Check `LLM_MODEL_SMALL` / `LLM_MODEL_MID` in `.env` (default `openai:gpt-6-luna`), restart workers, then Retry |
| Failed: `analysis_failed ... HTTP 429 credit_balance_exhausted` | The OpenAI account has no credit left | Add credit in the OpenAI billing page, then Retry (nothing before analysis runs again) |
| Failed: `unexpected_ValidationError ... Extra inputs are not permitted` | Workers are running old code | [Restart the workers](#7-restart-after-changing-code), then Retry |
| Failed: `asr_failed` with 403 | The Sarvam key is invalid or out of credit | Fix `SARVAM_API_KEY` in `.env`, restart workers, then Retry |
| Needs review: `unclear_roles` | It could not tell who is the teacher | Reviews → open it → choose the speaker |
| Worker killed, or WSL freezes during diarisation | Not enough memory | Close other programs; give WSL more memory in `C:\Users\<you>\.wslconfig` (`[wsl2]` then `memory=6GB`), then `wsl --shutdown` from Windows |
| Web page blank or old after `git pull` | Web dependencies changed | `pnpm -C apps/web install`, restart the web app |
| `ModuleNotFoundError` in Python | Python dependencies changed | `uv sync` (and `uv sync --extra speech` for diarisation), then restart |

The exact reason a recording failed:

```bash
docker exec sabha-dev-mongo-1 mongosh --quiet sabha --eval '
db.recordings.find({status: "FAILED"}, {file_name: 1, status_reason: 1, status_changed_at: 1}).sort({status_changed_at: -1}).limit(5).forEach(r => {
  printjson(r);
  db.stage_runs.find({recording_id: r._id, status: "failed"}, {stage: 1, attempt: 1, error_code: 1, error_detail: 1}).sort({started_at: -1}).limit(1).forEach(printjson);
})'
```

---

## 12. Reset or wipe local data

Stop and start the services again, keeping data:

```bash
make down && make dev
```

**Delete all local data** (every recording, user, transcript and stored file in MongoDB, Redis and RustFS). This
cannot be undone:

```bash
make down
docker compose --env-file .env -f infra/docker-compose.dev.yml -p sabha-dev down -v    # -v deletes the data volumes
make dev
uv run python scripts/admin/dev_seed.py                                                # demo data again
```

Remove the background logs:

```bash
rm -rf /tmp/sabha-logs
```
