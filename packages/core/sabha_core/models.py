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
from sabha_core.state import RecordingStatus

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
    # Other ways the name is said or transcribed, for recognising a greeting or a sales rep's introduction: the
    # speech recogniser often writes English names in Devanagari ("ब्राइट पाथ सॉफ्टवेयर" for "Brightpath Software").
    name_variants: list[str] = Field(default_factory=list)
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
    # Job title shown in the app under the name ("Coordinator, Class 6"). Display only: the role decides access.
    title: str | None = None
    unit_ids: list[str] = Field(default_factory=list)
    status: Literal["invited", "active", "disabled"] = "invited"
    # Notification preferences (P2.7)
    report_emails: bool = True  # "report ready" emails for their own recordings and their units'
    language: Literal["en", "hi"] = "en"


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
    dispatched: list[str] = Field(default_factory=list)  # pipeline tasks already sent for this event (relay)


class IdempotencyRecord(TenantDoc):
    """A create request seen with an Idempotency-Key, and its response for replays (sabha_api.idempotency).

    Expires 24 h after `created_at` (TTL index). `request_hash` is the SHA-256 of the canonical request body.
    """

    route: str = Field(min_length=1)
    key: str = Field(min_length=1)
    request_hash: str = Field(min_length=1)
    status: Literal["in_progress", "done"] = "in_progress"
    response_status: int | None = None
    response_body: dict[str, Any] | None = None
    created_at: UtcDatetime = Field(default_factory=utc_now)


class AudioInfo(BaseModel):
    """The original's audio stream as ffprobe reported it (P3.2)."""

    model_config = ConfigDict(extra="forbid")

    codec: str = Field(min_length=1)
    sample_rate: int = Field(ge=1)
    channels: int = Field(ge=1)


class Recording(TenantDoc):
    """A recorded conversation. Status changes only through sabha_core.state.transition (CLAUDE.md).

    Upload fields (P2.1): the browser uploads the original straight to `storage_key` in the audio bucket, in
    `part_count` parts of `part_size` bytes (the last may be smaller), under the multipart `upload_id`.
    """

    type: ConversationType
    status: RecordingStatus = RecordingStatus.CREATED
    consent_ref: str | None = None  # golden rule 9: without it nothing moves past UPLOADED
    status_reason: str | None = None
    status_changed_at: UtcDatetime | None = None
    person_id: str | None = None  # the staff member analysed
    unit_id: str | None = None
    file_name: str | None = None  # as the user named it; storage uses a safe form
    size_bytes: int | None = Field(default=None, ge=1)
    content_type: str | None = None
    recorded_at: UtcDatetime | None = None
    storage_key: str | None = None
    upload_id: str | None = None
    part_size: int | None = Field(default=None, ge=1)
    part_count: int | None = Field(default=None, ge=1)
    created_by: str | None = None  # user id
    # Completion (P2.2): the browser's SHA-256 of the file; a recording with the same hash already in the tenant
    # holds this one until the uploader confirms (force); without consent it waits as well.
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    duplicate_of: str | None = None
    duplicate_confirmed: bool = False
    awaiting_consent: bool = False
    completed_at: UtcDatetime | None = None
    # Preprocess (P3.2): the length of the recording (the original timeline) and its audio stream. The priority
    # lanes (P7.2) and billing (P8.6) read duration_ms.
    duration_ms: int | None = Field(default=None, ge=0)
    audio: AudioInfo | None = None
    # Review (ADR 0007): speaker label -> role, as a reviewer confirmed them for an "unclear_roles" recording. The
    # transcript stage uses them instead of guessing.
    confirmed_roles: dict[str, str] | None = None
    created_at: UtcDatetime = Field(default_factory=utc_now)


class Transcript(TenantDoc):
    """A recording's canonical transcript (P3.7): the file is `storage_key` (transcript@v1.json, ORIGINAL timeline).

    `roles` maps the diarizer's anonymous speaker labels to rubric roles (teacher/students, receptionist/caller);
    no student is identified (golden rule 10). `roles_need_review` is True while a person must confirm them.
    """

    recording_id: str = Field(min_length=1)
    version: str = Field(min_length=1)  # "transcript@v1"
    storage_key: str = Field(min_length=1)
    asr_model: str = Field(min_length=1)
    word_timing: Literal["word", "approximate"]
    word_count: int = Field(ge=0)
    utterance_count: int = Field(ge=0)
    language_mix: dict[str, float] = Field(default_factory=dict)  # share of the audio per language code
    roles: dict[str, str] = Field(default_factory=dict)
    roles_method: str = ""
    roles_need_review: bool = False
    # The rubric's two roles, staff first ("teacher", "students"): what a reviewer chooses between (ADR 0007).
    role_choices: list[str] = Field(default_factory=list)
    rubric_id: str = Field(min_length=1)
    created_at: UtcDatetime = Field(default_factory=utc_now)


