"""Speaker role assignment from diarization turns and ASR words, by heuristics only (plan task P3.6).

Output is roles@v1.json: {speaker_label: {role, confidence, method}}. Roles come from the rubric as a pair
(staff_role, other_role): the first is the staff member who is analysed ("teacher", "receptionist"), the second is
everyone else ("students", "caller"). Golden rule 10: staff are analysed, not students. "students" is a group role:
every non-teacher speaker gets it, with no per-student role, ranking or identity. Speaker labels are the diarizer's
anonymous cluster ids, kept only so transcript words can be joined to roles.

Times are compact milliseconds; talk share and turn lengths are the same on either timeline (silence is not talk).

Teaching (the speaker with the largest talk share AND the most long turns is the teacher):

- Consecutive turns of one speaker separated by at most `turn_join_gap_ms` are joined first (diarizers fragment a
  long explanation). A long turn is a joined turn of at least `long_turn_ms` (15 s): a stretch of continuous
  explanation that students rarely produce.
- If the talk-share leader and the long-turn leader are the same speaker (both unique), confidence is
  0.5 + 0.25 * share_score + 0.25 * long_score, where share_score = min(1, (top share - second share) /
  share_margin_full) and long_score = (leader's long turns - most long turns of anyone else) / leader's long turns.
  0.5 is a coin flip; 1.0 means both margins are decisive. share_margin_full (0.30) is the lead in talk share that
  earns full credit.
- If they differ, or nobody has a long turn, the heuristics disagree: the talk-share leader is recorded as the
  best guess with confidence 0.5.

Reception (the first speaker who greets with the school or company name is the receptionist):

- Only words starting in the first `greeting_window_ms` (30 s) of speech count. Text is case-folded, punctuation is
  removed and whitespace collapsed; phrases match whole words. The caller supplies the tenant's name variants.
- Per speaker: greets_with_name = a greeting ("namaste", "good morning", "hello", ...) and a name variant both
  occur; self_identifies = an introduction ("bol rahi hoon", "<name> se", "speaking", "how may I help", ...).
  Evidence points = 2 * greets_with_name + 1 * self_identifies + 1 * spoke_first (at most 4).
- The receptionist is the first speaker, in order of first speech, who greets with the name. Confidence is
  0.5 + 0.5 * max(0, margin) / 4, where margin is that speaker's points minus the most points of any other speaker.
  If nobody greets with the name, the first speaker is recorded as the best guess with confidence 0.5.
Reception, walk-in (the rubric's other role is "visitor": a visitor at the front desk of a business, one visit per
recording, owner's decision 2026-10-26):

- At a desk the visitor often speaks first ("Excuse me...") and the receptionist rarely says the company's name, so
  speaking first is NOT evidence. Only words in the first `intro_window_ms` (90 s) of speech count.
- Per speaker: greets_with_name as for calls (a greeting, or "welcome to", with a name variant); desk_phrases = how
  many different DESK_PHRASES occur ("how can I help", "kisse milna hai", "aapka naam", "please baithiye", ...),
  counted up to 2. Evidence points = 2 * greets_with_name + desk_phrases (at most 4).
- The receptionist is the speaker with the most points, if one speaker has strictly the most and at least 1;
  confidence 0.5 + 0.5 * margin / 4. So two different desk phrases and nothing from anyone else is confident (0.75);
  one alone goes to the tie-breaker. Without any evidence, the first speaker is the best guess with confidence 0.5.

Sales, in person (one rep with one or more people from the customer side; the rep introduces the company):

- Only words in the first `intro_window_ms` (90 s) of speech count for the introduction, as for reception.
- Per speaker: introduces_company = the company name (a tenant name variant) with an introduction ("<name> se",
  "from <name>", "main", "mera naam", "my name", "I am" or a reception introduction). Evidence points =
  2 * introduces_company + 1 * talk-share leader + 1 * long-turn leader (at most 4).
- The rep is the first speaker, in order of first speech, who introduces the company; confidence as for reception,
  0.5 + 0.5 * max(0, margin) / 4. If nobody introduces the company, the teaching rule decides (the rep runs the
  pitch and the demo: largest talk share AND most long turns). The customer side often speaks first, in its own
  office, so speaking first is not evidence here.

A stereo channel hint (`receptionist_channel_speaker`, the speaker label heard on the receptionist's channel) is
  configuration, not inference: when given it wins, with confidence 1.0 and method "channel".

Low confidence: when the heuristics disagree or confidence < `min_confidence` (0.7), every speaker's method is
"heuristic_low_confidence" and `needs_review_reason` is "unclear_roles", so the recording goes to NEEDS_REVIEW
(`next_status`). The best guess is still recorded for the reviewer; it is never used silently.

LLM tie-breaker hook: P5.1 adds a small-LLM tie-breaker through sabha_llm, which redacts PII before any text leaves
our servers (golden rule 8). It plugs in as `tie_breaker`, is called only for low-confidence results, and receives
the first 2 minutes of speech UNREDACTED; redaction is the implementation's job. It must be passed in explicitly
when configured (golden rule 7: no silent fallback). Nothing in this module calls an LLM.
"""

