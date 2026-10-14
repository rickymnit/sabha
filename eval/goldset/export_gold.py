#!/usr/bin/env python3
"""Write gold transcripts from Label Studio annotations (plan task P4.1).

Reads a Label Studio JSON export (a file from Export -> JSON, or fetched from the API) of a project
that uses infra/annotation/transcript_config.xml, and writes one file per recording:

    eval/goldset/gold/<recording_id>.json

in the canonical schema eval/goldset/transcript.schema.json. recording_id is the audio file stem.

Per task:
- no consent_ref in the task data           -> REFUSED (never written, whatever its annotations)
- no completed annotation                    -> SKIPPED (reported; cancelled/skipped ones don't count)
- several completed annotations              -> the one marked ground truth; REFUSED if none or several are
  (the workflow is one annotation per task, corrected in place by the reviewer; see infra/annotation/README.md)
- a region without exactly one speaker label, text on a Silence region, a speech region without text,
  an empty or reversed region, or anything not from the config's tags -> REFUSED with the region's time
- gold file already exists                   -> SKIPPED unless --overwrite

Conversion choices:
- Times: Label Studio seconds (float) -> integer ms, rounding half away from zero on the decimal value
  Label Studio stored (Decimal(repr(seconds)) * 1000, ROUND_HALF_UP), so 1.0005 s -> 1001 ms.
- Text: Unicode NFC, and every run of whitespace (including line breaks) becomes one space. Nothing else
  is changed: no case folding, punctuation or spelling fixes.
- Each Labels region is paired with its TextArea result through the shared region id.
- Segments are sorted by (start_ms, end_ms, speaker_role). Overlaps between speakers are kept.
- source.annotator is "ls-user-<Label Studio user id>": no names or emails in gold files.

Valid tasks are written even when others are refused (each gold file stands alone); the exit code is
then 1 so the refusals are not missed. Output is checked by check_transcript(), a hand-written mirror of
transcript.schema.json plus the ordering rules the schema cannot express, so this script needs only the
standard library. The tests validate output against the schema with the jsonschema package.

Exit codes: 0 ok (skips allowed), 1 at least one task refused, 2 bad invocation or unreadable export,
3 Label Studio API error.

Usage:
    python eval/goldset/export_gold.py --input eval/goldset/exports/project-1.json
    LABEL_STUDIO_API_KEY=... python eval/goldset/export_gold.py --project 1
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from goldset_common import (
    ALLOWED_LANGUAGE_MIX,
    ALLOWED_TYPES,
    AUDIO_DATA_KEY,
    LABEL_TO_ROLE,
    LABELS_TAG_NAME,
    RECORDING_ID_RE,
    SILENCE_ROLE,
    SPEAKER_ROLES,
    TENANT_RE,
    TEXT_TAG_NAME,
    LabelStudioClient,
    LabelStudioError,
    check_base_url,
    recording_id_from_audio,
    resolve_connection,
)

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2
EXIT_API = 3

DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "gold"
TOP_LEVEL_KEYS = ("recording_id", "tenant", "type", "language_mix", "consent_ref", "source", "segments")
SOURCE_KEYS = ("annotator", "annotation_id", "exported_at")
SEGMENT_KEYS = ("speaker_role", "start_ms", "end_ms", "text")
ANNOTATOR_RE = re.compile(r"^ls-user-[0-9]+$")
EXPORTED_AT_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z$")


class ExportFileError(Exception):
    """The export file is unreadable or not a Label Studio JSON export."""


class TaskRefused(Exception):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


# ---------------------------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------------------------


def seconds_to_ms(seconds: Any) -> int:
    """Label Studio seconds -> integer milliseconds, half away from zero (see module docstring)."""
    if isinstance(seconds, bool) or not isinstance(seconds, int | float) or not math.isfinite(seconds):
        raise ValueError(f"not a time in seconds: {seconds!r}")
    return int((Decimal(repr(float(seconds))) * 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def normalise_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        return int(value) or None
    return None


def _where(rid: str, start: Any) -> str:
    at = f" at {start:.2f}s" if isinstance(start, int | float) and not isinstance(start, bool) else ""
    return f"region {rid}{at}"


def segments_from_result(result: list[Any]) -> list[dict[str, Any]]:
    """Pair each Labels region with its per-region TextArea (same result id) and build segments."""
    regions: dict[str, dict[str, Any]] = {}
    texts: dict[str, Any] = {}
    problems: list[str] = []

    for index, item in enumerate(result):
        if not isinstance(item, dict):
            problems.append(f"result item {index} is not an object")
            continue
        rid = str(item.get("id") or "")
        from_name, rtype = item.get("from_name"), item.get("type")
        value = _dict(item.get("value"))
        if not rid:
            problems.append(f"result item {index} has no region id")
        elif from_name == LABELS_TAG_NAME and rtype == "labels":
            if rid in regions:
                problems.append(f"region {rid} has more than one speaker-label result")
            regions[rid] = value
        elif from_name == TEXT_TAG_NAME and rtype == "textarea":
            if rid in texts:
                problems.append(f"region {rid} has more than one transcript result")
            texts[rid] = value.get("text")
        else:
            problems.append(
                f"unexpected result {from_name!r} of type {rtype!r}; "
                "is this project using infra/annotation/transcript_config.xml?"
            )

    for rid in sorted(texts.keys() - regions.keys()):
        problems.append(f"transcript text for region {rid} has no speaker label region")

    segments: list[dict[str, Any]] = []
    for rid, value in regions.items():
        start, end = value.get("start"), value.get("end")
        where = _where(rid, start)
        labels = value.get("labels")
        if not isinstance(labels, list) or len(labels) != 1 or not isinstance(labels[0], str):
            problems.append(f"{where}: needs exactly one speaker label, has {labels!r}")
            continue
        label = labels[0]
        role = LABEL_TO_ROLE.get(label)
        if role is None:
            problems.append(f"{where}: unknown speaker label {label!r}")
            continue
        try:
            start_ms, end_ms = seconds_to_ms(start), seconds_to_ms(end)
        except ValueError as exc:
            problems.append(f"{where} ({label}): {exc}")
            continue
        if start_ms < 0:
            problems.append(f"{where} ({label}): starts before 0")
            continue
        if end_ms <= start_ms:
            problems.append(f"{where} ({label}): ends at or before its start (after rounding to ms)")
            continue

        raw_text = texts.get(rid)
        pieces = [raw_text] if isinstance(raw_text, str) else raw_text if raw_text is not None else []
        if not isinstance(pieces, list) or not all(isinstance(p, str) for p in pieces):
            problems.append(f"{where} ({label}): transcript is not text")
            continue
        non_empty = [t for t in (normalise_text(p) for p in pieces) if t]
        if len(non_empty) > 1:
            problems.append(f"{where} ({label}): has {len(non_empty)} separate texts; merge them into one")
            continue
        text = non_empty[0] if non_empty else ""
        if role == SILENCE_ROLE and text:
            problems.append(f"{where}: Silence region has text; remove the text or change the label")
            continue
        if role != SILENCE_ROLE and not text:
            problems.append(f"{where} ({label}): no transcript; type what was said, or [inaudible]")
            continue
        segments.append({"speaker_role": role, "start_ms": start_ms, "end_ms": end_ms, "text": text})

    if problems:
        raise TaskRefused(problems)
    segments.sort(key=lambda s: (s["start_ms"], s["end_ms"], s["speaker_role"]))
    return segments


def choose_annotation(task: dict[str, Any]) -> dict[str, Any] | None:
    """The completed annotation to use, or None if there is none. Refuses ambiguous choices."""
    annotations = task.get("annotations") or []
    completed = [
        a for a in annotations if isinstance(a, dict) and not a.get("was_cancelled") and a.get("result")
    ]
    if not completed:
        return None
    ground_truth = [a for a in completed if a.get("ground_truth")]
    if len(ground_truth) == 1:
        return ground_truth[0]
    if len(ground_truth) > 1:
        raise TaskRefused([f"{len(ground_truth)} annotations are marked ground truth; keep exactly one"])
    if len(completed) == 1:
        return completed[0]
    message = (
        f"{len(completed)} completed annotations and none is marked ground truth; "
        "delete all but the final one (or mark it as ground truth, if your Label Studio edition offers that)"
    )
    raise TaskRefused([message])


def task_to_transcript(task: dict[str, Any], exported_at: str) -> dict[str, Any] | None:
    """Canonical transcript for one Label Studio task, or None if it has no completed annotation."""
    data = _dict(task.get("data"))
    consent_ref = str(data.get("consent_ref") or "").strip()
    if not consent_ref:
        raise TaskRefused(["missing consent_ref in task data: no consent, no gold transcript"])

    problems: list[str] = []
    audio = str(data.get(AUDIO_DATA_KEY) or "")
    recording_id = recording_id_from_audio(audio) if audio else ""
    if not audio:
        problems.append(f"task data has no {AUDIO_DATA_KEY!r} URL")
    elif not RECORDING_ID_RE.match(recording_id):
        problems.append(f"audio file name {recording_id!r} cannot be a recording id")
    tenant = str(data.get("tenant") or "").strip()
    if not TENANT_RE.match(tenant):
        problems.append(f"task data has a missing or invalid tenant {tenant!r}")
    rec_type = str(data.get("type") or "").strip().lower()
    if rec_type not in ALLOWED_TYPES:
        problems.append(f"task data type {rec_type!r} is not one of {', '.join(ALLOWED_TYPES)}")
    language_mix = str(data.get("language_mix") or "").strip().lower()
    if language_mix not in ALLOWED_LANGUAGE_MIX:
        problems.append(f"task data language_mix {language_mix!r} is not one of {', '.join(ALLOWED_LANGUAGE_MIX)}")
    if problems:
        raise TaskRefused(problems)

    annotation = choose_annotation(task)
    if annotation is None:
        return None

    completed_by = annotation.get("completed_by")
    user_id = _as_positive_int(completed_by.get("id") if isinstance(completed_by, dict) else completed_by)
    annotation_id = _as_positive_int(annotation.get("id"))
    if user_id is None:
        problems.append("annotation has no completed_by user id")
    if annotation_id is None:
        problems.append("annotation has no id")
    raw_result: Any = annotation.get("result")
    result: list[Any] = raw_result if isinstance(raw_result, list) else []
    if not isinstance(raw_result, list):
        problems.append("annotation result is not a list")
    if problems:
        raise TaskRefused(problems)

    doc = {
        "recording_id": recording_id,
        "tenant": tenant,
        "type": rec_type,
        "language_mix": language_mix,
        "consent_ref": consent_ref,
        "source": {"annotator": f"ls-user-{user_id}", "annotation_id": annotation_id, "exported_at": exported_at},
        "segments": segments_from_result(result),
    }
    errors = check_transcript(doc)
    if errors:
        raise TaskRefused(errors)
    return doc


# ---------------------------------------------------------------------------------------------
# Validation (mirror of transcript.schema.json + ordering)
# ---------------------------------------------------------------------------------------------


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def check_transcript(doc: Any) -> list[str]:
    """Problems with a canonical transcript; empty list if valid."""
    if not isinstance(doc, dict):
        return ["transcript is not an object"]
    errors: list[str] = []
    if set(doc) != set(TOP_LEVEL_KEYS):
        errors.append(f"top-level keys must be exactly {', '.join(TOP_LEVEL_KEYS)}")
    if not isinstance(doc.get("recording_id"), str) or not RECORDING_ID_RE.match(doc["recording_id"]):
        errors.append("recording_id is missing or not a valid file stem")
    if not isinstance(doc.get("tenant"), str) or not TENANT_RE.match(doc["tenant"]):
        errors.append("tenant is missing or invalid")
    if doc.get("type") not in ALLOWED_TYPES:
        errors.append(f"type must be one of {', '.join(ALLOWED_TYPES)}")
    if doc.get("language_mix") not in ALLOWED_LANGUAGE_MIX:
        errors.append(f"language_mix must be one of {', '.join(ALLOWED_LANGUAGE_MIX)}")
    if not isinstance(doc.get("consent_ref"), str) or not doc["consent_ref"].strip():
        errors.append("consent_ref is missing or empty")

    source = doc.get("source")
    if not isinstance(source, dict) or set(source) != set(SOURCE_KEYS):
        errors.append(f"source must have exactly {', '.join(SOURCE_KEYS)}")
    else:
        if not isinstance(source["annotator"], str) or not ANNOTATOR_RE.match(source["annotator"]):
            errors.append("source.annotator must look like ls-user-<id>")
        if not _is_int(source["annotation_id"]) or source["annotation_id"] < 1:
            errors.append("source.annotation_id must be a positive integer")
        if not isinstance(source["exported_at"], str) or not EXPORTED_AT_RE.match(source["exported_at"]):
            errors.append("source.exported_at must be a UTC ISO 8601 time ending in Z")

    segments = doc.get("segments")
    if not isinstance(segments, list):
        errors.append("segments must be a list")
        return errors
    previous: tuple[int, int, str] | None = None
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict) or set(seg) != set(SEGMENT_KEYS):
            errors.append(f"segment {i} must have exactly {', '.join(SEGMENT_KEYS)}")
            continue
        role, start, end, text = seg["speaker_role"], seg["start_ms"], seg["end_ms"], seg["text"]
        if role not in SPEAKER_ROLES:
            errors.append(f"segment {i}: unknown speaker_role {role!r}")
        if not _is_int(start) or start < 0:
            errors.append(f"segment {i}: start_ms must be an integer >= 0")
        if not _is_int(end) or end < 1:
            errors.append(f"segment {i}: end_ms must be an integer >= 1")
        if _is_int(start) and _is_int(end) and start >= end:
            errors.append(f"segment {i}: start_ms must be less than end_ms")
        if not isinstance(text, str):
            errors.append(f"segment {i}: text must be a string")
        elif role == SILENCE_ROLE and text != "":
            errors.append(f"segment {i}: silence must have empty text")
        elif role != SILENCE_ROLE and not text.strip():
            errors.append(f"segment {i}: text may be empty only for silence")
        if _is_int(start) and _is_int(end) and isinstance(role, str):
            key = (start, end, role)
            if previous is not None and key < previous:
                errors.append(f"segment {i}: segments must be sorted by start_ms, end_ms, speaker_role")
            previous = key
    return errors


# ---------------------------------------------------------------------------------------------
# Export run
# ---------------------------------------------------------------------------------------------


@dataclass
class ExportReport:
    written: list[Path] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)


def _task_label(task: Any) -> str:
    task_id = task.get("id") if isinstance(task, dict) else None
    data = _dict(task.get("data")) if isinstance(task, dict) else {}
    audio = str(data.get(AUDIO_DATA_KEY) or "")
    name = recording_id_from_audio(audio) if audio else "no audio"
    return f"task {task_id} ({name})"


def _write_json(path: Path, doc: dict[str, Any]) -> None:
    """Write atomically so a crash never leaves half a gold file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def export_tasks(
    tasks: list[Any], out_dir: Path, exported_at: str, overwrite: bool = False
) -> ExportReport:
    report = ExportReport()
    converted: list[tuple[str, dict[str, Any]]] = []
    for task in tasks:
        label = _task_label(task)
        if not isinstance(task, dict):
            report.refused.append(f"{label}: not a task object")
            continue
        try:
            doc = task_to_transcript(task, exported_at)
        except TaskRefused as exc:
            report.refused.append(f"{label}: " + "; ".join(exc.reasons))
            continue
        if doc is None:
            report.skipped.append(f"{label}: no completed annotation")
            continue
        converted.append((label, doc))

    counts: dict[str, int] = {}
    for _, doc in converted:
        counts[doc["recording_id"]] = counts.get(doc["recording_id"], 0) + 1
    for label, doc in converted:
        rec_id = doc["recording_id"]
        if counts[rec_id] > 1:
            report.refused.append(f"{label}: {counts[rec_id]} tasks share recording id {rec_id!r}; none written")
            continue
        path = out_dir / f"{rec_id}.json"
        if path.exists() and not overwrite:
            report.skipped.append(f"{label}: {path} already exists (use --overwrite to replace it)")
            continue
        _write_json(path, doc)
        report.written.append(path)
    return report


