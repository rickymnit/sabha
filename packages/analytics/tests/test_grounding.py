"""Tests for sabha_analytics.grounding: the verifier every LLM quote must pass before a user sees it (golden rule 5).

A quote is verified only if it exists in the transcript the model saw (normalised fuzzy ratio >= 0.90 within one
utterance) AND the matched utterance lies within +-5 s of the time the model claimed. Matching runs on the redacted
text; the result maps back to the original wording for authorised users.
"""

from __future__ import annotations

from typing import Any

import pytest

from sabha_analytics.grounding import (
    MIN_QUOTE_WORDS,
    MIN_RATIO,
    TIME_TOLERANCE_MS,
    normalise,
    prepare_transcript,
    utterance_id,
    verify_quote,
)
from sabha_llm.redact import STAFF, STUDENT, KnownName

Row = tuple[str, int, int, str]


def transcript(*rows: Row) -> dict[str, Any]:
    """A transcript@v1 document from (role, start_ms, end_ms, text) rows."""
    return {
        "version": "transcript@v1",
        "timeline": "original",
        "asr_model": "fake-asr@1",
        "word_count": sum(len(text.split()) for *_, text in rows),
        "utterances": [
            {
                "role": role,
                "speaker_label": "SPEAKER_00" if role == "teacher" else "SPEAKER_01",
                "start_ms": start,
                "end_ms": end,
                "text": text,
                "avg_confidence": 0.9,
                "low_confidence_spans": [],
            }
            for role, start, end, text in rows
        ],
    }


LONG = (
    "Toh dekho, photosynthesis ek process hai jismein plant sunlight, paani aur carbon dioxide lekar apna khana "
    "banata hai, aur yeh kaam leaf ke andar chlorophyll karta hai jo green pigment hai, isliye leaves hari dikhti "
    "hain aur yahi reason hai ki plant ko dhoop chahiye"
)

LESSON = transcript(
    ("teacher", 12_000, 18_500, "Achha to aaj ham photosynthesis ke baare mein padhenge."),
    ("students", 19_000, 20_000, "Yes ma'am."),
    ("teacher", 21_000, 45_000, LONG),
    ("teacher", 46_000, 50_000, "Samajh aaya sab ko? Koi doubt?"),
    ("students", 51_000, 53_000, "Ma'am, chlorophyll kahan hota hai?"),
    ("teacher", 54_000, 60_000, "Bahut accha sawaal. Chlorophyll leaf ke cells mein hota hai."),
    ("teacher", 61_500, 64_000, "Ab hum ek experiment dekhenge."),
    ("teacher", 300_000, 304_000, "Samajh aaya sab ko? Koi doubt?"),
    ("teacher", 310_000, 316_000, "आज हम प्रकाश संश्लेषण के बारे में पढ़ेंगे।"),
    ("teacher", 317_000, 320_000, "पेज १२ खोलो और पहला सवाल पढ़ो।"),
)


@pytest.fixture(scope="module")
def lesson() -> Any:
    return prepare_transcript(LESSON)


# --- normalisation and ids -----------------------------------------------------------------------------------


def test_normalise_lowercases_strips_punctuation_and_spaces() -> None:
    assert normalise("  Samajh   aaya, SAB ko?!  ") == normalise("samajh aaya sab ko")
    assert normalise("Ma'am - yes.") == normalise("maam yes")


def test_normalise_folds_common_hinglish_spellings() -> None:
    assert normalise("Achha to aaj ham nahin padhenge") == normalise("acha toh aj hum nahi padhenge")
    assert normalise("theek hai, kyon?") == normalise("thik hai kyun")


def test_normalise_keeps_placeholders_whole_and_folds_devanagari_variants() -> None:
    assert normalise("[STUDENT_1], sahi!") == "[student_1] sahi"
    assert normalise("पेज १२") == normalise("पेज 12")
    assert normalise("में") == normalise("मेँ")  # anusvara and chandrabindu
    assert normalise("पढ़ो") == normalise("पढो")  # nukta


def test_utterance_ids_are_index_based_and_deterministic(lesson: Any) -> None:
    assert utterance_id(0) == "u0000"
    assert utterance_id(42) == "u0042"
    assert [u.id for u in lesson.utterances][:3] == ["u0000", "u0001", "u0002"]
    assert prepare_transcript(LESSON).utterances == lesson.utterances
    assert lesson.get("u0002").start_ms == 21_000
    assert lesson.get("u9999") is None


def test_prepare_rejects_an_invalid_transcript() -> None:
    bad = transcript(("teacher", 5_000, 4_000, "ends before it starts"))
    with pytest.raises(ValueError, match="after it starts"):
        prepare_transcript(bad)


