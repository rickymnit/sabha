"""Computed metrics: deterministic numbers from a transcript and the segment map (plan task P5.5).

Golden rule 5: talk share, question counts, pace, silence and monologue length are computed here, in code. No LLM
is involved and none of these numbers may come from one. Every metric carries a unit and a short definition for the
UI tooltip. All times are on the ORIGINAL recording timeline (golden rule 4): utterance times come from
transcript@v1 (sabha_asr.assembly) and silence from the segment map (sabha_core.timemap).

Inputs: a transcript@v1 document, the rubric's roles with the primary role (the staff member analysed: teacher,
receptionist; rubric files list it first), the segment map and its `timemap.stats`.

Metric keys (the naming scheme):

- `{role}_talk_share`, `{role}_turn_count`, `{role}_question_count` for every rubric role, so the rubric names
  teacher_talk_share, receptionist_talk_share, caller_talk_share and teacher_question_count are computed directly.
- Unprefixed speech metrics are about the primary role: `open_question_count`, `open_question_ratio`,
  `words_per_minute`, `longest_monologue_s` (with `longest_monologue_start_ms` and `longest_monologue_end_ms`).
- Recording metrics: `duration_s`, `silence_share`, `longest_silence_s`, `long_silence_count`.
- RUBRIC_KEY_ALIASES maps a rubric's own name to a key above (`call_duration_s` -> `duration_s`);
  `select_metrics` returns metrics under the rubric's names.

Golden rule 10: other roles get counts and shares per ROLE only ("students" is one group role). Speaker labels are
never read, so no number can be attributed to an individual student or caller.

Rules (first choices, to be checked against annotated recordings; none of them is a measured quality figure):

- Talk time of a role is the union of its utterance intervals [start_ms, end_ms), so two speakers of one role
  talking at once count once. Overlapping speech of DIFFERENT roles counts in full for each role. A role's talk
  share is its talk time divided by the talk time of all roles added together, so shares add up to 1. Talk time
  includes short pauses inside an utterance (assembly never lets an utterance span a removed silence of 1.5 s or
  more), and is measured from utterances, not from VAD speech.
- Turns: utterances in transcript order (sorted by start). A turn is a run of consecutive utterances of one role in
  which each next utterance starts less than TURN_GAP_MS (3 s) after the run's latest end. Any utterance of another
  role ends the turn, including a short overlapping backchannel ("haan ji"); this can only understate a monologue,
  never overstate it. 3 s is about the "wait time" after which a pause leaves the floor open to others; at or over
  it, the next utterance starts a new turn. A turn lasts from its first start to its latest end, pauses included.
- Longest monologue: the longest turn of the primary role; ties go to the earlier turn. None if the role never
  speaks.
- Questions are counted per sentence. Sentences end at . ? ! or the danda (। ॥) followed by whitespace; ASR text
  without punctuation is one sentence per utterance, so at most one question per utterance is counted there. A
  sentence is a question when:
  1. its closing punctuation contains "?" (this covers the tags "right?" and "na?"); otherwise
  2. its closing punctuation contains "!" -> not a question ("Kya baat hai!"); otherwise
  3. it contains a Hindi/Hinglish question word as a whole word (QUESTION_WORDS: kya, kyun, kaise, kaun, kab,
     kahan, kitna and spelling variants, and their Devanagari forms) or phrase (QUESTION_PHRASES: "samajh aaya",
     "समझ आया"), or its first word is an English wh-word (what, why, how, who, when, where, which).
  Words are matched whole after case folding and removing punctuation at word edges, so "kyaari", "kabhi",
  "kahani" and "क्योंकि" (because) do not match. "right" and "na" without "?" never count: both are far too common
  in statements.
  Known false positives: "kya"/"kaise"/"kab" inside a statement ("dekho maine kya likha", "main dikhata hoon kaise
  karte hain"), "kya baat hai" without "!", the greeting "aap kaise ho", and sentences starting with a subordinate
  "When ..."/"How ..." in English. Known false negatives: yes/no questions with no "?" and no question word
  ("tum ready ho", "is it clear"), and question words not in the list ("kis", "konsa").
- Open vs recall: a question is open when it contains an open marker: why, how (but not "how many"/"how much"),
  explain, kyun/kyon/kyu/kyoon, kaise, samjhao, "what if", "kya hoga", or the Devanagari क्यों, कैसे, समझाओ,
  "क्या होगा". Every other question is recall, including yes/no checks such as "samajh aaya?". open_question_ratio
  is open / all primary-role questions, and None (not 0) when there are no questions.
- Words per minute: whitespace-separated words of the primary role's utterances divided by its talk time in
  minutes; None when it never speaks.
- Silence: silence_share and longest_silence_s come from `timemap.stats`; the longest silence includes silence
  before the first and after the last speech. long_silence_count counts gaps BETWEEN consecutive segments longer
  than LONG_SILENCE_MS (strictly over 5 s); silence before the first or after the last speech is not a pause.
  Segment gaps are VAD silences after its end padding, so a gap can be up to 300 ms shorter than the raw silence.
- Rounding: shares and ratios to 4 decimals, words per minute to 1 decimal; seconds are milliseconds / 1000.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, TypedDict

from sabha_asr.assembly import validate_transcript
from sabha_core.timemap import SegmentMap, SegmentStats, stats

TURN_GAP_MS = 3000
"""Utterances of one role less than this far apart (after the turn's latest end) belong to the same turn."""

LONG_SILENCE_MS = 5000
HOLD_GAP_MS = 10_000
"""A gap longer than this between stretches of speech counts as a hold (P5.8: reception holds or silences)."""
"""A gap between segments strictly longer than this is a long silence (P5.5: long pauses > 5 s)."""

RUBRIC_KEY_ALIASES: Mapping[str, str] = MappingProxyType(
    {"call_duration_s": "duration_s", "handle_time_s": "duration_s"}
)
"""Rubric metric names that are another name for a computed key."""

ROLE_METRIC_SUFFIXES = ("talk_share", "turn_count", "question_count")
"""Per-role keys are f"{role}_{suffix}"."""

RECORDING_METRIC_KEYS = ("duration_s", "silence_share", "longest_silence_s", "long_silence_count", "hold_gap_count")
PRIMARY_METRIC_KEYS = (
    "open_question_count",
    "open_question_ratio",
    "words_per_minute",
    "longest_monologue_s",
    "longest_monologue_start_ms",
    "longest_monologue_end_ms",
)

# Question words, matched as whole words after case folding (NFC). Devanagari forms include common spellings with
# anusvara (ं) and chandrabindu (ँ).
QUESTION_WORDS = frozenset(
    {
        "kya",
        "kyun",
        "kyon",
        "kyu",
        "kyoon",
        "kaise",
        "kaun",
        "kab",
        "kahan",
        "kahaan",
        "kitna",
        "kitne",
        "kitni",
        "क्या",
        "क्यों",
        "क्यूं",
        "क्यूँ",
        "कैसे",
        "कौन",
        "कब",
        "कहाँ",
        "कहां",
        "कितना",
        "कितने",
        "कितनी",
    }
)
QUESTION_PHRASES: tuple[tuple[str, ...], ...] = (
    ("samajh", "aaya"),
    ("samajh", "aa", "gaya"),
    ("समझ", "आया"),
    ("समझ", "आ", "गया"),
)
ENGLISH_WH_WORDS = frozenset({"what", "why", "how", "who", "when", "where", "which"})
"""Count as a question marker only as the FIRST word of a sentence ("This is how we add." is not a question)."""

OPEN_WORDS = frozenset(
    {"why", "explain", "kyun", "kyon", "kyu", "kyoon", "kaise", "samjhao", "samjhaao", "क्यों", "क्यूं", "क्यूँ", "कैसे", "समझाओ"}
)
OPEN_PHRASES: tuple[tuple[str, ...], ...] = (("what", "if"), ("kya", "hoga"), ("क्या", "होगा"))
HOW_RECALL_FOLLOWERS = frozenset({"many", "much"})
""""how many" and "how much" ask for a count or amount: recall, not open."""

_DANDA = "।"
_DOUBLE_DANDA = "॥"
_SENTENCE_BREAK = re.compile(rf"(?<=[.?!{_DANDA}{_DOUBLE_DANDA}])\s+")
_EDGE_PUNCTUATION = "".join(
    (
        "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~",
        _DANDA,
        _DOUBLE_DANDA,
        "…",  # horizontal ellipsis
        "‘’“”",  # curly quotes
    )
)
_ROLE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class MetricRecord(TypedDict):
    key: str
    value: int | float | None
    unit: str
    definition: str


@dataclass(frozen=True, slots=True)
class Metric:
    """One computed number with its unit and a short definition for the UI tooltip."""

    key: str
    value: int | float | None
    unit: str
    definition: str

    def to_record(self) -> MetricRecord:
        return {"key": self.key, "value": self.value, "unit": self.unit, "definition": self.definition}


@dataclass(frozen=True, slots=True)
class Turn:
    """A run of one role's utterances; times are on the original timeline, half-open [start_ms, end_ms)."""

    role: str
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


# --- questions -------------------------------------------------------------------------------------------------


def split_sentences(text: str) -> tuple[str, ...]:
    """Split at . ? ! । ॥ followed by whitespace; the terminator stays with its sentence."""
    return tuple(part for part in _SENTENCE_BREAK.split(text.strip()) if part)


def _tokens(sentence: str) -> tuple[str, ...]:
    folded = unicodedata.normalize("NFC", sentence).casefold()
    return tuple(token for raw in folded.split() if (token := raw.strip(_EDGE_PUNCTUATION)))


def _closing_punctuation(sentence: str) -> str:
    stripped = sentence.rstrip()
    return stripped[len(stripped.rstrip(_EDGE_PUNCTUATION)) :]


def _has_phrase(tokens: Sequence[str], phrases: Iterable[tuple[str, ...]]) -> bool:
    return any(
        tuple(tokens[index : index + len(phrase)]) == phrase
        for phrase in phrases
        for index in range(len(tokens) - len(phrase) + 1)
    )


def is_question(sentence: str) -> bool:
    """Whether one sentence counts as a question. See the module docstring for the rules and their limits."""
    closing = _closing_punctuation(sentence)
    if "?" in closing:
        return True
    if "!" in closing:
        return False
    tokens = _tokens(sentence)
    if not tokens:
        return False
    return (
        any(token in QUESTION_WORDS for token in tokens)
        or _has_phrase(tokens, QUESTION_PHRASES)
        or tokens[0] in ENGLISH_WH_WORDS
    )


def is_open_question(sentence: str) -> bool:
    """Whether a question is open (why, how, explain, predict) rather than recall. Call only for questions."""
    tokens = _tokens(sentence)
    for index, token in enumerate(tokens):
        if token in OPEN_WORDS:
            return True
        if token == "how" and (index + 1 >= len(tokens) or tokens[index + 1] not in HOW_RECALL_FOLLOWERS):  # noqa: S105  # a word, not a secret
            return True
    return _has_phrase(tokens, OPEN_PHRASES)


def count_questions(text: str) -> tuple[int, int]:
    """(questions, open questions) in one utterance's text, counted per sentence."""
    questions = [sentence for sentence in split_sentences(text) if is_question(sentence)]
    return len(questions), sum(1 for sentence in questions if is_open_question(sentence))


# --- turns and time --------------------------------------------------------------------------------------------


def role_turns(utterances: Iterable[Mapping[str, Any]], gap_ms: int = TURN_GAP_MS) -> tuple[Turn, ...]:
    """Group utterances (sorted by start, as in transcript@v1) into turns. See the module docstring."""
    turns: list[Turn] = []
    for utterance in utterances:
        role, start, end = utterance["role"], utterance["start_ms"], utterance["end_ms"]
        if turns and turns[-1].role == role and start - turns[-1].end_ms < gap_ms:
            turns[-1] = Turn(role, turns[-1].start_ms, max(turns[-1].end_ms, end))
        else:
            turns.append(Turn(role, start, end))
    return tuple(turns)


def _union_ms(intervals: Iterable[tuple[int, int]]) -> int:
    total = 0
    current: tuple[int, int] | None = None
    for start, end in sorted(intervals):
        if current is not None and start <= current[1]:
            current = (current[0], max(current[1], end))
            continue
        if current is not None:
            total += current[1] - current[0]
        current = (start, end)
    if current is not None:
        total += current[1] - current[0]
    return total


def _ratio(numerator: float, denominator: float, places: int = 4) -> float | None:
    return round(numerator / denominator, places) if denominator else None


# --- metric keys -----------------------------------------------------------------------------------------------


def available_metric_keys(roles: Iterable[str]) -> frozenset[str]:
    """Every key compute_metrics produces for these roles, plus the rubric aliases."""
    role_keys = {f"{role}_{suffix}" for role in roles for suffix in ROLE_METRIC_SUFFIXES}
    return frozenset({*RECORDING_METRIC_KEYS, *PRIMARY_METRIC_KEYS, *role_keys, *RUBRIC_KEY_ALIASES})


def select_metrics(metrics: Iterable[Metric], keys: Iterable[str]) -> tuple[Metric, ...]:
    """The metrics a rubric lists, in its order and under its names (aliases resolved). KeyError if one is missing."""
    by_key = {metric.key: metric for metric in metrics}
    selected = []
    for key in keys:
        source = RUBRIC_KEY_ALIASES.get(key, key)
        if source not in by_key:
            raise KeyError(f"no computed metric {key!r}")
        selected.append(replace(by_key[source], key=key))
    return tuple(selected)


# --- compute ---------------------------------------------------------------------------------------------------


def _resolve_roles(primary_role: str, roles: Sequence[str] | None, transcript_roles: Sequence[str]) -> tuple[str, ...]:
    if roles is None:
        resolved = tuple(dict.fromkeys((primary_role, *transcript_roles)))
    else:
        resolved = tuple(roles)
        if len(set(resolved)) != len(resolved):
            raise ValueError(f"roles must be unique: {resolved}")
    if primary_role not in resolved:
        raise ValueError(f"primary role {primary_role!r} is not one of the roles {resolved}")
    for role in resolved:
        if not _ROLE_NAME.fullmatch(role):
            raise ValueError(f"role {role!r} must be snake_case (it becomes part of metric keys)")
    unknown = sorted(set(transcript_roles) - set(resolved))
    if unknown:
        raise ValueError(f"transcript has roles {unknown} that are not among the rubric roles {resolved}")
    return resolved


def compute_metrics(
    transcript: Mapping[str, Any],
    *,
    primary_role: str,
    segment_map: SegmentMap,
    segment_stats: SegmentStats,
    roles: Sequence[str] | None = None,
) -> tuple[Metric, ...]:
    """All metrics for one recording, in a stable order. Raises ValueError on inconsistent input.

    `roles` are the rubric roles (primary first); per-role metrics are produced for each, even a role that never
    speaks. Without `roles`, the primary role and the roles in the transcript (in order of first appearance) are
    used. `segment_stats` must be `timemap.stats(segment_map, total_ms)` for the same recording.
    """
    validate_transcript(transcript)
    utterances: list[Mapping[str, Any]] = list(transcript["utterances"])
    resolved = _resolve_roles(primary_role, roles, [u["role"] for u in utterances])

    total_ms = segment_stats["total_ms"]
    if dict(segment_stats) != dict(stats(segment_map, total_ms)):
        raise ValueError("segment stats do not match the segment map: compute them with timemap.stats(map, total_ms)")
    late = [u for u in utterances if u["end_ms"] > total_ms]
    if late:
        raise ValueError(f"an utterance ends at {late[0]['end_ms']} ms, after the end of the recording ({total_ms} ms)")

    talk_ms = {
        role: _union_ms((u["start_ms"], u["end_ms"]) for u in utterances if u["role"] == role) for role in resolved
    }
    all_talk_ms = sum(talk_ms.values())
    turns = role_turns(utterances)
    question_counts = {role: [0, 0] for role in resolved}
    for u in utterances:
        questions, open_questions = count_questions(u["text"])
        question_counts[u["role"]][0] += questions
        question_counts[u["role"]][1] += open_questions

    gaps = [
        later.orig_start_ms - earlier.orig_end_ms
        for earlier, later in zip(segment_map.segments, segment_map.segments[1:], strict=False)
    ]
    metrics = [
        Metric("duration_s", total_ms / 1000, "s", "Length of the whole recording."),
        Metric(
            "silence_share",
            _ratio(segment_stats["silence_ms"], total_ms),
            "ratio",
            "Share of the recording with no speech detected, including before the first and after the last words.",
        ),
        Metric(
            "longest_silence_s",
            segment_stats["longest_silence_ms"] / 1000,
            "s",
            "Longest stretch with no speech detected, including before the first and after the last words.",
        ),
        Metric(
            "long_silence_count",
            sum(1 for gap in gaps if gap > LONG_SILENCE_MS),
            "count",
            f"Number of gaps with no speech longer than {LONG_SILENCE_MS // 1000} s between stretches of speech.",
        ),
        Metric(
            "hold_gap_count",
            sum(1 for gap in gaps if gap > HOLD_GAP_MS),
            "count",
            f"Number of holds: gaps with no speech longer than {HOLD_GAP_MS // 1000} s between stretches of speech.",
        ),
    ]
    for role in resolved:
        metrics += [
            Metric(
                f"{role}_talk_share",
                _ratio(talk_ms[role], all_talk_ms),
                "ratio",
                f"Share of all speaking time spoken by the {role} role; overlapping speech counts for each role.",
            ),
            Metric(
                f"{role}_turn_count",
                sum(1 for turn in turns if turn.role == role),
                "count",
                f"Number of turns by the {role} role; pauses under {TURN_GAP_MS // 1000} s do not end a turn.",
            ),
            Metric(
                f"{role}_question_count",
                question_counts[role][0],
                "count",
                f"Questions asked by the {role} role: sentences ending in '?' or using a question word such as kya, "
                "kyun or kaise.",
            ),
        ]

    primary_questions, primary_open = question_counts[primary_role]
    primary_words = sum(len(u["text"].split()) for u in utterances if u["role"] == primary_role)
    primary_talk_ms = talk_ms[primary_role]
    monologue: Turn | None = None
    for turn in turns:
        if turn.role == primary_role and (monologue is None or turn.duration_ms > monologue.duration_ms):
            monologue = turn
    metrics += [
        Metric(
            "open_question_count",
            primary_open,
            "count",
            "Questions by the person analysed that ask why or how, or ask to explain or predict.",
        ),
        Metric(
            "open_question_ratio",
            _ratio(primary_open, primary_questions),
            "ratio",
            "Share of the questions by the person analysed that are open (why, how, explain, what if).",
        ),
        Metric(
            "words_per_minute",
            None if not primary_talk_ms else round(primary_words * 60_000 / primary_talk_ms, 1),
            "words/min",
            "Speaking pace of the person analysed: words spoken per minute of their speaking time.",
        ),
        Metric(
            "longest_monologue_s",
            None if monologue is None else monologue.duration_ms / 1000,
            "s",
            f"Longest turn by the person analysed without anyone else speaking; pauses under {TURN_GAP_MS // 1000} s "
            "are included.",
        ),
        Metric(
            "longest_monologue_start_ms",
            None if monologue is None else monologue.start_ms,
            "ms",
            "Where the longest turn by the person analysed starts in the recording.",
        ),
        Metric(
            "longest_monologue_end_ms",
            None if monologue is None else monologue.end_ms,
            "ms",
            "Where the longest turn by the person analysed ends in the recording.",
        ),
    ]
    return tuple(metrics)
