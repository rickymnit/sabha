"""Rubric files: schema, loader, content hash, immutable versions and diff (plan task P5.4).

A rubric file is `rubrics/<type>.<segment>.v<major>.<minor>.yaml` (rubrics/README.md). This module validates it
against a frozen Pydantic model, hashes its content and publishes it as an immutable version.

Schema (matches rubrics/teaching.school.v0.1.yaml and rubrics/reception.school.v0.1.yaml; unknown keys are errors):

- `id`, `segment`, `version`, `roles`, `dimensions`, `computed_metrics`, `output`, `visibility_gate`, and the
  optional `output_values` (allowed values for an output section, such as reception's category and status).
- The rubric's `type` (teaching, reception, ...) is not a key in the file: it is the first part of `id`, and must be
  a sabha_core.profiles.ConversationType. `id` must equal f"{type}.{segment}.v{version}", and a file loaded from
  disk must be named f"{id}.yaml". So {type, segment, version} identifies a rubric, and the id and file name say the
  same thing.
- `version` is a quoted "major.minor" string without leading zeros ("0.1", "1.0", "1.10"). An unquoted 0.1 is a
  YAML float and is rejected, because 0.10 would silently become 0.1.
- `roles` are snake_case and unique. The FIRST role is the person analysed (teacher, receptionist); the others are
  context only and are never scored (golden rule 10). `primary_role` returns it.
- Each dimension: snake_case `key` unique within the rubric, non-blank `name` and `definition`, `weight` in (0, 1],
  `min_quotes` >= 1, `anchors` with exactly the levels 1-5 and non-blank text, and `examples` for some of the
  levels 1-5 that include at least 1 and 5, and an optional non-blank `not_applicable_when` (a condition under which
  the dimension does not apply to a conversation). Weights must sum to 1.0 within WEIGHT_TOLERANCE (0.001).
- `computed_metrics` must be keys sabha_analytics.metrics computes for the rubric's roles (or a documented alias).
- `output` sections are snake_case and unique; every `output_values` key must be one of them, with a non-empty list
  of unique snake_case values.
- `visibility_gate` is {metric: cohens_kappa, min: m} with 0 < m <= 1.
- YAML is read with a loader that rejects duplicate keys (PyYAML otherwise keeps the last one silently).

Content hash: SHA-256 (hex) of a canonical JSON serialisation of the VALIDATED model: `model_dump(mode="json",
exclude_none=True)` with sorted keys, no whitespace and UTF-8 text. So comments, whitespace, quoting, YAML key order
and number spelling (0.10 vs 0.1) do not change the hash; any change to the content does, including the order of
dimensions, roles and lists (order is shown to users). `exclude_none` keeps hashes stable if an optional key is
added to the schema later.

Versions are immutable. Publishing {type, segment, version} that is not yet stored inserts it; publishing it again
with the SAME hash is a no-op; with a DIFFERENT hash it fails ("bump the version"). Publishing goes through the
small RubricStore protocol. The MongoDB-backed store for the `rubrics` collection arrives with the tenant-scoped
repository (P1.6); until then InMemoryRubricStore is the only implementation, and `sabha-rubric publish` is a dry run.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, Literal, Protocol

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    Strict,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from sabha_analytics.metrics import available_metric_keys
from sabha_core.profiles import ConversationType

SCALE: tuple[int, ...] = (1, 2, 3, 4, 5)
REQUIRED_EXAMPLE_LEVELS: tuple[int, ...] = (1, 5)
WEIGHT_TOLERANCE = 0.001

_SNAKE = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"
_VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
RUBRIC_ID = re.compile(rf"^(?P<type>[a-z]+)\.(?P<segment>[a-z][a-z0-9_]*)\.v(?P<version>{_VERSION})$")
"""<type>.<segment>.v<major>.<minor>; the type pattern matches sabha_core.profiles."""
_FILE_NAME = re.compile(
    r"^(?P<type>[a-z]+)\.(?P<segment>[a-z][a-z0-9_]*)\.v(?P<major>[0-9]+)\.(?P<minor>[0-9]+)\.yaml$"
)


def _freeze[K, V](value: Mapping[K, V]) -> Mapping[K, V]:
    return MappingProxyType(dict(value))


def _thaw[K, V](value: Mapping[K, V]) -> dict[K, V]:
    return dict(value)


Text = Annotated[str, StringConstraints(pattern=r"\S")]
SnakeName = Annotated[str, StringConstraints(pattern=_SNAKE)]
ScaleText = Annotated[
    Mapping[Annotated[int, Strict()], Text],
    AfterValidator(_freeze),
    PlainSerializer(_thaw, return_type=dict[int, str]),
]
OutputValues = Annotated[
    Mapping[SnakeName, Annotated[tuple[SnakeName, ...], Field(min_length=1)]],
    AfterValidator(_freeze),
    PlainSerializer(_thaw, return_type=dict[str, tuple[str, ...]]),
]


def _duplicates(items: Iterable[Hashable]) -> list[Hashable]:
    seen: set[Hashable] = set()
    repeated: list[Hashable] = []
    for item in items:
        if item in seen and item not in repeated:
            repeated.append(item)
        seen.add(item)
    return repeated


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Dimension(_Frozen):
    """One scored dimension. `anchors` and `examples` are read-only mappings keyed by level (1-5)."""

    key: SnakeName
    name: Text
    weight: Annotated[float, Field(strict=True, gt=0, le=1)]
    definition: Text
    min_quotes: Annotated[int, Field(strict=True, ge=1)]
    anchors: ScaleText
    examples: ScaleText
    # When set, the judge may answer "not applicable" for a conversation that matches this condition (for example a
    # call with nothing to escalate). Such a dimension is left out of that conversation's overall score and the other
    # weights are rescaled (sabha_analytics.synthesis). The judge must still quote what the conversation was about.
    not_applicable_when: Text | None = None

    @field_validator("anchors")
    @classmethod
    def _all_levels(cls, anchors: Mapping[int, str]) -> Mapping[int, str]:
        missing = [level for level in SCALE if level not in anchors]
        extra = sorted(level for level in anchors if level not in SCALE)
        if missing or extra:
            raise ValueError(
                f"anchors must cover exactly the levels 1-5: missing {missing or 'none'}, extra {extra or 'none'}"
            )
        return anchors

    @field_validator("examples")
    @classmethod
    def _end_levels(cls, examples: Mapping[int, str]) -> Mapping[int, str]:
        extra = sorted(level for level in examples if level not in SCALE)
        if extra:
            raise ValueError(f"examples are only for the levels 1-5, not {extra}")
        missing = [level for level in REQUIRED_EXAMPLE_LEVELS if level not in examples]
        if missing:
            raise ValueError(f"examples must include the levels 1 and 5: missing {missing}")
        return examples


class VisibilityGate(_Frozen):
    """Scores stay hidden until agreement with human raters (eval/kappa.py) reaches `min`."""

    metric: Literal["cohens_kappa"]
    min: Annotated[float, Field(strict=True, gt=0, le=1)]


class Rubric(_Frozen):
    """A validated rubric file. See the module docstring for every rule."""

    id: str
    segment: SnakeName
    version: Annotated[str, Strict(), StringConstraints(pattern=rf"^{_VERSION}$")]
    roles: Annotated[tuple[SnakeName, ...], Field(min_length=1)]
    dimensions: Annotated[tuple[Dimension, ...], Field(min_length=1)]
    computed_metrics: tuple[SnakeName, ...]
    output: Annotated[tuple[SnakeName, ...], Field(min_length=1)]
    output_values: OutputValues | None = None
    visibility_gate: VisibilityGate

    @model_validator(mode="after")
    def _consistent(self) -> Rubric:
        problems = []
        for name, items in (
            ("role", self.roles),
            ("dimension key", [d.key for d in self.dimensions]),
            ("computed metric", self.computed_metrics),
            ("output section", self.output),
        ):
            problems += [f"duplicate {name} {item!r}" for item in _duplicates(items)]
        total = math.fsum(d.weight for d in self.dimensions)
        if abs(total - 1.0) > WEIGHT_TOLERANCE:
            problems.append(f"dimension weights must sum to 1.0 (within {WEIGHT_TOLERANCE}), got {total:g}")
        problems += self._id_problems()
        known = available_metric_keys(self.roles)
        problems += [
            f"computed metric {key!r} is not computed by sabha_analytics.metrics for the roles {list(self.roles)}"
            for key in self.computed_metrics
            if key not in known
        ]
        for section, allowed in (self.output_values or {}).items():
            if section not in self.output:
                problems.append(f"output_values has {section!r}, which is not listed in output")
            problems += [f"output_values.{section}: duplicate value {value!r}" for value in _duplicates(allowed)]
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def _id_problems(self) -> list[str]:
        match = RUBRIC_ID.fullmatch(self.id)
        if match is None:
            return [f"id {self.id!r} must look like <type>.<segment>.v<major>.<minor>"]
        types = [t.value for t in ConversationType]
        if match["type"] not in types:
            return [f"id {self.id!r}: type {match['type']!r} is not a conversation type ({', '.join(types)})"]
        expected = f"{match['type']}.{self.segment}.v{self.version}"
        if self.id != expected:
            return [f"id {self.id!r} does not match the segment and version: expected {expected!r}"]
        return []

    @property
    def type(self) -> str:
        """The conversation type: the first part of `id` (teaching, reception, ...)."""
        match = RUBRIC_ID.fullmatch(self.id)
        assert match is not None  # noqa: S101  # guaranteed by validation; narrows the type for mypy
        return match["type"]

    @property
    def primary_role(self) -> str:
        """The person analysed: the first role in the file."""
        return self.roles[0]

    @property
    def version_key(self) -> tuple[int, int]:
        """(major, minor) for ordering versions numerically."""
        major, minor = self.version.split(".")
        return int(major), int(minor)


# --- loading ---------------------------------------------------------------------------------------------------


class RubricError(ValueError):
    """A rubric file or mapping is invalid. `problems` lists each problem on its own."""

    def __init__(self, source: str, problems: Sequence[str]) -> None:
        self.source = source
        self.problems = tuple(problems)
        super().__init__(f"{source}: " + "; ".join(self.problems))


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys."""


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node)
        if isinstance(key, Hashable) and key in seen:
            raise yaml.constructor.ConstructorError(
                "while reading a mapping", node.start_mark, f"found duplicate key {key!r}", key_node.start_mark
            )
        seen.add(key)
    return loader.construct_mapping(node)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _format_error(error: Mapping[str, Any]) -> str:
    location = ".".join(str(part) for part in error["loc"]) or "rubric"
    message = str(error["msg"]).removeprefix("Value error, ")
    return f"{location}: {message}"