def test_rendered_transcript_shows_ids_and_original_times(lesson: Any) -> None:
    lines = lesson.render().splitlines()
    assert len(lines) == len(LESSON["utterances"])
    assert lines[2].startswith("[u0002 start_ms=21000 end_ms=45000 teacher] Toh dekho")


# --- the core cases ------------------------------------------------------------------------------------------


def test_exact_quote_passes_with_corrected_times(lesson: Any) -> None:
    result = verify_quote(lesson, "Bahut accha sawaal.", start_ms=55_000, utterance_id="u0005")
    assert result.verified, result
    assert result.reason is None
    assert result.utterance_id == "u0005"
    assert (result.start_ms, result.end_ms) == (54_000, 60_000)  # from the transcript, not the claim
    assert result.ratio == 1.0
    assert result.matched_text == "Bahut accha sawaal"  # the matched words; trailing punctuation is not a word


def test_quote_with_small_asr_spelling_differences_passes(lesson: Any) -> None:
    result = verify_quote(lesson, "Acha toh aaj hum photosynthesis ke bare mein padhenge", start_ms=12_000)
    assert result.verified, result
    assert result.utterance_id == "u0000"
    typo = verify_quote(lesson, "yeh kaam leaf ke andar chlorophyl karta hai jo green pigmant hai", start_ms=21_000)
    assert typo.verified, typo
    assert MIN_RATIO <= typo.ratio < 1.0


def test_planted_fake_quote_fails(lesson: Any) -> None:
    fake = "Aaj hum photosynthesis ka experiment lab mein karenge"  # plausible, on topic, never said
    result = verify_quote(lesson, fake, start_ms=12_000, utterance_id="u0000")
    assert not result.verified
    assert result.reason == "not_found"
    assert result.ratio < MIN_RATIO
    assert result.utterance_id is None and result.start_ms is None and result.matched_text is None


def test_real_quote_with_claimed_time_far_off_fails(lesson: Any) -> None:
    result = verify_quote(lesson, "Ab hum ek experiment dekhenge.", start_ms=600_000, utterance_id="u0006")
    assert not result.verified
    assert result.reason == "time_mismatch"
    assert result.utterance_id == "u0006"  # where it really is, for the re-ask feedback
    assert result.start_ms == 61_500


def test_time_tolerance_is_five_seconds_either_side(lesson: Any) -> None:
    quote = "Ab hum ek experiment dekhenge."  # utterance 61_500 - 64_000
    assert TIME_TOLERANCE_MS == 5_000
    assert verify_quote(lesson, quote, start_ms=61_500 - 5_000).verified
    assert verify_quote(lesson, quote, start_ms=64_000 + 5_000).verified
    assert not verify_quote(lesson, quote, start_ms=61_500 - 5_001).verified
    assert not verify_quote(lesson, quote, start_ms=64_000 + 5_001).verified


def test_repeated_phrase_matches_the_occurrence_at_the_claimed_time(lesson: Any) -> None:
    early = verify_quote(lesson, "Samajh aaya sab ko? Koi doubt?", start_ms=46_000)
    late = verify_quote(lesson, "Samajh aaya sab ko? Koi doubt?", start_ms=301_000)
    assert (early.utterance_id, late.utterance_id) == ("u0003", "u0007")
    assert early.verified and late.verified


def test_quote_spanning_two_adjacent_utterances_fails_but_each_half_passes(lesson: Any) -> None:
    spanning = "Samajh aaya sab ko? Koi doubt? Ma'am, chlorophyll kahan hota hai?"
    result = verify_quote(lesson, spanning, start_ms=46_000)
    assert not result.verified
    assert result.reason == "not_found"
    assert verify_quote(lesson, "Samajh aaya sab ko? Koi doubt?", start_ms=46_000).verified
    assert verify_quote(lesson, "Ma'am, chlorophyll kahan hota hai?", start_ms=51_000).verified


def test_short_genuine_fragment_of_a_long_utterance_passes_with_the_utterance_times(lesson: Any) -> None:
    result = verify_quote(lesson, "isliye leaves hari dikhti hain", start_ms=40_000)
    assert result.verified, result
    assert result.utterance_id == "u0002"
    assert (result.start_ms, result.end_ms) == (21_000, 45_000)
    assert result.matched_text == "isliye leaves hari dikhti hain"


def test_quote_sharing_only_a_short_fragment_with_a_long_utterance_fails(lesson: Any) -> None:
    # The first five words are real; the rest is invented. partial_ratio-style matching of the real prefix would
    # be tempting to accept; a window of comparable length is not.
    invented = "Toh dekho, photosynthesis ek process hai jo sirf raat ko hota hai jab chand nikalta hai"
    result = verify_quote(lesson, invented, start_ms=21_000)
    assert not result.verified
    assert result.reason == "not_found"


def test_quote_with_invented_words_appended_to_a_whole_utterance_fails(lesson: Any) -> None:
    result = verify_quote(lesson, "Ab hum ek experiment dekhenge aur phir test bhi likhenge", start_ms=61_500)
    assert not result.verified


