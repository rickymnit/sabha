"""Due dates from the words said, and next-action priority (sabha_analytics.follow_up)."""

from __future__ import annotations

from datetime import date

import pytest

from sabha_analytics.follow_up import priority, resolve_due
from sabha_analytics.rubric import FollowUpRules

MONDAY = date(2026, 11, 9)


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("Thursday 4 pm", date(2026, 11, 12)),
        ("guruvar ko", date(2026, 11, 12)),
        ("this Friday", date(2026, 11, 13)),
        ("Monday", date(2026, 11, 16)),  # the same weekday means a week on
        ("kal tak", date(2026, 11, 10)),
        ("tomorrow morning", date(2026, 11, 10)),
        ("day after tomorrow", date(2026, 11, 11)),
        ("parso", date(2026, 11, 11)),
        ("aaj shaam", date(2026, 11, 9)),
        ("in 3 days", date(2026, 11, 12)),
        ("5 din mein", date(2026, 11, 14)),
        ("15 Nov", date(2026, 11, 15)),
        ("15th of November", date(2026, 11, 15)),
        ("December 2", date(2026, 12, 2)),
        ("2/1", date(2027, 1, 2)),  # day/month, already passed this year
        ("20-11-2026", date(2026, 11, 20)),
        ("कल, 12 बजे के बाद", date(2026, 11, 10)),  # Devanagari, as the transcripts keep it
        ("परसों तक", date(2026, 11, 11)),
        ("गुरुवार को", date(2026, 11, 12)),
        ("थर्सडे 4 बजे", date(2026, 11, 12)),
        ("15 नवंबर", date(2026, 11, 15)),
        ("३ दिन में", date(2026, 11, 12)),
    ],
)
def test_clear_words_give_a_date(said: str, expected: date) -> None:
    assert resolve_due(said, MONDAY) == expected


@pytest.mark.parametrize(
    "said",
    [
        None,
        "",
        "next week",
        "month end",
        "soon",
        "next Thursday",
        "Thursday or Friday",
        "31/2",
        "kal ya parso",
        "अभी",
        "निकल गया",
        "कल तक; थर्सडे 4 बजे",
        "अगले सोमवार",
    ],
)
def test_unclear_words_give_no_date(said: str | None) -> None:
    assert resolve_due(said, MONDAY) is None


RULE = FollowUpRules(high_interest=("high",), high_within_days=2, medium_within_days=7)
TODAY = date(2026, 11, 12)


@pytest.mark.parametrize(
    ("interest", "due", "expected"),
    [
        ("high", date(2026, 11, 14), "high"),  # interested, due within 2 days
        ("high", date(2026, 11, 1), "high"),  # interested and overdue
        ("high", date(2026, 11, 18), "medium"),  # interested, due within the week
        ("medium", date(2026, 11, 13), "medium"),  # not interested enough for high, however close
        ("medium", date(2026, 11, 30), "low"),
        ("high", None, "low"),  # no date
    ],
)
def test_priority_follows_the_rubric_rule(interest: str, due: date | None, expected: str) -> None:
    assert priority(RULE, interest=interest, due=due, today=TODAY) == expected
