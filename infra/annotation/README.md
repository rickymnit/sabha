# Label Studio for gold transcripts (plan task P4.1)

Human annotators use this Label Studio instance to mark who speaks when in pilot recordings and type
exactly what was said. The results become the gold set in `eval/goldset/gold/`, the only source of WER
and speaker-role numbers (CLAUDE.md rule 6).

| File | Purpose |
| --- | --- |
| `docker-compose.yml` | Label Studio 1.23.2, localhost only, own login, analytics off, audio mounted read-only |
| `.env.example` | Settings to copy into `.env` (gitignored): admin account, audio folder, bind address |
| `transcript_config.xml` | The labelling interface: waveform, speaker labels, one transcript box per region |
| `../../eval/goldset/import_tasks.py` | Creates tasks from a manifest CSV; refuses rows without `consent_ref` |
| `../../eval/goldset/export_gold.py` | Turns finished annotations into `eval/goldset/gold/<recording>.json` |
| `../../docs/annotation-guidelines.md` | The rules annotators follow |

## Decisions

- **Label Studio's own login, no basic-auth proxy in front.** Sign-up works only through the
  organisation's invite link (`LABEL_STUDIO_DISABLE_SIGNUP_WITHOUT_LINK=true`), and the first admin is
  created from `.env`. We decided against an HTTP basic-auth proxy: basic auth uses the `Authorization`
  header, and so does the Label Studio API (`Authorization: Token <key>` for legacy tokens,
  `Authorization: Bearer <access token>` for personal access tokens). With a proxy in front, the import
  and export scripts (and the Label Studio SDK) would have no header left for their token.
- **Localhost only by default.** Ports are published on `127.0.0.1:8080`. Label Studio serves plain
  HTTP. Annotators on other machines should use an SSH tunnel
  (`ssh -N -L 8080:127.0.0.1:8080 <host>`, then open http://localhost:8080). If the team needs a
  shared URL instead, put an HTTPS reverse proxy (TLS only, no basic auth) on the same host and only
  then change `ANNOTATION_BIND_ADDR`. If this ever runs on a cloud machine, it must be in AWS
  `ap-south-1` (CLAUDE.md rule 12).
- **No telemetry.** Usage analytics (`COLLECT_ANALYTICS`), Sentry error reports to HumanSignal
  (`SENTRY_DSN`, `FRONTEND_SENTRY_DSN`) and the PyPI version check (`LATEST_VERSION_CHECK`) are off.
  Each setting is cited in `docker-compose.yml`.
- **Audio is never uploaded.** The recordings folder is mounted read-only and served through Label
  Studio's local-files serving (`/data/local-files/?d=audio/<file>`). Don't use Label Studio's upload
  button for recordings: uploads are copied into Label Studio's own storage.
- **Named volume for Label Studio's data** (`sabha-annotation-label-studio-data`, mounted at
  `/label-studio/data`: SQLite database, generated secret key, exports). The image runs as UID 1001,
  and Docker gives a new named volume the right owner, while a `./data` bind mount would need a manual
  `chown` first. It also keeps real annotations out of the repository folder.
- **Image pinned** to `heartexlabs/label-studio:1.23.2` plus its digest. 1.23.2 (published 2026-09-29)
  was the newest stable release at least two weeks old when this was set up; it is a security patch
  release that also fixes access checks for local-files storage, which we rely on. To upgrade, pick a
  newer stable tag, update tag and digest together, and re-check every setting against that version.
- **SQLite**, the image default, is enough for a small annotation team on one machine. Move to the
  PostgreSQL setup in upstream's own `docker-compose.yml` if it becomes a bottleneck.
- **Everyone sees every project.** In Label Studio Community Edition all users have the same
  permissions and can see all projects (upstream docs, "Add users"). Invite only people who may hear
  every recording in this instance, and run one instance for the gold set only.

## 0. Before you start

- Docker with the Compose plugin (`docker compose version`).
- Only recordings with consent. `import_tasks.py` refuses any row without a `consent_ref`, but the
  audio folder itself is visible to Label Studio, so put nothing else in it.
- The container user (UID 1001) must be able to read the audio: files readable by others and folders
  enterable by others, for example `chmod -R o+rX <audio folder>`.

## 1. Start

```bash
cd infra/annotation
cp .env.example .env
chmod 600 .env
# edit .env: LABEL_STUDIO_USERNAME (an email), LABEL_STUDIO_PASSWORD, ANNOTATION_AUDIO_DIR
docker compose up -d
docker compose ps            # wait until the service is "healthy"
docker compose logs -f label-studio
```

Open http://localhost:8080 (or the port you set in `ANNOTATION_PORT`). Compose refuses to start if the
username, password or audio folder is missing.

Stop with `docker compose down`. That keeps the data volume; `docker compose down -v` deletes it and
every annotation in it. Back it up first:

```bash
docker run --rm -v sabha-annotation-label-studio-data:/data:ro -v "$PWD":/backup alpine:3.20 \
  tar czf /backup/label-studio-data-$(date +%F).tgz -C /data .
```

The backup contains real annotations: keep it off the repository and on encrypted storage in India.

## 2. Admin account and annotators

The admin account is created from `LABEL_STUDIO_USERNAME` / `LABEL_STUDIO_PASSWORD` on the first start;
log in with them. Those values are only used to create the account: editing `.env` later does not
change the password. Change it in the UI (**Account & Settings**) or reset it with
`docker compose exec label-studio label-studio reset_password --username <email>`.

