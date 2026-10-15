"""Shared pieces of the human-rater kit (plan task P4.4).

Rubric files are read directly here (only the dimension keys, names, anchors and examples), so the kit works
before sabha_analytics.rubric is published; it refuses a rubric without the five anchors a rater needs.

Rater sheets are plain CSV, which Google Sheets and Excel open and save without loss.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SCORE_COLUMNS = ("rater_id", "recording_id", "dimension_key", "dimension_name", "score", "note", "transcript_link")
"""Columns of a rater's score sheet. There is deliberately no column for an AI score."""

LEVELS = (1, 2, 3, 4, 5)


class RubricError(ValueError):
    """The rubric file cannot be used for rating."""


@dataclass(frozen=True)
class RaterDimension:
    key: str
    name: str
    definition: str
    anchors: dict[int, str]
    examples: dict[int, str]


def load_rubric_dimensions(path: Path) -> list[RaterDimension]:
    """The dimensions of the rubric at `path`, in file order."""
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RubricError(f"cannot read rubric {path}: {exc}") from None
    dimensions = data.get("dimensions") if isinstance(data, dict) else None
    if not isinstance(dimensions, list) or not dimensions:
        raise RubricError(f"{path}: no dimensions")
    result = []
    for item in dimensions:
        try:
            anchors = {int(k): str(v) for k, v in item["anchors"].items()}
            examples = {int(k): str(v) for k, v in (item.get("examples") or {}).items()}
            dimension = RaterDimension(str(item["key"]), str(item["name"]), str(item["definition"]), anchors, examples)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise RubricError(f"{path}: malformed dimension {item!r} ({exc})") from None
        if sorted(anchors) != list(LEVELS) or not all(anchors.values()):
            raise RubricError(f"{path}: dimension {dimension.key!r} needs an anchor for each level 1-5")
        result.append(dimension)
    keys = [d.key for d in result]
    if len(set(keys)) != len(keys):
        raise RubricError(f"{path}: duplicate dimension keys")
    return result