def parse_rubric(data: object, source: str = "<rubric>") -> Rubric:
    """Validate a rubric mapping (parsed YAML). Raises RubricError listing every problem found."""
    if not isinstance(data, Mapping):
        raise RubricError(source, ["a rubric must be a YAML mapping of keys to values"])
    try:
        return Rubric.model_validate(data)
    except ValidationError as exc:
        raise RubricError(source, [_format_error(error) for error in exc.errors()]) from None


def load_rubric(path: Path | str) -> tuple[Rubric, str]:
    """Read, validate and hash a rubric file. Raises RubricError (also for unreadable or malformed files)."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RubricError(str(path), [f"cannot read the file: {exc}"]) from None
    try:
        data = yaml.load(text, Loader=_StrictLoader)  # noqa: S506  # a SafeLoader subclass: no arbitrary objects
    except yaml.YAMLError as exc:
        raise RubricError(str(path), [f"not valid YAML: {exc}"]) from None
    rubric = parse_rubric(data, str(path))
    if path.name != f"{rubric.id}.yaml":
        raise RubricError(str(path), [f"file name {path.name!r} must be {rubric.id + '.yaml'!r} (the rubric id)"])
    return rubric, rubric_hash(rubric)


def canonical_json(rubric: Rubric) -> str:
    """The canonical serialisation that is hashed. See the module docstring."""
    return json.dumps(
        rubric.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def rubric_hash(rubric: Rubric) -> str:
    """SHA-256 hex digest of canonical_json(rubric)."""
    return hashlib.sha256(canonical_json(rubric).encode("utf-8")).hexdigest()


# --- publishing ------------------------------------------------------------------------------------------------


class RubricVersionExistsError(Exception):
    """A store already holds this {type, segment, version}. Raised by RubricStore.insert."""


class RubricVersionConflictError(Exception):
    """This {type, segment, version} is published with different content: versions are immutable."""


class PublishOutcome(StrEnum):
    PUBLISHED = "published"
    UNCHANGED = "unchanged"


class RubricStore(Protocol):
    """Where published rubric versions live. {type, segment, version} is unique and a stored version never changes.

    The MongoDB `rubrics` collection implements this once the tenant-scoped repository exists (P1.6); its unique
    index on {type, segment, version} makes `insert` atomic.
    """

    def get(self, rubric_type: str, segment: str, version: str) -> str | None:
        """The stored content hash, or None if this version is not published."""
        ...

    def insert(self, rubric: Rubric, content_hash: str) -> None:
        """Store a new version. Raises RubricVersionExistsError if it is already stored."""
        ...


class InMemoryRubricStore:
    """A RubricStore in a dict, for tests and for the dry-run CLI until P1.6 provides the database store."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str, str], tuple[str, str]] = {}

    def get(self, rubric_type: str, segment: str, version: str) -> str | None:
        row = self._rows.get((rubric_type, segment, version))
        return None if row is None else row[0]

    def insert(self, rubric: Rubric, content_hash: str) -> None:
        key = (rubric.type, rubric.segment, rubric.version)
        if key in self._rows:
            raise RubricVersionExistsError(f"{rubric.id} is already stored")
        self._rows[key] = (content_hash, canonical_json(rubric))

    def __len__(self) -> int:
        return len(self._rows)


