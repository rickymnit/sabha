"""Organisation profiles: the defaults a new tenant starts from (plan task P1.7).

A profile sets the product's wording, the conversation types switched on, the starting rubrics, consent rules and
audio retention. It never changes code paths (CLAUDE.md, ADR 0001). A tenant copies these defaults when it is
created, and its owner can then rename labels and switch types on or off; the Tenant model (P1.6) and the API
endpoints that do this are not here, and nothing in this module touches the database.

Sources: labels and conversation types come from the workspace setup design (docs/design/source/Setup.dc.html,
the `P` and `TYPES` tables); consent from CLAUDE.md golden rule 9, the design's consent notes and
docs/legal/drafts/; audio retention from plan task P7.3 and the legal drafts. A comment marks every value that
departs from those sources or is a proposal still to be confirmed.

Profiles are frozen, and `get_profile` returns a deep copy, so no caller can change the shared defaults.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationType(StrEnum):
    """The kinds of conversation Sabha analyses, in the order the setup screen lists them."""

    TEACHING = "teaching"
    COUNSELLING = "counselling"
    RECEPTION = "reception"
    MEETING = "meeting"
    SALES = "sales"


class ProfileName(StrEnum):
    SCHOOL = "school"
    COLLEGE = "college"
    COMPANY = "company"


class UnknownProfileError(ValueError):
    """No organisation profile has this name."""


# Rubric ids follow the rubric file names: <type>.<segment>.v<major>.<minor> (rubrics/README.md).
_RUBRIC_ID = re.compile(r"^(?P<type>[a-z]+)\.[a-z0-9_]+\.v\d+\.\d+$")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Labels(_Frozen):
    """The words the product uses for a tenant's own nouns; the web app reads them through useLabels()."""

    person: str = Field(min_length=1)  # the staff member analysed
    person_plural: str = Field(min_length=1)
    recording: str = Field(min_length=1)
    recording_plural: str = Field(min_length=1)
    unit: str = Field(min_length=1)  # the group people belong to (the units collection)
    manager: str = Field(min_length=1)


class ConsentDefaults(_Frozen):
    """What a tenant must have on record before its recordings are processed."""

    # Golden rule 9: a recording without consent_ref cannot move past UPLOADED. Every profile; not configurable.
    consent_ref_required: Literal[True] = True
    # Every recording of these types needs parental consent on record.
    parental_consent_types: frozenset[ConversationType]
    # Any recording in which people under 18 take part needs parental consent, whatever its type.
    parental_consent_for_minors: bool
    # Calls of these types must play a recording notice to the caller before they connect.
    call_notice_types: frozenset[ConversationType]
    # Each recorded staff member gives individual consent, rather than being covered by an employer policy.
    staff_consent_required: bool


class OrgProfile(_Frozen):
    """The defaults for one kind of organisation."""

    name: ProfileName
    enabled_types: tuple[ConversationType, ...]  # in ConversationType order
    labels: Labels
    # A rubric id, or None where no rubric exists yet, for EVERY conversation type, so a type switched on later
    # still has an entry.
    default_rubrics: dict[ConversationType, str | None]
    consent: ConsentDefaults
    # Days before original audio and playback copies are deleted (P7.3). Transcripts and scores are kept; their
    # retention period is not decided (docs/legal/drafts/questions-for-lawyer.md, D2).
    retention_days: int = Field(gt=0)

    @field_validator("enabled_types")
    @classmethod
    def _check_enabled_types(cls, value: tuple[ConversationType, ...]) -> tuple[ConversationType, ...]:
        if not value:
            raise ValueError("at least one conversation type must be enabled")
        if len(set(value)) != len(value):
            raise ValueError("enabled_types lists a type more than once")
        return tuple(t for t in ConversationType if t in value)

    @field_validator("default_rubrics")
    @classmethod
    def _check_default_rubrics(cls, value: dict[ConversationType, str | None]) -> dict[ConversationType, str | None]:
        missing = [t.value for t in ConversationType if t not in value]
        if missing:
            raise ValueError(f"default_rubrics needs an entry (a rubric id or None) for: {', '.join(missing)}")
        for conversation_type, rubric_id in value.items():
            match = None if rubric_id is None else _RUBRIC_ID.match(rubric_id)
            if rubric_id is not None and (match is None or match["type"] != conversation_type):
                raise ValueError(f"{rubric_id!r} is not a <type>.<segment>.v<major>.<minor> id for {conversation_type}")
        return {t: value[t] for t in ConversationType}


_T = ConversationType

