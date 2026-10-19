"""Documents of the tenant model: Tenant, Unit, User, Person, IdentityLink, OutboxEvent (plan task P1.6).

- `Tenant` is the scope itself: it lives in the system collection `tenants` and has no tenant_id.
- Everything else is a `TenantDoc`: it carries `tenant_id`, which the tenant-scoped repository (sabha_core.repo)
  sets on insert and never lets an update change (golden rule 1). A new TenantDoc may leave tenant_id empty; the
  repository fills it.
- Documents are stored under MongoDB's `_id`; in Python the field is `id`. Ids are random hex strings.
- Unknown fields are refused, so stray data (anything about students, golden rule 10) cannot be stored by accident.
- Times are UTC. MongoDB keeps milliseconds and returns naive datetimes, so times are truncated to milliseconds and
  naive values are read as UTC: a document reads back equal to what was written.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import AfterValidator, AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from sabha_core.profiles import ConversationType, Labels, ProfileName, get_profile
from sabha_core.quota import Plan
from sabha_core.settings import INDIA_REGION

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def new_id() -> str:
    return uuid.uuid4().hex


def _utc_ms(value: datetime) -> datetime:
    value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


UtcDatetime = Annotated[datetime, AfterValidator(_utc_ms)]


def utc_now() -> datetime:
    return _utc_ms(datetime.now(UTC))


def _email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL.match(value):
        raise ValueError("must be an email address")
    return value


Email = Annotated[str, AfterValidator(_email)]


class Role(StrEnum):
    """What a user may do in their tenant. Routes list every role they allow (sabha_api.auth.require_role)."""

    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    REVIEWER = "reviewer"
    STAFF = "staff"


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

    # Read from MongoDB's "_id" or Python's "id"; written as "_id" (model_dump(by_alias=True)).
    id: str = Field(
        default_factory=new_id, validation_alias=AliasChoices("_id", "id"), serialization_alias="_id", min_length=1
    )


class TenantDoc(Document):
    """A document owned by one tenant. Read and write it only through sabha_core.repo.TenantRepo."""

    tenant_id: str = ""


class Tenant(Document):
    name: str = Field(min_length=1)
    profile: ProfileName
    enabled_types: list[ConversationType] = Field(min_length=1)
    labels: Labels
    plan: Plan
    retention_days: int = Field(gt=0)
    region: str = INDIA_REGION
    kms_key_id: str | None = None
    created_at: UtcDatetime = Field(default_factory=utc_now)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("enabled_types")
    @classmethod
    def _unique_types(cls, value: list[ConversationType]) -> list[ConversationType]:
        if len(set(value)) != len(value):
            raise ValueError("enabled_types lists a type more than once")
        return value

    @field_validator("region")
    @classmethod
    def _india_only(cls, value: str) -> str:
        if value != INDIA_REGION:
            raise ValueError(f"region must be {INDIA_REGION}: data stays in India (golden rule 12)")
        return value

    @classmethod
    def from_profile(cls, profile: ProfileName | str, *, name: str, plan: Plan, **overrides: Any) -> Self:
        """A new tenant with its profile's labels, conversation types and retention (sabha_core.profiles)."""
        defaults = get_profile(profile)
        fields: dict[str, Any] = {
            "name": name,
            "profile": defaults.name,
            "enabled_types": list(defaults.enabled_types),
            "labels": defaults.labels,
            "plan": plan,
            "retention_days": defaults.retention_days,
            **overrides,
        }
        return cls(**fields)


class Unit(TenantDoc):
    """A group people belong to (campus, department, team); units form a tree through parent_id."""

    name: str = Field(min_length=1)
    parent_id: str | None = None

    @model_validator(mode="after")
    def _not_own_parent(self) -> Self:
        if self.parent_id == self.id:
            raise ValueError("a unit cannot be its own parent")
        return self


class User(TenantDoc):
    """Someone who signs in. Created by an invite (P1.5b); `status` moves invited -> active at first login."""

    email: Email
    name: str = Field(min_length=1)
    role: Role
    unit_ids: list[str] = Field(default_factory=list)
    status: Literal["invited", "active", "disabled"] = "invited"


class Person(TenantDoc):
    """A staff member whose conversations are analysed. May or may not also be a User."""

    name: str = Field(min_length=1)
    unit_id: str | None = None
    user_id: str | None = None


class IdentityLink(TenantDoc):
    """Links a login (issuer, subject) or an invited email to a user (ADR 0002). Subject is set at first login."""

    issuer: str = Field(min_length=1)
    subject: str | None = None
    email: Email
    user_id: str = Field(min_length=1)

    @field_validator("issuer")
    @classmethod
    def _strip_slash(cls, value: str) -> str:
        return value.rstrip("/")


class OutboxEvent(TenantDoc):
    """An event written in the same transaction as the change it reports; the relay publishes it (P2.5)."""

    type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: UtcDatetime = Field(default_factory=utc_now)
    published_at: UtcDatetime | None = None
