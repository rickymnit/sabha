"""Tests for sabha_llm.redact: PII masking before any text reaches an LLM provider.

Golden rule 8: phone numbers, Aadhaar-like and PAN-like numbers and emails are masked before text leaves our
servers. Student names are masked too (golden rule 10); staff names are not, unless configured. A missed value is a
leak, so the positive cases are broad; a false positive costs analysis quality, so the common school numbers
(times, classes, years, roll numbers, pages, percentages) are pinned as negatives.
"""

from __future__ import annotations

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sabha_llm.redact import (
    DEFAULT_MASKED_ROLES,
    STAFF,
    STUDENT,
    KnownName,
    RedactionMapping,
    redact,
    unredact,
)

_DEVANAGARI_TO_ASCII = str.maketrans("०१२३४५६७८९", "0123456789")


def assert_unchanged(text: str, names: tuple[KnownName, ...] = ()) -> None:
    result = redact(text, names=names)
    assert result.redacted_text == text
    assert result.spans == ()
    assert result.mapping.placeholders() == ()


def single(text: str) -> str:
    """Redact `text` and return the redacted text."""
    return redact(text).redacted_text


# --- phone numbers -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phone",
    [
        "9876543210",
        "98765 43210",
        "98765-43210",
        "987 654 3210",
        "9876 543 210",
        "98 76 54 32 10",
        "6123456789",
        "7012345678",
        "8123456789",
        "+91 98765 43210",
        "+91-98765-43210",
        "+919876543210",
        "+91 9876543210",
        "919876543210",
        "91 98765 43210",
        "09876543210",
        "0 98765 43210",
        "098765-43210",
        "9 8 7 6 5 4 3 2 1 0",  # read out digit by digit
        "९८७६५४३२१०",
        "९८७६५ ४३२१०",
        "+९१ ९८७६५ ४३२१०",
        "98765 ४३२१०",  # mixed scripts
    ],
)
def test_phone_numbers_are_masked(phone: str) -> None:
    assert single(f"Mera number {phone} hai.") == "Mera number [PHONE_1] hai."


@pytest.mark.parametrize(
    "text",
    [
        "1234567890",  # 10 digits but starts with 1: not an Indian mobile
        "5123456789",  # starts with 5
        "0123456789",
        "987654321",  # 9 digits
        "98765 4321",
        "98765432101",  # 11 digits, not a 0-prefixed mobile
        "19876543210",
        "9876543210123",  # part of a longer number
    ],
)
def test_numbers_that_are_not_mobiles_are_left(text: str) -> None:
    assert_unchanged(f"Number {text} likho.")


def test_phone_at_the_edges_of_text_and_next_to_punctuation() -> None:
    assert single("9876543210") == "[PHONE_1]"
    assert single("(98765 43210), call karo") == "([PHONE_1]), call karo"
    assert single("phone:9876543210.") == "phone:[PHONE_1]."
    assert single("9876543210@paytm") == "[PHONE_1]@paytm"


def test_phone_right_after_another_number_is_still_masked() -> None:
    assert single("Class 10 9876543210") == "Class 10 [PHONE_1]"
    assert single("roll no 23 98765 43210") == "roll no 23 [PHONE_1]"


# --- Aadhaar-like numbers ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "aadhaar",
    [
        "2345 6789 0123",
        "234567890123",
        "2345-6789-0123",
        "9999 8888 7777",
        "२३४५ ६७८९ ०१२३",
        "२३४५६७८९०१२३",
    ],
)
def test_aadhaar_like_numbers_are_masked(aadhaar: str) -> None:
    assert single(f"Aadhaar {aadhaar} hai") == "Aadhaar [AADHAAR_1] hai"


@pytest.mark.parametrize(
    "text",
    [
        "0123 4567 8901",  # first digit 0
        "1234 5678 9012",  # first digit 1
        "123456789012",
        "012345678901",
        "2345 6789 012",  # 11 digits
        "2345 6789 01234",  # 13 digits
        "12345 6789 0123",
    ],
)
def test_twelve_digit_numbers_that_are_not_aadhaar_like_are_left(text: str) -> None:
    assert_unchanged(f"Number {text} hai")


