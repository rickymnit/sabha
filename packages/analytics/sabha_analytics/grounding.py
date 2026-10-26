"""Grounding verifier: every quote an LLM cites must exist in the transcript, at the time it claims (plan task P5.6).

Golden rule 5: an LLM judgement must cite quotes with timestamps, and each quote must be confirmed in the transcript
before a user sees it. This module is that check. It is pure (no I/O, no model calls).

Preparing a transcript (`prepare_transcript`):

- The transcript@v1 document is validated with sabha_asr.assembly.validate_transcript. All its times are on the
  ORIGINAL recording timeline (golden rule 4), so every time this module returns is too.
- Utterance ids: transcript@v1 utterances have no id field, so the id is the utterance's position in the list,
  "u" plus at least four digits ("u0000", "u0042", "u12345"). The list is sorted by start time and the artefact
  is immutable (stage outputs are written once), so the same transcript always yields the same ids. An id is only
  meaningful together with the transcript it came from; the report stores the transcript's SHA-256 for that reason.
- Each utterance's text is redacted with sabha_llm.redact (golden rule 8), utterance by utterance with `extend=`
  so placeholders are stable across the whole transcript ([STUDENT_1] is the same student everywhere). The model
  only ever sees the redacted text, so quotes are matched against the redacted text. Each utterance keeps its
  RedactionResult, so a matched range maps back exactly to the original wording (`matched_text_original`,
  `original_range`) for authorised users, without the report itself carrying any PII.

Normalisation (`normalise`), applied identically to quotes and transcript text:

1. Words are runs of letters, digits and Devanagari signs; placeholders such as [STUDENT_1] are one word, lower-cased.
   Everything else (punctuation, the danda, hyphens, extra spaces) separates words; apostrophes are dropped.
2. Unicode NFD, then: nukta removed (ढ़ and ढ compare equal), chandrabindu read as anusvara, Devanagari digits read
   as ASCII digits, lower case; then NFC.
3. Roman words without digits get the Hinglish spelling folds below (the same idea as eval/textnorm.py, which this
   package must not import; kept deliberately small): "chh" -> "ch", "chch" -> "ch", "ph" -> "f", "w" -> "v",
   "z" -> "j", "q" -> "k", "ee" -> "i", "oo" -> "u", any run of one repeated letter -> one letter, then the whole-
   word folds in `WORD_FOLDS` ("ham" -> "hum", "toh" -> "to", "nahin" -> "nahi", ...). English words are folded
   too; that is harmless because both sides are folded the same way and only similarity is measured.
   Devanagari is not transliterated: a quote must be in the script the transcript uses (the prompt says so).

Matching (`verify_quote`), and why not plain `partial_ratio`:

- `fuzz.partial_ratio(quote, utterance)` scores the best character-level substring of the longer string with the
  length of the shorter one. For a short quote against a long utterance it over-matches: windows may start or end
  mid-word, and a quote whose first words are real but whose remainder is invented can still find a high-scoring
  stretch. Instead we compare word windows: for every utterance, every window of consecutive words whose length is
  within `max(2, ceil(n / 5))` words of the quote's n words is scored with `fuzz.ratio` (normalised Indel
  similarity), which penalises any difference in length. The best window per utterance is kept.
- A quote must lie inside ONE utterance. A quote that runs across two utterances is not matched (the prompt tells
  the model to cite two quotes instead). Reasons: an utterance is one speaker's words, so a spanning quote could
  merge a teacher's and a student's words into one attributed line; and an utterance is the unit we can play back,
  because transcript@v1 has no word times.
- A quote needs at least `MIN_QUOTE_WORDS` (3) normalised words: one or two words ("koi doubt") occur everywhere and
  prove nothing.
- Verified iff the best window's ratio >= `MIN_RATIO` (0.90, golden rule 5) AND the matched utterance's time range
  [start_ms, end_ms] overlaps the claimed start time widened by `TIME_TOLERANCE_MS` (5 s) on both sides. If the
  phrase occurs several times, the occurrence at the claimed time wins (then the higher ratio, then the earlier).
- The result carries the CORRECTED times (the matched utterance's start and end from the transcript, never the
  model's claim) and the matched utterance id. The model's claimed utterance id is recorded but not required to
  match: the claimed time already pins the moment, and the corrected id is what the report stores. Nothing is
  silently fixed: an unverified quote stays unverified, and callers re-ask the model (see scoring.py).
- Times are utterance-level: transcript@v1 has no word times, so playback of a quote plays its whole utterance.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

from sabha_asr.assembly import validate_transcript
from sabha_llm.redact import DEFAULT_MASKED_ROLES, KnownName, RedactionMapping, RedactionResult, redact

MIN_RATIO = 0.90
"""Minimum normalised fuzzy ratio (golden rule 5)."""

TIME_TOLERANCE_MS = 5_000
"""How far the claimed time may lie outside the matched utterance."""

MIN_QUOTE_WORDS = 3
"""Fewest normalised words a quote may have."""

UTTERANCE_ID_PREFIX = "u"

NOT_FOUND = "not_found"
TIME_MISMATCH = "time_mismatch"
TOO_SHORT = "too_short"
FAILURE_REASONS: frozenset[str] = frozenset({NOT_FOUND, TIME_MISMATCH, TOO_SHORT})

# --- normalisation -------------------------------------------------------------------------------------------

_TOKEN = re.compile(r"\[[A-Za-z]{2,20}_[0-9]+\]|[\ẁ-ͯऀ-ॣ०-ॿ'‘’`]+")
_PLACEHOLDER_TOKEN = re.compile(r"\[[A-Za-z]{2,20}_[0-9]+\]")
_APOSTROPHES = str.maketrans("", "", "'‘’`")
_NUKTA = "़"
_CHANDRABINDU = "ँ"
_ANUSVARA = "ं"
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_ROMAN_WORD = re.compile(r"[a-z]+")
_LETTER_FOLDS = (
    ("chh", "ch"),
    ("chch", "ch"),
    ("ph", "f"),
    ("w", "v"),
    ("z", "j"),
    ("q", "k"),
    ("ee", "i"),
    ("oo", "u"),
)
_REPEATED_LETTER = re.compile(r"([a-z])\1+")

WORD_FOLDS: Mapping[str, str] = {
    "ham": "hum",  # हम
    "toh": "to",  # तो
    "nahin": "nahi",  # नहीं
    "nhi": "nahi",
    "kyon": "kyun",  # क्यों
    "kyu": "kyun",
    "ye": "yeh",  # यह / ये
    "voh": "vo",  # वो (after w -> v)
}
"""Whole-word folds applied after the letter folds (keys are already letter-folded). Keep this list short."""


def _fold_roman(word: str) -> str:
    for old, new in _LETTER_FOLDS:
        word = word.replace(old, new)
    word = _REPEATED_LETTER.sub(r"\1", word)
    return WORD_FOLDS.get(word, word)


def _normalise_token(raw: str) -> str:
    if _PLACEHOLDER_TOKEN.fullmatch(raw):
        return raw.lower()
    text = unicodedata.normalize("NFD", raw).translate(_APOSTROPHES)
    text = text.replace(_NUKTA, "").replace(_CHANDRABINDU, _ANUSVARA).translate(_DEVANAGARI_DIGITS)
    text = unicodedata.normalize("NFC", text).lower()
    if _ROMAN_WORD.fullmatch(text):
        text = _fold_roman(text)
    return text


@dataclass(frozen=True, slots=True)
class _Token:
    norm: str
    start: int  # [start, end) in the raw (redacted) text
    end: int


def _tokens(text: str) -> tuple[_Token, ...]:
    out = []
    for found in _TOKEN.finditer(text):
        norm = _normalise_token(found.group())
        if norm:
            out.append(_Token(norm, found.start(), found.end()))
    return tuple(out)


def normalise(text: str) -> str:
    """The normalised words of `text` joined by single spaces (see the module docstring)."""
    return " ".join(token.norm for token in _tokens(text))


# --- prepared transcript -------------------------------------------------------------------------------------


def utterance_id(index: int) -> str:
    """The id of the utterance at `index` in transcript@v1 `utterances`: "u0000", "u0042", "u12345"."""
    if index < 0:
        raise ValueError("utterance index must not be negative")
    return f"{UTTERANCE_ID_PREFIX}{index:04d}"


@dataclass(frozen=True, slots=True)
class PreparedUtterance:
    """One utterance as the model sees it: redacted text, id and original-timeline times."""

    id: str
    index: int
    role: str
    start_ms: int
    end_ms: int
    text: str
    """Redacted text: the only version of the words that goes into a prompt."""
    redaction: RedactionResult = field(repr=False, compare=False)
    tokens: tuple[_Token, ...] = field(repr=False, compare=False)
    norm_text: str = field(repr=False, compare=False)
    norm_offsets: tuple[tuple[int, int], ...] = field(repr=False, compare=False)
    """[start, end) of each token in `norm_text`."""
    speaker: str = ""
    """The diarizer's anonymous speaker label ("S1"); shown to the model only when the transcript says so."""


