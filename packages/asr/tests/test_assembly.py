"""Tests for sabha_asr.assembly: words + turns + roles -> utterances on the ORIGINAL timeline (P3.7).

Golden rule 4: every timestamp a user sees is on the original recording. The fixture recording has 15 s of silence
removed between its two segments, so a wrong remap is off by 15 s and cannot pass by accident.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import jsonschema
import pytest

from sabha_asr.assembly import (
    DEFAULT_LOW_CONFIDENCE_BELOW,
    DEFAULT_SPLIT_SILENCE_MS,
    TRANSCRIPT_VERSION,
    assemble_transcript,
    assemble_utterances,
    load_transcript_schema,
    validate_transcript,
)
from sabha_asr.words import Turn, Word
from sabha_core.timemap import DEFAULT_MERGE_GAP_MS, Segment, SegmentMap

# Speech at original [1000, 5000) and [20000, 26000); compact audio is 10 s with a join at compact 4000.
SEGMENTS = SegmentMap((Segment(1000, 5000, 0), Segment(20_000, 26_000, 4000)))
ROLES = {"T": "teacher", "S": "students"}
WHOLE = [Turn("T", 0, 10_000)]


def w(text: str, start: int, end: int, confidence: float = 0.9) -> Word:
    return Word(text, start, end, confidence)


def spans(utterances: list[Any]) -> list[tuple[str, int, int, str]]:
    return [(u.speaker_label, u.start_ms, u.end_ms, u.text) for u in utterances]


def test_defaults() -> None:
    assert DEFAULT_SPLIT_SILENCE_MS == DEFAULT_MERGE_GAP_MS
    assert DEFAULT_LOW_CONFIDENCE_BELOW == 0.5


def test_original_time_remap_across_a_removed_silence() -> None:
    words = [w("aaj", 500, 900), w("hum", 3500, 3900), w("photosynthesis", 4200, 4800), w("padhenge", 9000, 10_000)]
    utterances = assemble_utterances(words, WHOLE, ROLES, SEGMENTS)
    assert spans(utterances) == [
        ("T", 1500, 4900, "aaj hum"),  # compact 500 -> original 1000 + 500
        ("T", 20_200, 26_000, "photosynthesis padhenge"),  # compact 4200 -> 20000 + 200; the end maps to 26000
    ]
    assert all(u.role == "teacher" for u in utterances)


def test_word_ending_exactly_at_a_join_keeps_its_end_in_the_earlier_segment() -> None:
    (utterance,) = assemble_utterances([w("khatam", 3600, 4000)], WHOLE, ROLES, SEGMENTS)
    assert (utterance.start_ms, utterance.end_ms) == (4600, 5000)  # not 20000: the join belongs to the end of speech


def test_word_straddling_a_join_is_clamped_to_the_segment_holding_its_midpoint() -> None:
    utterances = assemble_utterances([w("aage", 3900, 4300)], WHOLE, ROLES, SEGMENTS)  # midpoint 4100: second segment
    assert spans(utterances) == [("T", 20_000, 20_300, "aage")]


def test_small_or_no_removed_silence_does_not_split() -> None:
    touching = SegmentMap((Segment(0, 2000, 0), Segment(2000, 4000, 2000)))
    short_gap = SegmentMap((Segment(0, 2000, 0), Segment(3000, 5000, 2000)))  # 1 s removed: below the threshold
    words = [w("ek", 1500, 1900), w("do", 2100, 2500)]
    turns = [Turn("T", 0, 4000)]
    assert spans(assemble_utterances(words, turns, ROLES, touching)) == [("T", 1500, 2500, "ek do")]
    assert spans(assemble_utterances(words, turns, ROLES, short_gap)) == [("T", 1500, 3500, "ek do")]
    assert len(assemble_utterances(words, turns, ROLES, short_gap, split_silence_ms=1000)) == 2


def test_speaker_change_mid_segment() -> None:
    turns = [Turn("T", 0, 2000), Turn("S", 2000, 3000), Turn("T", 3000, 10_000)]
    words = [w("kaun", 100, 400), w("batayega", 500, 1000), w("main", 2100, 2400), w("haan", 3100, 3400)]
    utterances = assemble_utterances(words, turns, ROLES, SEGMENTS)
    assert spans(utterances) == [
        ("T", 1100, 2000, "kaun batayega"),
        ("S", 3100, 3400, "main"),
        ("T", 4100, 4400, "haan"),
    ]
    assert [u.role for u in utterances] == ["teacher", "students", "teacher"]


def test_word_with_no_overlapping_turn_goes_to_the_nearest_turn() -> None:
    turns = [Turn("T", 0, 1000), Turn("S", 3000, 4000)]
    words = [w("ek", 200, 600), w("bacha", 1200, 1400), w("do", 3100, 3500)]
    utterances = assemble_utterances(words, turns, ROLES, SEGMENTS)
    assert spans(utterances) == [("T", 1200, 2400, "ek bacha"), ("S", 4100, 4500, "do")]


def test_average_confidence_and_low_confidence_spans() -> None:
    words = [
        w("ek", 0, 100, 0.9),
        w("do", 200, 300, 0.3),
        w("teen", 400, 500, 0.2),
        w("char", 600, 700, 0.95),
        w("paanch", 800, 900, 0.4),
    ]
    (utterance,) = assemble_utterances(words, WHOLE, ROLES, SEGMENTS)
    assert utterance.text == "ek do teen char paanch"
    assert utterance.avg_confidence == pytest.approx((0.9 + 0.3 + 0.2 + 0.95 + 0.4) / 5)
    assert utterance.low_confidence_spans == ((3, 10), (16, 22))
    assert [utterance.text[a:b] for a, b in utterance.low_confidence_spans] == ["do teen", "paanch"]
    (strict,) = assemble_utterances(words, WHOLE, ROLES, SEGMENTS, low_confidence_below=0.95)
    assert strict.low_confidence_spans == ((0, 10), (16, 22))


def test_words_are_ordered_by_time_whatever_the_input_order() -> None:
    words = [w("do", 600, 900), w("ek", 100, 400)]
    assert spans(assemble_utterances(words, WHOLE, ROLES, SEGMENTS)) == [("T", 1100, 1900, "ek do")]


def test_zero_length_word_gets_one_millisecond_inside_its_segment() -> None:
    def span(word: Word) -> tuple[int, int]:
        (utterance,) = assemble_utterances([word], WHOLE, ROLES, SEGMENTS)
        return utterance.start_ms, utterance.end_ms

    assert span(w("haan", 1000, 1000)) == (2000, 2001)
    assert span(w("join", 4000, 4000)) == (20_000, 20_001)  # at a join: the later segment, as in timemap
    assert span(w("bas", 10_000, 10_000)) == (25_999, 26_000)  # at the very end: the last millisecond


def test_bad_inputs() -> None:
    with pytest.raises(ValueError, match="outside"):
        assemble_utterances([w("ghost", 9_900, 10_001)], WHOLE, ROLES, SEGMENTS)
    with pytest.raises(ValueError, match="no role"):
        assemble_utterances([w("ek", 0, 100)], [Turn("X", 0, 1000)], ROLES, SEGMENTS)
    assert assemble_utterances([], [], ROLES, SEGMENTS) == []
    with pytest.raises(ValueError, match="no speech"):
        assemble_utterances([w("ek", 0, 0)], WHOLE, ROLES, SegmentMap(()))


# --- transcript@v1 and its schema ------------------------------------------------------------------------------


def good_transcript() -> dict[str, Any]:
    words = [w("aaj", 500, 900, 0.3), w("hum", 3500, 3900), w("photosynthesis", 4200, 4800)]
    turns = [Turn("T", 0, 4000), Turn("S", 4000, 10_000)]
    return dict(assemble_transcript(words, turns, ROLES, SEGMENTS, asr_model="example-asr@1"))


def test_assembled_transcript_is_valid_json_and_matches_the_schema() -> None:
    doc = json.loads(json.dumps(good_transcript(), ensure_ascii=False))
    assert doc["version"] == TRANSCRIPT_VERSION == "transcript@v1"
    assert doc["timeline"] == "original"
    assert doc["word_count"] == 3
    assert doc["utterances"][0] == {
        "role": "teacher",
        "speaker_label": "T",
        "start_ms": 1500,
        "end_ms": 4900,
        "text": "aaj hum",
        "avg_confidence": 0.6,
        "low_confidence_spans": [[0, 3]],
    }
    validate_transcript(doc)
    jsonschema.Draft202012Validator.check_schema(load_transcript_schema())
    jsonschema.validate(doc, load_transcript_schema(), cls=jsonschema.Draft202012Validator)


def test_empty_transcript_is_valid() -> None:
    doc = dict(assemble_transcript([], [], ROLES, SEGMENTS, asr_model="example-asr@1"))
    validate_transcript(doc)
    jsonschema.validate(doc, load_transcript_schema(), cls=jsonschema.Draft202012Validator)


def mutate(path: tuple[str | int, ...], value: Any) -> dict[str, Any]:
    doc = copy.deepcopy(good_transcript())
    target: Any = doc
    for key in path[:-1]:
        target = target[key]
    if value is DELETE:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return doc


DELETE = object()

# Rules both the JSON schema and the code enforce.
SCHEMA_VIOLATIONS = [
    pytest.param(("version",), "transcript@v2", id="wrong-version"),
    pytest.param(("timeline",), "compact", id="compact-timeline"),
    pytest.param(("asr_model",), "", id="blank-model"),
    pytest.param(("word_count",), -1, id="negative-word-count"),
    pytest.param(("word_count",), 2.5, id="fractional-word-count"),
    pytest.param(("extra",), 1, id="unknown-top-level-key"),
    pytest.param(("utterances",), DELETE, id="missing-utterances"),
    pytest.param(("utterances", 0, "start_ms"), -1, id="negative-start"),
    pytest.param(("utterances", 0, "start_ms"), 1.5, id="fractional-start"),
    pytest.param(("utterances", 0, "end_ms"), True, id="boolean-end"),
    pytest.param(("utterances", 0, "text"), "  ", id="blank-text"),
    pytest.param(("utterances", 0, "role"), "", id="blank-role"),
    pytest.param(("utterances", 0, "speaker_label"), DELETE, id="missing-speaker"),
    pytest.param(("utterances", 0, "avg_confidence"), 1.5, id="confidence-above-one"),
    pytest.param(("utterances", 0, "low_confidence_spans"), [[0]], id="span-not-a-pair"),
    pytest.param(("utterances", 0, "low_confidence_spans"), [[-1, 2]], id="negative-span"),
    pytest.param(("utterances", 0, "student_id"), "x", id="unknown-utterance-key"),
]

# Rules JSON Schema cannot express; only validate_transcript enforces them (the schema's description lists them).
CODE_ONLY_VIOLATIONS = [
    pytest.param(("utterances", 0, "end_ms"), 1000, id="end-before-start"),
    pytest.param(("utterances", 0, "end_ms"), 1500, id="zero-length-utterance"),
    pytest.param(("utterances", 0, "low_confidence_spans"), [[2, 2]], id="empty-span"),
    pytest.param(("utterances", 0, "low_confidence_spans"), [[0, 99]], id="span-past-text"),
    pytest.param(("utterances", 0, "low_confidence_spans"), [[4, 6], [0, 3]], id="spans-out-of-order"),
    pytest.param(("utterances", 1, "start_ms"), 1000, id="utterances-out-of-order"),
]


@pytest.mark.parametrize(("path", "value"), SCHEMA_VIOLATIONS)
def test_schema_and_code_both_reject(path: tuple[str | int, ...], value: Any) -> None:
    doc = mutate(path, value)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, load_transcript_schema(), cls=jsonschema.Draft202012Validator)
    with pytest.raises(ValueError):
        validate_transcript(doc)


@pytest.mark.parametrize(("path", "value"), CODE_ONLY_VIOLATIONS)
def test_code_rejects_what_the_schema_cannot_express(path: tuple[str | int, ...], value: Any) -> None:
    with pytest.raises(ValueError):
        validate_transcript(mutate(path, value))


def test_validator_rejects_non_objects() -> None:
    docs: tuple[object, ...] = (None, [], "transcript")
    for doc in docs:
        with pytest.raises(ValueError):
            validate_transcript(doc)
