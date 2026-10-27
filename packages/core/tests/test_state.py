"""Tests for sabha_core.state: the recording status transition table (CLAUDE.md, domain model; plan task P2.3).

The expected table is written out here by hand, independently of the module, so a change to the module's table
fails these tests until someone changes this file on purpose.
"""

from __future__ import annotations

from itertools import product
from typing import cast

import pytest

from sabha_core.state import (
    ALLOWED_TRANSITIONS,
    REANALYSIS_TRANSITIONS,
    RETRY_TRANSITIONS,
    TERMINAL_STATUSES,
    WORKER_STAGES,
    ConcurrentTransition,
    InvalidTransition,
    RecordingStatus,
    TransitionError,
    check_transition,
    next_statuses,
    retry_status,
)

S = RecordingStatus

EXPECTED = {
    (S.CREATED, S.UPLOADED),
    (S.UPLOADED, S.PREPROCESSING),
    (S.PREPROCESSING, S.DIARIZING),
    (S.PREPROCESSING, S.FAILED),
    (S.PREPROCESSING, S.NEEDS_REVIEW),
    (S.DIARIZING, S.TRANSCRIBING),
    (S.DIARIZING, S.FAILED),
    (S.DIARIZING, S.NEEDS_REVIEW),
    (S.TRANSCRIBING, S.ANALYZING),
    (S.TRANSCRIBING, S.FAILED),
    (S.TRANSCRIBING, S.NEEDS_REVIEW),
    (S.ANALYZING, S.COMPLETED),
    (S.ANALYZING, S.FAILED),
    (S.ANALYZING, S.NEEDS_REVIEW),
}
REANALYSIS = (S.COMPLETED, S.ANALYZING)

ALL_PAIRS = list(product(RecordingStatus, repeat=2))


def test_statuses_are_exactly_the_documented_ones() -> None:
    assert [status.value for status in RecordingStatus] == [
        "CREATED",
        "UPLOADED",
        "PREPROCESSING",
        "DIARIZING",
        "TRANSCRIBING",
        "ANALYZING",
        "COMPLETED",
        "FAILED",
        "NEEDS_REVIEW",
    ]
    assert all(status.name == status.value for status in RecordingStatus)
    assert RecordingStatus("UPLOADED") is S.UPLOADED
    assert S.UPLOADED == "UPLOADED"  # a StrEnum, so it can be stored in MongoDB as the plain string


def test_table_is_exactly_the_expected_table() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(RecordingStatus)
    allowed = {(source, target) for source, targets in ALLOWED_TRANSITIONS.items() for target in targets}
    assert allowed == EXPECTED
    assert set(REANALYSIS_TRANSITIONS) == {REANALYSIS}


@pytest.mark.parametrize(("from_status", "to_status"), ALL_PAIRS, ids=str)
def test_every_transition_is_allowed_or_refused_exactly_as_the_table_says(
    from_status: RecordingStatus, to_status: RecordingStatus
) -> None:
    if (from_status, to_status) in EXPECTED:
        check_transition(from_status, to_status)  # must not raise
    else:
        with pytest.raises(InvalidTransition) as raised:
            check_transition(from_status, to_status)
        assert raised.value.from_status is from_status
        assert raised.value.to_status is to_status


@pytest.mark.parametrize(("from_status", "to_status"), ALL_PAIRS, ids=str)
def test_reanalysis_unlocks_only_completed_to_analyzing(
    from_status: RecordingStatus, to_status: RecordingStatus
) -> None:
    if (from_status, to_status) in EXPECTED or (from_status, to_status) == REANALYSIS:
        check_transition(from_status, to_status, reanalysis=True)  # must not raise
    else:
        with pytest.raises(InvalidTransition):
            check_transition(from_status, to_status, reanalysis=True)


REVIEW = {(S.NEEDS_REVIEW, S.TRANSCRIBING), (S.NEEDS_REVIEW, S.FAILED)}


