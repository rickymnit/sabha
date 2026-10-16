"""Grounding evaluation over analysis reports (plan task P4.6).

    uv run python eval/grounding.py --ai-dir <dir of analysis@v1 reports>

Groups reports by model ids and scoring-prompt version (the SHA-256 of every scoring.* prompt), and reports per
group: how many evidence quotes the model offered and how many the grounding verifier accepted (from each
dimension's `grounding` counts, summed over both attempts), and how many dimensions were verified at the first
attempt, verified after the one re-ask, or excluded. Unverified quotes themselves are never stored, only counted.

Reports go to eval/reports/grounding-<date>.md and .json.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent


def _group_key(report: dict[str, Any]) -> tuple[str, str]:
    models = ", ".join(sorted(report.get("model_ids", []))) or "unknown"
    prompts = report.get("prompts", {})
    scoring = sorted(
        f"{name}@{p['version']}:{p['sha256'][:12]}" for name, p in prompts.items() if name.startswith("scoring")
    )
    return models, "; ".join(scoring) or "unknown"


def summarise(reports: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for report in reports:
        g = groups[_group_key(report)]
        g["reports"] += 1
        for d in report.get("dimensions", []):
            g["dimensions"] += 1
            counts = d.get("grounding", {})
            g["quotes_offered"] += int(counts.get("quotes_offered", 0))
            g["quotes_verified"] += int(counts.get("quotes_verified", 0))
            if not d.get("verified"):
                g["excluded"] += 1
            elif d.get("attempts") == 1:
                g["verified_first_attempt"] += 1
            else:
                g["verified_after_reask"] += 1
    out = []
    for (models, prompts), g in sorted(groups.items()):
        offered, dims = g["quotes_offered"], g["dimensions"]
        out.append(
            {
                "model_ids": models,
                "scoring_prompts": prompts,
                "reports": g["reports"],
                "dimensions": dims,
                "verified_first_attempt": g["verified_first_attempt"],
                "verified_after_reask": g["verified_after_reask"],
                "excluded": g["excluded"],
                "excluded_share": g["excluded"] / dims if dims else None,
                "quotes_offered": offered,
                "quotes_verified": g["quotes_verified"],
                "quotes_verified_share": g["quotes_verified"] / offered if offered else None,
            }
        )
    return out


def _pct(value: float | None) -> str:
    return "MISSING" if value is None else f"{value * 100:.1f}%"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ai-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=EVAL_DIR / "reports")
    args = parser.parse_args(argv)
    paths = sorted(args.ai_dir.glob("*.json"))
    if not paths:
        print(f"error: no reports in {args.ai_dir}", file=sys.stderr)
        return 2
    groups = summarise([json.loads(p.read_text(encoding="utf-8")) for p in paths])
    generated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# Grounding by model and prompt version",
        "",
        f"Generated {generated} by `eval/grounding.py` from {len(paths)} reports.",
        "",
        "| Models | Scoring prompts | Reports | Quotes verified | Dimensions: first try / after re-ask / excluded |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {g['model_ids']} | {g['scoring_prompts']} | {g['reports']} | {g['quotes_verified']} of "
        f"{g['quotes_offered']} ({_pct(g['quotes_verified_share'])}) | {g['verified_first_attempt']} / "
        f"{g['verified_after_reask']} / {g['excluded']} ({_pct(g['excluded_share'])} excluded) |"
        for g in groups
    ]
    md = "\n".join(lines) + "\n"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    data = {"generated_at": generated, "groups": groups}
    (args.out_dir / f"grounding-{generated[:10]}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (args.out_dir / f"grounding-{generated[:10]}.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