def test_ninety_one_prefixed_mobile_is_a_phone_not_aadhaar() -> None:
    assert single("919876543210") == "[PHONE_1]"
    assert single("+91 98765 43210") == "[PHONE_1]"
    # Grouped 4-4-4 it reads as an Aadhaar number; either way it is masked.
    assert single("9198 7654 3210") == "[AADHAAR_1]"


# --- PAN -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pan",
    [
        "ABCDE1234F",  # pragma: allowlist secret
        "ABCPD1234E",  # pragma: allowlist secret
        "abcde1234f",  # pragma: allowlist secret
        "AbCdE1234F",  # pragma: allowlist secret
        "ABCDE 1234 F",
        "ABCDE-1234-F",
    ],
)
def test_pan_like_values_are_masked(pan: str) -> None:
    assert single(f"Mera PAN {pan} hai") == "Mera PAN [PAN_1] hai"


def test_pan_with_devanagari_digits_is_masked() -> None:
    assert single("PAN ABCDE१२३४F") == "PAN [PAN_1]"


@pytest.mark.parametrize(
    "text",
    [
        "ABCD1234F",  # pragma: allowlist secret
        "ABCDEF1234F",  # pragma: allowlist secret
        "ABCDE12345F",  # pragma: allowlist secret
        "ABCDE1234FG",
        "after 2026 a",  # five letters, four digits, one letter, but spaced lower-case words
        "hello1234",
        "Class 10A",
    ],
)
def test_pan_negatives(text: str) -> None:
    assert_unchanged(text)


# --- email ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "email",
    [
        "riya.sharma@gmail.com",
        "RIYA_99@school.edu.in",
        "a+b@x.co",
        "parent-2026@yahoo.co.in",
        "riya at the rate gmail dot com",
        "riya at gmail dot com",
        "riya dot sharma at the rate gmail dot com",
        "office at school dot co dot in",
    ],
)
def test_emails_are_masked(email: str) -> None:
    assert single(f"Email {email} pe bhejo") == "Email [EMAIL_1] pe bhejo"


def test_email_followed_by_a_full_stop() -> None:
    assert single("Mail riya@gmail.com.") == "Mail [EMAIL_1]."


def test_written_and_spoken_forms_of_one_email_share_a_placeholder() -> None:
    text = "riya@gmail.com, haan riya at the rate gmail dot com"
    assert single(text) == "[EMAIL_1], haan [EMAIL_1]"


@pytest.mark.parametrize("text", ["@ symbol dabao", "riya@home", "meet at 10:30", "look at the board", "dot com era"])
def test_email_negatives(text: str) -> None:
    assert_unchanged(text)


def test_email_wins_over_a_phone_or_name_inside_it() -> None:
    names = (KnownName("Riya", STUDENT),)
    result = redact("riya9876543210@gmail.com", names=names)
    assert result.redacted_text == "[EMAIL_1]"


# --- names ---------------------------------------------------------------------------------------------------

STUDENTS = (
    KnownName("Riya", STUDENT, aliases=("रिया",)),
    KnownName("Aarav Mehta", STUDENT, aliases=("Aarav", "आरव")),
)
STAFF_NAMES = (KnownName("Sunita Verma", STAFF, aliases=("Sunita",)),)


def test_student_names_are_masked() -> None:
    result = redact("Riya, answer do. Aarav Mehta, tum bhi.", names=STUDENTS)
    assert result.redacted_text == "[STUDENT_1], answer do. [STUDENT_2], tum bhi."


def test_name_matching_ignores_case_and_shares_a_placeholder_across_aliases() -> None:
    result = redact("RIYA aur riya. Aarav, Aarav Mehta, आरव.", names=STUDENTS)
    assert result.redacted_text == "[STUDENT_1] aur [STUDENT_1]. [STUDENT_2], [STUDENT_2], [STUDENT_2]."


