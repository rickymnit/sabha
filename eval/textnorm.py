"""Text normalisation for word and character error rates on Hindi, English and Hinglish transcripts (P4.3).

Gold transcripts follow docs/annotation-guidelines.md; ASR output does not. Both go through the same steps so that
only real recognition errors count:

1. Unicode NFC; Devanagari digits (०-९) become ASCII digits; lowercase (only affects Roman script).
2. Punctuation and symbols become spaces, except apostrophes, which are dropped ("ma'am" -> "maam"), and commas
   inside numbers ("1,000" -> "1000"). The danda (।) is punctuation. Hyphens split words.
3. Bracket tokens from the guidelines are kept whole. `[inaudible]` is removed from the text: nothing can be scored
   there, and any ASR words in that stretch then count as insertions (never in the system's favour). The privacy
   tokens in PRIVACY_TOKENS stay, and wer.py lets each one match any single hypothesis word.
4. English number words become digits ("twenty five" -> "25", "two thousand twenty six" -> "2026"), because
   annotators write numbers as words and ASR systems often write digits. Only valid compositions join: "ten
   thirty" stays "10 30" and "four five two" stays "4 5 2". Hindi number words (पच्चीस) are NOT converted; this is
   a known limitation, so Hindi numbers count as errors when one side used digits.

Raw mode keeps Devanagari and Roman as written. Transliterated mode (`transliterated=True`) also romanises every
Devanagari word with `transliterate()` and folds common Hinglish spelling variants on every word, so "अच्छा" and
"achha" compare equal. The romanisation is deliberately simple and is the same for both sides:

- Consonants take an inherent "a" unless a vowel sign or virama follows; the final inherent "a" of a word is
  dropped ("कल" -> "kal"). Medial schwas are kept ("समझना" -> "samajhana"), a known limitation.
- Nukta is ignored (ज़ -> j, ढ़ -> dh), anusvara and chandrabindu both become "n", visarga becomes "h".
- Folding, applied to letters only (never digits): "chh" -> "ch", "ph" -> "f", "w" -> "v", "z" -> "j", "q" -> "k",
  "ee" -> "i", "oo" -> "u", a doubled "chch" -> "ch", and any run of one repeated letter becomes one letter.
- A few very frequent words whose usual Hinglish spelling differs from the scheme are folded whole (WORD_FOLDS:
  "ham" -> "hum" for हम, "nahin" -> "nahi" for नहीं). The list is kept short on purpose; other spelling gaps
  remain as errors, which is why raw and transliterated WER are both reported.
"""

from __future__ import annotations

import re
import unicodedata

INAUDIBLE = "[inaudible]"
PRIVACY_TOKENS: frozenset[str] = frozenset({"[student]", "[name]", "[phone]", "[id]", "[email]", "[address]"})

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_BRACKET_OR_WORD = re.compile(r"\[[a-z]+\]|[^\s\[]+")
_NUMBER_COMMA = re.compile(r"(?<=\d),(?=\d{3}\b)")
_APOSTROPHES = "'’‘`´"

# --- numbers -------------------------------------------------------------------------------------------------------

_UNITS = {w: i for i, w in enumerate(["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"])}
_TEENS = {
    w: i + 10
    for i, w in enumerate(
        ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
    )
}
_TENS = {
    w: (i + 2) * 10
    for i, w in enumerate(["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"])
}
_SCALES = {"thousand": 1_000, "lakh": 100_000, "lakhs": 100_000, "crore": 10_000_000, "crores": 10_000_000}
_NUMBER_WORDS = {**_UNITS, **_TEENS, **_TENS}


class _NumberParser:
    """Joins a run of English number words into one number while the composition stays valid."""

    def __init__(self) -> None:
        self.total = 0  # value from completed scale groups (thousands, lakhs, crores)
        self.group = 0  # value below the current scale
        self.last = ""  # kind of the last word: unit, teen, tens, hundred, scale, and, zero
        self.last_scale = 10**12
        self.words = 0

    def accepts(self, word: str, next_word: str | None) -> bool:
        kind = self._kind(word)
        if kind is None:
            return False
        if self.words == 0:
            return kind in ("unit", "teen", "tens", "zero")
        if self.last == "zero" or kind == "zero":
            return False
        if kind == "and":
            return (
                self.last in ("hundred", "scale")
                and next_word is not None
                and self._kind(next_word)
                in (
                    "unit",
                    "teen",
                    "tens",
                )
            )
        if kind == "unit":
            return self.last in ("tens", "hundred", "scale", "and") and not (self.last == "tens" and self.group % 10)
        if kind in ("teen", "tens"):
            return self.last in ("hundred", "scale", "and")
        if kind == "hundred":
            return self.last in ("unit", "teen") and self.group < 100
        if kind == "scale":
            return self.last in ("unit", "teen", "tens", "hundred") and _SCALES[word] < self.last_scale
        return False

    def add(self, word: str) -> None:
        kind = self._kind(word)
        if kind == "hundred":
            self.group *= 100
        elif kind == "scale":
            self.total += self.group * _SCALES[word]
            self.group = 0
            self.last_scale = _SCALES[word]
        elif kind != "and":
            self.group += _NUMBER_WORDS[word]
        self.last = kind or ""
        self.words += 1

    def value(self) -> int:
        return self.total + self.group

    @staticmethod
    def _kind(word: str) -> str | None:
        if word == "zero":
            return "zero"
        if word in _UNITS:
            return "unit"
        if word in _TEENS:
            return "teen"
        if word in _TENS:
            return "tens"
        if word == "hundred":
            return "hundred"
        if word in _SCALES:
            return "scale"
        if word == "and":
            return "and"
        return None


