"""Next actions for a sales rep: the due date from the words said, and a priority (founder's Sales Executive
dashboard doc, 2026-11-12; defaults agreed by the product owner the same day).

Due dates are worked out in code, never by the model (golden rule 5): `resolve_due` turns the deal card's `due`, the
date or time exactly as said ("Thursday 4 pm", "kal tak", "15 Nov"), into a calendar date counted from the day of the
conversation, and only when that is unambiguous:

- today / aaj: that day; tomorrow / kal: the next day; day after tomorrow / parso / parson: two days on;
- "in 3 days" / "3 din mein": that many days on;
- a weekday (English or Hindi: Thursday, Thu, guruvar, ...), optionally "this ...": the next such day after the
  conversation (the same weekday means a week on). "next Thursday" is ambiguous (this week's or the next?): None;
- a day and month ("15 Nov", "15th November", "November 15", "15/11", "15-11-2026"; numbers are day/month, as
  written in India): that date, in the conversation's year, or the next year if it has already passed.
- anything else ("next week", "month end", "soon"), or two different dates in the words: None.

`priority` applies a rubric's `follow_up` rule: high when the interest is one of `high_interest` and the action is
due within `high_within_days` or is overdue; medium when it is due within `medium_within_days` (or overdue); low
otherwise, including when there is no date.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Literal, Protocol

Priority = Literal["high", "medium", "low"]

_WEEKDAYS = {
    0: ("monday", "mon", "somvar", "somwar"),
    1: ("tuesday", "tue", "tues", "mangalvar", "mangalwar"),
    2: ("wednesday", "wed", "budhvar", "budhwar"),
    3: ("thursday", "thu", "thur", "thurs", "guruvar", "guruwar", "brihaspativar"),
    4: ("friday", "fri", "shukravar", "shukrawar"),
    5: ("saturday", "sat", "shanivar", "shaniwar"),
    6: ("sunday", "sun", "ravivar", "raviwar", "itvaar", "itwar"),
}
_DAY_OF = {word: day for day, words in _WEEKDAYS.items() for word in words}
_MONTHS = {
    name: number
    for number, names in enumerate(
        (("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
         ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"),
         ("nov", "november"), ("dec", "december")),
        start=1,
    )
    for name in names
}  # fmt: skip
_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))
_RELATIVE = (
    (re.compile(r"\b(day after tomorrow|parso|parson|parsoon)\b"), 2),
    (re.compile(r"\b(today|aaj)\b"), 0),
    (re.compile(r"\b(tomorrow|kal)\b"), 1),
)
_IN_DAYS = re.compile(r"\bin (\d{1,2}) days?\b|\b(\d{1,2}) din (?:mein|me|main)\b")
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH})\b")
_MONTH_DAY = re.compile(rf"\b({_MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b")
_NUMERIC = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2}|\d{4}))?\b")
_WORD = re.compile(r"[a-z]+")


def _calendar(day: int, month: int, year: int | None, spoken_on: date) -> date | None:
    try:
        if year is not None:
            return date(year + 2000 if year < 100 else year, month, day)
        found = date(spoken_on.year, month, day)
        return found if found >= spoken_on else date(spoken_on.year + 1, month, day)
    except ValueError:
        return None


def _candidates(text: str, spoken_on: date) -> set[date | None]:
    found: set[date | None] = set()
    rest = text
    for pattern, days in _RELATIVE:
        if pattern.search(rest):
            found.add(spoken_on + timedelta(days=days))
            rest = pattern.sub(" ", rest)  # "day after tomorrow" is not also "tomorrow"
    for match in _IN_DAYS.finditer(text):
        found.add(spoken_on + timedelta(days=int(match.group(1) or match.group(2))))
    for match in _DAY_MONTH.finditer(text):
        found.add(_calendar(int(match.group(1)), _MONTHS[match.group(2)], None, spoken_on))
    for match in _MONTH_DAY.finditer(text):
        found.add(_calendar(int(match.group(2)), _MONTHS[match.group(1)], None, spoken_on))
    for match in _NUMERIC.finditer(text):
        year = int(match.group(3)) if match.group(3) else None
        found.add(_calendar(int(match.group(1)), int(match.group(2)), year, spoken_on))
    words = _WORD.findall(text)
    for i, word in enumerate(words):
        if word in _DAY_OF and not (word in ("sat", "sun", "wed") and i > 0 and words[i - 1] in _MONTHS):
            if i > 0 and words[i - 1] == "next":
                found.add(None)  # "next Thursday": this week's or the next?
                continue
            ahead = (_DAY_OF[word] - spoken_on.weekday()) % 7 or 7
            found.add(spoken_on + timedelta(days=ahead))
    return found


def resolve_due(said: str | None, spoken_on: date) -> date | None:
    """The calendar date the words name, counted from the day of the conversation, or None (module docstring)."""
    if not said:
        return None
    found = _candidates(said.lower(), spoken_on)
    if len(found) != 1:
        return None
    return next(iter(found))


class FollowUpRule(Protocol):
    @property
    def high_interest(self) -> tuple[str, ...]: ...
    @property
    def high_within_days(self) -> int: ...
    @property
    def medium_within_days(self) -> int: ...


def priority(rule: FollowUpRule, *, interest: str | None, due: date | None, today: date) -> Priority:
    """The next action's priority under the rubric's follow_up rule (module docstring)."""
    if due is None:
        return "low"
    days = (due - today).days
    if interest in rule.high_interest and days <= rule.high_within_days:
        return "high"
    if days <= rule.medium_within_days:
        return "medium"
    return "low"