@dataclass(frozen=True, slots=True)
class PreparedTranscript:
    """A validated, redacted transcript with utterance ids, ready for prompts and quote verification."""

    utterances: tuple[PreparedUtterance, ...]
    mapping: RedactionMapping
    """Placeholders of the whole transcript and the values behind them. Holds PII: keep it server-side."""
    sha256: str
    """SHA-256 of the canonical JSON of the source transcript; utterance ids refer to that exact transcript."""
    asr_model: str
    show_speakers: bool = False
    """Meetings: every line is a "participant", so prompts also show the speaker label (owners of action items)."""
    _by_id: dict[str, PreparedUtterance] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_id", {u.id: u for u in self.utterances})

    def get(self, uid: str) -> PreparedUtterance | None:
        """The utterance with id `uid`, or None."""
        return self._by_id.get(uid)

    def render(self) -> str:
        """The redacted transcript for a prompt, one utterance per line:
        `[u0042 start_ms=310300 end_ms=314000 teacher] text`. Times stay as words apart ("start_ms=") so that no two
        numbers touch, which would look like a phone or Aadhaar number to the PII guard."""
        return "\n".join(
            f"[{u.id} start_ms={u.start_ms} end_ms={u.end_ms} {u.role}"
            f"{' ' + u.speaker if self.show_speakers and u.speaker else ''}] {' '.join(u.text.split())}"
            for u in self.utterances
        )