from __future__ import annotations

import json
import operator
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol, TypedDict

from sabha_asr.words import Turn, Word, assign_words_to_turns
from sabha_core.state import RecordingStatus

TEACHING = "teaching"
RECEPTION = "reception"
SALES = "sales"
RECORDING_TYPES = frozenset({TEACHING, RECEPTION, SALES})
VISITOR = "visitor"
"""The other role of a walk-in reception rubric (reception.company): a visitor at the desk, not a caller."""

METHOD_HEURISTIC = "heuristic"
METHOD_CHANNEL = "channel"
METHOD_LOW_CONFIDENCE = "heuristic_low_confidence"
REASON_UNCLEAR_ROLES = "unclear_roles"

DEFAULT_LONG_TURN_MS = 15_000
DEFAULT_TURN_JOIN_GAP_MS = 1_000
DEFAULT_SHARE_MARGIN_FULL = 0.30
DEFAULT_GREETING_WINDOW_MS = 30_000
DEFAULT_INTRO_WINDOW_MS = 90_000
DEFAULT_TIE_BREAK_WINDOW_MS = 120_000
DEFAULT_MIN_CONFIDENCE = 0.7

GREETINGS: tuple[str, ...] = (
    "namaste",
    "namastey",
    "namaskar",
    "namaskaar",
    "pranam",
    "good morning",
    "good afternoon",
    "good evening",
    "hello",
    "hallo",
    "helo",
    "hi",
    "welcome",
    "नमस्ते",
    "नमस्कार",
    "प्रणाम",
    "हेलो",
    "हैलो",
)
"""Opening greetings, normalised (lower case, no punctuation). Matched as whole words."""

SELF_INTRODUCTIONS: tuple[str, ...] = (
    "bol rahi hoon",
    "bol rahi hun",
    "bol rahi hu",
    "bol raha hoon",
    "bol raha hun",
    "bol raha hu",
    "bol rahe hain",
    "speaking",
    "this is",
    "calling from",
    "how may i help",
    "how can i help",
    "kaise madad",
    "kya madad",
    "बोल रही हूँ",
    "बोल रही हूं",
    "बोल रहा हूँ",
    "बोल रहा हूं",
    "बोल रहे हैं",
)
"""Phrases a receptionist uses to introduce herself or the office. "<name> se" is added per tenant name."""

_EVIDENCE_MAX = 4  # reception: 2 (greets with name) + 1 (introduces herself) + 1 (spoke first); sales: see docstring

DESK_PHRASES: tuple[str, ...] = (
    "how can i help",
    "how may i help",
    "kaise madad",
    "kya madad",
    "kya help",
    "kisse milna",
    "kis se milna",
    "kisko milna",
    "kinse milna",
    "whom do you want to meet",
    "who are you here to meet",
    "aapka naam",
    "your name",
    "appointment hai",
    "do you have an appointment",
    "baithiye",
    "baith jaiye",
    "have a seat",
    "please sit",
    "wait kijiye",
    "inform kar",
    "bula deti",
    "bula deta",
    "welcome to",
    "किससे मिलना",
    "किसको मिलना",
    "आपका नाम",
    "बैठिए",
    "बैठिये",
    "बैठ जाइए",
)
"""Phrases a receptionist uses with a walk-in visitor, normalised. Matched as whole words; counted up to 2."""
_DESK_PHRASES_COUNTED = 2