def test_names_match_whole_words_only() -> None:
    assert_unchanged("Priya aur Riyaz aur Aaravi", names=STUDENTS)


def test_names_followed_by_possessive_or_hinglish_postposition() -> None:
    result = redact("Riya's notebook, Riya ko do, Riya-ji", names=STUDENTS)
    assert result.redacted_text == "[STUDENT_1]'s notebook, [STUDENT_1] ko do, [STUDENT_1]-ji"


def test_name_with_extra_whitespace_inside_still_matches() -> None:
    assert redact("Aarav   Mehta aaya", names=STUDENTS).redacted_text == "[STUDENT_1] aaya"


def test_devanagari_names_are_masked_and_match_whole_words() -> None:
    result = redact("रिया को बुलाओ, रियाज़ को नहीं", names=STUDENTS)
    assert result.redacted_text == "[STUDENT_1] को बुलाओ, रियाज़ को नहीं"


def test_staff_names_are_not_masked_by_default() -> None:
    assert STAFF not in DEFAULT_MASKED_ROLES
    text = "Sunita Verma ma'am ne kaha, Sunita ji ka period hai"
    assert_unchanged(text, names=STAFF_NAMES)


def test_staff_names_can_be_masked_when_configured() -> None:
    result = redact("Sunita ma'am, Riya", names=STAFF_NAMES + STUDENTS, masked_roles={STUDENT, STAFF})
    assert result.redacted_text == "[STAFF_1] ma'am, [STUDENT_1]"


def test_a_name_listed_under_two_roles_is_masked() -> None:
    names = (KnownName("Riya", STAFF), KnownName("Riya", STUDENT))
    assert redact("Riya aayi", names=names).redacted_text == "[STUDENT_1] aayi"


def test_two_students_sharing_a_first_name() -> None:
    names = (
        KnownName("Riya Sharma", STUDENT, aliases=("Riya",)),
        KnownName("Riya Gupta", STUDENT, aliases=("Riya",)),
    )
    result = redact("Riya Gupta, Riya Sharma, aur Riya", names=names)
    # The shared first name cannot tell the two apart, so it gets its own placeholder; it is still masked.
    assert result.redacted_text == "[STUDENT_1], [STUDENT_2], aur [STUDENT_3]"


def test_a_longer_staff_name_keeps_a_student_first_name_inside_it() -> None:
    names = (KnownName("Riya", STUDENT), KnownName("Riya Sharma", STAFF))
    result = redact("Riya Sharma ma'am ne Riya ko bulaya", names=names)
    assert result.redacted_text == "Riya Sharma ma'am ne [STUDENT_1] ko bulaya"


@pytest.mark.parametrize(
    ("name", "role"),
    [
        ("", STUDENT),
        ("   ", STUDENT),
        ("A", STUDENT),  # one character would mask every "a"
        ("Riya", "student"),  # roles are upper-case placeholder words
        ("Riya", "STU DENT"),
        ("Riya", "PHONE"),  # reserved for the pattern recognisers
        ("Riya", "EMAIL"),
        ("[Riya]", STUDENT),
    ],
)
def test_bad_name_config_raises(name: str, role: str) -> None:
    with pytest.raises(ValueError):
        redact("text", names=(KnownName(name, role),))


def test_bad_masked_role_raises() -> None:
    with pytest.raises(ValueError):
        redact("text", masked_roles={"student"})


# --- Hinglish ------------------------------------------------------------------------------------------------


def test_roman_hinglish_sentence() -> None:
    text = (
        "Riya ka phone number 98765 43210 hai, uski mummy ka email riya.mom@gmail.com hai, "
        "aur Aadhaar 2345 6789 0123. Class 10 ka test 10:30 baje hai."
    )
    expected = (
        "[STUDENT_1] ka phone number [PHONE_1] hai, uski mummy ka email [EMAIL_1] hai, "
        "aur Aadhaar [AADHAAR_1]. Class 10 ka test 10:30 baje hai."
    )
    assert redact(text, names=STUDENTS).redacted_text == expected


