"""Which rubric a recording is analysed with (used by role assignment, P3.6, and the analyze stage, P5.7).

A recording's rubric is its tenant's organisation profile default for the recording's conversation type
(sabha_core.profiles: `default_rubrics`), read from `{RUBRICS_DIR}/<rubric id>.yaml` and validated with
sabha_analytics.rubric. Files are cached per process by path and content hash, so a changed file is picked up.

No rubric for the type (for example counselling at a school today): NoRubric, which the stages turn into a
PermanentError `no_rubric` (replayable once a rubric exists). Nothing falls back to another rubric.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from sabha_analytics.rubric import Rubric, load_rubric
from sabha_core.models import Tenant
from sabha_core.profiles import ConversationType, get_profile


class NoRubric(LookupError):
    pass


@cache
def _load(path: Path, mtime_ns: int) -> tuple[Rubric, str]:
    del mtime_ns  # part of the cache key only
    return load_rubric(path)


def rubric_id_for(tenant: Tenant, conversation_type: ConversationType) -> str:
    rubric_id = get_profile(tenant.profile).default_rubrics.get(conversation_type)
    if rubric_id is None:
        raise NoRubric(f"no rubric for {conversation_type} recordings in the {tenant.profile} profile")
    return rubric_id


def rubric_for(tenant: Tenant, conversation_type: ConversationType, rubrics_dir: Path) -> tuple[Rubric, str]:
    """(rubric, content hash) for this tenant's recordings of this type (module docstring)."""
    path = rubrics_dir / f"{rubric_id_for(tenant, conversation_type)}.yaml"
    if not path.exists():
        raise NoRubric(f"rubric file {path} is missing")
    return _load(path, path.stat().st_mtime_ns)
