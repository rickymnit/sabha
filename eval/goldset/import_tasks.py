#!/usr/bin/env python3
"""Create Label Studio tasks for gold-set recordings (plan task P4.1).

Reads a manifest CSV with exactly these columns (any order):

    file,tenant,type,language_mix,room_type,consent_ref

`file` is a path relative to --audio-dir, the host folder that infra/annotation/docker-compose.yml
mounts read-only into Label Studio (ANNOTATION_AUDIO_DIR). Each task points at the audio through
Label Studio's local-files serving (/data/local-files/?d=audio/<file>), so audio is never uploaded.

All or nothing: if ANY row is refused (no consent_ref, file missing, unknown type, ...) every refused
row is reported and NOTHING is imported. A half-imported manifest is easy to miss and hard to clean
up; fixing the manifest and re-running is cheap. Rows whose audio is already a task in the project
are skipped, so re-running after adding rows is safe.

Exit codes: 0 ok (or nothing new to import), 1 refused (nothing imported), 2 bad invocation or
unreadable manifest, 3 Label Studio API error.

Usage:
    export LABEL_STUDIO_API_KEY=...          # never pass real tokens on shared machines' command lines
    python eval/goldset/import_tasks.py --manifest m.csv --audio-dir /data/goldset-audio --dry-run
    python eval/goldset/import_tasks.py --manifest m.csv --audio-dir /data/goldset-audio --project 1
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from goldset_common import (
    ALLOWED_LANGUAGE_MIX,
    ALLOWED_TYPES,
    AUDIO_DATA_KEY,
    AUDIO_EXTENSIONS,
    DEFAULT_AUDIO_PREFIX,
    LOCAL_FILES_DOCUMENT_ROOT,
    MANIFEST_COLUMNS,
    RECORDING_ID_RE,
    ROOM_TYPE_RE,
    TENANT_RE,
    LabelStudioClient,
    LabelStudioError,
    audio_path_from_url,
    check_base_url,
    local_files_url,
    recording_id_from_audio,
    resolve_connection,
)

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2
EXIT_API = 3


class ManifestError(Exception):
    """The manifest as a whole is unusable (unreadable, empty, wrong columns)."""


@dataclass(frozen=True)
class ManifestRow:
    line: int
    file: str  # POSIX path relative to the audio folder
    tenant: str
    type: str
    language_mix: str
    room_type: str
    consent_ref: str

    @property
    def recording_id(self) -> str:
        return PurePosixPath(self.file).stem


@dataclass(frozen=True)
class Refusal:
    line: int
    file: str
    reasons: tuple[str, ...]

    def __str__(self) -> str:
        return f"line {self.line} ({self.file or 'no file'}): " + "; ".join(self.reasons)


def _check_file(raw: str, audio_dir: Path) -> tuple[str, list[str]]:
    """Return (normalised relative POSIX path, reasons)."""
    reasons: list[str] = []
    if not raw:
        return "", ["missing file"]
    if "\\" in raw:
        return raw, ["file must use / as separator"]
    rel = PurePosixPath(raw)
    if rel.is_absolute() or any(part in ("..", ".") or part.startswith(".") for part in rel.parts):
        return raw, ["file must be a plain path inside the audio folder (no absolute paths, '..' or hidden parts)"]
    normalised = rel.as_posix()
    if rel.suffix.lower() not in AUDIO_EXTENSIONS:
        reasons.append(f"file extension {rel.suffix or '(none)'!r} is not one of {', '.join(AUDIO_EXTENSIONS)}")
    if not RECORDING_ID_RE.match(rel.stem):
        reasons.append(
            f"file name {rel.stem!r} cannot be a recording id (letters, digits, '.', '_', '-'; start with a letter or digit)"
        )
    host_path = audio_dir / Path(*rel.parts)
    if not host_path.is_file():
        reasons.append(f"file not found in audio folder: {host_path}")
    else:
        try:
            host_path.resolve().relative_to(audio_dir.resolve())
        except ValueError:
            reasons.append("file is a link to somewhere outside the audio folder")
    return normalised, reasons


def validate_row(values: dict[str, str], line: int, audio_dir: Path) -> ManifestRow | Refusal:
    """Validate one manifest row. Reports every problem in the row, not just the first."""
    v = {key: (values.get(key) or "").strip() for key in MANIFEST_COLUMNS}
    reasons: list[str] = []

    if not v["consent_ref"]:
        reasons.append("missing consent_ref: recordings without consent are never annotated")

    file, file_reasons = _check_file(v["file"], audio_dir)
    reasons.extend(file_reasons)

    if not v["tenant"]:
        reasons.append("missing tenant")
    elif not TENANT_RE.match(v["tenant"]):
        reasons.append(f"tenant {v['tenant']!r} has unexpected characters")

    rec_type = v["type"].lower()
    if rec_type not in ALLOWED_TYPES:
        reasons.append(f"type {v['type']!r} is not one of {', '.join(ALLOWED_TYPES)}")

    language_mix = v["language_mix"].lower()
    if language_mix not in ALLOWED_LANGUAGE_MIX:
        reasons.append(f"language_mix {v['language_mix']!r} is not one of {', '.join(ALLOWED_LANGUAGE_MIX)}")

    room_type = v["room_type"].lower()
    if not ROOM_TYPE_RE.match(room_type):
        reasons.append(f"room_type {v['room_type']!r} must be a lowercase word like 'classroom' or 'front_desk'")

    if reasons:
        return Refusal(line, v["file"], tuple(reasons))
    return ManifestRow(line, file, v["tenant"], rec_type, language_mix, room_type, v["consent_ref"])


def read_manifest(manifest_path: Path, audio_dir: Path) -> tuple[list[ManifestRow], list[Refusal]]:
    """Parse and validate the manifest. Raises ManifestError for problems with the file itself."""
    try:
        handle = manifest_path.open(encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise ManifestError(f"cannot read manifest {manifest_path}: {exc.strerror}") from None
    with handle:
        reader = csv.reader(handle)
        try:
            header_row = next(reader, None)
            if header_row is None:
                raise ManifestError("manifest is empty")
            header = [h.strip() for h in header_row]
            missing = [c for c in MANIFEST_COLUMNS if c not in header]
            unknown = [h for h in header if h not in MANIFEST_COLUMNS]
            repeated = sorted({h for h in header if header.count(h) > 1})
            problems = []
            if missing:
                problems.append("missing columns: " + ", ".join(missing))
            if unknown:
                problems.append("unknown columns: " + ", ".join(repr(h) for h in unknown))
            if repeated:
                problems.append("repeated columns: " + ", ".join(repeated))
            if problems:
                raise ManifestError(
                    "manifest header must be exactly " + ",".join(MANIFEST_COLUMNS) + " (" + "; ".join(problems) + ")"
                )

            rows: list[ManifestRow] = []
            refusals: list[Refusal] = []
            for cells in reader:
                line = reader.line_num
                if not any(cell.strip() for cell in cells):
                    continue  # blank line
                if len(cells) != len(header):
                    refusals.append(
                        Refusal(line, "", (f"row has {len(cells)} values but the header has {len(header)} columns",))
                    )
                    continue
                result = validate_row(dict(zip(header, cells, strict=True)), line, audio_dir)
                if isinstance(result, Refusal):
                    refusals.append(result)
                else:
                    rows.append(result)
        except csv.Error as exc:
            raise ManifestError(f"manifest is not valid CSV (line {reader.line_num}): {exc}") from None

    # The same audio twice, or two files with the same stem, would collide in gold/<recording_id>.json.
    by_file: dict[str, list[ManifestRow]] = defaultdict(list)
    by_id: dict[str, list[ManifestRow]] = defaultdict(list)
    for row in rows:
        by_file[row.file].append(row)
        by_id[row.recording_id].append(row)
    clashing: dict[int, str] = {}
    for file, group in by_file.items():
        if len(group) > 1:
            for row in group:
                clashing[row.line] = f"file {file!r} is listed {len(group)} times"
    for rec_id, group in by_id.items():
        if len({row.file for row in group}) > 1:
            for row in group:
                clashing.setdefault(row.line, f"recording id {rec_id!r} is used by more than one file")
    if clashing:
        refusals.extend(Refusal(row.line, row.file, (clashing[row.line],)) for row in rows if row.line in clashing)
        rows = [row for row in rows if row.line not in clashing]
    refusals.sort(key=lambda r: r.line)
    return rows, refusals


def build_task(row: ManifestRow, audio_prefix: str = DEFAULT_AUDIO_PREFIX) -> dict[str, Any]:
    """Label Studio task for one recording. Keys must match transcript_config.xml and export_gold.py."""
    return {
        "data": {
            AUDIO_DATA_KEY: local_files_url(audio_prefix, row.file),
            "tenant": row.tenant,
            "type": row.type,
            "language_mix": row.language_mix,
            "room_type": row.room_type,
            "consent_ref": row.consent_ref,
        }
    }


def storage_covers(storages: list[dict[str, Any]], container_dir: str) -> bool:
    """True if a local-files storage path equals container_dir or is a parent of it.
    Label Studio 1.23.x only serves /data/local-files/ for files under such a storage."""
    target = container_dir.rstrip("/")
    for storage in storages:
        path = str(storage.get("path") or "").rstrip("/")
        if path and (target == path or target.startswith(path + "/")):
            return True
    return False


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create Label Studio tasks for gold-set recordings. Refuses rows without consent_ref.",
    )
    parser.add_argument("--manifest", type=Path, required=True, help="manifest CSV")
    parser.add_argument(
        "--audio-dir",
        type=Path,
        required=True,
        help="host folder holding the audio (the ANNOTATION_AUDIO_DIR mounted into Label Studio)",
    )
    parser.add_argument("--project", type=int, help="Label Studio project id (required unless --dry-run)")
    parser.add_argument("--url", help="Label Studio base URL (default: $LABEL_STUDIO_URL or http://localhost:8080)")
    parser.add_argument("--token", help="API token (default: $LABEL_STUDIO_API_KEY; prefer the env var)")
    parser.add_argument(
        "--audio-prefix",
        default=DEFAULT_AUDIO_PREFIX,
        help=f"folder under {LOCAL_FILES_DOCUMENT_ROOT} where the audio dir is mounted (default: %(default)s)",
    )
    parser.add_argument("--dry-run", action="store_true", help="validate and print the tasks; contact nothing")
    parser.add_argument("--allow-insecure-http", action="store_true", help="allow http:// to a non-local host")
    args = parser.parse_args(argv)
    if not args.dry_run and args.project is None:
        parser.error("--project is required unless --dry-run")
    if not args.audio_prefix.strip("/") or ".." in args.audio_prefix.split("/"):
        parser.error("--audio-prefix must be a folder name such as 'audio'")
    return args


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    audio_dir: Path = args.audio_dir
    if not audio_dir.is_dir():
        _err(f"error: audio folder not found: {audio_dir}")
        return EXIT_USAGE

    try:
        rows, refusals = read_manifest(args.manifest, audio_dir)
    except ManifestError as exc:
        _err(f"error: {exc}")
        return EXIT_USAGE

    if refusals:
        for refusal in refusals:
            _err(f"REFUSED {refusal}")
        _err(f"{len(refusals)} row(s) refused, {len(rows)} valid. Nothing imported: fix the manifest and re-run.")
        return EXIT_REFUSED
    if not rows:
        _err("manifest has no rows; nothing to import")
        return EXIT_OK

    tasks = [build_task(row, args.audio_prefix) for row in rows]

    if args.dry_run:
        print(json.dumps(tasks, ensure_ascii=False, indent=2))
        _err(
            f"dry run: {len(tasks)} task(s) would be imported"
            + (f" into project {args.project}" if args.project is not None else "")
            + ". Not checked in dry run: tasks already in the project, the project's local-files storage."
        )
        return EXIT_OK

    try:
        base_url, token = resolve_connection(args.url, args.token)
        check_base_url(base_url, args.allow_insecure_http)
        client = LabelStudioClient(base_url, token)

        container_dir = f"{LOCAL_FILES_DOCUMENT_ROOT}/{args.audio_prefix.strip('/')}"
        if not storage_covers(client.local_storages(args.project), container_dir):
            _err(
                f"REFUSED: project {args.project} has no Local Files source storage for {container_dir}, so "
                "Label Studio would not play the audio. Add one (infra/annotation/README.md, step 5) and re-run. "
                "Nothing imported."
            )
            return EXIT_REFUSED

        existing_urls: set[str] = set()
        existing_ids: dict[str, str] = {}
        for task in client.export_tasks(args.project):
            url = str((task.get("data") or {}).get(AUDIO_DATA_KEY) or "")
            if url:
                existing_urls.add(audio_path_from_url(url))
                existing_ids.setdefault(recording_id_from_audio(url), url)

        new_tasks: list[dict[str, Any]] = []
        for row, task in zip(rows, tasks, strict=True):
            url = task["data"][AUDIO_DATA_KEY]
            if audio_path_from_url(url) in existing_urls:
                _err(f"SKIPPED line {row.line} ({row.file}): already a task in project {args.project}")
            elif row.recording_id in existing_ids:
                refusals.append(
                    Refusal(
                        row.line,
                        row.file,
                        (f"recording id {row.recording_id!r} is already used by {existing_ids[row.recording_id]}",),
                    )
                )
            else:
                new_tasks.append(task)
        if refusals:
            for refusal in refusals:
                _err(f"REFUSED {refusal}")
            _err(f"{len(refusals)} row(s) refused. Nothing imported.")
            return EXIT_REFUSED
        if not new_tasks:
            _err("nothing new to import")
            return EXIT_OK

        response = client.import_tasks(args.project, new_tasks)
    except LabelStudioError as exc:
        _err(f"error: {exc}")
        return EXIT_API

    created = response.get("task_count")
    _err(f"imported {created} task(s) into project {args.project}")
    if created != len(new_tasks):
        _err(f"warning: sent {len(new_tasks)} task(s) but Label Studio reports {created}; check the project")
        return EXIT_API
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