def _canonical_sha256(document: object) -> str:
    data = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def prepare_transcript(
    transcript: Mapping[str, Any],
    *,
    names: Iterable[KnownName] = (),
    masked_roles: Iterable[str] = DEFAULT_MASKED_ROLES,
    show_speakers: bool = False,
) -> PreparedTranscript:
    """Validate a transcript@v1 document, give each utterance its id and redact its text.

    `names` are the people the redactor should look for (students are masked by default, golden rules 8 and 10).
    Raises ValueError for an invalid transcript or redaction configuration.
    """
    document = dict(transcript)
    validate_transcript(document)
    names = tuple(names)
    roles = tuple(masked_roles)
    mapping: RedactionMapping | None = None
    prepared: list[PreparedUtterance] = []
    for index, utterance in enumerate(document["utterances"]):
        result = redact(utterance["text"], names=names, masked_roles=roles, extend=mapping)
        mapping = result.mapping
        tokens = _tokens(result.redacted_text)
        offsets = []
        cursor = 0
        for token in tokens:
            offsets.append((cursor, cursor + len(token.norm)))
            cursor += len(token.norm) + 1
        prepared.append(
            PreparedUtterance(
                id=utterance_id(index),
                index=index,
                role=utterance["role"],
                start_ms=utterance["start_ms"],
                end_ms=utterance["end_ms"],
                text=result.redacted_text,
                redaction=result,
                tokens=tokens,
                norm_text=" ".join(token.norm for token in tokens),
                norm_offsets=tuple(offsets),
                speaker=str(utterance.get("speaker_label") or ""),
            )
        )
    return PreparedTranscript(
        utterances=tuple(prepared),
        mapping=mapping if mapping is not None else RedactionMapping(),
        sha256=_canonical_sha256(document),
        asr_model=document["asr_model"],
        show_speakers=show_speakers,
    )


# --- verification --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GroundingResult:
    """The outcome of checking one quote. Times are the matched utterance's, on the ORIGINAL timeline.

    `utterance_id`, `start_ms`, `end_ms`, `matched_text` and `original_range` describe the best match: set when
    verified, and also for TIME_MISMATCH (so feedback can say where the quote really is); None for NOT_FOUND and
    TOO_SHORT. `matched_text_original` holds PII and is excluded from the repr; it is for authorised display only.
    """

    quote: str
    """The quote as the model wrote it (redacted text)."""
    claimed_start_ms: int
    claimed_utterance_id: str | None
    verified: bool
    reason: str | None
    """None when verified, else one of FAILURE_REASONS."""
    ratio: float
    """Best normalised ratio found, in [0, 1], rounded to 4 decimals (0.0 for TOO_SHORT)."""
    utterance_id: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    matched_text: str | None = None
    """The matched words exactly as in the redacted transcript."""
    original_range: tuple[int, int] | None = None
    """[start, end) of the match in the ORIGINAL (unredacted) utterance text, in code points."""
    matched_text_original: str | None = field(default=None, repr=False)

    @property
    def claimed_id_matches(self) -> bool:
        return self.claimed_utterance_id is not None and self.claimed_utterance_id == self.utterance_id