@pytest.mark.parametrize(("from_status", "to_status"), ALL_PAIRS, ids=str)
def test_a_review_outcome_unlocks_only_its_two_ways_out_of_needs_review(
    from_status: RecordingStatus, to_status: RecordingStatus
) -> None:
    if (from_status, to_status) in EXPECTED or (from_status, to_status) in REVIEW:
        check_transition(from_status, to_status, review=True)  # must not raise
    else:
        with pytest.raises(InvalidTransition):
            check_transition(from_status, to_status, review=True)


def test_leaving_needs_review_needs_the_review_flag() -> None:
    for target in (S.TRANSCRIBING, S.FAILED):
        with pytest.raises(InvalidTransition, match="review outcome"):
            check_transition(S.NEEDS_REVIEW, target)
        check_transition(S.NEEDS_REVIEW, target, review=True)  # must not raise
    with pytest.raises(InvalidTransition):  # the flags do not combine into other ways out
        check_transition(S.NEEDS_REVIEW, S.ANALYZING, review=True, reanalysis=True)
    assert next_statuses(S.NEEDS_REVIEW, review=True) == frozenset({S.TRANSCRIBING, S.FAILED})


def test_completed_to_analyzing_needs_the_reanalysis_flag() -> None:
    with pytest.raises(InvalidTransition, match="re-analysis"):
        check_transition(S.COMPLETED, S.ANALYZING)

    check_transition(S.COMPLETED, S.ANALYZING, reanalysis=True)  # must not raise


@pytest.mark.parametrize("status", list(RecordingStatus))
def test_same_status_is_never_a_transition(status: RecordingStatus) -> None:
    with pytest.raises(InvalidTransition):
        check_transition(status, status)
    with pytest.raises(InvalidTransition):
        check_transition(status, status, reanalysis=True)


def test_worker_stages_can_each_fail_or_ask_for_review() -> None:
    assert {S.PREPROCESSING, S.DIARIZING, S.TRANSCRIBING, S.ANALYZING} == WORKER_STAGES
    for stage in WORKER_STAGES:
        check_transition(stage, S.FAILED)  # must not raise
        check_transition(stage, S.NEEDS_REVIEW)  # must not raise


@pytest.mark.parametrize("status", [S.CREATED, S.UPLOADED, S.COMPLETED])
def test_only_worker_stages_can_fail_or_ask_for_review(status: RecordingStatus) -> None:
    for target in (S.FAILED, S.NEEDS_REVIEW):
        with pytest.raises(InvalidTransition):
            check_transition(status, target)


def test_terminal_statuses_have_no_ordinary_way_out() -> None:
    assert {S.COMPLETED, S.FAILED, S.NEEDS_REVIEW} == TERMINAL_STATUSES
    for status in TERMINAL_STATUSES:
        assert next_statuses(status) == frozenset()
    assert next_statuses(S.COMPLETED, reanalysis=True) == frozenset({S.ANALYZING})
    assert next_statuses(S.FAILED, reanalysis=True) == frozenset()


def test_next_statuses_follow_the_table() -> None:
    assert next_statuses(S.CREATED) == frozenset({S.UPLOADED})
    assert next_statuses(S.DIARIZING) == frozenset({S.TRANSCRIBING, S.FAILED, S.NEEDS_REVIEW})
    assert next_statuses(S.DIARIZING, reanalysis=True) == next_statuses(S.DIARIZING)


def test_refusal_message_names_the_statuses_and_the_allowed_next_ones() -> None:
    with pytest.raises(InvalidTransition) as raised:
        check_transition(S.UPLOADED, S.DIARIZING)

    message = str(raised.value)
    assert "UPLOADED" in message
    assert "DIARIZING" in message
    assert "PREPROCESSING" in message


def test_refusal_from_a_final_status_says_so() -> None:
    # PREPROCESSING is not even a retry target: preprocessing is retried through UPLOADED.
    with pytest.raises(InvalidTransition, match=r"no transitions out of FAILED except a retry \(retry=True\)$"):
        check_transition(S.FAILED, S.PREPROCESSING)
    with pytest.raises(InvalidTransition, match="no transitions out of COMPLETED except re-analysis"):
        check_transition(S.COMPLETED, S.FAILED)