SALES_INTRODUCTIONS: tuple[str, ...] = ("main", "mera naam", "my name", "i am", "im", "मैं", "मेरा नाम")
"""Words a sales rep introduces themselves with, besides SELF_INTRODUCTIONS; counted only with the company name."""


class SpeakerRoleRecord(TypedDict):
    role: str
    confidence: float
    method: str


@dataclass(frozen=True, slots=True)
class RoleParams:
    """Thresholds for the heuristics. Defaults are first choices to be checked against the gold set (eval/roles.py)."""

    long_turn_ms: int = DEFAULT_LONG_TURN_MS
    turn_join_gap_ms: int = DEFAULT_TURN_JOIN_GAP_MS
    share_margin_full: float = DEFAULT_SHARE_MARGIN_FULL
    greeting_window_ms: int = DEFAULT_GREETING_WINDOW_MS
    intro_window_ms: int = DEFAULT_INTRO_WINDOW_MS
    tie_break_window_ms: int = DEFAULT_TIE_BREAK_WINDOW_MS
    min_confidence: float = DEFAULT_MIN_CONFIDENCE

    def __post_init__(self) -> None:
        for name in (
            "long_turn_ms",
            "turn_join_gap_ms",
            "greeting_window_ms",
            "intro_window_ms",
            "tie_break_window_ms",
        ):
            if operator.index(getattr(self, name)) < 0:
                raise ValueError(f"{name} cannot be negative")
        if not self.share_margin_full > 0:
            raise ValueError("share_margin_full must be positive")
        if not 0 <= self.min_confidence <= 1:
            raise ValueError("min_confidence must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class SpeakerRole:
    """One entry of roles@v1.json."""

    role: str
    confidence: float
    method: str

    def __post_init__(self) -> None:
        if not (isinstance(self.role, str) and self.role.strip() and isinstance(self.method, str) and self.method):
            raise ValueError(f"role and method must be non-blank strings: {self}")
        if isinstance(self.confidence, bool) or not 0 <= self.confidence <= 1:
            raise ValueError(f"confidence must be in [0, 1]: {self}")


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    """Roles for every speaker of one recording. `needs_review_reason` is set when the roles are not trustworthy."""

    speakers: Mapping[str, SpeakerRole]
    needs_review_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "speakers", MappingProxyType(dict(self.speakers)))

    def role_by_speaker(self) -> dict[str, str]:
        return {label: speaker.role for label, speaker in self.speakers.items()}

    def to_records(self) -> dict[str, SpeakerRoleRecord]:
        """The roles@v1.json content."""
        return {
            label: {"role": s.role, "confidence": s.confidence, "method": s.method}
            for label, s in sorted(self.speakers.items())
        }

    def to_json(self) -> str:
        return json.dumps(self.to_records(), ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class TieBreakRequest:
    """What the P5.1 tie-breaker gets: the heuristic result and the opening of the recording, NOT redacted."""

    recording_type: str
    rubric_roles: tuple[str, str]
    heuristic: RoleAssignment
    opening: tuple[tuple[str, str], ...] = field(default=())  # (speaker_label, text) per stretch of one speaker


class RoleTieBreaker(Protocol):
    """Settles low-confidence roles (P5.1). Returns a confident assignment, or None when it is unsure too."""

    def __call__(self, request: TieBreakRequest) -> RoleAssignment | None: ...


def next_status(assignment: RoleAssignment) -> RecordingStatus:
    """Where the recording goes after the transcribe stage, as far as roles are concerned."""
    return RecordingStatus.NEEDS_REVIEW if assignment.needs_review_reason else RecordingStatus.ANALYZING


def normalise_text(text: str) -> str:
    """Case-fold, turn punctuation and symbols into spaces, collapse whitespace. Keeps Devanagari vowel signs."""
    folded = unicodedata.normalize("NFC", text.casefold())
    kept = "".join(" " if unicodedata.category(ch)[0] in "PSZC" else ch for ch in folded)
    return " ".join(kept.split())


def _contains(text: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {text} "


def _speaker_runs(turns: Sequence[Turn], words: Sequence[Word], window_ms: int) -> list[tuple[str, str]]:
    """(speaker_label, text) for each run of consecutive words by one speaker, for words starting before window_ms."""
    early = sorted((w for w in words if w.start_ms < window_ms), key=lambda w: (w.start_ms, w.end_ms))
    runs: list[tuple[str, list[str]]] = []
    for word, turn in zip(early, assign_words_to_turns(early, turns), strict=True):
        if runs and runs[-1][0] == turn.speaker_label:
            runs[-1][1].append(word.text)
        else:
            runs.append((turn.speaker_label, [word.text]))
    return [(label, " ".join(texts)) for label, texts in runs]


def _joined_turns(turns: Sequence[Turn], join_gap_ms: int) -> list[Turn]:
    """Turns in time order, with consecutive turns of one speaker joined when the gap between them is small."""
    joined: list[Turn] = []
    for turn in sorted(turns, key=lambda t: (t.start_ms, t.end_ms, t.speaker_label)):
        last = joined[-1] if joined else None
        if last and last.speaker_label == turn.speaker_label and turn.start_ms - last.end_ms <= join_gap_ms:
            joined[-1] = Turn(last.speaker_label, last.start_ms, max(last.end_ms, turn.end_ms))
        else:
            joined.append(turn)
    return joined


def _talk_ms(turns: Sequence[Turn]) -> dict[str, int]:
    """Speaking time per speaker: the union of that speaker's turns, so overlapping turns are not counted twice."""
    by_speaker: dict[str, list[tuple[int, int]]] = {}
    for turn in turns:
        by_speaker.setdefault(turn.speaker_label, []).append((turn.start_ms, turn.end_ms))
    talk = {}
    for label, spans in by_speaker.items():
        total, covered_to = 0, -1
        for start, end in sorted(spans):
            if end > covered_to:
                total += end - max(start, covered_to)
                covered_to = end
        talk[label] = total
    return talk


def _unique_leader(scores: Mapping[str, float]) -> str | None:
    """The speaker with the highest score, or None if the top score is shared or not positive."""
    ranked = sorted(scores.values(), reverse=True)
    if not ranked or ranked[0] <= 0 or (len(ranked) > 1 and ranked[0] == ranked[1]):
        return None
    return next(label for label, score in scores.items() if score == ranked[0])


def _teaching_guess(turns: Sequence[Turn], params: RoleParams) -> tuple[str, float, bool]:
    """(teacher label, confidence, heuristics agree)."""
    talk = _talk_ms(turns)
    total = sum(talk.values())
    shares = {label: ms / total for label, ms in talk.items()}
    long_turns: dict[str, float] = dict.fromkeys(talk, 0)
    for turn in _joined_turns(turns, params.turn_join_gap_ms):
        if turn.duration_ms >= params.long_turn_ms:
            long_turns[turn.speaker_label] += 1

    share_leader = _unique_leader(shares)
    long_leader = _unique_leader(long_turns)
    guess = share_leader or min(talk, key=lambda label: (-talk[label], label))
    if share_leader is None or share_leader != long_leader:
        return guess, 0.5, False
    second_share = max((s for label, s in shares.items() if label != guess), default=0.0)
    second_long = max((n for label, n in long_turns.items() if label != guess), default=0)
    share_score = min(1.0, (shares[guess] - second_share) / params.share_margin_full)
    long_score = (long_turns[guess] - second_long) / long_turns[guess]
    return guess, 0.5 + 0.25 * share_score + 0.25 * long_score, True


def _reception_guess(
    turns: Sequence[Turn], words: Sequence[Word], name_variants: Sequence[str], params: RoleParams
) -> tuple[str, float, bool]:
    """(receptionist label, confidence, a speaker greeted with the name)."""
    order = list(dict.fromkeys(t.speaker_label for t in sorted(turns, key=lambda t: (t.start_ms, t.end_ms))))
    texts: dict[str, list[str]] = {label: [] for label in order}
    for label, text in _speaker_runs(turns, words, params.greeting_window_ms):
        texts[label].append(text)
    names = [name for name in (normalise_text(v) for v in name_variants) if name]
    introductions = [*SELF_INTRODUCTIONS, *(f"{name} se" for name in names)]

    points: dict[str, int] = {}
    greets_with_name: dict[str, bool] = {}
    for label in order:
        text = normalise_text(" ".join(texts[label]))
        greets_with_name[label] = any(_contains(text, g) for g in GREETINGS) and any(_contains(text, n) for n in names)
        introduces = any(_contains(text, phrase) for phrase in introductions)
        points[label] = 2 * greets_with_name[label] + introduces + (label == order[0])

    candidate = next((label for label in order if greets_with_name[label]), None)
    if candidate is None:
        return order[0], 0.5, False
    margin = points[candidate] - max((p for label, p in points.items() if label != candidate), default=0)
    return candidate, 0.5 + 0.5 * max(0, margin) / _EVIDENCE_MAX, True


def _walk_in_guess(
    turns: Sequence[Turn], words: Sequence[Word], name_variants: Sequence[str], params: RoleParams
) -> tuple[str, float, bool]:
    """(receptionist label, confidence, some speaker gave evidence) for a visitor at the desk."""
    order = list(dict.fromkeys(t.speaker_label for t in sorted(turns, key=lambda t: (t.start_ms, t.end_ms))))
    texts: dict[str, list[str]] = {label: [] for label in order}
    for label, text in _speaker_runs(turns, words, params.intro_window_ms):
        texts[label].append(text)
    names = [name for name in (normalise_text(v) for v in name_variants) if name]

    points: dict[str, int] = {}
    for label in order:
        text = normalise_text(" ".join(texts[label]))
        greets = any(_contains(text, g) for g in GREETINGS) or _contains(text, "welcome to")
        greets_with_name = greets and any(_contains(text, n) for n in names)
        phrases = sum(_contains(text, phrase) for phrase in DESK_PHRASES)
        points[label] = 2 * greets_with_name + min(phrases, _DESK_PHRASES_COUNTED)

    leader = _unique_leader({label: float(p) for label, p in points.items()})
    if leader is None:
        return order[0], 0.5, False
    margin = points[leader] - max((p for label, p in points.items() if label != leader), default=0)
    return leader, 0.5 + 0.5 * margin / _EVIDENCE_MAX, True


def _sales_guess(
    turns: Sequence[Turn], words: Sequence[Word], name_variants: Sequence[str], params: RoleParams
) -> tuple[str, float, bool]:
    """(sales rep label, confidence, the evidence agrees)."""
    order = list(dict.fromkeys(t.speaker_label for t in sorted(turns, key=lambda t: (t.start_ms, t.end_ms))))
    texts: dict[str, list[str]] = {label: [] for label in order}
    for label, text in _speaker_runs(turns, words, params.intro_window_ms):
        texts[label].append(text)
    names = [name for name in (normalise_text(v) for v in name_variants) if name]
    intros = [*SELF_INTRODUCTIONS, *SALES_INTRODUCTIONS]

    def introduces_company(label: str) -> bool:
        text = normalise_text(" ".join(texts[label]))
        if any(_contains(text, f"{name} se") or _contains(text, f"from {name}") for name in names):
            return True
        return any(_contains(text, n) for n in names) and any(_contains(text, phrase) for phrase in intros)

    introducing = {label: introduces_company(label) for label in order}
    candidate = next((label for label in order if introducing[label]), None)
    if candidate is None:
        return _teaching_guess(turns, params)

    talk = _talk_ms(turns)
    long_turns: dict[str, int] = dict.fromkeys(talk, 0)
    for turn in _joined_turns(turns, params.turn_join_gap_ms):
        if turn.duration_ms >= params.long_turn_ms:
            long_turns[turn.speaker_label] += 1
    share_leader = _unique_leader({label: float(ms) for label, ms in talk.items()})
    long_leader = _unique_leader({label: float(n) for label, n in long_turns.items()})
    points = {label: 2 * introducing[label] + (label == share_leader) + (label == long_leader) for label in order}
    margin = points[candidate] - max((p for label, p in points.items() if label != candidate), default=0)
    return candidate, 0.5 + 0.5 * max(0, margin) / _EVIDENCE_MAX, True


def _build(
    labels: Sequence[str], staff_label: str, roles: tuple[str, str], confidence: float, method: str
) -> dict[str, SpeakerRole]:
    staff_role, other_role = roles
    return {
        label: SpeakerRole(staff_role if label == staff_label else other_role, confidence, method) for label in labels
    }


def _check_tie_break(answer: RoleAssignment, heuristic: RoleAssignment, roles: tuple[str, str]) -> None:
    if set(answer.speakers) != set(heuristic.speakers):
        raise ValueError("tie-breaker must assign a role to exactly the diarized speakers")
    assigned = [speaker.role for speaker in answer.speakers.values()]
    if not set(assigned) <= set(roles):
        raise ValueError(f"tie-breaker used roles outside the rubric's {roles}")
    if assigned.count(roles[0]) != 1:
        raise ValueError(f"tie-breaker must name exactly one {roles[0]}")


def assign_roles(
    turns: Sequence[Turn],
    words: Sequence[Word],
    recording_type: str,
    rubric_roles: Sequence[str],
    *,
    tenant_name_variants: Sequence[str] = (),
    receptionist_channel_speaker: str | None = None,
    params: RoleParams = RoleParams(),  # noqa: B008  # frozen, so a shared default is safe
    tie_breaker: RoleTieBreaker | None = None,
) -> RoleAssignment:
    """Assign a role to every diarized speaker. See the module docstring for the rules.

    `rubric_roles` is (staff_role, other_role), as listed in the rubric file. Raises ValueError for an unknown
    recording type, bad rubric roles, or a channel hint that names no diarized speaker (or is given for teaching).
    No turns at all gives an empty assignment that needs review.
    """
    if recording_type not in RECORDING_TYPES:
        raise ValueError(f"recording_type must be one of {sorted(RECORDING_TYPES)}, got {recording_type!r}")
    roles = tuple(rubric_roles)
    if len(roles) != 2 or len(set(roles)) != 2 or not all(isinstance(r, str) and r.strip() for r in roles):
        raise ValueError(f"rubric_roles must be two different role names (staff, other), got {roles!r}")
    role_pair = (roles[0], roles[1])
    labels = sorted({turn.speaker_label for turn in turns})
    if receptionist_channel_speaker is not None:
        if recording_type != RECEPTION:
            raise ValueError("a receptionist channel hint applies only to reception recordings")
        if receptionist_channel_speaker not in labels:
            raise ValueError(f"channel hint names {receptionist_channel_speaker!r}, which is not a diarized speaker")
        return RoleAssignment(_build(labels, receptionist_channel_speaker, role_pair, 1.0, METHOD_CHANNEL))
    if not labels:
        return RoleAssignment({}, REASON_UNCLEAR_ROLES)

    if recording_type == TEACHING:
        staff, confidence, agree = _teaching_guess(turns, params)
    elif recording_type == SALES:
        staff, confidence, agree = _sales_guess(turns, words, tenant_name_variants, params)
    elif role_pair[1] == VISITOR:
        staff, confidence, agree = _walk_in_guess(turns, words, tenant_name_variants, params)
    else:
        staff, confidence, agree = _reception_guess(turns, words, tenant_name_variants, params)
    confidence = round(confidence, 3)
    if agree and confidence >= params.min_confidence:
        return RoleAssignment(_build(labels, staff, role_pair, confidence, METHOD_HEURISTIC))

    heuristic = RoleAssignment(
        _build(labels, staff, role_pair, confidence, METHOD_LOW_CONFIDENCE), REASON_UNCLEAR_ROLES
    )
    if tie_breaker is None:
        return heuristic
    request = TieBreakRequest(
        recording_type, role_pair, heuristic, tuple(_speaker_runs(turns, words, params.tie_break_window_ms))
    )
    answer = tie_breaker(request)
    if answer is None or answer.needs_review_reason is not None:
        return heuristic
    _check_tie_break(answer, heuristic, role_pair)
    if any(speaker.confidence < params.min_confidence for speaker in answer.speakers.values()):
        return heuristic
    return answer
