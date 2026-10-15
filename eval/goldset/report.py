"""Gold-set coverage report (plan task P4.2).

    uv run python eval/goldset/report.py [--split holdout|dev|all]

Prints hours by language mix, room type and school, for completed recordings and for all recordings in the
manifest. Hours come from the manifest's duration_s. The school is the `tenant` recorded in the gold transcript;
recordings without a gold transcript yet are counted under "(no gold yet)".
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path

from manifest import ManifestError, ManifestRow, read_manifest

GOLDSET_DIR = Path(__file__).resolve().parent
NO_GOLD = "(no gold yet)"


def school_of(row: ManifestRow, gold_dir: Path) -> str:
    path = gold_dir / f"{row.recording_id}.json"
    if not path.is_file():
        return NO_GOLD
    try:
        tenant = json.loads(path.read_text(encoding="utf-8")).get("tenant")
    except json.JSONDecodeError:
        return NO_GOLD
    return str(tenant) if tenant else NO_GOLD


def table(title: str, rows: Sequence[ManifestRow], key: Callable[[ManifestRow], str]) -> list[str]:
    completed: dict[str, float] = defaultdict(float)
    everything: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        group = key(row)
        everything[group] += row.duration_s / 3600
        counts[group] += 1
        if row.status == "completed":
            completed[group] += row.duration_s / 3600
    lines = [f"## {title}", "", "| Group | Recordings | Hours (completed) | Hours (all) |", "| --- | --- | --- | --- |"]
    for group in sorted(everything):
        lines.append(f"| {group} | {counts[group]} | {completed[group]:.2f} | {everything[group]:.2f} |")
    lines.append(
        f"| **Total** | {sum(counts.values())} | {sum(completed.values()):.2f} | {sum(everything.values()):.2f} |"
    )
    return [*lines, ""]


def render(rows: Sequence[ManifestRow], gold_dir: Path, split: str) -> str:
    chosen = [r for r in rows if split == "all" or r.split == split]
    lines = [f"# Gold-set coverage: {split}", ""]
    if not chosen:
        return "\n".join([*lines, "No recordings in this split yet.", ""])
    lines += table("By language mix", chosen, lambda r: r.language_mix)
    lines += table("By room type", chosen, lambda r: r.room_type)
    lines += table("By school", chosen, lambda r: school_of(r, gold_dir))
    lines += table("By status", chosen, lambda r: r.status)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", type=Path, default=GOLDSET_DIR / "manifest.csv")
    parser.add_argument("--gold-dir", type=Path, default=GOLDSET_DIR / "gold")
    parser.add_argument("--split", choices=["holdout", "dev", "all"], default="all")
    args = parser.parse_args(argv)
    try:
        rows = read_manifest(args.manifest)
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(render(rows, args.gold_dir, args.split))
    return 0


if __name__ == "__main__":
    sys.exit(main())
