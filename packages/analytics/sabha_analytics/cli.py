"""`sabha-rubric`: validate, diff and publish rubric files (plan task P5.4).

    uv run sabha-rubric validate <file> [<file> ...]   print problems; exit 1 if any file is invalid
    uv run sabha-rubric diff <old> <new>               dimension-by-dimension changes from old to new
    uv run sabha-rubric diff <file>                    changes from the previous version in the same folder
    uv run sabha-rubric publish <file> [<file> ...]    publish immutable versions; exit 1 on a version conflict

`publish` is a DRY RUN until the tenant-scoped repository (P1.6) provides the MongoDB rubrics store: it validates,
hashes and publishes into an in-memory store that is thrown away when the command ends.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from sabha_analytics.rubric import (
    InMemoryRubricStore,
    PublishOutcome,
    RubricError,
    RubricStore,
    RubricVersionConflictError,
    diff_rubrics,
    find_previous_version,
    load_rubric,
    publish_rubric,
)

DRY_RUN_NOTICE = (
    "DRY RUN: nothing is saved. Rubrics are published to an in-memory store until the tenant-scoped repository "
    "(P1.6) provides the MongoDB rubrics store."
)


def _error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


def _validate(files: Sequence[Path]) -> int:
    status = 0
    for path in files:
        try:
            rubric, content_hash = load_rubric(path)
        except RubricError as exc:
            status = 1
            print(f"INVALID {path}")
            for problem in exc.problems:
                print(f"  - {problem}")
            continue
        print(f"ok      {path}  {rubric.id}  sha256:{content_hash}")
    return status


def _diff(old_path: Path, new_path: Path | None) -> int:
    if new_path is None:
        new_path = old_path
        try:
            previous = find_previous_version(new_path)
        except ValueError as exc:
            _error(str(exc))
            return 1
        if previous is None:
            _error(f"no previous version of {new_path.name} in {new_path.parent}")
            return 1
        old_path = previous
    try:
        old, _ = load_rubric(old_path)
        new, _ = load_rubric(new_path)
    except RubricError as exc:
        _error(str(exc))
        return 1
    changes = diff_rubrics(old, new)
    print(f"{old.id} -> {new.id}: {len(changes)} change(s)")
    for change in changes:
        print(f"  {change}")
    return 0


def _publish(files: Sequence[Path], store: RubricStore | None) -> int:
    if store is None:
        store = InMemoryRubricStore()
    if isinstance(store, InMemoryRubricStore):
        print(DRY_RUN_NOTICE)
    status = 0
    for path in files:
        try:
            rubric, content_hash = load_rubric(path)
            outcome = publish_rubric(rubric, content_hash, store)
        except (RubricError, RubricVersionConflictError) as exc:
            _error(str(exc))
            status = 1
            continue
        if outcome is PublishOutcome.PUBLISHED:
            print(f"published {rubric.id}  sha256:{content_hash}")
        else:
            print(f"unchanged {rubric.id}: already published with the same content")
    return status


def main(argv: Sequence[str] | None = None, *, store: RubricStore | None = None) -> int:
    """Entry point of the `sabha-rubric` console script. `store` lets tests pass a store; the CLI uses none."""
    parser = argparse.ArgumentParser(prog="sabha-rubric", description="Validate, diff and publish rubric files.")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="check rubric files and print every problem")
    validate.add_argument("files", nargs="+", type=Path)
    diff = commands.add_parser("diff", help="compare two rubric files, or one with its previous version")
    diff.add_argument("old", type=Path, help="the older file, or the only file to compare with its previous version")
    diff.add_argument("new", type=Path, nargs="?", help="the newer file")
    publish = commands.add_parser("publish", help="publish immutable rubric versions (dry run until P1.6)")
    publish.add_argument("files", nargs="+", type=Path)

    args = parser.parse_args(argv)
    if args.command == "validate":
        return _validate(args.files)
    if args.command == "diff":
        return _diff(args.old, args.new)
    return _publish(args.files, store)


if __name__ == "__main__":
    raise SystemExit(main())
