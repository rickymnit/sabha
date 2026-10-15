"""PII redaction applied to text before it reaches any LLM provider (golden rule 8).

`redact(text, names=..., masked_roles=...)` masks Indian mobile numbers, Aadhaar-like and PAN-like numbers, emails
and caller-supplied names, and returns a `RedactionResult`:

- `redacted_text` is the only thing that may be sent to a provider.
- `mapping` (a `RedactionMapping`) says which original value each placeholder stands for. It holds PII, so it stays
  on our servers; `unredact(text, mapping)` puts the values back into provider output for authorised users.
- `spans` record each masked value's offsets in both texts. Grounding (P5.6) matches quotes against the redacted
  text and maps the match back with `to_original_range` / `restore`, which are exact even when one value was
  written in several ways (for example "98765 43210" and "+91 9876543210" share [PHONE_1]).

Placeholders are stable within one document: the same value always gets the same placeholder, numbered by first
appearance per kind ([PHONE_1], [PHONE_2], [AADHAAR_1], [PAN_1], [EMAIL_1], [STUDENT_1]). To keep them stable
across several texts of one document (for example a transcript split into chunks), pass the previous mapping as
`extend=`. Phones compare by their 10-digit number, Aadhaar by its 12 digits, PAN and email case-insensitively
(a spoken "riya at the rate gmail dot com" equals "riya@gmail.com"), names by the `KnownName` they belong to.

What is matched (on a copy of the text in which every Unicode decimal digit, Devanagari included, is read as ASCII):

- PHONE: a 10-digit mobile starting 6-9, optionally prefixed by +91, 91 or 0. A single space, no-break space or
  hyphen may separate any two digits, so "98765 43210", "987-654-3210" and a number read out digit by digit all
  match. The match may not touch another digit, so 10-digit numbers starting 1-5 and longer digit runs are left.
- AADHAAR: 12 digits in groups of 4 (optionally separated), first digit 2-9. A contiguous 91 + mobile is a PHONE.
- PAN: five letters, four digits, one letter, contiguous in any case; spaced or hyphenated only in upper case, so
  ordinary words ("after 2026 a") never match.
- EMAIL: a written address, or a spoken one ("x at the rate y dot com", "x at y dot co dot in").
- Names: each `KnownName` whose role is in `masked_roles` (default: STUDENT only, so staff names stay readable),
  as whole words, ignoring case and runs of whitespace. Roman and Devanagari spellings are separate aliases.

Overlaps resolve to the longest match; on a tie EMAIL > AADHAAR > PHONE > PAN > masked name > unmasked name. A
listed name whose role is not masked still takes part, so a staff name "Riya Sharma" is kept whole even if a
student is called "Riya". Known false positives, accepted because a miss is a leak: three 4-digit numbers in a
row ("2024 2025 2026") read as an Aadhaar number, and ten single digits in a row read as a phone number.

Decision (P5.2): this module uses `re`, not Microsoft Presidio. presidio-analyzer requires spaCy (with thinc,
blis, numpy and friends), tldextract and phonenumbers even when only pattern recognisers are used, and its
default NLP engine loads (and offers to download) en_core_web_lg. None of that helps here: every recogniser
above is a pattern or a deny-list that we would write ourselves anyway, Presidio's anonymizer has no stable
per-document numbering, and its default email recogniser may fetch the public-suffix list over the network.
Plain `re` adds no dependency and keeps memory flat. Presidio stays an option if we later want NER for names
nobody listed. The recognisers are compiled at import and every configuration error raises; nothing is skipped
quietly.
"""

from __future__ import annotations

import re
import unicodedata
from bisect import bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

PHONE = "PHONE"
AADHAAR = "AADHAAR"
PAN = "PAN"
EMAIL = "EMAIL"
PATTERN_KINDS: frozenset[str] = frozenset({PHONE, AADHAAR, PAN, EMAIL})
"""Kinds found by pattern; they cannot be used as name roles."""

STUDENT = "STUDENT"
STAFF = "STAFF"
DEFAULT_MASKED_ROLES: frozenset[str] = frozenset({STUDENT})
"""Name roles masked unless the caller says otherwise. Staff are analysed by name; students never are (rule 10)."""

