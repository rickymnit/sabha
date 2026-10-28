"""Workspace settings (plan task P1.7): the tenant's name, the product's words and the conversation types it uses.

- GET /v1/settings: owners and admins. The settings, plus every conversation type with whether it is on and whether
  it can be switched on (the tenant's profile has a rubric for it), and how many the plan allows.
- PATCH /v1/settings {name?, labels?, enabled_types?}: owners and admins ("Admins can rename any of these in
  Settings", docs/design/source/Setup.dc.html). Labels are merged word by word. Types are stored in the setup
  screen's order; at least one, each with a rubric, at most the plan's number (sabha_core.quota.MAX_TYPES). A type
  switched off refuses new uploads (services/recordings.py); recordings already made stay readable.
  One transaction writes the change and its audit entry (settings.update, the changed fields before and after); a
  request that changes nothing writes nothing.

Plan, profile, retention and region are not settings: Sabha changes them (scripts/admin), so the tenant record is
written through OwnTenantRepo, which refuses any other field.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from sabha_api.audit import audit
from sabha_api.auth import Principal, Role
from sabha_api.deps import Transactions
from sabha_api.errors import ApiError, NotFoundError
from sabha_core.models import AuditEntry, Tenant
from sabha_core.profiles import ConversationType, Labels, get_profile
from sabha_core.quota import MAX_TYPES
from sabha_core.repo import OwnTenantRepo, TenantRepo

ALLOWED = (Role.OWNER, Role.ADMIN)

Word = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class TypeUnavailableError(ApiError):
    status, code, title = 422, "type_unavailable", "Conversation type not available"


class PlanLimitError(ApiError):
    status, code, title = 422, "plan_limit", "Plan limit reached"


class LabelsIn(BaseModel):
    """Any of the words; words left out keep their current value."""

    model_config = ConfigDict(extra="forbid")

    person: Word | None = None
    person_plural: Word | None = None
    recording: Word | None = None
    recording_plural: Word | None = None
    unit: Word | None = None
    manager: Word | None = None
    unit_group: Word | None = None
    unit_group_plural: Word | None = None
    unit_sub: Word | None = None
    unit_sub_plural: Word | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("leave a word out to keep it; it cannot be empty")
        return value


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    labels: LabelsIn | None = None
    enabled_types: list[ConversationType] | None = Field(default=None, min_length=1)

    @field_validator("enabled_types")
    @classmethod
    def _unique(cls, value: list[ConversationType] | None) -> list[ConversationType] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("a conversation type is listed more than once")
        return value


class TypeOut(BaseModel):
    type: ConversationType
    enabled: bool
    available: bool  # the tenant's profile has a rubric for it, so it can be switched on


class SettingsOut(BaseModel):
    name: str
    profile: str
    plan: str
    labels: dict[str, str]
    enabled_types: list[ConversationType]
    types: list[TypeOut]
    max_types: int
    retention_days: int  # audio is deleted after this many days (P7.3); read-only, set by Sabha


def available_types(tenant: Tenant) -> set[ConversationType]:
    rubrics = get_profile(tenant.profile).default_rubrics
    return {t for t, rubric_id in rubrics.items() if rubric_id is not None}


def settings_out(tenant: Tenant) -> SettingsOut:
    available = available_types(tenant)
    return SettingsOut(
        name=tenant.name,
        profile=tenant.profile,
        plan=tenant.plan,
        labels=tenant.labels.model_dump(),
        enabled_types=tenant.enabled_types,
        types=[TypeOut(type=t, enabled=t in tenant.enabled_types, available=t in available) for t in ConversationType],
        max_types=MAX_TYPES[tenant.plan],
        retention_days=tenant.retention_days,
    )


async def read(tenant_repo: OwnTenantRepo) -> SettingsOut:
    return settings_out(await _tenant(tenant_repo))


async def update(
    principal: Principal,
    body: SettingsIn,
    request: Request,
    *,
    tenant_repo: OwnTenantRepo,
    entries: TenantRepo[AuditEntry],
    transactions: Transactions,
) -> SettingsOut:
    async with transactions.run() as session:
        tenant = await _tenant(tenant_repo, session=session)
        before, after = _changes(tenant, body)
        if not after:
            return settings_out(tenant)
        stored = dict(after)
        if "labels" in after:  # written whole, so the record always has every word
            stored["labels"] = Labels.model_validate({**tenant.labels.model_dump(), **after["labels"]}).model_dump()
        await tenant_repo.update_settings(stored, session=session)
        await audit(entries, principal, request, action="settings.update", target_type="tenant", target_id=tenant.id,
                    meta={"before": before, "after": after}, session=session)  # fmt: skip
        changed = await _tenant(tenant_repo, session=session)
    return settings_out(changed)


async def _tenant(tenant_repo: OwnTenantRepo, **kwargs: Any) -> Tenant:
    tenant = await tenant_repo.get(**kwargs)
    if tenant is None:
        raise NotFoundError("Your organisation could not be found.")
    return tenant


def _changes(tenant: Tenant, body: SettingsIn) -> tuple[dict[str, Any], dict[str, Any]]:
    """(before, after) of the fields that change; labels list only the words that change."""
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    if body.name is not None and body.name != tenant.name:
        before["name"], after["name"] = tenant.name, body.name
    if body.labels is not None:
        current = tenant.labels.model_dump()
        words = {k: v for k, v in body.labels.model_dump(exclude_none=True).items() if v != current[k]}
        if words:
            before["labels"] = {k: current[k] for k in words}
            after["labels"] = words
    if body.enabled_types is not None:
        types = [t for t in ConversationType if t in body.enabled_types]  # the setup screen's order
        if types != tenant.enabled_types:
            _check_types(tenant, types)
            before["enabled_types"] = [t.value for t in tenant.enabled_types]
            after["enabled_types"] = [t.value for t in types]
    return before, after


def _check_types(tenant: Tenant, types: list[ConversationType]) -> None:
    # Only types being switched on: one Sabha switched on before its rubric existed does not block other changes.
    missing = [t for t in types if t not in tenant.enabled_types and t not in available_types(tenant)]
    if missing:
        names = ", ".join(t.value.capitalize() for t in missing)
        raise TypeUnavailableError(f"{names} is not set up for your organisation yet. Ask your Sabha contact.")
    limit = MAX_TYPES[tenant.plan]
    if len(types) > limit:
        raise PlanLimitError(
            f"Your plan covers {limit} conversation types at a time. Switch one off, or ask your Sabha contact "
            "about upgrading."
        )