@dataclass(frozen=True, slots=True)
class _Candidate:
    utterance: PreparedUtterance
    score: float  # 0..100
    first: int  # token index
    length: int  # tokens


def _window_lengths(n: int, m: int) -> list[int]:
    slack = max(2, math.ceil(n / 5))
    lengths = [length for length in range(max(1, n - slack), n + slack + 1) if length <= m]
    if not lengths:
        lengths = [m]  # the utterance is shorter than any window: compare with all of it
    return sorted(lengths, key=lambda length: (abs(length - n), length))


def _best_window(query: str, n: int, utterance: PreparedUtterance) -> _Candidate | None:
    m = len(utterance.tokens)
    if m == 0:
        return None
    offsets = utterance.norm_offsets
    text = utterance.norm_text
    best: _Candidate | None = None
    best_score = 0.0
    for length in _window_lengths(n, m):
        for first in range(m - length + 1):
            window = text[offsets[first][0] : offsets[first + length - 1][1]]
            score = fuzz.ratio(query, window, score_cutoff=best_score)
            if score > best_score or best is None:
                best_score = score
                best = _Candidate(utterance, score, first, length)
    return best


def _distance_ms(utterance: PreparedUtterance, claimed: int) -> int:
    if utterance.start_ms <= claimed <= utterance.end_ms:
        return 0
    return min(abs(claimed - utterance.start_ms), abs(claimed - utterance.end_ms))


def verify_quote(
    transcript: PreparedTranscript,
    quote: str,
    *,
    start_ms: int,
    utterance_id: str | None = None,
    min_ratio: float = MIN_RATIO,
    tolerance_ms: int = TIME_TOLERANCE_MS,
) -> GroundingResult:
    """Check that `quote` occurs in one utterance of `transcript` near the claimed `start_ms`.

    `utterance_id` is the id the model cited; it is recorded, not required to match (see the module docstring).
    """
    words = _tokens(quote)
    if len(words) < MIN_QUOTE_WORDS:
        return GroundingResult(quote, start_ms, utterance_id, verified=False, reason=TOO_SHORT, ratio=0.0)
    query = " ".join(token.norm for token in words)
    best_any = 0.0
    candidates: list[_Candidate] = []
    for utterance in transcript.utterances:
        found = _best_window(query, len(words), utterance)
        if found is None:
            continue
        best_any = max(best_any, found.score)
        if found.score / 100 >= min_ratio:
            candidates.append(found)
    if not candidates:
        return GroundingResult(
            quote, start_ms, utterance_id, verified=False, reason=NOT_FOUND, ratio=round(best_any / 100, 4)
        )

    def in_time(candidate: _Candidate) -> bool:
        u = candidate.utterance
        return u.start_ms - tolerance_ms <= start_ms <= u.end_ms + tolerance_ms

    def rank(candidate: _Candidate) -> tuple[float, int, int]:
        return (-candidate.score, _distance_ms(candidate.utterance, start_ms), candidate.utterance.index)

    timely = [candidate for candidate in candidates if in_time(candidate)]
    chosen = min(timely or candidates, key=rank)
    u = chosen.utterance
    raw_start = u.tokens[chosen.first].start
    raw_end = u.tokens[chosen.first + chosen.length - 1].end
    original_range = u.redaction.to_original_range(raw_start, raw_end)
    return GroundingResult(
        quote,
        start_ms,
        utterance_id,
        verified=bool(timely),
        reason=None if timely else TIME_MISMATCH,
        ratio=round(chosen.score / 100, 4),
        utterance_id=u.id,
        start_ms=u.start_ms,
        end_ms=u.end_ms,
        matched_text=u.text[raw_start:raw_end],
        original_range=original_range,
        matched_text_original=u.redaction.original_text[original_range[0] : original_range[1]],
    )