def test_devanagari_sentence() -> None:
    text = "रिया का नंबर ९८७६५ ४३२१० है और आधार २३४५ ६७८९ ०१२३ है। कक्षा १० में ९:४५ बजे आना।"
    expected = "[STUDENT_1] का नंबर [PHONE_1] है और आधार [AADHAAR_1] है। कक्षा १० में ९:४५ बजे आना।"
    assert redact(text, names=STUDENTS).redacted_text == expected


def test_mixed_script_sentence_with_staff_and_students() -> None:
    text = "Sunita ma'am: आरव, apne papa ka number +91 98765 43210 likho, PAN abcde1234f nahi."
    expected = "Sunita ma'am: [STUDENT_1], apne papa ka number [PHONE_1] likho, PAN [PAN_1] nahi."
    assert redact(text, names=STUDENTS + STAFF_NAMES).redacted_text == expected


# --- false positives -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Class 10 ka test 10:30 baje hai",
        "9:45 baje aana",
        "kal 10:30 se 11:15 tak",
        "class 8-B aur class 9-A",
        "Grade 3 ke 30 students",
        "Class 10 mein 45 bachche hain",
        "2026",
        "Academic year 2025-2026 session",
        "roll no 23",
        "roll number 23, 24 aur 25",
        "95% marks aaye",
        "attendance 87.5 percent",
        "page 123 kholo",
        "page number 45, exercise 3.4, question 12",
        "chapter 12 ka 2nd para",
        "fees ₹1,50,000 hai",
        "date 15-08-2026",
        "15/08/2026 ko chhutti hai",
        "100 pe call karo",
        "1098 child helpline",
        "batch 2026-27",
        "kamra 204, block B",
        "कक्षा १० में ९:४५ बजे आना",
        "पेज १२३ खोलो",
        "",
    ],
)
def test_no_false_positives_on_school_numbers(text: str) -> None:
    assert_unchanged(text, names=STUDENTS + STAFF_NAMES)


# --- placeholders and mapping --------------------------------------------------------------------------------


def test_same_value_gets_the_same_placeholder_and_numbering_follows_first_appearance() -> None:
    text = "9876543210, 91234 56789, phir 98765 43210, aur +91 98765-43210. Email a@b.in, c@d.in, a@b.in"
    result = redact(text)
    assert result.redacted_text == (
        "[PHONE_1], [PHONE_2], phir [PHONE_1], aur [PHONE_1]. Email [EMAIL_1], [EMAIL_2], [EMAIL_1]"
    )
    assert result.counts == {"PHONE": 2, "EMAIL": 2}


def test_mapping_keeps_the_first_written_form() -> None:
    result = redact("98765 43210 ya 9876543210")
    assert result.mapping.value("[PHONE_1]") == "98765 43210"
    assert "[PHONE_1]" in result.mapping
    assert "[PHONE_2]" not in result.mapping
    with pytest.raises(KeyError):
        result.mapping.value("[PHONE_2]")


def test_unredact_round_trip() -> None:
    text = "Riya (9876543210, riya@gmail.com) aur Aarav (2345 6789 0123, ABCDE1234F) ka data"
    result = redact(text, names=STUDENTS)
    assert result.redacted_text != text
    assert unredact(result.redacted_text, result.mapping) == text


def test_restore_is_exact_even_when_one_value_is_written_two_ways() -> None:
    text = "98765 43210 ya 9876543210, RIYA ya riya"
    result = redact(text, names=STUDENTS)
    assert result.redacted_text == "[PHONE_1] ya [PHONE_1], [STUDENT_1] ya [STUDENT_1]"
    assert result.restore(0, len(result.redacted_text)) == text
    # unredact only has the placeholder, so every [PHONE_1] becomes the first written form.
    assert unredact(result.redacted_text, result.mapping) == "98765 43210 ya 98765 43210, RIYA ya RIYA"


