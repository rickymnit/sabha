"""Freeze the gold-set hold-out split (plan task P4.2).

    uv run python eval/goldset/freeze.py            # validate and write eval/goldset/FROZEN.json
    uv run python eval/goldset/freeze.py --check    # verify nothing frozen has changed (exit 1 if it has)

Freezing refuses unless every hold-out recording in manifest.csv is `completed` and has a valid gold transcript
(export_gold.check_transcript) with at least one labelled speech segment, and unless the hold-out adds up to at
least `goldset.holdout_hours_min` hours from eval/targets.yaml. That target must be set by a person; an unset
target refuses rather than freezing whatever exists.

FROZEN.json records a SHA-256 of every hold-out gold transcript (and of its audio file when the audio is present
under eval/goldset/audio/), the hold-out membership and the hours per language mix and room type. It holds hashes
only, never transcript text, so it can be committed.

`--check` compares the current files with FROZEN.json: a changed, added, removed or re-split hold-out recording
fails. Gold transcripts and audio are real data and are not in git (golden rule 11), so the check can only run
where the gold set lives; files that are absent here are reported as "not available", which is exit code 3.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from export_gold import check_transcript
from manifest import ManifestError, ManifestRow, read_manifest

GOLDSET_DIR = Path(__file__).resolve().parent
DEFAULTS = {
    "manifest": GOLDSET_DIR / "manifest.csv",
    "gold_dir": GOLDSET_DIR / "gold",
    "audio_dir": GOLDSET_DIR / "audio",
    "frozen": GOLDSET_DIR / "FROZEN.json",
    "targets": GOLDSET_DIR.parent / "targets.yaml",
}
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_NOT_AVAILABLE = 0, 1, 2, 3


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def holdout_hours_min(targets_path: Path) -> float | None:
    if not targets_path.is_file():
        return None
    data = yaml.safe_load(targets_path.read_text(encoding="utf-8")) or {}
    value = (data.get("goldset") or {}).get("holdout_hours_min") if isinstance(data, dict) else None
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"goldset.holdout_hours_min must be a number, got {value!r}")
    return float(value)


def validate_holdout(rows: Sequence[ManifestRow], gold_dir: Path) -> list[str]:
    problems: list[str] = []
    holdout = [r for r in rows if r.split == "holdout"]
    if not holdout:
        problems.append("the manifest has no hold-out recordings")
    for row in holdout:
        where = f"{row.recording_id} (manifest line {row.line})"
        if row.status != "completed":
            problems.append(f"{where}: status is {row.status!r}, not completed")
            continue
        path = gold_dir / f"{row.recording_id}.json"
        if not path.is_file():
            problems.append(f"{where}: no gold transcript at {path}")
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{where}: gold transcript is not valid JSON ({exc})")
            continue
        problems.extend(f"{where}: {p}" for p in check_transcript(doc))
        speech = [s for s in doc.get("segments", []) if isinstance(s, dict) and s.get("speaker_role") != "silence"]
        if not speech:
            problems.append(f"{where}: no labelled speech segments")
    return problems


def hours_by(rows: Sequence[ManifestRow], attribute: str) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        totals[str(getattr(row, attribute))] += row.duration_s / 3600
    return {k: round(v, 3) for k, v in sorted(totals.items())}


def build_frozen(rows: Sequence[ManifestRow], gold_dir: Path, audio_dir: Path) -> dict[str, Any]:
    holdout = sorted((r for r in rows if r.split == "holdout"), key=lambda r: r.recording_id)
    files = []
    for row in holdout:
        audio = audio_dir / row.file
        files.append(
            {
                "recording_id": row.recording_id,
                "gold_sha256": sha256(gold_dir / f"{row.recording_id}.json"),
                "audio_file": row.file,
                "audio_sha256": sha256(audio) if audio.is_file() else None,
                "duration_s": row.duration_s,
                "language_mix": row.language_mix,
                "room_type": row.room_type,
            }
        )
    return {
        "frozen_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "holdout_hours": round(sum(r.duration_s for r in holdout) / 3600, 3),
        "hours_by_language_mix": hours_by(holdout, "language_mix"),
        "hours_by_room_type": hours_by(holdout, "room_type"),
        "files": files,
    }


def check(frozen_path: Path, rows: Sequence[ManifestRow], gold_dir: Path, audio_dir: Path) -> int:
    if not frozen_path.is_file():
        print(f"nothing frozen yet ({frozen_path} does not exist)")
        return EXIT_OK
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    expected = {f["recording_id"]: f for f in frozen["files"]}
    current = {r.recording_id: r for r in rows if r.split == "holdout"}
    removed, added = sorted(set(expected) - set(current)), sorted(set(current) - set(expected))
    failures = [f"{rid}: was frozen in the hold-out but is no longer in it" for rid in removed]
    failures += [f"{rid}: added to the hold-out after freezing" for rid in added]
    not_available = []
    for rid, entry in sorted(expected.items()):
        gold = gold_dir / f"{rid}.json"
        if not gold.is_file():
            not_available.append(f"{rid}: gold transcript not available here")
        elif sha256(gold) != entry["gold_sha256"]:
            failures.append(f"{rid}: gold transcript changed after freezing")
        audio = audio_dir / entry["audio_file"]
        if entry.get("audio_sha256") and audio.is_file() and sha256(audio) != entry["audio_sha256"]:
            failures.append(f"{rid}: audio changed after freezing")
    for line in failures:
        print(f"FAIL  {line}")
    for line in not_available:
        print(f"N/A   {line}")
    if failures:
        return EXIT_FAILED
    if not_available:
        print("Some frozen files are not on this machine, so they could not be verified.")
        return EXIT_NOT_AVAILABLE
    print(f"ok: {len(expected)} frozen hold-out recordings unchanged")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="verify FROZEN.json instead of writing it")
    parser.add_argument("--manifest", type=Path, default=DEFAULTS["manifest"])
    parser.add_argument("--gold-dir", type=Path, default=DEFAULTS["gold_dir"])
    parser.add_argument("--audio-dir", type=Path, default=DEFAULTS["audio_dir"])
    parser.add_argument("--frozen", type=Path, default=DEFAULTS["frozen"])
    parser.add_argument("--targets", type=Path, default=DEFAULTS["targets"])
    parser.add_argument(
        "--replace", action="store_true", help="overwrite an existing FROZEN.json (say why in the commit)"
    )
    args = parser.parse_args(argv)
    try:
        rows = read_manifest(args.manifest)
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if args.check:
        return check(args.frozen, rows, args.gold_dir, args.audio_dir)

    if args.frozen.exists() and not args.replace:
        print(f"refusing: {args.frozen} already exists; a frozen hold-out is changed only on purpose (--replace)")
        return EXIT_FAILED
    problems = validate_holdout(rows, args.gold_dir)
    if problems:
        print("refusing to freeze:\n  " + "\n  ".join(problems))
        return EXIT_FAILED
    try:
        minimum = holdout_hours_min(args.targets)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    hours = sum(r.duration_s for r in rows if r.split == "holdout") / 3600
    if minimum is None:
        print(f"refusing to freeze: set goldset.holdout_hours_min in {args.targets} first (hold-out has {hours:.2f} h)")
        return EXIT_FAILED
    if hours < minimum:
        print(f"refusing to freeze: hold-out has {hours:.2f} h, below the target of {minimum:g} h")
        return EXIT_FAILED
    frozen = build_frozen(rows, args.gold_dir, args.audio_dir)
    args.frozen.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
    print(f"froze {len(frozen['files'])} hold-out recordings, {frozen['holdout_hours']} h -> {args.frozen}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
