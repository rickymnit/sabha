"""Create blank score sheets for human raters (plan task P4.4).

    uv run python eval/raters/export_sheet.py --rubric rubrics/teaching.school.v0.1.yaml \\
        --recordings lesson-1 lesson-2 --raters r1 r2 r3 --app-url https://app.example.in

Writes, into --out-dir:
- scores-<rater>.csv: one row per (recording, dimension) with empty score and note columns and a link to the
  recording's transcript view. Rows are shuffled per rater (seeded), so raters do not all see items in the same
  order. There is no AI score anywhere in the sheet, and this script never reads one: raters must score blind.
- anchors.csv: the rubric's anchor for every dimension and level, plus the level 1 and 5 examples, as the
  reference tab.

Import each CSV into its own Google Sheet (File > Import), and the anchors as a second tab.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections.abc import Sequence
from pathlib import Path

from kit import LEVELS, SCORE_COLUMNS, RubricError, load_rubric_dimensions

RATER_ID_ALLOWED = set("abcdefghijklmnopqrstuvwxyz0123456789-_")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--recordings", nargs="+", required=True, help="recording ids to rate")
    parser.add_argument("--raters", nargs="+", required=True, help="rater ids (no names: e.g. r1, r2, r3)")
    parser.add_argument("--app-url", required=True, help="base URL of the web app, for transcript links")
    parser.add_argument("--out-dir", type=Path, default=Path("eval/raters/sheets"))
    parser.add_argument("--seed", type=int, default=0, help="shuffle seed (each rater gets a different order)")
    args = parser.parse_args(argv)

    bad = [r for r in args.raters if not r or set(r.lower()) - RATER_ID_ALLOWED]
    if bad:
        print(f"error: rater ids may contain only letters, digits, '-' and '_': {bad}", file=sys.stderr)
        return 2
    if len(set(args.raters)) != len(args.raters) or len(set(args.recordings)) != len(args.recordings):
        print("error: rater and recording ids must be unique", file=sys.stderr)
        return 2
    try:
        dimensions = load_rubric_dimensions(args.rubric)
    except RubricError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    base = args.app_url.rstrip("/")
    for index, rater in enumerate(args.raters):
        rows = [
            {
                "rater_id": rater,
                "recording_id": recording,
                "dimension_key": d.key,
                "dimension_name": d.name,
                "score": "",
                "note": "",
                "transcript_link": f"{base}/recordings/{recording}",
            }
            for recording in args.recordings
            for d in dimensions
        ]
        random.Random(f"{args.seed}:{index}:{rater}").shuffle(rows)  # noqa: S311  # item order, not security
        with (args.out_dir / f"scores-{rater}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SCORE_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    with (args.out_dir / "anchors.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["dimension_key", "dimension_name", "level", "anchor", "example"])
        writer.writeheader()
        for d in dimensions:
            for level in LEVELS:
                writer.writerow(
                    {
                        "dimension_key": d.key,
                        "dimension_name": d.name,
                        "level": level,
                        "anchor": d.anchors[level],
                        "example": d.examples.get(level, ""),
                    }
                )
    print(f"wrote {len(args.raters)} score sheets and anchors.csv to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