def test_unredact_a_quote_from_llm_output() -> None:
    result = redact("Riya ne kaha mera number 9876543210 hai", names=STUDENTS)
    quote = "[STUDENT_1] ne kaha mera number [PHONE_1]"
    assert unredact(quote, result.mapping) == "Riya ne kaha mera number 9876543210"


def test_unredact_leaves_unknown_placeholders_alone() -> None:
    result = redact("9876543210")
    assert unredact("[PHONE_1] and [PHONE_7] and [STUDENT_1]", result.mapping) == (
        "9876543210 and [PHONE_7] and [STUDENT_1]"
    )


def test_grounding_maps_a_redacted_quote_back_to_original_offsets() -> None:
    text = "Teacher: Riya, apna number 98765 43210 batao. Riya: ji, 98765 43210."
    result = redact(text, names=STUDENTS)
    quote = "[STUDENT_1]: ji, [PHONE_1]"
    start = result.redacted_text.index(quote)
    original_start, original_end = result.to_original_range(start, start + len(quote))
    assert text[original_start:original_end] == "Riya: ji, 98765 43210"
    assert result.restore(start, start + len(quote)) == "Riya: ji, 98765 43210"


def test_a_range_cutting_into_a_placeholder_expands_to_the_whole_value() -> None:
    text = "abc 9876543210 xyz"
    result = redact(text)
    assert result.redacted_text == "abc [PHONE_1] xyz"
    assert result.to_original_range(6, 8) == (4, 14)  # "HO" inside [PHONE_1]
    assert result.to_original_range(0, 3) == (0, 3)
    assert result.to_original_range(13, 17) == (14, 18)
    assert result.to_original_range(4, 4) == (4, 4)


def test_to_original_range_rejects_bad_ranges() -> None:
    result = redact("abc 9876543210")
    for start, end in [(-1, 2), (3, 2), (0, len(result.redacted_text) + 1)]:
        with pytest.raises(ValueError):
            result.to_original_range(start, end)


def test_spans_record_both_offsets() -> None:
    text = "x 9876543210 y riya@gmail.com"
    result = redact(text)
    assert [(s.placeholder, s.kind) for s in result.spans] == [("[PHONE_1]", "PHONE"), ("[EMAIL_1]", "EMAIL")]
    for span in result.spans:
        assert result.redacted_text[span.redacted_start : span.redacted_end] == span.placeholder
        assert text[span.original_start : span.original_end] in ("9876543210", "riya@gmail.com")


def test_extending_a_mapping_keeps_placeholders_stable_across_messages() -> None:
    first = redact("Riya: 9876543210", names=STUDENTS)
    second = redact("Aarav: 91234 56789, Riya: 98765 43210", names=STUDENTS, extend=first.mapping)
    assert second.redacted_text == "[STUDENT_2]: [PHONE_2], [STUDENT_1]: [PHONE_1]"
    assert second.mapping.value("[PHONE_1]") == "9876543210"
    assert first.mapping.placeholders() == ("[STUDENT_1]", "[PHONE_1]")  # the first mapping is not changed


def test_mapping_serialises_for_server_side_storage() -> None:
    result = redact("Riya 9876543210 riya@gmail.com", names=STUDENTS)
    records = result.mapping.to_records()
    restored = RedactionMapping.from_records(records)
    assert restored == result.mapping
    assert unredact(result.redacted_text, restored) == "Riya 9876543210 riya@gmail.com"
    with pytest.raises(ValueError):
        RedactionMapping.from_records([{"placeholder": "PHONE_1", "kind": "PHONE", "key": "x", "value": "x"}])


