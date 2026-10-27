"""Reading rubrics (plan task P6.8; owner's decision 2026-10-27: everyone signed in, staff included, read-only).

- GET /v1/rubrics: for each conversation type the tenant has switched on and has a rubric for, the one in use (its
  profile's default, sabha_core.profiles) and every version of that family (same type and segment) in the rubric
  folder, newest first.
- GET /v1/rubrics/{rubric_id}: one version of such a family: dimensions with their 1-5 scale and examples, and the
  changes from the version before (sabha_analytics.rubric.diff_rubrics). Anything else is 404, so ids are never
  read as paths outside the family's files.

Rubric files are product content shared by every tenant of a profile, not tenant data. They are read with the
same validated loader the analyze stage uses, and cached until a file changes.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from sabha_analytics.rubric import SCALE, Rubric, diff_rubrics, load_rubric
from sabha_api.errors import NotFoundError
from sabha_core.models import Tenant
from sabha_core.profiles import ConversationType, get_profile

_ID = re.compile(r"^(?P<type>[a-z]+)\.(?P<segment>[a-z0-9_]+)\.v(?P<major>\d+)\.(?P<minor>\d+)$")


class VersionOut(BaseModel):
    id: str
    version: str
    in_use: bool


class RubricItem(BaseModel):
    type: ConversationType
    current_id: str
    dimension_count: int
    versions: list[VersionOut]


class RubricList(BaseModel):
    items: list[RubricItem]


class LevelOut(BaseModel):
    level: int
    description: str
    example: str | None


class DimensionOut(BaseModel):
    key: str
    name: str
    weight: float
    definition: str
    min_quotes: int
    not_applicable_when: str | None
    scale: list[LevelOut]


class ChangeOut(BaseModel):
    dimension: str | None
    item: str
    old: str | None
    new: str | None


class RubricOut(BaseModel):
    id: str
    type: ConversationType
    version: str
    in_use: bool
    dimensions: list[DimensionOut]
    versions: list[VersionOut]
    previous_id: str | None
    changes: list[ChangeOut]


def _not_found() -> NotFoundError:
    return NotFoundError("This rubric does not exist or is not used by your organisation.")


@lru_cache(maxsize=64)
def _load(path: str, _mtime_ns: int) -> Rubric:
    return load_rubric(path)[0]


def _read(folder: Path, rubric_id: str) -> Rubric:
    path = folder / f"{rubric_id}.yaml"
    return _load(str(path), path.stat().st_mtime_ns)


def _version_key(rubric_id: str) -> tuple[int, int]:
    match = _ID.fullmatch(rubric_id)
    assert match is not None  # noqa: S101  # only ids that matched _ID reach here
    return int(match["major"]), int(match["minor"])


def _family(folder: Path, current_id: str) -> list[str]:
    """Every version of the current rubric's type and segment, newest first."""
    match = _ID.fullmatch(current_id)
    if match is None:
        return []
    ids = [p.stem for p in folder.glob(f"{match['type']}.{match['segment']}.v*.yaml") if _ID.fullmatch(p.stem)]
    return sorted(ids, key=_version_key, reverse=True)


def _current(tenant: Tenant) -> dict[ConversationType, str]:
    """Enabled type -> the rubric in use, in the setup screen's order."""
    defaults = get_profile(tenant.profile).default_rubrics
    return {t: rid for t in ConversationType if t in tenant.enabled_types and (rid := defaults[t]) is not None}


def _versions(family: list[str], current_id: str) -> list[VersionOut]:
    return [VersionOut(id=rid, version="{}.{}".format(*_version_key(rid)), in_use=rid == current_id) for rid in family]


def list_rubrics(tenant: Tenant, rubrics_dir: str) -> RubricList:
    folder = Path(rubrics_dir)
    items = []
    for conversation_type, current_id in _current(tenant).items():
        family = _family(folder, current_id)
        if current_id not in family:
            continue  # the profile names a file that is not deployed: nothing to show
        items.append(RubricItem(type=conversation_type, current_id=current_id,
                                dimension_count=len(_read(folder, current_id).dimensions),
                                versions=_versions(family, current_id)))  # fmt: skip
    return RubricList(items=items)


def _owner_family(tenant: Tenant, folder: Path, rubric_id: str) -> tuple[ConversationType, str, list[str]]:
    """(type, rubric in use, versions) of the tenant's family holding `rubric_id`; 404 when there is none."""
    if _ID.fullmatch(rubric_id) is not None:
        for conversation_type, current_id in _current(tenant).items():
            family = _family(folder, current_id)
            if rubric_id in family:
                return conversation_type, current_id, family
    raise _not_found()


def read_rubric(tenant: Tenant, rubric_id: str, rubrics_dir: str) -> RubricOut:
    folder = Path(rubrics_dir)
    conversation_type, current_id, family = _owner_family(tenant, folder, rubric_id)
    rubric = _read(folder, rubric_id)
    older = family[family.index(rubric_id) + 1 :]
    previous_id = older[0] if older else None
    changes = diff_rubrics(_read(folder, previous_id), rubric) if previous_id else ()
    return RubricOut(
        id=rubric.id,
        type=conversation_type,
        version=rubric.version,
        in_use=rubric_id == current_id,
        dimensions=[
            DimensionOut(
                key=d.key,
                name=d.name,
                weight=d.weight,
                definition=d.definition,
                min_quotes=d.min_quotes,
                not_applicable_when=d.not_applicable_when,
                scale=[LevelOut(level=n, description=d.anchors[n], example=d.examples.get(n)) for n in SCALE],
            )
            for d in rubric.dimensions
        ],
        versions=_versions(family, current_id),
        previous_id=previous_id,
        changes=[ChangeOut(dimension=c.dimension, item=c.item, old=c.old, new=c.new) for c in changes],
    )
