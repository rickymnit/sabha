"""Tenant, Unit, User, Person, IdentityLink and OutboxEvent models (plan task P1.6). No database needed."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sabha_core.models import IdentityLink, OutboxEvent, Person, Role, Tenant, TenantDoc, Unit, User
from sabha_core.profiles import ConversationType, ProfileName, get_profile
from sabha_core.quota import Plan

# --- Tenant ---


def test_a_tenant_starts_from_its_profile_defaults() -> None:
    tenant = Tenant.from_profile("school", name="Green Valley School", plan=Plan.PILOT)
    profile = get_profile("school")
    assert tenant.profile is ProfileName.SCHOOL
    assert tenant.labels == profile.labels
    assert tenant.enabled_types == list(profile.enabled_types)
    assert tenant.retention_days == profile.retention_days
    assert tenant.region == "ap-south-1"
    assert tenant.kms_key_id is None


def test_tenant_region_must_be_india() -> None:
    # Golden rule 12: data stays in India.
    with pytest.raises(ValidationError, match="ap-south-1"):
        Tenant.from_profile("school", name="X", plan=Plan.PILOT, region="us-east-1")


def test_tenant_name_is_required_and_trimmed() -> None:
    assert Tenant.from_profile("school", name="  Green Valley  ", plan=Plan.PILOT).name == "Green Valley"
    with pytest.raises(ValidationError):
        Tenant.from_profile("school", name="   ", plan=Plan.PILOT)


def test_tenant_enabled_types_have_no_duplicates() -> None:
    with pytest.raises(ValidationError):
        Tenant.from_profile(
            "school",
            name="X",
            plan=Plan.PILOT,
            enabled_types=[ConversationType.TEACHING, ConversationType.TEACHING],
        )


def test_tenant_ids_are_generated_and_unique() -> None:
    first = Tenant.from_profile("school", name="A", plan=Plan.PILOT)
    second = Tenant.from_profile("school", name="B", plan=Plan.PILOT)
    assert first.id and second.id and first.id != second.id


def test_tenant_is_not_a_tenant_doc() -> None:
    # Tenants are the scope itself; they live in a system collection and have no tenant_id.
    assert not issubclass(Tenant, TenantDoc)
    assert "tenant_id" not in Tenant.model_fields


# --- Documents inside a tenant ---


@pytest.mark.parametrize("model", [Unit, User, Person, IdentityLink, OutboxEvent])
def test_every_tenant_owned_model_is_a_tenant_doc(model: type[TenantDoc]) -> None:
    assert issubclass(model, TenantDoc)


def test_documents_are_stored_under_underscore_id() -> None:
    person = Person(name="Asha")
    dumped = person.model_dump(by_alias=True)
    assert dumped["_id"] == person.id and "id" not in dumped
    assert Person.model_validate(dumped) == person


def test_unknown_fields_are_refused() -> None:
    # Keeps stray data (for example anything about students, golden rule 10) out of the database by accident.
    with pytest.raises(ValidationError):
        Person.model_validate({"name": "Asha", "student_scores": [1, 2]})


def test_unit_cannot_be_its_own_parent() -> None:
    with pytest.raises(ValidationError):
        Unit(id="u1", name="Primary", parent_id="u1")


def test_user_email_is_normalised() -> None:
    user = User(email="  Asha.Rao@Example.COM ", name="Asha", role=Role.STAFF)
    assert user.email == "asha.rao@example.com"
    assert user.unit_ids == []
    assert user.status == "invited"


@pytest.mark.parametrize("email", ["", "asha", "asha@", "@example.com", "a b@example.com"])
def test_user_email_must_look_like_an_email(email: str) -> None:
    with pytest.raises(ValidationError):
        User(email=email, name="Asha", role=Role.STAFF)


def test_user_role_must_be_known() -> None:
    with pytest.raises(ValidationError):
        User.model_validate({"email": "a@example.com", "name": "A", "role": "superuser"})


def test_roles() -> None:
    assert [r.value for r in Role] == ["owner", "admin", "manager", "reviewer", "staff"]


def test_identity_link_normalises_issuer_and_email() -> None:
    link = IdentityLink(issuer="https://sabha-dev.eu.auth0.com/", email="Asha@Example.com", user_id="u1")
    assert link.issuer == "https://sabha-dev.eu.auth0.com"
    assert link.email == "asha@example.com"
    assert link.subject is None  # set at first login


def test_outbox_event_starts_unpublished() -> None:
    event = OutboxEvent(type="recording.completed", payload={"recording_id": "r1"})
    assert event.published_at is None
    assert event.created_at.tzinfo is not None  # UTC, CLAUDE.md API conventions