def publish_rubric(rubric: Rubric, content_hash: str, store: RubricStore) -> PublishOutcome:
    """Publish an immutable version: insert if new, no-op if the same content is stored, else conflict."""
    if content_hash != rubric_hash(rubric):
        raise ValueError(f"content hash does not match {rubric.id}: pass the hash that load_rubric returned")
    stored = store.get(rubric.type, rubric.segment, rubric.version)
    if stored is None:
        try:
            store.insert(rubric, content_hash)
        except RubricVersionExistsError:
            stored = store.get(rubric.type, rubric.segment, rubric.version)  # another publisher got there first
        else:
            return PublishOutcome.PUBLISHED
    if stored == content_hash:
        return PublishOutcome.UNCHANGED
    raise RubricVersionConflictError(
        f"{rubric.id} is already published with different content (stored {str(stored)[:12]}, this file "
        f"{content_hash[:12]}). Versions are immutable: bump the version and publish it as a new file."
    )


# --- diff ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Change:
    """One difference between two rubrics. `dimension` is None for rubric-level fields."""

    dimension: str | None
    item: str
    old: str | None
    new: str | None

    def __str__(self) -> str:
        where = self.dimension if self.dimension is not None else "rubric"
        if self.old is None and self.new is None:
            return f"{where}: {self.item}"
        if self.old is not None and self.new is not None and "\n" not in self.old + self.new and len(self.old) < 40:
            return f"{where}: {self.item} {self.old} -> {self.new}"
        return f"{where}: {self.item} changed\n  - {self.old}\n  + {self.new}"


