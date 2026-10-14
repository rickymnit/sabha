Tests (until P1.1 adds eval to the uv workspace): `cd /root/sabha && ~/.local/bin/uv run --no-project --python 3.12 --with pytest --with jsonschema pytest eval/goldset/tests -q`

# eval/goldset

Tooling for the human-annotated gold set (plan task P4.1). Label Studio setup and the full workflow:
`infra/annotation/README.md`. Rules for annotators: `docs/annotation-guidelines.md`.

| File | Purpose |
| --- | --- |
| `import_tasks.py` | Manifest CSV + audio folder -> Label Studio tasks. Refuses rows without `consent_ref`. |
| `export_gold.py` | Label Studio JSON export -> `gold/<recording_id>.json`. |
| `transcript.schema.json` | Canonical gold transcript schema (JSON Schema draft 2020-12). |
| `goldset_common.py` | Shared vocabulary (types, language mixes, speaker roles, tag names) and a small urllib client. |
| `gold/` | Output. Gitignored: gold transcripts of pilot recordings are real data. |
| `exports/` | Put downloaded Label Studio exports here if you use `--input`. Gitignored; delete after use. |

Both scripts use only the Python standard library and run with any Python 3.12:
`python3 eval/goldset/import_tasks.py --help`. They read the Label Studio URL and token from
`LABEL_STUDIO_URL` and `LABEL_STUDIO_API_KEY` (or `--url` / `--token`; prefer the environment so the
token stays out of shell history). The token is never printed.

## Manifest CSV

Exactly these columns, in any order, UTF-8 (a spreadsheet BOM is fine):

| Column | Rule |
| --- | --- |
| `file` | Path relative to the audio folder, `/` separators, no `..`. Audio extension (`.wav .mp3 .m4a .ogg .opus .flac .webm`). The file name without extension becomes the recording id, so it may only use letters, digits, `.`, `_`, `-`, and must be unique in the manifest and the project. |
| `tenant` | Tenant id (letters, digits, `.`, `_`, `-`). |
| `type` | `teaching` or `reception` (the pilot types; the labelling interface has speaker labels only for these). |
| `language_mix` | `english`, `hindi` or `hinglish`. |
| `room_type` | Lowercase word such as `classroom`, `lab`, `front_desk`, `phone`. No fixed list yet. |
| `consent_ref` | Reference to the consent record. Required: rows without it are refused. |

Example (fictional):

```csv
file,tenant,type,language_mix,room_type,consent_ref
demo-school/demo-teaching-001.wav,demo-school,teaching,hinglish,classroom,CONSENT-DEMO-0001
demo-school/demo-reception-001.mp3,demo-school,reception,english,front_desk,CONSENT-DEMO-0002
```

Values are trimmed; `type`, `language_mix` and `room_type` are lowercased.

**All or nothing.** If any row is refused, every problem in every refused row is printed and nothing is
imported (exit code 1). A partly imported manifest is easy to miss and the missing recordings would
quietly drop out of the gold set; fixing the CSV and re-running is cheap. Tasks whose audio is already
in the project are skipped, so re-running is safe. `--dry-run` validates and prints the tasks without
contacting Label Studio.

## Gold transcript

`gold/<recording_id>.json`, valid against `transcript.schema.json`:

```json
{
  "recording_id": "demo-teaching-001",
  "tenant": "demo-school",
  "type": "teaching",
  "language_mix": "hinglish",
  "consent_ref": "CONSENT-DEMO-0001",
  "source": {"annotator": "ls-user-3", "annotation_id": 502, "exported_at": "2026-10-14T06:00:00Z"},
  "segments": [
    {"speaker_role": "teacher", "start_ms": 512, "end_ms": 6000, "text": "अच्छा, so आज हम photosynthesis पढ़ेंगे"},
    {"speaker_role": "silence", "start_ms": 12500, "end_ms": 15001, "text": ""}
  ]
}
```

- `speaker_role`: `teacher`, `students`, `receptionist`, `caller`, `other`, `silence`.
- Times are integer milliseconds on the original recording: Label Studio's seconds x 1000, rounded half
  away from zero on the decimal value Label Studio stored (`1.0005 s` -> `1001`).
- `start_ms < end_ms`; segments sorted by start (then end, then role); speakers may overlap.
- `text` is empty for `silence` and only for `silence`. Text is kept verbatim apart from Unicode NFC
  and collapsing runs of whitespace into one space.
- `source.annotator` is the Label Studio user id, never a name or email. `exported_at` is UTC.

`export_gold.py` checks its output with a hand-written mirror of the schema (plus the ordering and
`start_ms < end_ms` rules the schema cannot express), so it needs no third-party package; the tests
validate the same output with `jsonschema`. Exit codes: 0 ok (skipped tasks allowed), 1 some task
refused (valid ones are still written), 2 bad input, 3 Label Studio API error.