def load_export(path: Path) -> list[Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise ExportFileError(f"cannot read {path}: {exc.strerror}") from None
    except json.JSONDecodeError as exc:
        raise ExportFileError(f"{path} is not JSON: {exc}") from None
    if not isinstance(data, list):
        raise ExportFileError(
            f"{path} is not a Label Studio JSON export (expected a list of tasks; use Export -> JSON)"
        )
    return data


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write gold transcripts from Label Studio annotations.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Label Studio JSON export file")
    source.add_argument("--project", type=int, help="fetch the export of this project from the API")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="default: eval/goldset/gold")
    parser.add_argument("--overwrite", action="store_true", help="replace existing gold files")
    parser.add_argument("--url", help="Label Studio base URL (default: $LABEL_STUDIO_URL or http://localhost:8080)")
    parser.add_argument("--token", help="API token (default: $LABEL_STUDIO_API_KEY; prefer the env var)")
    parser.add_argument("--allow-insecure-http", action="store_true", help="allow http:// to a non-local host")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.input is not None:
            tasks = load_export(args.input)
        else:
            base_url, token = resolve_connection(args.url, args.token)
            check_base_url(base_url, args.allow_insecure_http)
            tasks = LabelStudioClient(base_url, token).export_tasks(args.project)
    except ExportFileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except LabelStudioError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_API

    exported_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = export_tasks(tasks, args.out_dir, exported_at, overwrite=args.overwrite)
    for path in report.written:
        print(f"WROTE {path}", file=sys.stderr)
    for line in report.skipped:
        print(f"SKIPPED {line}", file=sys.stderr)
    for line in report.refused:
        print(f"REFUSED {line}", file=sys.stderr)
    print(
        f"{len(tasks)} task(s): {len(report.written)} written, {len(report.skipped)} skipped, "
        f"{len(report.refused)} refused",
        file=sys.stderr,
    )
    return EXIT_REFUSED if report.refused else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
