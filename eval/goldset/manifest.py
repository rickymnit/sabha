"""The gold-set manifest (P4.2): one CSV row per recording, shared by freeze.py, report.py, wer.py and roles.py.

Columns (all required, in any order): recording_id, file, type, language_mix, room_type, duration_s, consent_ref,
split, annotator, status.

- split is `dev` (used while building and tuning) or `holdout` (frozen; only scored, never tuned on).
- status is `pending`, `in_progress` or `completed`; only completed recordings have a gold transcript.
- consent_ref is never empty (golden rule 9).

A malformed row raises ManifestError naming the line, rather than being skipped: a silently dropped holdout file
would change every number computed from the set.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from goldset_common import ALLOWED_LANGUAGE_MIX, ALLOWED_TYPES, RECORDING_ID_RE, ROOM_TYPE_RE

COLUMNS = (
    "recording_id",
    "file",
    "type",
    "language_mix",
    "room_type",
    "duration_s",
    "consent_ref",
    "split",
    "annotator",
    "status",
)
SPLITS = frozenset({"dev", "holdout"})
STATUSES = frozenset({"pending", "in_progress", "completed"})


class ManifestError(ValueError):
    """The manifest is missing, malformed or inconsistent."""


@dataclass(frozen=True)
class ManifestRow:
    line: int
    recording_id: str
    file: str
    type: str
    language_mix: str
    room_type: str
    duration_s: float
    consent_ref: str
    split: str
    annotator: str
    status: str


def read_manifest(path: Path) -> list[ManifestRow]:
    """All rows of the manifest at `path`, validated. Raises ManifestError listing every problem found."""
    if not path.is_file():
        raise ManifestError(f"manifest not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ManifestError(f"{path}: missing column(s): {', '.join(missing)}")
        rows: list[ManifestRow] = []
        problems: list[str] = []
        seen: set[str] = set()
        for line, raw in enumerate(reader, start=2):
            values = {k: (raw.get(k) or "").strip() for k in COLUMNS}
            row_problems = _check(values)
            if values["recording_id"] in seen:
                row_problems.append(f"duplicate recording_id {values['recording_id']!r}")
            seen.add(values["recording_id"])
            if row_problems:
                problems.extend(f"line {line}: {p}" for p in row_problems)
                continue
            rows.append(
                ManifestRow(
                    line=line,
                    recording_id=values["recording_id"],
                    file=values["file"],
                    type=values["type"],
                    language_mix=values["language_mix"],
                    room_type=values["room_type"],
                    duration_s=float(values["duration_s"]),
                    consent_ref=values["consent_ref"],
                    split=values["split"],
                    annotator=values["annotator"],
                    status=values["status"],
                )
            )
    if problems:
        raise ManifestError(f"{path}:\n  " + "\n  ".join(problems))
    return rows


def _check(values: dict[str, str]) -> list[str]:
    problems = []
    if not RECORDING_ID_RE.match(values["recording_id"]):
        problems.append(f"bad recording_id {values['recording_id']!r}")
    if not values["file"]:
        problems.append("file is empty")
    if values["type"] not in ALLOWED_TYPES:
        problems.append(f"type must be one of {list(ALLOWED_TYPES)}, got {values['type']!r}")
    if values["language_mix"] not in ALLOWED_LANGUAGE_MIX:
        problems.append(f"language_mix must be one of {list(ALLOWED_LANGUAGE_MIX)}, got {values['language_mix']!r}")
    if not ROOM_TYPE_RE.match(values["room_type"]):
        problems.append(f"bad room_type {values['room_type']!r}")
    try:
        if float(values["duration_s"]) <= 0:
            problems.append("duration_s must be positive")
    except ValueError:
        problems.append(f"duration_s is not a number: {values['duration_s']!r}")
    if not values["consent_ref"]:
        problems.append("consent_ref is empty: recordings without consent are never in the gold set")
    if values["split"] not in SPLITS:
        problems.append(f"split must be dev or holdout, got {values['split']!r}")
    if values["status"] not in STATUSES:
        problems.append(f"status must be one of {sorted(STATUSES)}, got {values['status']!r}")
    return problems