_PROFILES: dict[ProfileName, OrgProfile] = {
    ProfileName.SCHOOL: OrgProfile(
        name=ProfileName.SCHOOL,
        # The pilot covers teaching and reception (CLAUDE.md). The design also ticks counselling for schools
        # (Setup.dc.html:143), but student counselling must not be recorded without a separate legal review
        # (docs/legal/drafts/staff-consent-and-notice.md, section 2), so it starts switched off.
        enabled_types=(_T.TEACHING, _T.RECEPTION),
        labels=Labels(  # Setup.dc.html:144
            person="Teacher",
            person_plural="Teachers",
            recording="Lesson",
            recording_plural="Lessons",
            unit="Campus and section",
            manager="Principal or coordinator",
        ),
        default_rubrics={  # only rubrics that exist in rubrics/
            _T.TEACHING: "teaching.school.v0.1",
            _T.COUNSELLING: None,
            _T.RECEPTION: "reception.school.v0.2",  # reviewed and approved for the pilot (2026-10-20)
            _T.MEETING: None,
            _T.SALES: None,
        },
        consent=ConsentDefaults(
            # Classroom lessons need parental consent (parent-consent-form.md, Scope; Setup.dc.html:148).
            parental_consent_types=frozenset({_T.TEACHING}),
            parental_consent_for_minors=True,  # Setup.dc.html:148
            # Reception: call-recording-notice.md. Sales (the design's "Admissions calls", Setup.dc.html:146) is a
            # proposal: they are calls with parents too, and it keeps school at least as strict as company.
            call_notice_types=frozenset({_T.RECEPTION, _T.SALES}),
            staff_consent_required=True,  # staff-consent-and-notice.md
        ),
        retention_days=90,  # P7.3 default; parent-consent-form.md and staff-consent-and-notice.md say 90 days
    ),
    ProfileName.COLLEGE: OrgProfile(
        name=ProfileName.COLLEGE,
        enabled_types=(_T.TEACHING, _T.COUNSELLING, _T.RECEPTION),  # Setup.dc.html:153
        labels=Labels(  # Setup.dc.html:154
            person="Faculty member",
            person_plural="Faculty",
            recording="Lecture",
            recording_plural="Lectures",
            unit="Department",
            manager="Head of department",
        ),
        default_rubrics=dict.fromkeys(ConversationType),  # no college rubrics exist yet
        consent=ConsentDefaults(
            parental_consent_types=frozenset(),
            parental_consent_for_minors=True,  # "Parental consent is needed only for students under 18" (:158)
            # Proposal: the design says "Participants are told they are being recorded" (:158); for calls that
            # means a recording notice, as for school and company.
            call_notice_types=frozenset({_T.RECEPTION, _T.SALES}),
            staff_consent_required=False,  # proposal: the design describes a notice to participants, not consent
        ),
        retention_days=90,  # P7.3 default
    ),
    ProfileName.COMPANY: OrgProfile(
        name=ProfileName.COMPANY,
        enabled_types=(_T.RECEPTION, _T.MEETING, _T.SALES),  # Setup.dc.html:163
        labels=Labels(  # Setup.dc.html:164
            person="Sales rep",
            person_plural="Team",
            # "Conversation", not the design's "Call" (Setup.dc.html:164): in-person sales meetings and team meetings
            # are not calls (owner's decision on sales, 2026-10-24). A tenant can rename it.
            recording="Conversation",
            recording_plural="Conversations",
            unit="Team or branch",
            manager="Sales manager",
        ),
        default_rubrics={
            **dict.fromkeys(ConversationType),
            _T.SALES: "sales.company.v0.1",  # draft for the owner's review (2026-10-26): in-person sales meetings
        },
        consent=ConsentDefaults(
            parental_consent_types=frozenset(),
            parental_consent_for_minors=True,  # proposal: the design is silent; kept as strict as the others
            # "Customers hear a recording notice at the start of each call" (:168): customer calls are these types.
            call_notice_types=frozenset({_T.RECEPTION, _T.SALES}),
            staff_consent_required=False,  # "Staff are covered by your recording policy" (:168)
        ),
        retention_days=90,  # P7.3 default
    ),
}


def get_profile(name: ProfileName | str) -> OrgProfile:
    """A deep copy of the named profile's defaults. Raises UnknownProfileError for an unknown name."""
    try:
        profile = _PROFILES[ProfileName(name)]
    except ValueError:
        known = ", ".join(ProfileName)
        raise UnknownProfileError(f"unknown organisation profile {name!r}; choose one of: {known}") from None
    return profile.model_copy(deep=True)
