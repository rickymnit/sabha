"""Word and character error rates on the gold set (plan task P4.3; `make eval-wer`).

    uv run python eval/wer.py --hyp-dir <dir of transcript@v1 files> [--split holdout]

For every completed recording of the chosen split in eval/goldset/manifest.csv, the gold transcript (reference) is
compared with the system transcript of the same recording_id (hypothesis). Text is normalised by textnorm.py, once
as written (raw) and once transliterated; both are reported.

Definitions:
- WER = (substitutions + deletions + insertions) / reference words, from an exact minimum-edit alignment. A privacy
  token in the reference ([student], [name], ...) matches any single hypothesis word at no cost.
- CER is computed over that word alignment: a substituted word pair counts its character edit distance, inserted
  and deleted words count all their characters, matched words count none. It is not a global character
  alignment (too slow in pure Python for hour-long lessons); it can only be higher than a global one. Characters
  exclude spaces; a privacy token counts as one character.
- Totals are word-weighted (all errors / all reference words), per language mix, per room type and overall.
- 95% confidence intervals: percentile bootstrap over files (files resampled with replacement), seeded.

Nothing is estimated. A recording without a system transcript is listed as MISSING and the targets are reported
as "not assessed" rather than met. Targets come from eval/targets.yaml; a null target is "not set".
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "goldset"))  # run as a script: python eval/wer.py

from evaldata import EvalDataError, load_gold, load_system, load_targets, target, text_of
from manifest import ManifestError, ManifestRow, read_manifest
from textnorm import PRIVACY_TOKENS, tokens

EVAL_DIR = Path(__file__).resolve().parent
_DIAG, _UP, _LEFT = 0, 1, 2  # backtrace: match/substitution, deletion, insertion


@dataclass(frozen=True)
class Counts:
    ref_words: int
    substitutions: int
    deletions: int
    insertions: int
    ref_chars: int = 0
    char_errors: int = 0
    wildcard_matches: int = 0

    @property
    def errors(self) -> int:
        return self.substitutions + self.deletions + self.insertions

    @property
    def wer(self) -> float | None:
        return self.errors / self.ref_words if self.ref_words else None

    @property
    def cer(self) -> float | None:
        return self.char_errors / self.ref_chars if self.ref_chars else None


def _char_len(word: str) -> int:
    return 1 if word in PRIVACY_TOKENS else len(word)


def _char_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def align(ref: Sequence[str], hyp: Sequence[str], *, wildcards: frozenset[str] = PRIVACY_TOKENS) -> Counts:
    """Minimum-edit word alignment with substitution, deletion and insertion counts.

    Ties prefer a match or substitution, then a deletion, then an insertion. Memory is one cost row plus one byte
    per cell for the backtrace.
    """
    n, m = len(ref), len(hyp)
    back = bytearray((n + 1) * (m + 1))
    prev = list(range(m + 1))
    for j in range(1, m + 1):
        back[j] = _LEFT
    for i in range(1, n + 1):
        r = ref[i - 1]
        wild = r in wildcards
        cur = [i] + [0] * m
        back[i * (m + 1)] = _UP
        row = i * (m + 1)
        for j in range(1, m + 1):
            diag = prev[j - 1] + (0 if wild or r == hyp[j - 1] else 1)
            up = prev[j] + 1
            left = cur[j - 1] + 1
            if diag <= up and diag <= left:
                cur[j], back[row + j] = diag, _DIAG
            elif up <= left:
                cur[j], back[row + j] = up, _UP
            else:
                cur[j], back[row + j] = left, _LEFT
        prev = cur

    subs = dels = ins = wild_matches = char_errors = 0
    i, j = n, m
    while i > 0 or j > 0:
        move = back[i * (m + 1) + j]
        if move == _DIAG and i > 0 and j > 0:
            r, h = ref[i - 1], hyp[j - 1]
            if r in wildcards:
                wild_matches += 1
            elif r != h:
                subs += 1
                char_errors += _char_distance(r, h)
            i, j = i - 1, j - 1
        elif move == _UP and i > 0:
            dels += 1
            char_errors += _char_len(ref[i - 1])
            i -= 1
        else:
            ins += 1
            char_errors += _char_len(hyp[j - 1])
            j -= 1
    return Counts(
        ref_words=n,
        substitutions=subs,
        deletions=dels,
        insertions=ins,
        ref_chars=sum(_char_len(w) for w in ref),
        char_errors=char_errors,
        wildcard_matches=wild_matches,
    )


def corpus_counts(items: Iterable[Counts]) -> Counts:
    """Sum of counts: the word-weighted total."""
    total: dict[str, int] = defaultdict(int)
    for c in items:
        for key, value in asdict(c).items():
            total[key] += value
    return Counts(**{k: total[k] for k in Counts.__dataclass_fields__})


@dataclass(frozen=True)
class FileResult:
    recording_id: str
    language_mix: str
    room_type: str
    raw: Counts
    transliterated: Counts


def group_results(results: Iterable[FileResult], key: Callable[[FileResult], str]) -> dict[str, list[FileResult]]:
    groups: dict[str, list[FileResult]] = defaultdict(list)
    for result in results:
        groups[key(result)].append(result)
    return dict(groups)


def bootstrap_ci(
    results: Sequence[FileResult],
    pick: Callable[[FileResult], Counts],
    *,
    seed: int,
    iterations: int = 2000,
    level: float = 0.95,
) -> tuple[float, float] | None:
    """Percentile bootstrap interval of the word-weighted WER, resampling files. None with fewer than 2 files."""
    if len(results) < 2:
        return None
    rng = random.Random(seed)  # noqa: S311  # statistical resampling, not security
    values: list[float] = []
    for _ in range(iterations):
        sample = corpus_counts(pick(rng.choice(results)) for _ in results)
        if sample.wer is not None:
            values.append(sample.wer)
    if not values:
        return None
    values.sort()
    low_index = int(((1 - level) / 2) * (len(values) - 1))
    high_index = int((1 - (1 - level) / 2) * (len(values) - 1))
    return values[low_index], values[high_index]


# --- report --------------------------------------------------------------------------------------------------------


@dataclass
class Report:
    split: str
    generated_at: str
    files: list[FileResult] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # completed gold files with no system transcript
    errors: list[str] = field(default_factory=list)


def evaluate(rows: Sequence[ManifestRow], gold_dir: Path, hyp_dir: Path, split: str) -> Report:
    report = Report(split=split, generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    for row in rows:
        if row.split != split or row.status != "completed":
            continue
        hyp_path = hyp_dir / f"{row.recording_id}.json"
        if not hyp_path.is_file():
            report.missing.append(row.recording_id)
            continue
        try:
            ref_text = text_of(load_gold(gold_dir / f"{row.recording_id}.json"))
            hyp_text = text_of(load_system(hyp_path))
        except EvalDataError as exc:
            report.errors.append(str(exc))
            continue
        report.files.append(
            FileResult(
                recording_id=row.recording_id,
                language_mix=row.language_mix,
                room_type=row.room_type,
                raw=align(tokens(ref_text), tokens(hyp_text)),
                transliterated=align(tokens(ref_text, transliterated=True), tokens(hyp_text, transliterated=True)),
            )
        )
    return report


def _pct(value: float | None) -> str:
    return "MISSING" if value is None else f"{value * 100:.1f}%"


def _ci(interval: tuple[float, float] | None) -> str:
    return "MISSING" if interval is None else f"{interval[0] * 100:.1f} to {interval[1] * 100:.1f}%"


def target_status(value: float | None, limit: float | None, *, complete: bool) -> str:
    """'met', 'not met', 'target not set' or 'not assessed'; never 'met' without complete data."""
    if limit is None:
        return "target not set"
    if value is None or not complete:
        return "not assessed (data missing)"
    return "met" if value <= limit else "not met"


@dataclass(frozen=True)
class GroupStats:
    name: str
    files: int
    ref_words: int
    wer_raw: float | None
    wer_transliterated: float | None
    cer_raw: float | None
    wer_raw_ci95: tuple[float, float] | None
    wer_transliterated_ci95: tuple[float, float] | None


@dataclass(frozen=True)
class TargetCheck:
    metric: str
    value: float | None
    target_max: float | None
    status: str


@dataclass(frozen=True)
class Summary:
    split: str
    generated_at: str
    complete: bool
    overall: GroupStats
    by_language_mix: list[GroupStats]
    by_room_type: list[GroupStats]
    targets: list[TargetCheck]
    files: list[FileResult]
    missing: list[str]
    input_errors: list[str]
    bootstrap_seed: int


def _stats(name: str, items: Sequence[FileResult], seed: int) -> GroupStats:
    raw = corpus_counts(r.raw for r in items)
    translit = corpus_counts(r.transliterated for r in items)
    return GroupStats(
        name=name,
        files=len(items),
        ref_words=raw.ref_words,
        wer_raw=raw.wer,
        wer_transliterated=translit.wer,
        cer_raw=raw.cer,
        wer_raw_ci95=bootstrap_ci(items, lambda r: r.raw, seed=seed),
        wer_transliterated_ci95=bootstrap_ci(items, lambda r: r.transliterated, seed=seed),
    )


def summarise(report: Report, targets: dict[str, object], seed: int) -> Summary:
    complete = not report.missing and not report.errors and bool(report.files)
    by_mix = [_stats(k, v, seed) for k, v in sorted(group_results(report.files, lambda r: r.language_mix).items())]
    by_room = [_stats(k, v, seed) for k, v in sorted(group_results(report.files, lambda r: r.room_type).items())]
    overall = _stats("overall", report.files, seed)
    stats_by_name = {g.name: g for g in by_mix} | {"overall": overall}
    checks = []
    for mix in ("overall", "english", "hindi", "hinglish"):
        group = stats_by_name.get(mix)
        for kind in ("raw", "transliterated"):
            value = None if group is None else (group.wer_raw if kind == "raw" else group.wer_transliterated)
            limit = target(targets, "gate1", f"wer_{kind}_max", mix)
            status = target_status(value, limit, complete=complete)
            checks.append(TargetCheck(f"WER {kind} ({mix})", value, limit, status))
    return Summary(
        split=report.split,
        generated_at=report.generated_at,
        complete=complete,
        overall=overall,
        by_language_mix=by_mix,
        by_room_type=by_room,
        targets=checks,
        files=report.files,
        missing=report.missing,
        input_errors=report.errors,
        bootstrap_seed=seed,
    )


def markdown(s: Summary) -> str:
    o = s.overall
    lines = [
        f"# WER report: {s.split} split",
        "",
        f"Generated {s.generated_at} by `eval/wer.py`. Definitions are in the script's docstring.",
        "",
    ]
    if not s.complete:
        lines += ["> **Incomplete:** some recordings could not be scored (below). No target is reported as met.", ""]
    lines += [
        "## Overall (word-weighted)",
        "",
        "| Files | Reference words | WER raw | 95% CI | WER transliterated | 95% CI | CER (word-aligned) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        f"| {o.files} | {o.ref_words} | {_pct(o.wer_raw)} | {_ci(o.wer_raw_ci95)} | {_pct(o.wer_transliterated)} | "
        f"{_ci(o.wer_transliterated_ci95)} | {_pct(o.cer_raw)} |",
        "",
    ]
    for title, groups in (("By language mix", s.by_language_mix), ("By room type", s.by_room_type)):
        lines += [
            f"## {title}",
            "",
            "| Group | Files | Words | WER raw | 95% CI | WER transliterated | CER |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"| {g.name} | {g.files} | {g.ref_words} | {_pct(g.wer_raw)} | {_ci(g.wer_raw_ci95)} | "
            f"{_pct(g.wer_transliterated)} | {_pct(g.cer_raw)} |"
            for g in groups
        ]
        lines.append("")
    lines += ["## Targets (eval/targets.yaml)", "", "| Metric | Value | Target (max) | Status |"]
    lines += ["| --- | --- | --- | --- |"]
    lines += [f"| {c.metric} | {_pct(c.value)} | {_pct(c.target_max) if c.target_max is not None else 'not set'} | "
              f"{c.status} |" for c in s.targets]  # fmt: skip
    lines += [
        "",
        "## Per file",
        "",
        "| Recording | Mix | Room | Words | S | D | I | WER raw | WER translit. |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {f.recording_id} | {f.language_mix} | {f.room_type} | {f.raw.ref_words} | {f.raw.substitutions} | "
        f"{f.raw.deletions} | {f.raw.insertions} | {_pct(f.raw.wer)} | {_pct(f.transliterated.wer)} |"
        for f in s.files
    ]
    if s.missing or s.input_errors:
        lines += ["", "## Not scored", ""]
        lines += [f"- MISSING system transcript: {rid}" for rid in s.missing]
        lines += [f"- Input error: {e}" for e in s.input_errors]
    return "\n".join(lines) + "\n"


def to_json(s: Summary) -> str:
    def default(value: object) -> object:
        raise TypeError(f"not serialisable: {value!r}")

    data = asdict(s)
    for f, result in zip(data["files"], s.files, strict=True):
        f["raw"]["wer"], f["transliterated"]["wer"] = result.raw.wer, result.transliterated.wer
    return json.dumps(data, indent=2, ensure_ascii=False, default=default) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--hyp-dir", type=Path, required=True, help="system transcripts, <recording_id>.json")
    parser.add_argument("--manifest", type=Path, default=EVAL_DIR / "goldset" / "manifest.csv")
    parser.add_argument("--gold-dir", type=Path, default=EVAL_DIR / "goldset" / "gold")
    parser.add_argument("--split", choices=["dev", "holdout"], default="holdout")
    parser.add_argument("--targets", type=Path, default=EVAL_DIR / "targets.yaml")
    parser.add_argument("--out-dir", type=Path, default=EVAL_DIR / "reports")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        rows = read_manifest(args.manifest)
        targets = load_targets(args.targets)
    except (ManifestError, EvalDataError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = evaluate(rows, args.gold_dir, args.hyp_dir, args.split)
    s = summarise(report, targets, args.seed)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"wer-{stamp}.json").write_text(to_json(s), encoding="utf-8")
    md = markdown(s)
    (args.out_dir / f"wer-{stamp}.md").write_text(md, encoding="utf-8")
    print(md)
    return 0 if s.complete else 1


if __name__ == "__main__":
    sys.exit(main())
