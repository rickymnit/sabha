"""Read completed rater sheets and validate them (plan task P4.4).

    uv run python eval/raters/import_scores.py --rubric rubrics/teaching.school.v0.1.yaml \\
        --out eval/raters/scores/batch-1.json sheets/scores-r1.csv sheets/scores-r2.csv ...

A sheet is accepted only if it holds exactly one rater, every score is a whole number from 1 to 5, every dimension
of the rubric is scored for every recording in the sheet, and nothing is scored twice. Any problem rejects the
whole sheet with every problem listed, so a half-filled sheet never mixes into the agreement numbers.

Validated scores are written as JSON records {recording_id, rater_id, dimension, score, note}. The rater_scores
collection needs the tenant-scoped repository (P1.6); until then the JSON file is the store. Rater scores are about
real staff: eval/raters/scores/ is gitignored and must not be committed (golden rule 11).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from kit import SCORE_COLUMNS, RubricError, load_rubric_dimensions


class ScoreImportError(ValueError):
    """A rater sheet is incomplete or invalid."""


@dataclass(frozen=True)
class RaterScore:
    recording_id: str
    rater_id: str
    dimension: str
    score: int
    note: str


def _parse_score(raw: str) -> int | None:
    text = raw.strip()
    if not text.isdigit():
        return None
    value = int(text)
    return value if 1 <= value <= 5 else None


def read_scores(path: Path, rubric: Path) -> list[RaterScore]:
    """The validated scores in one rater sheet. Raises ScoreImportError listing every problem."""
    keys = {d.key for d in load_rubric_dimensions(rubric)}
    problems: list[str] = []
    scores: list[RaterScore] = []
    seen: set[tuple[str, str]] = set()
    with path.open(newline="", encoding="utf-8-sig") as handle:  # utf-8-sig: Excel adds a byte-order mark
        reader = csv.DictReader(handle)
        missing = [c for c in SCORE_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ScoreImportError(f"{path}: missing column(s): {', '.join(missing)}")
        raters = set()
        for line, row in enumerate(reader, start=2):
            rater, recording, key = row["rater_id"].strip(), row["recording_id"].strip(), row["dimension_key"].strip()
            raters.add(rater)
            where = f"line {line} ({recording}, {key})"
            if key not in keys:
                problems.append(f"{where}: unknown dimension {key!r}")
                continue
            if (recording, key) in seen:
                problems.append(f"{where}: scored twice")
                continue
            seen.add((recording, key))
            raw = row["score"] or ""
            if not raw.strip():
                problems.append(f"{where}: score is missing")
                continue
            score = _parse_score(raw)
            if score is None:
                problems.append(f"{where}: score must be a whole number from 1 to 5, got {raw!r}")
                continue
            scores.append(RaterScore(recording, rater, key, score, (row["note"] or "").strip()))
    if len(raters) != 1:
        problems.append(f"expected one rater per sheet, found {sorted(raters)}")
    recordings = {recording for recording, _ in seen}
    for recording in sorted(recordings):
        for key in sorted(keys - {k for r, k in seen if r == recording}):
            problems.append(f"{recording}: dimension {key!r} not scored")
    if problems:
        raise ScoreImportError(f"{path}:\n  " + "\n  ".join(problems))
    return scores


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="JSON file for the validated scores")
    parser.add_argument("sheets", nargs="+", type=Path)
    args = parser.parse_args(argv)
    records: list[RaterScore] = []
    failed = False
    for sheet in args.sheets:
        try:
            records.extend(read_scores(sheet, args.rubric))
        except (ScoreImportError, RubricError) as exc:
            print(f"REJECTED {exc}")
            failed = True
    if failed:
        print("Nothing written: fix the rejected sheets and run again.")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps([asdict(r) for r in records], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} scores from {len(args.sheets)} sheets to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