def test_too_short_quote_fails_even_if_exact(lesson: Any) -> None:
    assert MIN_QUOTE_WORDS == 3
    result = verify_quote(lesson, "Koi doubt?", start_ms=46_000)
    assert not result.verified
    assert result.reason == "too_short"
    assert verify_quote(lesson, " ?! ", start_ms=46_000).reason == "too_short"


def test_devanagari_quote_passes_with_spelling_variants(lesson: Any) -> None:
    exact = verify_quote(lesson, "आज हम प्रकाश संश्लेषण के बारे में पढ़ेंगे", start_ms=310_000)
    assert exact.verified and exact.utterance_id == "u0008"
    variant = verify_quote(lesson, "आज हम प्रकाश संश्लेषण के बारे मेँ पढेंगे", start_ms=310_000)
    assert variant.verified, variant
    digits = verify_quote(lesson, "पेज 12 खोलो और पहला सवाल पढ़ो", start_ms=317_000)
    assert digits.verified and digits.utterance_id == "u0009"


def test_devanagari_fake_quote_fails(lesson: Any) -> None:
    result = verify_quote(lesson, "आज हम प्रयोगशाला में नया प्रयोग करेंगे", start_ms=310_000)
    assert not result.verified


def test_claimed_utterance_id_is_recorded_but_times_come_from_the_match(lesson: Any) -> None:
    result = verify_quote(lesson, "Ab hum ek experiment dekhenge.", start_ms=60_000, utterance_id="u0005")
    assert result.verified  # 60_000 is within 5 s of u0006 (61_500 - 64_000)
    assert result.claimed_utterance_id == "u0005"
    assert result.utterance_id == "u0006"
    assert not result.claimed_id_matches


# --- redaction -----------------------------------------------------------------------------------------------

REDACTED = transcript(
    ("teacher", 1_000, 6_000, "Riya, tumhara answer sahi hai, bahut accha."),
    ("teacher", 7_000, 12_000, "Kisi ko problem ho toh mujhe 98765 43210 pe call karna."),
    ("students", 13_000, 15_000, "Ma'am Riya ne copy kiya tha."),
    ("teacher", 16_000, 20_000, "Mrs Sharma kal test lengi, Riya aur Aman dono taiyaar raho."),
)
NAMES = (
    KnownName("Riya", STUDENT),
    KnownName("Aman", STUDENT),
    KnownName("Mrs Sharma", STAFF),
)


@pytest.fixture(scope="module")
def redacted() -> Any:
    return prepare_transcript(REDACTED, names=NAMES)


def test_prepared_text_is_redacted_with_stable_placeholders(redacted: Any) -> None:
    texts = [u.text for u in redacted.utterances]
    assert texts[0] == "[STUDENT_1], tumhara answer sahi hai, bahut accha."
    assert texts[1] == "Kisi ko problem ho toh mujhe [PHONE_1] pe call karna."
    assert texts[2] == "Ma'am [STUDENT_1] ne copy kiya tha."  # same student, same placeholder across utterances
    assert texts[3] == "Mrs Sharma kal test lengi, [STUDENT_1] aur [STUDENT_2] dono taiyaar raho."
    rendered = redacted.render()
    for secret in ("Riya", "Aman", "98765", "43210"):
        assert secret not in rendered
    assert "Riya" not in repr(redacted)


def test_quote_over_a_placeholder_passes_and_maps_back_to_the_original(redacted: Any) -> None:
    result = verify_quote(redacted, "[STUDENT_1], tumhara answer sahi hai", start_ms=1_000)
    assert result.verified, result
    assert result.matched_text == "[STUDENT_1], tumhara answer sahi hai"
    assert result.matched_text_original == "Riya, tumhara answer sahi hai"
    assert result.original_range is not None
    start, end = result.original_range
    assert REDACTED["utterances"][0]["text"][start:end] == "Riya, tumhara answer sahi hai"
    assert "Riya" not in repr(result)


def test_quote_ending_on_a_phone_placeholder_restores_the_whole_number(redacted: Any) -> None:
    result = verify_quote(redacted, "toh mujhe [PHONE_1] pe call karna", start_ms=7_000)
    assert result.verified, result
    assert result.matched_text_original == "toh mujhe 98765 43210 pe call karna"


def test_quote_with_a_different_placeholder_number_does_not_pass_as_exact(redacted: Any) -> None:
    right = verify_quote(redacted, "[STUDENT_1] aur [STUDENT_2] dono taiyaar raho", start_ms=16_000)
    wrong = verify_quote(redacted, "[STUDENT_2] aur [STUDENT_1] dono taiyaar raho", start_ms=16_000)
    assert right.verified and right.ratio == 1.0
    assert wrong.ratio < 1.0