def _show(value: object) -> str:
    if isinstance(value, tuple):
        return ", ".join(str(item) for item in value)
    if isinstance(value, Mapping):
        return "; ".join(f"{key}: {_show(item)}" for key, item in value.items())
    return str(value)


def diff_rubrics(old: Rubric, new: Rubric) -> tuple[Change, ...]:
    """Differences from `old` to `new`: dimensions added or removed, then weights, anchors, definitions and the
    other dimension fields, then rubric-level fields. Empty when the content is the same."""
    changes: list[Change] = []
    old_dims = {d.key: d for d in old.dimensions}
    new_dims = {d.key: d for d in new.dimensions}
    changes += [Change(key, "dimension removed", None, None) for key in old_dims if key not in new_dims]
    changes += [Change(key, "dimension added", None, None) for key in new_dims if key not in old_dims]
    for key, before in old_dims.items():
        after = new_dims.get(key)
        if after is None:
            continue
        for name in ("name", "weight", "definition", "min_quotes", "not_applicable_when"):
            if getattr(before, name) != getattr(after, name):
                changes.append(Change(key, name, _show(getattr(before, name)), _show(getattr(after, name))))
        for field_name, levels in (("anchors", SCALE), ("examples", sorted({*before.examples, *after.examples}))):
            old_texts: Mapping[int, str] = getattr(before, field_name)
            new_texts: Mapping[int, str] = getattr(after, field_name)
            for level in levels:
                if old_texts.get(level) != new_texts.get(level):
                    changes.append(Change(key, f"{field_name}[{level}]", old_texts.get(level), new_texts.get(level)))
    common = [key for key in old_dims if key in new_dims]
    if common != [key for key in new_dims if key in old_dims]:
        changes.append(
            Change(None, "dimension order", _show(tuple(common)), _show(tuple(k for k in new_dims if k in old_dims)))
        )
    for name in ("segment", "roles", "computed_metrics", "output", "output_values", "visibility_gate"):
        before_value, after_value = getattr(old, name), getattr(new, name)
        if before_value != after_value:
            show = _show if name != "visibility_gate" else lambda g: f"{g.metric} >= {g.min:g}"
            changes.append(Change(None, name, show(before_value), show(after_value)))
    return tuple(changes)


def find_previous_version(path: Path | str) -> Path | None:
    """The file in the same folder with the same type and segment and the highest version below this one."""
    path = Path(path)
    match = _FILE_NAME.fullmatch(path.name)
    if match is None:
        raise ValueError(f"{path.name!r} is not named <type>.<segment>.v<major>.<minor>.yaml")
    current = (int(match["major"]), int(match["minor"]))
    best: tuple[tuple[int, int], Path] | None = None
    for candidate in path.parent.glob(f"{match['type']}.{match['segment']}.v*.yaml"):
        found = _FILE_NAME.fullmatch(candidate.name)
        if found is None or (found["type"], found["segment"]) != (match["type"], match["segment"]):
            continue
        version = (int(found["major"]), int(found["minor"]))
        if version < current and (best is None or version > best[0]):
            best = (version, candidate)
    return None if best is None else best[1]


__all__ = [
    "Change",
    "Dimension",
    "InMemoryRubricStore",
    "PublishOutcome",
    "Rubric",
    "RubricError",
    "RubricStore",
    "RubricVersionConflictError",
    "RubricVersionExistsError",
    "VisibilityGate",
    "canonical_json",
    "diff_rubrics",
    "find_previous_version",
    "load_rubric",
    "parse_rubric",
    "publish_rubric",
    "rubric_hash",
]
