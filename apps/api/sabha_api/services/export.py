"""The Recordings page's "Export list" (UI v2; owner's decision 2026-11-03): the current tab and filters as CSV.

One row per recording the caller may see, newest first, at most MAX_ROWS. Times are Asia/Kolkata, as the web app
shows them. A cell that a spreadsheet would read as a formula (=, +, -, @) is prefixed with an apostrophe. The
router audits every export (recordings.export).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from sabha_api.services.results import RecordingOut

MAX_ROWS = 5000
IST = timezone(timedelta(hours=5, minutes=30))
HEADER = ["Title", "Person", "Unit", "Type", "Length", "Score", "Status", "Recorded"]
STATUS_WORDS = {
    "COMPLETED": "Ready",
    "NEEDS_REVIEW": "Needs review",
    "FAILED": "Failed",
}


def _safe(value: str) -> str:
    return f"'{value}" if value[:1] in ("=", "+", "-", "@") else value


def _clock(ms: int | None) -> str:
    if ms is None:
        return ""
    s = round(ms / 1000)
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def _when(value: datetime) -> str:
    return value.astimezone(IST).strftime("%Y-%m-%d %H:%M")


def to_csv(rows: list[RecordingOut], unit_names: Mapping[str, str], type_names: Mapping[str, str]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(HEADER)
    for r in rows:
        writer.writerow([_safe(cell) for cell in (
            r.title,
            r.person.name if r.person else "",
            unit_names.get(r.unit_id or "", ""),
            type_names.get(r.type, r.type),
            _clock(r.duration_ms),
            "" if r.overall_score is None else f"{r.overall_score:.1f}",
            STATUS_WORDS.get(r.status, "Processing"),
            _when(r.recorded_at or r.created_at),
        )])  # fmt: skip
    return out.getvalue()