To add annotators: menu at the top left, **Organization**, **Add Members**, copy the invite link and
send it to each person directly. After onboarding, use **Reset Link** so the old link stops working.
The sign-up page refuses anyone without the link.

## 3. Get an API token

The import and export scripts need a token for the admin (or another) account.

1. **Account & Settings** (user icon, top right) > **Personal Access Token** > create one. It is shown once.
2. Keep it in your shell only, never in a file in the repository:

   ```bash
   read -rs LABEL_STUDIO_API_KEY && export LABEL_STUDIO_API_KEY   # paste, Enter
   export LABEL_STUDIO_URL=http://localhost:8080
   ```

A personal access token is a JWT refresh token: the scripts exchange it at `/api/token/refresh/` for a
short-lived access token and send `Authorization: Bearer <access token>`. Legacy tokens
(`Authorization: Token <key>`) also work with the scripts, but they never expire and new organisations
have them switched off (**Organization** > **Settings** > **Access Token Settings**); keep them off.
Revoke a personal access token on the same page when it is no longer needed.

For the `curl` calls below, get an access token first:

```bash
ACCESS=$(curl -s -X POST "$LABEL_STUDIO_URL/api/token/refresh/" -H 'Content-Type: application/json' \
  -d "{\"refresh\": \"$LABEL_STUDIO_API_KEY\"}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access"])')
```

## 4. Create the project from `transcript_config.xml`

In the UI: **Create Project**, give it a name (for example "Gold transcripts, batch 1"), open
**Labeling Setup**, choose **Custom template**, switch to **Code**, paste the whole of
`transcript_config.xml`, then **Save**. The project id is the number in the project's URL
(`/projects/<id>/`).

Or with the API (from `infra/annotation`):

```bash
python3 -c 'import json; print(json.dumps({"title": "Gold transcripts, batch 1",
  "label_config": open("transcript_config.xml", encoding="utf-8").read()}))' \
| curl -s -X POST "$LABEL_STUDIO_URL/api/projects/" -H "Authorization: Bearer $ACCESS" \
    -H 'Content-Type: application/json' --data-binary @- \
| python3 -c 'import json,sys; print("project id:", json.load(sys.stdin)["id"])'
```

Keep the tag names (`audio`, `speaker`, `transcript`) and label values unchanged: `export_gold.py`
depends on them (`eval/goldset/goldset_common.py`, checked by `eval/goldset/tests/test_transcript_config.py`).

## 5. Connect the audio folder (once per project)

Label Studio only plays a local file if the project has a Local Files storage that contains it.

Project **Settings** > **Cloud Storage** > **Add Source Storage** > **Local Files**:

- Storage title: `Sabha audio (read-only)`
- Absolute local path: `/label-studio/files/audio`
- **Test connection**
- Import method: **Tasks**; file name filter: empty
- Click **Save**, not **Save & Sync**. Syncing would create one task per audio file, without the
  consent and metadata checks. Tasks come only from `import_tasks.py`.

`import_tasks.py` refuses to import into a project that does not have this storage.

## 6. Import recordings

Write a manifest CSV (see `eval/goldset/README.md`), with `file` relative to `ANNOTATION_AUDIO_DIR`:

```bash
python3 eval/goldset/import_tasks.py --manifest path/to/manifest.csv \
  --audio-dir /path/to/ANNOTATION_AUDIO_DIR --dry-run          # check first, contacts nothing
python3 eval/goldset/import_tasks.py --manifest path/to/manifest.csv \
  --audio-dir /path/to/ANNOTATION_AUDIO_DIR --project <id>
```

If any row is refused (no `consent_ref`, missing file, unknown type or language mix, ...), nothing is
imported. Rows already in the project are skipped, so re-running after adding rows is safe.

## 7. Annotate

Annotators follow `docs/annotation-guidelines.md`; the short version is on screen above the waveform.
Keep one annotation per task (the project default). A reviewer corrects that annotation in place and
clicks **Update**, rather than adding a second annotation. `export_gold.py` refuses tasks with more
than one finished annotation unless exactly one is marked ground truth.

## 8. Export gold transcripts

From the API (nothing written to disk except the gold files):

```bash
python3 eval/goldset/export_gold.py --project <id>
```

Or from a file: project > **Export** > **JSON**, save it under `eval/goldset/exports/` (gitignored),
then:

```bash
python3 eval/goldset/export_gold.py --input eval/goldset/exports/<file>.json
```

Output goes to `eval/goldset/gold/<recording_id>.json` (gitignored: it is real data). Tasks without a
finished annotation are skipped; tasks without `consent_ref` or with labelling mistakes are refused
with the region time, so they can be fixed in Label Studio and exported again. Existing gold files are
kept unless you pass `--overwrite`. Delete exported JSON files from `eval/goldset/exports/` when done.

## What has not been tested

Docker was not available when this was written. `docker compose config` (Compose v5.5.1) accepted the
file, `transcript_config.xml` passed Label Studio 1.23.2's own config validation (run offline), and the
scripts were tested against a synthetic export. Not yet tried against a running Label Studio: start-up,
admin creation, sign-up lock, audio playback through local-files serving, the healthcheck, and the
scripts' API calls (token refresh, storage check, import, export). Do that once on the first real
machine and note the result here.