_ROLE = re.compile(r"[A-Z]{2,20}")
_PLACEHOLDER = re.compile(r"\[([A-Z]{2,20})_([1-9][0-9]*)\]")
_PLACEHOLDER_SHAPE = re.compile(r"\[[A-Z]{2,20}_[0-9]+\]")

# --- pattern recognisers (run on the digit-normalised copy) --------------------------------------------------

_SEP = r"[ \u00a0-]?"
_MOBILE = rf"[6-9](?:{_SEP}[0-9]){{9}}"
_PHONE_RE = re.compile(rf"(?<![0-9])(?:\+91{_SEP}|91{_SEP}|0{_SEP})?{_MOBILE}(?![0-9])")
_NOT_91_MOBILE = r"(?!91[6-9][0-9]{9}(?![0-9]))"  # a contiguous 91 + mobile is a PHONE
_AADHAAR_RE = re.compile(rf"(?<![0-9]){_NOT_91_MOBILE}[2-9][0-9]{{3}}{_SEP}[0-9]{{4}}{_SEP}[0-9]{{4}}(?![0-9])")
_PAN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{5}[0-9]{4}[A-Za-z](?![A-Za-z0-9])")
_PAN_SPACED_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{5}[ -]?[0-9]{4}[ -]?[A-Z](?![A-Za-z0-9])")
_EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?![A-Za-z0-9-])")
_SPOKEN_PART = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_SPOKEN_EMAIL_RE = re.compile(
    rf"(?<![A-Za-z0-9._-])(?P<local>{_SPOKEN_PART}(?:\s+dot\s+{_SPOKEN_PART})*)"
    r"\s+(?:at\s+the\s+rate(?:\s+of)?|at)\s+"
    r"(?P<domain>[A-Za-z0-9][A-Za-z0-9-]*(?:\s+dot\s+[A-Za-z0-9][A-Za-z0-9-]*)*?)"
    r"\s+dot\s+(?P<tld>com|in|org|net|edu|(?:co|ac|org|edu|gov|net)\s+dot\s+in)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_SPOKEN_DOT = re.compile(r"\s+dot\s+", re.IGNORECASE)
_NAME_CHAR = r"[\w\u0900-\u097F]"  # Devanagari vowel signs and virama are not \w, but are part of a word

# Tie-break order for matches of equal length (lower wins).
_RANK = {EMAIL: 0, AADHAAR: 1, PHONE: 2, PAN: 3}
_RANK_MASKED_NAME = 4
_RANK_KEPT_NAME = 5


class _AsciiDigits(dict[int, str]):
    """str.translate table mapping every Unicode decimal digit to its ASCII digit; one character stays one."""

    def __missing__(self, codepoint: int) -> str:
        digit = unicodedata.decimal(chr(codepoint), None)
        if digit is None:
            raise LookupError(codepoint)  # str.translate leaves the character unchanged
        self[codepoint] = str(digit)
        return self[codepoint]


_ASCII_DIGITS = _AsciiDigits()


def _digits(value: str) -> str:
    return "".join(ch for ch in value if "0" <= ch <= "9")


def _check_role(role: object, what: str) -> str:
    if not isinstance(role, str) or not _ROLE.fullmatch(role):
        raise ValueError(f"{what} must be 2-20 upper-case letters A-Z, such as {STUDENT!r}")
    if role in PATTERN_KINDS:
        raise ValueError(f"{what} {role!r} is reserved for a pattern recogniser")
    return role


# --- configuration -------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class KnownName:
    """A person's name to look for. `role` becomes the placeholder word ([STUDENT_1]); aliases share it.

    The repr shows the role only, because names are PII.
    """

    text: str = field(repr=False)
    role: str
    aliases: tuple[str, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        _check_role(self.role, "name role")
        aliases = tuple(self.aliases)  # accept any iterable, never keep a caller's list
        for spelling in (self.text, *aliases):
            if not isinstance(spelling, str) or len(spelling.strip()) < 2:
                raise ValueError(f"a {self.role} name or alias must have at least 2 characters")
            if "[" in spelling or "]" in spelling:
                raise ValueError(f"a {self.role} name or alias cannot contain '[' or ']'")
        object.__setattr__(self, "aliases", aliases)

    @property
    def spellings(self) -> tuple[str, ...]:
        return (self.text, *self.aliases)


def _fold(name: str) -> str:
    return " ".join(name.split()).lower()


# --- mapping -------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MappingEntry:
    """One placeholder: its kind, the normalised value it was matched by, and the value as first written."""

    placeholder: str
    kind: str
    key: str = field(repr=False)
    value: str = field(repr=False)


_RECORD_KEYS = frozenset({"placeholder", "kind", "key", "value"})


@dataclass(frozen=True, slots=True)
class RedactionMapping:
    """Placeholders of one document and the original values behind them. Holds PII: keep it server-side.

    The repr lists placeholders only.
    """

    entries: tuple[MappingEntry, ...] = ()
    _by_placeholder: dict[str, MappingEntry] = field(init=False, repr=False, compare=False)
    _by_key: dict[tuple[str, str], str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        entries = tuple(self.entries)
        by_placeholder: dict[str, MappingEntry] = {}
        by_key: dict[tuple[str, str], str] = {}
        for entry in entries:
            if not isinstance(entry, MappingEntry):
                raise ValueError("mapping entries must be MappingEntry objects")
            parsed = _PLACEHOLDER.fullmatch(entry.placeholder)
            if parsed is None or parsed.group(1) != entry.kind:
                raise ValueError(f"placeholder {entry.placeholder!r} does not match kind {entry.kind!r}")
            if entry.placeholder in by_placeholder or (entry.kind, entry.key) in by_key:
                raise ValueError(f"placeholder {entry.placeholder!r} or its value appears twice")
            by_placeholder[entry.placeholder] = entry
            by_key[(entry.kind, entry.key)] = entry.placeholder
        object.__setattr__(self, "entries", entries)
        object.__setattr__(self, "_by_placeholder", by_placeholder)
        object.__setattr__(self, "_by_key", by_key)

    def __repr__(self) -> str:
        return f"RedactionMapping(placeholders={self.placeholders()!r})"

    def __contains__(self, placeholder: object) -> bool:
        return placeholder in self._by_placeholder

    def placeholders(self) -> tuple[str, ...]:
        """All placeholders, in the order they were created."""
        return tuple(entry.placeholder for entry in self.entries)

    def value(self, placeholder: str) -> str:
        """The original value as first written. Raises KeyError for an unknown placeholder."""
        return self._by_placeholder[placeholder].value

    def to_records(self) -> list[dict[str, str]]:
        """Plain dicts for server-side storage: [{placeholder, kind, key, value}, ...]."""
        return [{"placeholder": e.placeholder, "kind": e.kind, "key": e.key, "value": e.value} for e in self.entries]

    @classmethod
    def from_records(cls, records: Iterable[object]) -> RedactionMapping:
        """Rebuild and validate a mapping from `to_records` output. Raises ValueError on any problem."""
        entries = []
        for index, record in enumerate(records):
            if not isinstance(record, Mapping) or set(record) != _RECORD_KEYS:
                raise ValueError(f"mapping record {index} must have exactly the keys {', '.join(sorted(_RECORD_KEYS))}")
            values = [record[name] for name in ("placeholder", "kind", "key", "value")]
            if not all(isinstance(value, str) for value in values):
                raise ValueError(f"mapping record {index} values must be strings")
            entries.append(MappingEntry(*values))
        return cls(tuple(entries))

    def _with(self, kind: str, key: str, value: str) -> tuple[RedactionMapping, str]:
        """This mapping plus (kind, key) if new, and the placeholder for it."""
        existing = self._by_key.get((kind, key))
        if existing is not None:
            return self, existing
        number = 1 + sum(1 for entry in self.entries if entry.kind == kind)
        placeholder = f"[{kind}_{number}]"
        return RedactionMapping((*self.entries, MappingEntry(placeholder, kind, key, value))), placeholder


# --- result --------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RedactedSpan:
    """One masked value: [original_start, original_end) of the original became [redacted_start, redacted_end)."""

    placeholder: str
    kind: str
    original_start: int
    original_end: int
    redacted_start: int
    redacted_end: int


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """Output of `redact`. Only `redacted_text` may leave our servers; the repr never shows original values."""

    redacted_text: str
    mapping: RedactionMapping
    spans: tuple[RedactedSpan, ...]
    original_text: str = field(repr=False)
    _redacted_starts: tuple[int, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_redacted_starts", tuple(span.redacted_start for span in self.spans))

    @property
    def counts(self) -> dict[str, int]:
        """Distinct placeholders per kind in this text, safe to log."""
        seen: dict[str, set[str]] = {}
        for span in self.spans:
            seen.setdefault(span.kind, set()).add(span.placeholder)
        return {kind: len(placeholders) for kind, placeholders in seen.items()}

    def _original_offset(self, offset: int, *, is_end: bool) -> int:
        index = bisect_right(self._redacted_starts, offset) - 1
        if index < 0:
            return offset
        span = self.spans[index]
        if offset >= span.redacted_end:
            return span.original_end + (offset - span.redacted_end)
        if offset == span.redacted_start:
            return span.original_start
        # Inside a placeholder: widen to the whole original value.
        return span.original_end if is_end else span.original_start

    def to_original_range(self, start: int, end: int) -> tuple[int, int]:
        """Map [start, end) of `redacted_text` to the original text. A range cutting into a placeholder widens
        to cover the whole value. Raises ValueError for a range outside the redacted text."""
        if not 0 <= start <= end <= len(self.redacted_text):
            raise ValueError(f"range [{start}, {end}) is outside the redacted text [0, {len(self.redacted_text)}]")
        return self._original_offset(start, is_end=False), self._original_offset(end, is_end=True)

    def restore(self, start: int, end: int) -> str:
        """The original text behind [start, end) of `redacted_text`, exactly as written."""
        original_start, original_end = self.to_original_range(start, end)
        return self.original_text[original_start:original_end]


# --- redaction -----------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Match:
    start: int
    end: int
    kind: str
    key: str
    rank: int
    masked: bool


def _pattern_matches(normalised: str) -> list[_Match]:
    matches: list[_Match] = []
    for found in _PHONE_RE.finditer(normalised):
        matches.append(_Match(found.start(), found.end(), PHONE, _digits(found.group())[-10:], _RANK[PHONE], True))
    for found in _AADHAAR_RE.finditer(normalised):
        matches.append(_Match(found.start(), found.end(), AADHAAR, _digits(found.group()), _RANK[AADHAAR], True))
    for pattern in (_PAN_RE, _PAN_SPACED_RE):
        for found in pattern.finditer(normalised):
            key = re.sub(r"[ -]", "", found.group()).upper()
            matches.append(_Match(found.start(), found.end(), PAN, key, _RANK[PAN], True))
    for found in _EMAIL_RE.finditer(normalised):
        matches.append(_Match(found.start(), found.end(), EMAIL, found.group().lower(), _RANK[EMAIL], True))
    for found in _SPOKEN_EMAIL_RE.finditer(normalised):
        local, domain, tld = (_SPOKEN_DOT.sub(".", found.group(part)) for part in ("local", "domain", "tld"))
        key = f"{local}@{domain}.{tld}".lower()
        matches.append(_Match(found.start(), found.end(), EMAIL, key, _RANK[EMAIL], True))
    return matches


def _name_matches(normalised: str, names: Iterable[KnownName], masked_roles: frozenset[str]) -> list[_Match]:
    # folded spelling -> (role, key, masked). Masked entries are registered first so they win a shared spelling.
    table: dict[str, tuple[str, str, bool]] = {}
    entries = list(names)
    for entry in entries:
        if not isinstance(entry, KnownName):
            raise TypeError("names must be KnownName objects")
    for masked in (True, False):
        for entry in entries:
            if (entry.role in masked_roles) != masked:
                continue
            key = f"{entry.role}:{_fold(entry.text)}"
            for spelling in entry.spellings:
                folded = _fold(spelling)
                current = table.get(folded)
                if current is None:
                    table[folded] = (entry.role, key, masked)
                elif masked and current[2] and current[1] != key:
                    # Two masked people share this spelling (two students called Riya): give it its own placeholder.
                    table[folded] = (current[0], f"{current[0]}:{folded}", True)
    if not table:
        return []
    alternatives = sorted(table, key=len, reverse=True)
    body = "|".join(r"\s+".join(re.escape(word) for word in spelling.split()) for spelling in alternatives)
    pattern = re.compile(rf"(?<!{_NAME_CHAR})(?:{body})(?!{_NAME_CHAR})", re.IGNORECASE)
    matches = []
    for found in pattern.finditer(normalised):
        folded = _fold(found.group())
        if folded not in table:
            raise RuntimeError("a matched name has no entry: case folding disagreed with the regex")
        role, key, masked = table[folded]
        rank = _RANK_MASKED_NAME if masked else _RANK_KEPT_NAME
        matches.append(_Match(found.start(), found.end(), role, key, rank, masked))
    return matches


def _resolve(matches: list[_Match], length: int) -> list[_Match]:
    """Keep the longest non-overlapping matches (ties by rank), then drop the unmasked ones; sorted by start."""
    taken = bytearray(length)
    kept = []
    for match in sorted(matches, key=lambda m: (m.start - m.end, m.rank, m.start)):
        if any(taken[match.start : match.end]):
            continue
        taken[match.start : match.end] = b"\x01" * (match.end - match.start)
        kept.append(match)
    return sorted((m for m in kept if m.masked), key=lambda m: m.start)


def redact(
    text: str,
    *,
    names: Iterable[KnownName] = (),
    masked_roles: Iterable[str] = DEFAULT_MASKED_ROLES,
    extend: RedactionMapping | None = None,
) -> RedactionResult:
    """Mask PII in `text`. See the module docstring for what is matched and how placeholders are numbered.

    `names` lists the people to look for, with their roles; only roles in `masked_roles` are masked. Pass the
    mapping of an earlier text of the same document as `extend` to keep its placeholders. Raises ValueError for a
    bad configuration or for text that already contains a placeholder-shaped token such as "[PHONE_1]", which
    would make `unredact` ambiguous.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, not {type(text).__name__}")
    roles = frozenset(_check_role(role, "masked role") for role in masked_roles)
    if _PLACEHOLDER_SHAPE.search(text):
        raise ValueError("text already contains a placeholder-shaped token like [PHONE_1]; redact raw text only")

    normalised = text.translate(_ASCII_DIGITS)
    if len(normalised) != len(text):  # translate maps one character to one; offsets depend on it
        raise RuntimeError("digit normalisation changed the text length")
    matches = _resolve(_pattern_matches(normalised) + _name_matches(normalised, names, roles), len(text))

    mapping = extend if extend is not None else RedactionMapping()
    pieces: list[str] = []
    spans: list[RedactedSpan] = []
    cursor = 0
    redacted_length = 0
    for match in matches:
        mapping, placeholder = mapping._with(match.kind, match.key, text[match.start : match.end])
        pieces.append(text[cursor : match.start])
        redacted_length += match.start - cursor
        spans.append(
            RedactedSpan(
                placeholder=placeholder,
                kind=match.kind,
                original_start=match.start,
                original_end=match.end,
                redacted_start=redacted_length,
                redacted_end=redacted_length + len(placeholder),
            )
        )
        pieces.append(placeholder)
        redacted_length += len(placeholder)
        cursor = match.end
    pieces.append(text[cursor:])
    return RedactionResult("".join(pieces), mapping, tuple(spans), text)


def unredact(text: str, mapping: RedactionMapping) -> str:
    """Replace every placeholder in `text` that `mapping` knows with its value as first written.

    For quotes and model output shown to authorised users after grounding. Placeholders the mapping does not know
    (for example one a model invented) are left as they are. To recover the exact original wording of a range of
    the redacted text, use `RedactionResult.restore` instead.
    """
    return _PLACEHOLDER.sub(lambda m: mapping.value(m.group()) if m.group() in mapping else m.group(), text)