def test_plain_strings_from_the_database_are_accepted() -> None:
    check_transition("UPLOADED", "PREPROCESSING")  # must not raise
    with pytest.raises(InvalidTransition):
        check_transition("UPLOADED", "COMPLETED")


def test_unknown_status_is_rejected() -> None:
    with pytest.raises(ValueError, match="BOGUS"):
        check_transition("BOGUS", "UPLOADED")
    with pytest.raises(ValueError, match="BOGUS"):
        check_transition("CREATED", "BOGUS")


def test_error_hierarchy() -> None:
    assert issubclass(InvalidTransition, TransitionError)
    assert issubclass(ConcurrentTransition, TransitionError)
    assert not issubclass(InvalidTransition, ConcurrentTransition)
    assert not issubclass(ConcurrentTransition, InvalidTransition)


def test_table_cannot_be_changed_at_runtime() -> None:
    table = cast("dict[RecordingStatus, frozenset[RecordingStatus]]", ALLOWED_TRANSITIONS)
    with pytest.raises(TypeError):
        table[S.FAILED] = frozenset({S.PREPROCESSING})
    assert isinstance(ALLOWED_TRANSITIONS[S.CREATED], frozenset)


# --- Retrying a failed recording (P7.8, owner's decision 2026-10-27) ---

# FAILED goes back to where the failed stage starts: UPLOADED for preprocessing (its start event is the upload's),
# the stage's own status for the others. Written out by hand, like EXPECTED.
RETRY = {(S.FAILED, S.UPLOADED), (S.FAILED, S.DIARIZING), (S.FAILED, S.TRANSCRIBING), (S.FAILED, S.ANALYZING)}


def test_the_retry_table_is_exactly_the_expected_one() -> None:
    assert set(RETRY_TRANSITIONS) == RETRY


@pytest.mark.parametrize(("from_status", "to_status"), ALL_PAIRS, ids=str)
def test_retry_unlocks_only_the_ways_back_from_failed(from_status: RecordingStatus, to_status: RecordingStatus) -> None:
    if (from_status, to_status) in EXPECTED or (from_status, to_status) in RETRY:
        check_transition(from_status, to_status, retry=True)  # must not raise
    else:
        with pytest.raises(InvalidTransition):
            check_transition(from_status, to_status, retry=True)


def test_leaving_failed_needs_the_retry_flag() -> None:
    for target in (S.UPLOADED, S.DIARIZING, S.TRANSCRIBING, S.ANALYZING):
        with pytest.raises(InvalidTransition, match="retry"):
            check_transition(S.FAILED, target)
        with pytest.raises(InvalidTransition):  # the other flags do not open it
            check_transition(S.FAILED, target, reanalysis=True, review=True)
    assert next_statuses(S.FAILED, retry=True) == frozenset({S.UPLOADED, S.DIARIZING, S.TRANSCRIBING, S.ANALYZING})
    assert next_statuses(S.FAILED) == frozenset()


def test_retry_never_skips_to_the_end_or_to_review() -> None:
    for target in (S.COMPLETED, S.NEEDS_REVIEW, S.CREATED, S.PREPROCESSING):
        with pytest.raises(InvalidTransition):
            check_transition(S.FAILED, target, retry=True)


@pytest.mark.parametrize(
    ("stage", "target"),
    [("preprocess", S.UPLOADED), ("diarize", S.DIARIZING), ("transcribe", S.TRANSCRIBING), ("analyze", S.ANALYZING)],
)
def test_each_stage_has_its_retry_status(stage: str, target: RecordingStatus) -> None:
    assert retry_status(stage) is target


def test_an_unknown_stage_has_no_retry_status() -> None:
    with pytest.raises(ValueError, match="no stage"):
        retry_status("cooking")