def _numbers_to_digits(words: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(words):
        parser = _NumberParser()
        j = i
        while j < len(words) and parser.accepts(words[j], words[j + 1] if j + 1 < len(words) else None):
            parser.add(words[j])
            j += 1
        if parser.words:
            out.append(str(parser.value()))
            i = j
        else:
            out.append(words[i])
            i += 1
    return out


# --- transliteration -----------------------------------------------------------------------------------------------

_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h",
}  # fmt: skip
_VOWELS = {
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o", "ऍ": "e",
}  # fmt: skip
_VOWEL_SIGNS = {
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e",
}  # fmt: skip
_SIGNS = {"ं": "n", "ँ": "n", "ः": "h"}
_VIRAMA = "्"
_NUKTA = "़"
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_FOLDS = (("chh", "ch"), ("chch", "ch"), ("ph", "f"), ("w", "v"), ("z", "j"), ("q", "k"), ("ee", "i"), ("oo", "u"))
_REPEATED_LETTER = re.compile(r"([a-z])\1+")
WORD_FOLDS: dict[str, str] = {"ham": "hum", "nahin": "nahi"}


def fold(word: str) -> str:
    """Fold common Roman spelling variants of Hinglish words. Words containing digits are returned unchanged."""
    if any(ch.isdigit() for ch in word):
        return word
    for old, new in _FOLDS:
        word = word.replace(old, new)
    word = _REPEATED_LETTER.sub(r"\1", word)
    return WORD_FOLDS.get(word, word)


def transliterate(word: str) -> str:
    """Romanise one Devanagari word with the simple scheme in the module docstring, then fold it."""
    chars = [ch for ch in unicodedata.normalize("NFD", word) if ch != _NUKTA]
    out: list[str] = []
    for i, ch in enumerate(chars):
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if ch in _CONSONANTS:
            out.append(_CONSONANTS[ch])
            if nxt not in _VOWEL_SIGNS and nxt != _VIRAMA and nxt != "":
                out.append("a")  # inherent vowel; the word-final one is dropped (schwa deletion)
        elif ch in _VOWEL_SIGNS:
            out.append(_VOWEL_SIGNS[ch])
        elif ch in _VOWELS:
            out.append(_VOWELS[ch])
        elif ch in _SIGNS:
            out.append(_SIGNS[ch])
        elif ch == _VIRAMA:
            continue
        else:
            out.append(ch)
    return fold("".join(out))


# --- normalisation -------------------------------------------------------------------------------------------------


def _clean_piece(piece: str) -> list[str]:
    for apostrophe in _APOSTROPHES:
        piece = piece.replace(apostrophe, "")
    cleaned = "".join(" " if unicodedata.category(ch)[0] in "PS" else ch for ch in piece)
    return cleaned.split()


def tokens(text: str, *, transliterated: bool = False) -> list[str]:
    """Normalised words of `text` (see the module docstring); `[inaudible]` is dropped, privacy tokens kept."""
    text = unicodedata.normalize("NFC", text).translate(_DEVANAGARI_DIGITS).lower()
    text = _NUMBER_COMMA.sub("", text)
    words: list[str] = []
    run: list[str] = []  # plain words waiting for number conversion

    def flush() -> None:
        words.extend(_numbers_to_digits(run))
        run.clear()

    for piece in _BRACKET_OR_WORD.findall(text):
        if piece.startswith("[") and piece.endswith("]"):
            flush()
            if piece != INAUDIBLE:
                words.append(piece)
        else:
            run.extend(_clean_piece(piece))
    flush()
    if transliterated:
        words = [w if w.startswith("[") else (transliterate(w) if _DEVANAGARI.search(w) else fold(w)) for w in words]
    return words


def normalise(text: str, *, transliterated: bool = False) -> str:
    """`tokens(text)` joined by single spaces."""
    return " ".join(tokens(text, transliterated=transliterated))