class Analysis(TenantDoc):
    """One stored analysis of a recording (P5.7): the report is the file at `report_key` (analysis@v1.json).

    One per (recording, version), where version is the analyze stage's artefact version, so a retried stage
    replaces its own result and a re-analysis under a new version keeps the history. `status` is the report's
    outcome: COMPLETED, or NEEDS_REVIEW with `review_reasons`. `cost_usd` is the sum of this recording's LLM calls
    from the published price table, or None when any call's model has no price there (golden rule 6).
    """

    recording_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    person_id: str | None = None
    unit_id: str | None = None
    conversation_type: ConversationType
    rubric_id: str = Field(min_length=1)
    rubric_version: str = Field(min_length=1)
    rubric_hash: str = Field(min_length=1)
    report_key: str = Field(min_length=1)
    status: Literal["COMPLETED", "NEEDS_REVIEW"]
    overall_score: float | None = None
    verified_share: float = Field(ge=0, le=1)
    review_reasons: list[str] = Field(default_factory=list)
    model_ids: list[str] = Field(default_factory=list)
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    usage: dict[str, int] = Field(default_factory=dict)
    cost_usd: float | None = None
    created_at: UtcDatetime = Field(default_factory=utc_now)


class Score(TenantDoc):
    """One rubric dimension of one analysis, flattened for trends (P5.7). Staff only: never a student (rule 10).

    Unverified dimensions have no score and no evidence (golden rule 5); not-applicable ones have no score but
    keep their evidence of why.
    """

    analysis_id: str = Field(min_length=1)
    recording_id: str = Field(min_length=1)
    person_id: str | None = None
    dimension: str = Field(min_length=1)
    name: str = Field(min_length=1)
    weight: float = Field(ge=0)
    score: int | None = Field(default=None, ge=1, le=5)
    verified: bool
    not_applicable: bool = False
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    created_at: UtcDatetime = Field(default_factory=utc_now)


class StageRun(TenantDoc):
    """One attempt of one pipeline stage for one recording (plan task P2.3); cost inputs go in `meta`."""

    recording_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    version: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    status: Literal["running", "succeeded", "failed"] = "running"
    worker: str = Field(min_length=1)
    started_at: UtcDatetime
    heartbeat_at: UtcDatetime | None = None  # refreshed while a long stage runs; the stuck-job sweeper reads it
    finished_at: UtcDatetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    error_detail: str | None = Field(default=None, max_length=2000)
    meta: dict[str, Any] = Field(default_factory=dict)


class AuditEntry(TenantDoc):
    """One append-only audit record (CLAUDE.md: playback, export and score changes are audited; P1.8 completes it).

    Written by sabha_api.audit.audit; nothing updates or deletes these.
    """

    actor_user_id: str
    actor_role: str
    action: str = Field(min_length=1)  # e.g. recording.create, recording.play, score.change
    target_type: str
    target_id: str
    at: UtcDatetime = Field(default_factory=utc_now)
    ip: str | None = None
    user_agent: str | None = Field(default=None, max_length=500)
    request_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class LlmCall(TenantDoc):
    """One request to an LLM provider, written by the gateway (sabha_llm.gateway, plan task P5.1).

    Measured values only: token counts as the provider reported them, cost from the published price table or None
    when the model has no price there (golden rule 6). No prompt text is stored, only its hash.
    """

    recording_id: str | None = None
    task: str = Field(min_length=1)
    provider: str
    model: str
    prompt_hash: str
    prompt_version: str | None = None
    status: Literal["ok", "error"]
    error_code: str | None = None
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = None
    latency_ms: int = Field(ge=0)
    attempt: int = Field(ge=1)
    fallback_reason: str | None = None
    created_at: UtcDatetime = Field(default_factory=utc_now)


class RelayState(Document):
    """Where the outbox relay's change stream stopped (system collection `relay_state`; P2.5)."""

    resume_token: dict[str, Any] | None = None
    updated_at: UtcDatetime = Field(default_factory=utc_now)


class DeadLetter(TenantDoc):
    """A pipeline job that failed for good, with what an operator needs to replay it (P2.4; replay in P7.8)."""

    recording_id: str
    stage: str
    task: str
    error_code: str
    error_detail: str | None = Field(default=None, max_length=2000)
    attempts: int = Field(ge=1)
    args: dict[str, Any] = Field(default_factory=dict)
    replayed_at: UtcDatetime | None = None
    created_at: UtcDatetime = Field(default_factory=utc_now)


class Delivery(TenantDoc):
    """One email or webhook delivery, keyed so a retried event never sends it twice (P2.7).

    claimed: a worker is sending it; sent: done; failed: refused for good (not retried).
    """

    key: str = Field(min_length=1)
    channel: Literal["email", "webhook"] = "email"
    status: Literal["claimed", "sent", "failed"] = "claimed"
    message_id: str | None = None
    last_error: str | None = Field(default=None, max_length=500)
    claimed_at: UtcDatetime = Field(default_factory=utc_now)
    sent_at: UtcDatetime | None = None
