"""Speaker role accuracy and role-level diarization error rate on the gold set (plan task P4.3).

    uv run python eval/roles.py --hyp-dir <dir of transcript@v1 files> [--split holdout]

- Role accuracy: the share of reference speech time that the system attributed to the correct role
  (teacher, students, receptionist, caller, other). Overlapping reference speech counts once per speaker.
- Role-level DER = (missed speech + false alarm + speaker confusion) / reference speech time. The gold set labels
  roles, not individual voices (all students are one group), so each system speaker_label is mapped to the
  reference role it overlaps most, and several system speakers may map to the same role. Speech the system
  produced inside gold silence is a false alarm. No collar is applied.

The two answer different questions: a perfect diarization with swapped roles has DER 0 and role accuracy 0.
Totals are time-weighted over files. Missing system transcripts make the report incomplete, and then no target is
reported as met (targets: gate1.role_accuracy_min and gate1.der_max in eval/targets.yaml).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "goldset"))  # run as a script: python eval/roles.py

from evaldata import EvalDataError, Span, load_gold, load_system, load_targets, target
from manifest import ManifestError, read_manifest

EVAL_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class RoleCounts:
    ref_ms: int = 0
    correct_role_ms: int = 0
    missed_ms: int = 0
    false_alarm_ms: int = 0
    confusion_ms: int = 0

    @property
    def role_accuracy(self) -> float | None:
        return self.correct_role_ms / self.ref_ms if self.ref_ms else None

    @property
    def der(self) -> float | None:
        return (self.missed_ms + self.false_alarm_ms + self.confusion_ms) / self.ref_ms if self.ref_ms else None


def _speaker_to_role(reference: Sequence[Span], system: Sequence[Span]) -> dict[str, str]:
    """Map each system speaker to the reference role it overlaps most (many-to-one)."""
    overlap: dict[str, Counter[str]] = defaultdict(Counter)
    for h in system:
        for r in reference:
            shared = min(h.end_ms, r.end_ms) - max(h.start_ms, r.start_ms)
            if shared > 0:
                overlap[h.speaker][r.role] += shared
    return {speaker: roles.most_common(1)[0][0] for speaker, roles in overlap.items()}


def score_roles(reference: Sequence[Span], system: Sequence[Span]) -> RoleCounts:
    """Role accuracy and role-level DER counts for one recording, by sweeping the elementary time intervals."""
    mapping = _speaker_to_role(reference, system)
    bounds = sorted({t for s in (*reference, *system) for t in (s.start_ms, s.end_ms)})
    ref_ms = correct = missed = false_alarm = confusion = 0
    for start, end in pairwise(bounds):
        duration = end - start
        ref_roles = {r.role for r in reference if r.start_ms <= start and r.end_ms >= end}
        active = [h for h in system if h.start_ms <= start and h.end_ms >= end]
        sys_roles = {h.role for h in active}
        sys_speakers = {h.speaker for h in active}
        mapped = Counter(mapping[s] for s in sys_speakers if s in mapping)
        unmapped = len(sys_speakers) - sum(mapped.values())  # system speakers that never overlap reference speech
        n_ref, n_sys = len(ref_roles), len(sys_speakers)
        n_correct = sum(min(1, mapped[role]) for role in ref_roles) if n_sys else 0
        n_correct = min(n_correct, n_sys - unmapped) if n_sys else 0
        ref_ms += duration * n_ref
        correct += duration * len(ref_roles & sys_roles)
        missed += duration * max(0, n_ref - n_sys)
        false_alarm += duration * max(0, n_sys - n_ref)
        confusion += duration * (min(n_ref, n_sys) - n_correct)
    return RoleCounts(ref_ms, correct, missed, false_alarm, confusion)


def total(items: Iterable[RoleCounts]) -> RoleCounts:
    sums: Counter[str] = Counter()
    for c in items:
        sums.update(asdict(c))
    return RoleCounts(**{k: sums[k] for k in RoleCounts.__dataclass_fields__})


def _pct(value: float | None) -> str:
    return "MISSING" if value is None else f"{value * 100:.1f}%"


def _status(value: float | None, limit: float | None, *, complete: bool, higher_is_better: bool) -> str:
    if limit is None:
        return "target not set"
    if value is None or not complete:
        return "not assessed (data missing)"
    ok = value >= limit if higher_is_better else value <= limit
    return "met" if ok else "not met"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--hyp-dir", type=Path, required=True, help="system transcripts, <recording_id>.json")
    parser.add_argument("--manifest", type=Path, default=EVAL_DIR / "goldset" / "manifest.csv")
    parser.add_argument("--gold-dir", type=Path, default=EVAL_DIR / "goldset" / "gold")
    parser.add_argument("--split", choices=["dev", "holdout"], default="holdout")
    parser.add_argument("--targets", type=Path, default=EVAL_DIR / "targets.yaml")
    parser.add_argument("--out-dir", type=Path, default=EVAL_DIR / "reports")
    args = parser.parse_args(argv)
    try:
        rows = read_manifest(args.manifest)
        targets = load_targets(args.targets)
    except (ManifestError, EvalDataError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    per_file: list[tuple[str, RoleCounts]] = []
    missing: list[str] = []
    errors: list[str] = []
    for row in rows:
        if row.split != args.split or row.status != "completed":
            continue
        hyp_path = args.hyp_dir / f"{row.recording_id}.json"
        if not hyp_path.is_file():
            missing.append(row.recording_id)
            continue
        try:
            reference = load_gold(args.gold_dir / f"{row.recording_id}.json")
            per_file.append((row.recording_id, score_roles(reference, load_system(hyp_path))))
        except EvalDataError as exc:
            errors.append(str(exc))

    complete = bool(per_file) and not missing and not errors
    overall = total(c for _, c in per_file)
    acc_target = target(targets, "gate1", "role_accuracy_min")
    der_target = target(targets, "gate1", "der_max")
    checks = [
        ("Role accuracy (overall)", overall.role_accuracy, acc_target, "min",
         _status(overall.role_accuracy, acc_target, complete=complete, higher_is_better=True)),
        ("Role-level DER (overall)", overall.der, der_target, "max",
         _status(overall.der, der_target, complete=complete, higher_is_better=False)),
    ]  # fmt: skip
    generated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [f"# Role report: {args.split} split", "", f"Generated {generated} by `eval/roles.py`.", ""]
    if not complete:
        lines += ["> **Incomplete:** some recordings could not be scored (below). No target is reported as met.", ""]
    lines += ["| Metric | Value | Target | Status |", "| --- | --- | --- | --- |"]
    for metric, value, limit, kind, status in checks:
        shown = "not set" if limit is None else f"{kind} {_pct(limit)}"
        lines.append(f"| {metric} | {_pct(value)} | {shown} | {status} |")
    lines += ["", "| Recording | Speech (s) | Role accuracy | DER | Missed (s) | False alarm (s) | Confusion (s) |",
              "| --- | --- | --- | --- | --- | --- | --- |"]  # fmt: skip
    lines += [
        f"| {rid} | {c.ref_ms / 1000:.1f} | {_pct(c.role_accuracy)} | {_pct(c.der)} | {c.missed_ms / 1000:.1f} | "
        f"{c.false_alarm_ms / 1000:.1f} | {c.confusion_ms / 1000:.1f} |"
        for rid, c in per_file
    ]
    if missing or errors:
        lines += ["", "## Not scored", ""] + [f"- MISSING system transcript: {r}" for r in missing]
        lines += [f"- Input error: {e}" for e in errors]
    md = "\n".join(lines) + "\n"
    data = {
        "split": args.split,
        "generated_at": generated,
        "complete": complete,
        "overall": {**asdict(overall), "role_accuracy": overall.role_accuracy, "der": overall.der},
        "targets": [{"metric": m, "value": v, "target": t, "kind": k, "status": st} for m, v, t, k, st in checks],
        "files": [
            {"recording_id": rid, **asdict(c), "role_accuracy": c.role_accuracy, "der": c.der} for rid, c in per_file
        ],
        "missing": missing,
        "input_errors": errors,
    }
    stamp = generated[:10]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"roles-{stamp}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (args.out_dir / f"roles-{stamp}.md").write_text(md, encoding="utf-8")
    print(md)
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
