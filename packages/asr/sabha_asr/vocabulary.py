"""The organisation's own words in a transcript (ADR 0019).

Speech-to-text does not know a company's words: "Schoollog" comes back as "schoolo" or "school log", "ERP" as "arp".
Each tenant keeps a list of terms with the wrong spellings heard so far (Tenant.vocabulary). Two things use it:

1. `hints` gives the terms to a provider that accepts a word list (Deepgram key terms, the OpenAI and Groq prompt,
   Gemini's instruction).
2. `fix_words` replaces the wrong spellings in the merged words, before speaker roles and scoring. It matches whole
   words only, ignoring case and punctuation, so "arp" becomes "ERP" but "sharp" stays as it is. A run of words that
   matches a spelling ("school log") becomes the term; the term's own words share the run's time. The longest
   spelling wins where two could match. The term in another case ("erp", "schoollog") is put in the term's case.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sabha_asr.roles import normalise_text
from sabha_asr.words import Word

MAX_HINTS = 50  # Deepgram allows about 100 key terms; a long OpenAI prompt is cut, so keep the list short
MAX_SPAN = 5  # words one wrong spelling may cover


@dataclass(frozen=True, slots=True)
class Term:
    term: str
    sounds_like: tuple[str, ...] = ()


def terms_of(vocabulary: Iterable[object]) -> tuple[Term, ...]:
    """Terms from Tenant.vocabulary (objects with `term` and `sounds_like`), blanks dropped."""
    out: list[Term] = []
    for item in vocabulary:
        term = str(getattr(item, "term", "") or "").strip()
        if term:
            spellings = tuple(s.strip() for s in getattr(item, "sounds_like", ()) or () if s and s.strip())
            out.append(Term(term, spellings))
    return tuple(out)


def hints(terms: Sequence[Term]) -> tuple[str, ...]:
    """The terms to tell a speech model, in the order given, without repeats."""
    return tuple(dict.fromkeys(t.term for t in terms))[:MAX_HINTS]


def _edges(text: str) -> tuple[str, str]:
    """Punctuation before and after a word ('"', ',' ...), kept around a replacement."""

    def punct(ch: str) -> bool:
        return unicodedata.category(ch)[0] in "PS"

    start = 0
    while start < len(text) and punct(text[start]):
        start += 1
    end = len(text)
    while end > start and punct(text[end - 1]):
        end -= 1
    return text[:start], text[end:]


def _patterns(terms: Sequence[Term]) -> dict[str, str]:
    """Normalised spelling -> term. The term itself is a pattern too, to put it in the term's case."""
    patterns: dict[str, str] = {}
    for t in terms:
        for spelling in (t.term, *t.sounds_like):
            key = normalise_text(spelling)
            if key and len(key.split()) <= MAX_SPAN * 2:
                patterns.setdefault(key, t.term)
    return patterns


def fix_words(words: Sequence[Word], terms: Sequence[Term]) -> tuple[list[Word], int]:
    """The words with wrong spellings replaced by their terms, and how many replacements changed the text."""
    patterns = _patterns(terms)
    if not patterns or not words:
        return list(words), 0
    cores = [normalise_text(w.text) for w in words]
    out: list[Word] = []
    fixes = 0
    i = 0
    while i < len(words):
        match: tuple[int, str] | None = None
        for span in range(min(MAX_SPAN, len(words) - i), 0, -1):
            parts = cores[i : i + span]
            if not all(parts):
                continue
            term = patterns.get(" ".join(parts))
            if term is not None:
                match = (span, term)
                break
        if match is None:
            out.append(words[i])
            i += 1
            continue
        span, term = match
        run = words[i : i + span]
        lead, _ = _edges(run[0].text)
        _, trail = _edges(run[-1].text)
        pieces = term.split()
        texts = [p for p in pieces]
        texts[0] = lead + texts[0]
        texts[-1] = texts[-1] + trail
        if [w.text for w in run] == texts:
            out.extend(run)
            i += span
            continue
        start, end = run[0].start_ms, run[-1].end_ms
        confidences = [w.confidence for w in run]
        confidence = None if any(c is None for c in confidences) else min(c for c in confidences if c is not None)
        step = (end - start) / len(texts)
        for k, text in enumerate(texts):
            a = start + round(step * k)
            b = end if k == len(texts) - 1 else start + round(step * (k + 1))
            out.append(Word(text, a, max(a, b), confidence))
        fixes += 1
        i += span
    return out, fixes


def hint_sentence(hints_: Sequence[str]) -> str:
    """One line for a prompt: the organisation's words, as they are written."""
    return "Words that may be said, spelled like this: " + ", ".join(hints_) + "." if hints_ else ""
