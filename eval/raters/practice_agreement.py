"""Agreement among human raters on the practice set (plan task P4.4).

    uv run python eval/raters/practice_agreement.py --rubric rubrics/teaching.school.v0.1.yaml \\
        sheets/scores-r1.csv sheets/scores-r2.csv sheets/scores-r3.csv

For each rubric dimension, quadratic-weighted Cohen's kappa for every pair of raters over the recordings they all
scored, and the mean over pairs. Quadratic weights count a 1-vs-5 disagreement sixteen times a 1-vs-2 one, which
suits an ordinal 1-5 scale.

Kappa is undefined when chance agreement is total (for example both raters gave every recording the same score);
it is then reported as "undefined", never as 0 or 1. The calibration threshold comes from
`raters.practice_kappa_min` in eval/targets.yaml; when it is not set the report says so, and the raters are never
reported as calibrated. Exit code 0 only when every dimension's mean kappa meets a set threshold.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from itertools import combinations
from pathlib import Path

import yaml
from import_scores import RaterScore, ScoreImportError, read_scores
from kit import LEVELS, RubricError, load_rubric_dimensions


def weighted_kappa(a: Sequence[int], b: Sequence[int], levels: Sequence[int] = LEVELS) -> float | None:
    """Quadratic-weighted Cohen's kappa of paired ratings; None when it is undefined."""
    if len(a) != len(b):
        raise ValueError("ratings must be paired")
    n = len(a)
    if n == 0:
        return None
    index = {level: i for i, level in enumerate(levels)}
    k = len(levels)
    observed = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b, strict=True):
        observed[index[x]][index[y]] += 1
    rows = [sum(observed[i]) for i in range(k)]
    cols = [sum(observed[i][j] for i in range(k)) for j in range(k)]
    weight = [[((i - j) ** 2) / ((k - 1) ** 2) for j in range(k)] for i in range(k)]
    disagreement_observed = sum(weight[i][j] * observed[i][j] for i in range(k) for j in range(k))
    disagreement_expected = sum(weight[i][j] * rows[i] * cols[j] / n for i in range(k) for j in range(k))
    if disagreement_expected == 0:
        return None
    return 1 - disagreement_observed / disagreement_expected


def practice_kappa_min(targets: Path) -> float | None:
    if not targets.is_file():
        return None
    data = yaml.safe_load(targets.read_text(encoding="utf-8")) or {}
    value = (data.get("raters") or {}).get("practice_kappa_min") if isinstance(data, dict) else None
    return None if value is None else float(value)


def _fmt(value: float | None) -> str:
    return "undefined" if value is None else f"{value:.2f}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--targets", type=Path, default=Path(__file__).resolve().parents[1] / "targets.yaml")
    parser.add_argument("sheets", nargs="+", type=Path)
    args = parser.parse_args(argv)
    try:
        dimensions = load_rubric_dimensions(args.rubric)
        per_rater: dict[str, dict[tuple[str, str], int]] = {}
        for sheet in args.sheets:
            scores: list[RaterScore] = read_scores(sheet, args.rubric)
            rater = scores[0].rater_id
            if rater in per_rater:
                raise ScoreImportError(f"rater {rater!r} appears in more than one sheet")
            per_rater[rater] = {(s.recording_id, s.dimension): s.score for s in scores}
        threshold = practice_kappa_min(args.targets)
    except (ScoreImportError, RubricError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    raters = sorted(per_rater)
    if len(raters) < 2:
        print("error: agreement needs at least two raters", file=sys.stderr)
        return 2
    common = set.intersection(*({rec for rec, _ in scores} for scores in per_rater.values()))
    recordings = sorted(common)
    pairs = list(combinations(raters, 2))
    print(f"Raters: {', '.join(raters)}. Recordings scored by all: {len(recordings)}.")
    shown = "threshold not set" if threshold is None else threshold
    print(f"Calibration threshold (raters.practice_kappa_min): {shown}")
    print("")
    print("| Dimension | " + " | ".join(f"{x} vs {y}" for x, y in pairs) + " | Mean | Status |")
    print("| --- | " + " | ".join("---" for _ in pairs) + " | --- | --- |")
    all_ok = threshold is not None and bool(recordings)
    for d in dimensions:
        values = [
            weighted_kappa(
                [per_rater[x][(r, d.key)] for r in recordings], [per_rater[y][(r, d.key)] for r in recordings]
            )
            for x, y in pairs
        ]
        defined = [v for v in values if v is not None]
        mean = sum(defined) / len(defined) if len(defined) == len(values) and defined else None
        if threshold is None:
            status = "threshold not set"
        elif mean is None:
            status = "cannot assess (undefined kappa)"
        else:
            status = "calibrated" if mean >= threshold else "not yet"
        all_ok = all_ok and status == "calibrated"
        print(f"| {d.key} | " + " | ".join(_fmt(v) for v in values) + f" | {_fmt(mean)} | {status} |")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
