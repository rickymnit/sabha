"""The calibration split (plan task P4.6): which calibration recordings may be used for tuning, and which never.

    uv run python eval/calibration.py split --manifest eval/calibration/manifest.csv --holdout-share 0.3

Each calibration recording is assigned to `train` or `holdout` ONCE, stratified by school (tenant) and conversation
type, with a seeded shuffle, and the result is written to eval/calibration/split.json. The script refuses to
overwrite an existing split: re-splitting after looking at results would leak the holdout into tuning.

The holdout share is a required argument because the plan does not fix one; choose it with the calibration lead.
Within each stratum, round(n * share) recordings (half up) go to the holdout.

`recordings_for(split, part, purpose=...)` is how code reads the split. Asking for the holdout with
purpose="tuning" raises HoldoutForbidden, so a prompt-tuning or threshold-fitting script cannot use it by accident.

The manifest is a CSV with columns recording_id, tenant, type (one row per calibration recording).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Literal

EVAL_DIR = Path(__file__).resolve().parent
PARTS = ("train", "holdout")


class HoldoutForbidden(PermissionError):
    """The holdout was requested for tuning."""


@dataclass(frozen=True)
class CalibrationRow:
    recording_id: str
    tenant: str
    type: str


def read_calibration_manifest(path: Path) -> list[CalibrationRow]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = {"recording_id", "tenant", "type"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing column(s): {', '.join(sorted(missing))}")
        rows = [CalibrationRow(r["recording_id"].strip(), r["tenant"].strip(), r["type"].strip()) for r in reader]
    ids = [r.recording_id for r in rows]
    if len(set(ids)) != len(ids) or not all(ids):
        raise ValueError(f"{path}: recording ids must be unique and non-empty")
    return rows


def make_split(rows: Sequence[CalibrationRow], *, holdout_share: float, seed: int) -> dict[str, Any]:
    """The split as a JSON-ready dict. Deterministic for the same rows, share and seed."""
    if not 0 < holdout_share < 1:
        raise ValueError("holdout share must be between 0 and 1")
    strata: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        strata[(row.tenant, row.type)].append(row.recording_id)
    assignments: dict[str, str] = {}
    summary = []
    for (tenant, kind), ids in sorted(strata.items()):
        ordered = sorted(ids)
        random.Random(f"{seed}:{tenant}:{kind}").shuffle(ordered)  # noqa: S311  # reproducible sampling, not security
        k = int((Decimal(len(ordered)) * Decimal(str(holdout_share))).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        for index, rid in enumerate(ordered):
            assignments[rid] = "holdout" if index < k else "train"
        summary.append({"tenant": tenant, "type": kind, "total": len(ordered), "holdout": k})
    return {
        "seed": seed,
        "holdout_share": holdout_share,
        "strata": summary,
        "assignments": dict(sorted(assignments.items())),
    }


def recordings_for(
    split: dict[str, Any], part: Literal["train", "holdout"], *, purpose: Literal["tuning", "evaluation"]
) -> list[str]:
    """Recording ids in `part`. The holdout is never available for tuning."""
    if part not in PARTS:
        raise ValueError(f"part must be train or holdout, got {part!r}")
    if part == "holdout" and purpose == "tuning":
        raise HoldoutForbidden("the calibration holdout must never be used for tuning")
    return sorted(rid for rid, assigned in split["assignments"].items() if assigned == part)


def load_split(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("assignments"), dict):
        raise ValueError(f"{path}: not a calibration split")
    return data


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    split = sub.add_parser("split", help="assign calibration recordings to train or holdout, once")
    split.add_argument("--manifest", type=Path, default=EVAL_DIR / "calibration" / "manifest.csv")
    split.add_argument("--out", type=Path, default=EVAL_DIR / "calibration" / "split.json")
    split.add_argument("--holdout-share", type=float, required=True, help="share of each stratum in the holdout")
    split.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    if args.out.exists():
        print(f"refusing: {args.out} exists; the split is made once and never redone")
        return 1
    try:
        result = make_split(read_calibration_manifest(args.manifest), holdout_share=args.holdout_share, seed=args.seed)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    result["created_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    holdout = sum(1 for part in result["assignments"].values() if part == "holdout")
    print(f"wrote {args.out}: {holdout} holdout, {len(result['assignments']) - holdout} train")
    return 0


if __name__ == "__main__":
    sys.exit(main())