def test_repr_never_shows_pii() -> None:
    result = redact("Riya 9876543210 riya@gmail.com", names=STUDENTS)
    for shown in (repr(result), str(result), repr(result.mapping), repr(result.spans)):
        assert "9876543210" not in shown
        assert "riya@gmail.com" not in shown
        assert "Riya" not in shown


def test_text_that_already_contains_a_placeholder_is_rejected() -> None:
    with pytest.raises(ValueError, match="placeholder"):
        redact("already masked: [PHONE_1]")


def test_non_string_input_is_rejected() -> None:
    with pytest.raises(TypeError):
        redact(b"9876543210")  # type: ignore[arg-type]  # deliberately wrong type


# --- property: no recognised PII survives --------------------------------------------------------------------

PHONES = ["9876543210", "+91 91234 56789", "08123456789", "७०१२३ ४५६७८", "6000 111 222"]
AADHAARS = ["2345 6789 0123", "876543210987", "५४३२-१०९८-७६५४"]
PANS = ["ABCDE1234F", "pqrst9876z"]  # pragma: allowlist secret
EMAILS = ["riya.sharma@gmail.com", "parent_7@school.edu.in", "aarav at the rate yahoo dot com"]
STUDENT_ALIASES = ["Riya", "रिया", "Aarav Mehta", "Aarav", "आरव"]
FILLER = [
    "Class 10",
    "10:30 baje",
    "9:45",
    "roll no 23",
    "page 45",
    "95%",
    "2026",
    "Grade 3",
    "class 8-B",
    "ka",
    "hai",
    "aur",
    "का",
    "है",
    "Sunita ma'am",
    ",",
    ".",
]
PII = PHONES + AADHAARS + PANS + EMAILS + STUDENT_ALIASES


def _digits(text: str) -> str:
    return re.sub(r"[^0-9]", "", text.translate(_DEVANAGARI_TO_ASCII))


@given(st.lists(st.sampled_from(PII + FILLER), max_size=25))
def test_no_recognised_pii_survives_and_restore_is_exact(pieces: list[str]) -> None:
    text = " ".join(pieces)
    result = redact(text, names=STUDENTS + STAFF_NAMES)
    redacted = result.redacted_text
    normalised = re.sub(r"[ -]", "", redacted.translate(_DEVANAGARI_TO_ASCII))
    for value in PII:
        if value in pieces:
            assert value not in redacted
            if value in PHONES + AADHAARS:
                assert _digits(value)[-10:] not in normalised
    for name in ("Riya", "Aarav", "Mehta"):
        assert name.lower() not in redacted.lower()
    assert "Sunita" in redacted or "Sunita ma'am" not in pieces
    assert result.restore(0, len(redacted)) == text
    # unredact is exact whenever every placeholder stands for a single written form (aliases share a placeholder).
    forms: dict[str, set[str]] = {}
    for span in result.spans:
        forms.setdefault(span.placeholder, set()).add(text[span.original_start : span.original_end])
    if all(len(written) == 1 for written in forms.values()):
        assert unredact(redacted, result.mapping) == text


# --- redact_again: the gateway's safety net on text that may already be redacted ---


def test_redact_again_is_redact_on_plain_text() -> None:
    from sabha_llm.redact import redact_again

    assert redact_again("call 9876543210 today") == redact("call 9876543210 today").redacted_text


def test_redact_again_keeps_existing_placeholders_and_numbers_new_ones_after_them() -> None:
    from sabha_llm.redact import redact_again

    text = (
        "[STUDENT_1] said [PHONE_1] earlier; now call 9876543210 or mail a.b@example.com. Placeholders like [NAME_1]."
    )
    out = redact_again(text)
    assert "[STUDENT_1]" in out and "[NAME_1]" in out and out.count("[PHONE_1]") == 1
    assert "9876543210" not in out and "a.b@example.com" not in out
    assert "[PHONE_2]" in out and "[EMAIL_1]" in out  # never reuses [PHONE_1], which means something else here
    assert redact_again(out) == out  # running it again changes nothing
