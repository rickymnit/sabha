"""Text normalisation for WER on Hinglish transcripts (P4.3)."""

from __future__ import annotations

import pytest
from textnorm import PRIVACY_TOKENS, normalise, tokens, transliterate


def test_lowercases_roman_and_strips_punctuation() -> None:
    assert normalise("Good Morning, Sunrise Public School!") == "good morning sunrise public school"


def test_devanagari_is_kept_as_written_and_danda_removed() -> None:
    assert normalise("आज हम photosynthesis पढ़ेंगे।") == "आज हम photosynthesis पढ़ेंगे"


def test_apostrophes_are_dropped_so_spellings_agree() -> None:
    assert normalise("Ma'am, it's okay") == "maam its okay"


def test_whitespace_and_hyphens_collapse() -> None:
    assert normalise("  twenty-five \n  copies  ") == "25 copies"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("twenty five", "25"),
        ("two thousand twenty six", "2026"),
        ("five hundred rupees", "500 rupees"),
        ("one hundred and five", "105"),
        ("class ten", "class 10"),
        ("ten thirty", "10 30"),  # a time said as two numbers stays two numbers
        ("four five two", "4 5 2"),  # digit by digit stays digit by digit
        ("page 25", "page 25"),
        ("page २५", "page 25"),  # Devanagari digits become ASCII
        ("1,000 copies", "1000 copies"),
        ("zero", "0"),
    ],
)
def test_numbers_are_normalised_to_digits(text: str, expected: str) -> None:
    assert normalise(text) == expected


def test_hindi_number_words_are_left_as_written() -> None:
    # Documented limitation: Hindi number words are not converted.
    assert normalise("पच्चीस") == "पच्चीस"


def test_inaudible_is_removed_and_privacy_tokens_are_kept() -> None:
    assert tokens("[inaudible] [student] की copy, [phone]") == ["[student]", "की", "copy", "[phone]"]


def test_privacy_tokens_are_the_annotation_guideline_set() -> None:
    assert frozenset({"[student]", "[name]", "[phone]", "[id]", "[email]", "[address]"}) == PRIVACY_TOKENS


def test_privacy_token_with_possessive_keeps_the_token() -> None:
    assert tokens("[student]'s copy") == ["[student]", "s", "copy"]


@pytest.mark.parametrize(
    ("devanagari", "roman"),
    [
        ("पढ़ो", "padho"),
        ("हाँ", "han"),
        ("हां", "han"),  # chandrabindu and anusvara fold together
        ("अच्छा", "acha"),
        ("कल", "kal"),
        ("क्या", "kya"),
        ("बच्चे", "bache"),
        ("फल", "fal"),
        ("ज़रूर", "jarur"),
        ("हम", "hum"),  # word fold: the scheme gives "ham"
        ("नहीं", "nahi"),  # word fold: the scheme gives "nahin"
        ("नमस्ते", "namaste"),
    ],
)
def test_transliteration_matches_common_hinglish_spelling(devanagari: str, roman: str) -> None:
    assert transliterate(devanagari) == roman


def test_transliterated_mode_folds_roman_spelling_variants() -> None:
    # Both sides go through the same folding, so these compare equal.
    assert normalise("Achha, padho", transliterated=True) == normalise("अच्छा, पढ़ो", transliterated=True)
    assert normalise("kyaa phal", transliterated=True) == normalise("क्या फल", transliterated=True)


def test_raw_mode_does_not_transliterate() -> None:
    assert normalise("अच्छा") != normalise("acha")


def test_tokens_of_empty_text_is_empty() -> None:
    assert tokens("  ...  ") == []
