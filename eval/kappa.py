"""Agreement between AI scores and human raters on the calibration set (plan task P4.6; `make eval-kappa`).

    uv run python eval/kappa.py --rubric rubrics/teaching.school.v0.1.yaml --ai-dir <analysis@v1 reports> \\
        --rater-scores eval/raters/scores/*.json [--split eval/calibration/split.json] [--part holdout]

For each rubric dimension, over the recordings in the chosen part of the calibration split (the holdout by
default; see calibration.py):

- Human reference = the median of the raters' scores. It needs an odd number of raters, at least 3, so the median
  is a whole score; recordings with fewer or an even number are excluded and counted.
- AI score = the dimension's score in the recording's analysis@v1 report, only when the dimension is verified
  (an unverified dimension has no score by design). Missing reports and unverified dimensions are excluded and
  counted, never silently dropped.
- Quadratic-weighted Cohen's kappa between AI and reference (the same function as eval/raters, tested against a
  hand-computed value), exact agreement, agreement within one point, n, and a percentile bootstrap 95% interval
  over recordings (seeded).
- Rater-rater agreement for context: the mean pairwise quadratic-weighted kappa among raters.

Each dimension is PASS when kappa >= the rubric's visibility_gate minimum (0.60 in the v0 rubrics), FAIL when it
is below, and "not assessed" when kappa is undefined or n is 0. Nothing is reported as passing without data.
Reports go to eval/reports/kappa-<date>.md and .json. Exit code 0 only when every dimension passes.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from statistics import median
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent / "raters"))  # run as a script: python eval/kappa.py

from calibration import load_split
from kit import load_rubric_dimensions
from practice_agreement import weighted_kappa

EVAL_DIR = Path(__file__).resolve().parent
MIN_RATERS = 3
BOOTSTRAP_ITERATIONS = 2000


def median_reference(scores: Sequence[int]) -> int | None:
    """The median of an odd number (>= 3) of rater scores; None otherwise."""
    if len(scores) < MIN_RATERS or len(scores) % 2 == 0:
        return None
    return int(median(scores))


def visibility_gate_min(rubric: Path) -> float:
    data = yaml.safe_load(rubric.read_text(encoding="utf-8"))
    value = (data.get("visibility_gate") or {}).get("min") if isinstance(data, dict) else None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{rubric}: visibility_gate.min must be a number")
    return float(value)


def load_ai_scores(ai_dir: Path, recording_ids: Sequence[str]) -> tuple[dict[str, dict[str, int | None]], list[str]]:
    """{recording_id: {dimension: score or None when unverified}} and the ids with no report."""
    scores: dict[str, dict[str, int | None]] = {}
    missing = []
    for rid in recording_ids:
        path = ai_dir / f"{rid}.json"
        if not path.is_file():
            missing.append(rid)
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        scores[rid] = {d["key"]: (d["score"] if d.get("verified") else None) for d in report.get("dimensions", [])}
    return scores, missing


def load_rater_scores(paths: Sequence[Path]) -> dict[tuple[str, str], dict[str, int]]:
    """{(recording_id, dimension): {rater_id: score}} from import_scores.py output files."""
    out: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for path in paths:
        for record in json.loads(path.read_text(encoding="utf-8")):
            key = (record["recording_id"], record["dimension"])
            if record["rater_id"] in out[key]:
                raise ValueError(f"{path}: rater {record['rater_id']!r} scored {key} twice")
            out[key][record["rater_id"]] = int(record["score"])
    return out


def _bootstrap(pairs: Sequence[tuple[int, int]], seed: int) -> tuple[float, float] | None:
    if len(pairs) < 2:
        return None
    rng = random.Random(seed)  # noqa: S311  # statistical resampling, not security
    values = []
    for _ in range(BOOTSTRAP_ITERATIONS):
        sample = [rng.choice(pairs) for _ in pairs]
        k = weighted_kappa([a for a, _ in sample], [h for _, h in sample])
        if k is not None:
            values.append(k)
    if not values:
        return None
    values.sort()
    return values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]


def _rater_rater(ratings: dict[str, dict[str, int]]) -> float | None:
    """Mean pairwise kappa among raters, over recordings each pair both scored. `ratings`: {recording: {rater: s}}."""
    raters = sorted({r for scores in ratings.values() for r in scores})
    values = []
    for x, y in combinations(raters, 2):
        common = [rec for rec, scores in ratings.items() if x in scores and y in scores]
        k = weighted_kappa([ratings[c][x] for c in common], [ratings[c][y] for c in common])
        if k is not None:
            values.append(k)
    return sum(values) / len(values) if values else None


def evaluate(
    *,
    dimensions: Sequence[str],
    recordings: Sequence[str],
    ai: dict[str, dict[str, int | None]],
    raters: dict[tuple[str, str], dict[str, int]],
    threshold: float,
    seed: int,
) -> list[dict[str, Any]]:
    results = []
    for key in dimensions:
        pairs: list[tuple[int, int]] = []
        excluded = {"ai_missing": 0, "ai_unverified": 0, "too_few_raters": 0}
        per_recording: dict[str, dict[str, int]] = {}
        for rid in recordings:
            human = raters.get((rid, key), {})
            if human:
                per_recording[rid] = human
            if rid not in ai:
                excluded["ai_missing"] += 1
                continue
            ai_score = ai[rid].get(key)
            if ai_score is None:
                excluded["ai_unverified"] += 1
                continue
            reference = median_reference(list(human.values()))
            if reference is None:
                excluded["too_few_raters"] += 1
                continue
            pairs.append((ai_score, reference))
        n = len(pairs)
        kappa = weighted_kappa([a for a, _ in pairs], [h for _, h in pairs]) if pairs else None
        status = "not assessed" if kappa is None else ("PASS" if kappa >= threshold else "FAIL")
        results.append(
            {
                "key": key,
                "n": n,
                "kappa": kappa,
                "kappa_ci95": _bootstrap(pairs, seed),
                "exact_agreement": sum(a == h for a, h in pairs) / n if n else None,
                "within_one": sum(abs(a - h) <= 1 for a, h in pairs) / n if n else None,
                "rater_rater_kappa": _rater_rater(per_recording),
                "excluded": excluded,
                "status": status,
            }
        )
    return results


def _fmt(value: float | None, pct: bool = False) -> str:
    if value is None:
        return "MISSING"
    return f"{value * 100:.0f}%" if pct else f"{value:.2f}"


def markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# AI-human agreement: {report['rubric']} ({report['part']})",
        "",
        f"Generated {report['generated_at']} by `eval/kappa.py`. PASS needs quadratic-weighted kappa >= "
        f"{report['threshold']:.2f} (the rubric's visibility gate).",
        "",
        "| Dimension | n | Kappa | 95% CI | Exact | Within 1 | Rater-rater kappa | Excluded | Status |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for d in report["dimensions"]:
        ci = "MISSING" if d["kappa_ci95"] is None else f"{d['kappa_ci95'][0]:.2f} to {d['kappa_ci95'][1]:.2f}"
        excluded = ", ".join(f"{k} {v}" for k, v in d["excluded"].items() if v) or "none"
        lines.append(
            f"| {d['key']} | {d['n']} | {_fmt(d['kappa'])} | {ci} | {_fmt(d['exact_agreement'], True)} | "
            f"{_fmt(d['within_one'], True)} | {_fmt(d['rater_rater_kappa'])} | {excluded} | {d['status']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--ai-dir", type=Path, required=True, help="analysis@v1 reports, <recording_id>.json")
    parser.add_argument("--rater-scores", type=Path, nargs="+", required=True, help="import_scores.py output files")
    parser.add_argument("--split", type=Path, default=EVAL_DIR / "calibration" / "split.json")
    parser.add_argument("--part", choices=["holdout", "train"], default="holdout")
    parser.add_argument("--out-dir", type=Path, default=EVAL_DIR / "reports")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        split = load_split(args.split)
        recordings = sorted(rid for rid, part in split["assignments"].items() if part == args.part)
        dims = [d.key for d in load_rubric_dimensions(args.rubric)]
        threshold = visibility_gate_min(args.rubric)
        ai, missing = load_ai_scores(args.ai_dir, recordings)
        raters = load_rater_scores(args.rater_scores)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    generated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = {
        "rubric": args.rubric.stem,
        "part": args.part,
        "generated_at": generated,
        "threshold": threshold,
        "recordings": len(recordings),
        "ai_reports_missing": missing,
        "dimensions": evaluate(
            dimensions=dims, recordings=recordings, ai=ai, raters=raters, threshold=threshold, seed=args.seed
        ),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"kappa-{generated[:10]}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md = markdown(report)
    (args.out_dir / f"kappa-{generated[:10]}.md").write_text(md, encoding="utf-8")
    print(md)
    return 0 if all(d["status"] == "PASS" for d in report["dimensions"]) else 1


if __name__ == "__main__":
    sys.exit(main())
