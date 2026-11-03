"""Tests for sabha_asr.imported: reading a Google Meet .txt transcript (ADR 0009).

The sample below copies the layout of a real Meet export (BOM, CRLF, header, minute markers, footer). Every name,
company and line in it is fictional.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sabha_asr.assembly import assemble_transcript
from sabha_asr.imported import TranscriptImportError, meeting_start_from_name, parse_meet_transcript
from sabha_core.timemap import Segment, SegmentMap

SAMPLE = "﻿" + "\r\n".join([
    "Nov 2, 2026",
    "Attendance Demo : Example Traders, Indore - Transcript",
    "00:00:04",
    "",
    "Asha Rao: Good morning sir, I am Asha from Brightpath.",
    "Vikram Iyer: Morning.",
    "Asha Rao: Shall I share my screen",
    "and show you the face recognition models?",
    "",
    "00:01:04",
    "",
    "Vikram Iyer: Yes please.",
    "Asha Rao: This one marks five people a second.",
    "",
    "Transcription ended after 00:01:30",
    "",
    "This editable transcript was computer generated and might contain errors. People can also change the text.",
])  # fmt: skip


def test_speakers_become_anonymous_labels_and_their_names_are_kept_apart() -> None:
    transcript = parse_meet_transcript(SAMPLE)
    assert [line.speaker_label for line in transcript.lines] == ["S1", "S2", "S1", "S2", "S1"]
    assert transcript.names == {"S1": "Asha Rao", "S2": "Vikram Iyer"}
    assert transcript.title == "Attendance Demo : Example Traders, Indore"


def test_a_line_without_a_name_continues_the_line_before_it() -> None:
    lines = parse_meet_transcript(SAMPLE).lines
    assert lines[2].text == "Shall I share my screen and show you the face recognition models?"


def test_lines_share_the_time_between_markers_in_order_and_on_the_original_timeline() -> None:
    transcript = parse_meet_transcript(SAMPLE)
    first, *_, last = transcript.lines
    assert first.start_ms == 4_000
    assert transcript.lines[3].start_ms == 64_000  # the second marker starts its block
    assert all(a.end_ms == b.start_ms for a, b in zip(transcript.lines[:2], transcript.lines[1:3], strict=True))
    assert last.end_ms == transcript.duration_ms == 90_000  # "Transcription ended after 00:01:30"
    starts = [w.start_ms for w in transcript.words]
    assert starts == sorted(starts)
    assert all(line.start_ms < line.end_ms for line in transcript.lines)


def test_every_word_of_the_file_is_kept_exactly() -> None:
    transcript = parse_meet_transcript(SAMPLE)
    spoken = " ".join(line.text for line in transcript.lines).split()
    assert [w.text for w in transcript.words] == spoken
    assert all(w.confidence is None for w in transcript.words)


def test_without_an_end_line_the_last_stretch_is_estimated_from_its_words() -> None:
    text = "00:00:00\nAsha Rao: one two three four five\n"
    transcript = parse_meet_transcript(text)
    assert transcript.duration_ms == 5 * 400


def test_the_result_assembles_into_a_valid_transcript() -> None:
    transcript = parse_meet_transcript(SAMPLE)
    whole = SegmentMap((Segment(0, transcript.duration_ms, 0),))
    record = assemble_transcript(transcript.words, transcript.turns, {"S1": "sales_rep", "S2": "customer"}, whole,
                                 asr_model="import:google-meet", word_timing="approximate")  # fmt: skip
    roles = [u["role"] for u in record["utterances"]]
    assert roles == ["sales_rep", "customer", "sales_rep", "customer", "sales_rep"]
    assert record["utterances"][0]["start_ms"] == 4_000


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Asha Rao: hello\nVikram Iyer: hi\n", "no_timestamps"),
        ("Nov 2, 2026\nNotes - Transcript\nAsha Rao: hello\n00:00:10\nVikram Iyer: hi\n", "no_timestamps"),
        ("just some notes\nwith no speakers\n", "not_a_transcript"),
        ("00:00:04\n00:01:00\n", "not_a_transcript"),
        ("00:01:00\nAsha Rao: hello\n00:00:10\nVikram Iyer: hi\n", "not_a_transcript"),
    ],
    ids=["no markers", "speech before the first marker", "no speakers", "markers only", "markers go backwards"],
)
def test_files_it_cannot_place_in_time_are_refused_with_a_code(text: str, code: str) -> None:
    with pytest.raises(TranscriptImportError) as raised:
        parse_meet_transcript(text)
    assert raised.value.code == code


def test_the_meeting_start_comes_from_the_meet_file_name() -> None:
    name = "Attendance Demo _ Example Traders, Indore \u2013 2026_11_02 11_18 IST.txt"
    assert meeting_start_from_name(name) == datetime(2026, 11, 2, 5, 48, tzinfo=UTC)
    assert meeting_start_from_name("meeting notes.txt") is None
    assert meeting_start_from_name("Demo \u2013 2026_13_40 11_18 IST.txt") is None
