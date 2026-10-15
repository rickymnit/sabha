"""Loading inputs shared by wer.py and roles.py: gold transcripts, system transcripts and targets (P4.3).

- Gold: eval/goldset/gold/<recording_id>.json, written by goldset/export_gold.py (goldset/transcript.schema.json).
  Segments are on the original timeline; `silence` segments carry no speech.
- System output: <hyp-dir>/<recording_id>.json in the transcript@v1 shape from the transcribe stage (P3.7):
  {"utterances": [{"role", "speaker_label", "start_ms", "end_ms", "text", ...}]} on the original timeline.
- Targets: eval/targets.yaml. A target that is missing or null is "not set", never assumed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SILENCE = "silence"


class EvalDataError(ValueError):
    """An input file is missing or not in the expected shape."""


@dataclass(frozen=True)
class Span:
    """A stretch of speech on the original timeline."""

    start_ms: int
    end_ms: int
    role: str
    speaker: str  # gold: the role (gold has no individual speaker ids); system: the diarization speaker_label
    text: str


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EvalDataError(f"not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvalDataError(f"{path}: not valid JSON ({exc})") from None
    if not isinstance(data, dict):
        raise EvalDataError(f"{path}: expected a JSON object")
    return data


def _span(item: Any, path: Path, *, role_key: str, speaker_key: str) -> Span:
    try:
        start, end = int(item["start_ms"]), int(item["end_ms"])
        role, speaker, text = str(item[role_key]), str(item[speaker_key]), str(item.get("text", ""))
    except (KeyError, TypeError, ValueError) as exc:
        raise EvalDataError(f"{path}: malformed segment {item!r} ({exc})") from None
    if end <= start:
        raise EvalDataError(f"{path}: segment ends before it starts: {item!r}")
    return Span(start_ms=start, end_ms=end, role=role, speaker=speaker, text=text)


def load_gold(path: Path) -> list[Span]:
    """Speech segments of a gold transcript (silence dropped), sorted by time."""
    data = _load_json(path)
    segments = data.get("segments")
    if not isinstance(segments, list):
        raise EvalDataError(f"{path}: no 'segments' list")
    spans = [_span(s, path, role_key="speaker_role", speaker_key="speaker_role") for s in segments]
    return sorted((s for s in spans if s.role != SILENCE), key=lambda s: (s.start_ms, s.end_ms))


def load_system(path: Path) -> list[Span]:
    """Utterances of a system transcript, sorted by time."""
    data = _load_json(path)
    utterances = data.get("utterances")
    if not isinstance(utterances, list):
        raise EvalDataError(f"{path}: no 'utterances' list (expected transcript@v1)")
    spans = [_span(u, path, role_key="role", speaker_key="speaker_label") for u in utterances]
    return sorted(spans, key=lambda s: (s.start_ms, s.end_ms))


def text_of(spans: list[Span]) -> str:
    return " ".join(s.text for s in spans)


def load_targets(path: Path) -> dict[str, Any]:
    """The targets file as a dict; an absent file means no targets are set."""
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise EvalDataError(f"{path}: expected a mapping at the top level")
    return data


def target(targets: dict[str, Any], *keys: str) -> float | None:
    """The number at targets[k1][k2]..., or None when any level is missing or the value is null."""
    node: Any = targets
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    if node is None:
        return None
    if isinstance(node, bool) or not isinstance(node, int | float):
        raise EvalDataError(f"target {'.'.join(keys)} must be a number or null, got {node!r}")
    return float(node)
