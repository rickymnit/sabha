"""Tests for sabha_core.profiles: organisation profile defaults (plan task P1.7).

Words come from the workspace setup design (docs/design/source/Setup.dc.html); rubric ids must name rubric files
that exist; consent and retention follow CLAUDE.md and docs/legal/drafts/.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from sabha_core.profiles import (
    ConsentDefaults,
    ConversationType,
    OrgProfile,
    ProfileName,
    UnknownProfileError,
    get_profile,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

T = ConversationType
ALL_PROFILES = list(ProfileName)


def test_profile_names_and_conversation_types() -> None:
    assert [name.value for name in ProfileName] == ["school", "college", "company"]
    # The order the setup screen lists them in (Setup.dc.html, TYPES).
    assert [t.value for t in ConversationType] == ["teaching", "counselling", "reception", "meeting", "sales"]


def test_school_defaults() -> None:
    school = get_profile("school")

    assert school.name is ProfileName.SCHOOL
    assert school.enabled_types == (T.TEACHING, T.RECEPTION)
    assert school.labels.model_dump() == {
        "person": "Teacher",
        "person_plural": "Teachers",
        "recording": "Lesson",
        "recording_plural": "Lessons",
        "unit": "Campus and section",
        "manager": "Principal or coordinator",
    }
    assert school.default_rubrics == {
        T.TEACHING: "teaching.school.v0.1",
        T.COUNSELLING: None,
        T.RECEPTION: "reception.school.v0.2",
        T.MEETING: None,
        T.SALES: None,
    }
    assert school.consent == ConsentDefaults(
        consent_ref_required=True,
        parental_consent_types=frozenset({T.TEACHING}),
        parental_consent_for_minors=True,
        call_notice_types=frozenset({T.RECEPTION, T.SALES}),
        staff_consent_required=True,
    )
    assert school.retention_days == 90


def test_college_defaults() -> None:
    college = get_profile("college")

    assert college.name is ProfileName.COLLEGE
    assert college.enabled_types == (T.TEACHING, T.COUNSELLING, T.RECEPTION)
    assert college.labels.model_dump() == {
        "person": "Faculty member",
        "person_plural": "Faculty",
        "recording": "Lecture",
        "recording_plural": "Lectures",
        "unit": "Department",
        "manager": "Head of department",
    }
    assert college.default_rubrics == dict.fromkeys(ConversationType)
    assert college.consent == ConsentDefaults(
        consent_ref_required=True,
        parental_consent_types=frozenset(),
        parental_consent_for_minors=True,
        call_notice_types=frozenset({T.RECEPTION, T.SALES}),
        staff_consent_required=False,
    )
    assert college.retention_days == 90


def test_company_defaults() -> None:
    company = get_profile("company")

    assert company.name is ProfileName.COMPANY
    assert company.enabled_types == (T.RECEPTION, T.MEETING, T.SALES)
    assert company.labels.model_dump() == {
        "person": "Sales rep",
        "person_plural": "Team",
        "recording": "Call",
        "recording_plural": "Calls",
        "unit": "Team or branch",
        "manager": "Sales manager",
    }
    assert company.default_rubrics == dict.fromkeys(ConversationType)
    assert company.consent == ConsentDefaults(
        consent_ref_required=True,
        parental_consent_types=frozenset(),
        parental_consent_for_minors=True,
        call_notice_types=frozenset({T.RECEPTION, T.SALES}),
        staff_consent_required=False,
    )
    assert company.retention_days == 90


def test_company_uses_sales_words() -> None:
    # P1.7 done-when: switching a tenant to `company` changes the UI words to Sales rep, Call, Team.
    labels = get_profile(ProfileName.COMPANY).labels

    assert (labels.person, labels.recording, labels.person_plural) == ("Sales rep", "Call", "Team")


@pytest.mark.parametrize("name", ALL_PROFILES)
def test_every_type_has_a_rubric_entry(name: ProfileName) -> None:
    profile = get_profile(name)

    assert set(profile.default_rubrics) == set(ConversationType)
    assert set(profile.enabled_types) <= set(profile.default_rubrics)


@pytest.mark.parametrize("name", ALL_PROFILES)
def test_every_rubric_id_names_an_existing_rubric_file(name: ProfileName) -> None:
    for conversation_type, rubric_id in get_profile(name).default_rubrics.items():
        if rubric_id is None:
            continue
        path = REPO_ROOT / "rubrics" / f"{rubric_id}.yaml"
        assert path.is_file(), f"{name}: no rubric file for {rubric_id}"
        assert f"id: {rubric_id}" in path.read_text(encoding="utf-8").splitlines()
        assert rubric_id.startswith(f"{conversation_type}.")


@pytest.mark.parametrize("name", ALL_PROFILES)
def test_consent_ref_is_required_by_every_profile(name: ProfileName) -> None:
    # Golden rule 9: a recording without consent_ref cannot move past UPLOADED, whatever the profile.
    assert get_profile(name).consent.consent_ref_required is True


def test_consent_ref_cannot_be_switched_off() -> None:
    fields = get_profile("company").consent.model_dump()

    with pytest.raises(ValidationError):
        ConsentDefaults.model_validate({**fields, "consent_ref_required": False})


@pytest.mark.parametrize("other", [ProfileName.COLLEGE, ProfileName.COMPANY])
def test_school_consent_is_the_strictest(other: ProfileName) -> None:
    school, rival = get_profile("school").consent, get_profile(other).consent

    assert school.parental_consent_types >= rival.parental_consent_types
    assert school.parental_consent_for_minors >= rival.parental_consent_for_minors
    assert school.call_notice_types >= rival.call_notice_types
    assert school.staff_consent_required >= rival.staff_consent_required
    assert school.parental_consent_types > rival.parental_consent_types


@pytest.mark.parametrize("name", ALL_PROFILES)
def test_audio_retention_defaults_to_90_days(name: ProfileName) -> None:
    assert get_profile(name).retention_days == 90


@pytest.mark.parametrize("name", ALL_PROFILES)
def test_profiles_are_frozen(name: ProfileName) -> None:
    profile = get_profile(name)

    # setattr with a variable name: the point is to try an assignment that the model must refuse.
    for target, attribute, value in [
        (profile, "retention_days", 1),
        (profile, "enabled_types", ()),
        (profile.labels, "person", "Boss"),
        (profile.consent, "staff_consent_required", False),
    ]:
        with pytest.raises(ValidationError):
            setattr(target, attribute, value)


@pytest.mark.parametrize("name", ALL_PROFILES)
def test_changing_a_returned_profile_does_not_change_the_defaults(name: ProfileName) -> None:
    first = get_profile(name)
    first.default_rubrics[T.TEACHING] = "teaching.hacked.v9.9"
    first.default_rubrics.clear()

    second = get_profile(name)
    assert second is not first
    assert set(second.default_rubrics) == set(ConversationType)
    assert second.default_rubrics[T.TEACHING] != "teaching.hacked.v9.9"
    assert get_profile(name) == second


@pytest.mark.parametrize("name", ["hospital", "", "School", "schools"])
def test_unknown_profile_is_rejected(name: str) -> None:
    with pytest.raises(UnknownProfileError, match="school, college, company"):
        get_profile(name)
    assert issubclass(UnknownProfileError, ValueError)


def test_profile_rejects_a_rubric_for_the_wrong_type() -> None:
    fields = get_profile("school").model_dump()
    fields["default_rubrics"][T.TEACHING] = "reception.school.v0.1"

    with pytest.raises(ValidationError, match="teaching"):
        OrgProfile.model_validate(fields)


def test_profile_rejects_a_missing_rubric_entry() -> None:
    fields = get_profile("school").model_dump()
    del fields["default_rubrics"][T.SALES]

    with pytest.raises(ValidationError, match="sales"):
        OrgProfile.model_validate(fields)


@pytest.mark.parametrize("enabled_types", [(), (T.TEACHING, T.TEACHING)])
def test_profile_rejects_empty_or_repeated_enabled_types(enabled_types: tuple[ConversationType, ...]) -> None:
    fields = {**get_profile("school").model_dump(), "enabled_types": enabled_types}

    with pytest.raises(ValidationError):
        OrgProfile.model_validate(fields)


def test_profile_rejects_non_positive_retention() -> None:
    fields = {**get_profile("school").model_dump(), "retention_days": 0}

    with pytest.raises(ValidationError):
        OrgProfile.model_validate(fields)


def test_profile_serialises_to_plain_json_types() -> None:
    dumped = get_profile("school").model_dump(mode="json")

    assert dumped["enabled_types"] == ["teaching", "reception"]
    assert dumped["default_rubrics"]["teaching"] == "teaching.school.v0.1"
    assert sorted(dumped["consent"]["call_notice_types"]) == ["reception", "sales"]
