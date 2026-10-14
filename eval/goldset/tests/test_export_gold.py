"""export_gold.py on a synthetic Label Studio export (fictional content, no real data)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import export_gold
import jsonschema
import pytest
from export_gold import (
    TaskRefused,
    check_transcript,
    export_tasks,
    load_export,
    seconds_to_ms,
    task_to_transcript,
)

GOLDSET_DIR = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ls_export_sample.json"
SCHEMA = json.loads((GOLDSET_DIR / "transcript.schema.json").read_text(encoding="utf-8"))
EXPORTED_AT = "2026-10-14T06:00:00Z"


@pytest.fixture
def tasks() -> list[dict[str, Any]]:
    return load_export(FIXTURE)


@pytest.fixture
def exported(tasks: list[dict[str, Any]], tmp_path: Path) -> tuple[export_gold.ExportReport, Path]:
    return export_tasks(tasks, tmp_path, EXPORTED_AT), tmp_path


def _read(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _task(tasks: list[dict[str, Any]], task_id: int) -> dict[str, Any]:
    return copy.deepcopy(next(t for t in tasks if t["id"] == task_id))


def _validator() -> jsonschema.Draft202012Validator:
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    return jsonschema.Draft202012Validator(SCHEMA)


# --- output files ------------------------------------------------------------------------------


def test_writes_one_file_per_annotated_task_named_by_audio_stem(exported: tuple[Any, Path]) -> None:
    report, out = exported
    assert sorted(p.name for p in report.written) == ["demo-reception-001.json", "demo-teaching-001.json"]
    assert sorted(p.name for p in out.glob("*.json")) == ["demo-reception-001.json", "demo-teaching-001.json"]
    assert _read(out / "demo-teaching-001.json")["recording_id"] == "demo-teaching-001"


def test_output_validates_against_schema(exported: tuple[Any, Path]) -> None:
    report, _ = exported
    validator = _validator()
    for path in report.written:
        doc = _read(path)
        errors = sorted(validator.iter_errors(doc), key=str)
        assert errors == [], [e.message for e in errors]
        assert check_transcript(doc) == []


def test_metadata_and_source(exported: tuple[Any, Path]) -> None:
    _, out = exported
    doc = _read(out / "demo-teaching-001.json")
    assert doc["tenant"] == "demo-school"
    assert doc["type"] == "teaching"
    assert doc["language_mix"] == "hinglish"
    assert doc["consent_ref"] == "CONSENT-DEMO-0001"
    # The cancelled annotation 501 is ignored; 502 is the only completed one.
    assert doc["source"] == {"annotator": "ls-user-3", "annotation_id": 502, "exported_at": EXPORTED_AT}


def test_times_converted_to_integer_ms_half_away_from_zero(exported: tuple[Any, Path]) -> None:
    _, out = exported
    segments = _read(out / "demo-teaching-001.json")["segments"]
    spans = [(s["speaker_role"], s["start_ms"], s["end_ms"]) for s in segments]
    assert spans == [
        ("teacher", 512, 6000),
        ("students", 6800, 8250),
        ("teacher", 8000, 12346),  # 12.3456 s -> 12345.6 ms -> 12346
        ("silence", 12500, 15001),  # 15.0005 s -> 15000.5 ms -> 15001 (tie goes away from zero)
        ("students", 15200, 17000),
        ("teacher", 17400, 21000),  # 21.0004 s -> 21000.4 ms -> 21000
    ]
    assert all(isinstance(s["start_ms"], int) and isinstance(s["end_ms"], int) for s in segments)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, 0),
        (0.0, 0),
        (1.0005, 1001),
        (2.0004, 2000),
        (0.0015, 2),
        (0.0025, 3),  # half away from zero, not banker's rounding (which would give 2)
        (3599.9995, 3600000),
        (-0.0005, -1),
    ],
)
def test_seconds_to_ms(seconds: float, expected: int) -> None:
    assert seconds_to_ms(seconds) == expected


@pytest.mark.parametrize("bad", [True, None, "1.5", float("nan"), float("inf")])
def test_seconds_to_ms_rejects_non_numbers(bad: Any) -> None:
    with pytest.raises(ValueError):
        seconds_to_ms(bad)


def test_segments_sorted_and_overlaps_kept(exported: tuple[Any, Path]) -> None:
    _, out = exported
    segments = _read(out / "demo-teaching-001.json")["segments"]
    keys = [(s["start_ms"], s["end_ms"], s["speaker_role"]) for s in segments]
    assert keys == sorted(keys)
    # Student turn 6800-8250 overlaps teacher turn 8000-12346; both are kept.
    assert segments[1]["end_ms"] > segments[2]["start_ms"]


def test_text_paired_with_region_by_id(exported: tuple[Any, Path]) -> None:
    _, out = exported
    by_start = {s["start_ms"]: s for s in _read(out / "demo-teaching-001.json")["segments"]}
    assert by_start[512]["text"].startswith("अच्छा, so आज हम photosynthesis")
    assert by_start[6800]["text"] == "sunlight से ma'am"
    assert by_start[8000]["text"] == "हाँ, बिल्कुल. [student], तुम बताओ chlorophyll क्या करता है?"
    assert by_start[15200]["text"] == "[inaudible] green colour देता है"
    assert by_start[12500] == {"speaker_role": "silence", "start_ms": 12500, "end_ms": 15001, "text": ""}


def test_whitespace_collapsed_but_text_otherwise_verbatim(exported: tuple[Any, Path]) -> None:
    _, out = exported
    by_start = {s["start_ms"]: s for s in _read(out / "demo-teaching-001.json")["segments"]}
    assert by_start[17400]["text"] == "very good. Chapter seven खोलो"


def test_ground_truth_annotation_wins(exported: tuple[Any, Path]) -> None:
    _, out = exported
    doc = _read(out / "demo-reception-001.json")
    assert doc["source"]["annotation_id"] == 504
    assert doc["source"]["annotator"] == "ls-user-2"  # completed_by given as an object; no email kept
    assert "example.com" not in json.dumps(doc)
    assert all("NOT THE GROUND TRUTH" not in s["text"] for s in doc["segments"])
    assert [s["speaker_role"] for s in doc["segments"]] == ["other", "receptionist", "caller"]


def test_skips_tasks_without_completed_annotation(exported: tuple[Any, Path]) -> None:
    report, out = exported
    skipped = "\n".join(report.skipped)
    assert "task 103" in skipped and "task 104" in skipped  # none / only cancelled
    assert len(report.skipped) == 2
    assert not (out / "demo-teaching-002.json").exists()
    assert not (out / "demo-teaching-003.json").exists()


def test_refuses_tasks_without_consent_ref(exported: tuple[Any, Path]) -> None:
    report, out = exported
    assert len(report.refused) == 2
    refused = {line.split(" ", 2)[1]: line for line in report.refused}
    assert "consent_ref" in refused["105"]  # whitespace-only consent_ref, annotated
    assert "consent_ref" in refused["106"]  # no consent_ref key, not annotated: consent is checked first
    assert not (out / "demo-teaching-004.json").exists()
    assert not (out / "demo-reception-002.json").exists()


def test_cli_exit_code_and_overwrite(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "gold"
    assert export_gold.main(["--input", str(FIXTURE), "--out-dir", str(out)]) == export_gold.EXIT_REFUSED
    first = (out / "demo-teaching-001.json").read_text(encoding="utf-8")
    err = capsys.readouterr().err
    assert "2 written, 2 skipped, 2 refused" in err

    (out / "demo-teaching-001.json").write_text("{}", encoding="utf-8")
    export_gold.main(["--input", str(FIXTURE), "--out-dir", str(out)])
    assert (out / "demo-teaching-001.json").read_text(encoding="utf-8") == "{}"  # not replaced
    assert "already exists" in capsys.readouterr().err

    export_gold.main(["--input", str(FIXTURE), "--out-dir", str(out), "--overwrite"])
    replaced = json.loads((out / "demo-teaching-001.json").read_text(encoding="utf-8"))
    assert replaced["segments"] == json.loads(first)["segments"]
    assert not list(out.glob(".tmp-*"))


def test_cli_rejects_non_export_json(tmp_path: Path) -> None:
    bad = tmp_path / "not-export.json"
    bad.write_text('{"tasks": []}', encoding="utf-8")
    assert export_gold.main(["--input", str(bad), "--out-dir", str(tmp_path)]) == export_gold.EXIT_USAGE


# --- refusals for broken annotations -------------------------------------------------------------


def _first_completed(task: dict[str, Any]) -> dict[str, Any]:
    return next(a for a in task["annotations"] if not a["was_cancelled"])


def _refusal(task: dict[str, Any]) -> str:
    with pytest.raises(TaskRefused) as info:
        task_to_transcript(task, EXPORTED_AT)
    return str(info.value)


def _result_by(task: dict[str, Any], rid: str, from_name: str) -> dict[str, Any]:
    return next(r for r in _first_completed(task)["result"] if r["id"] == rid and r["from_name"] == from_name)


def test_refuses_speech_region_without_text(tasks: list[dict[str, Any]]) -> None:
    task = _task(tasks, 101)
    _result_by(task, "r-students-1", "transcript")["value"]["text"] = ["   "]
    assert "no transcript" in _refusal(task)


def test_refuses_speech_region_with_no_textarea_result(tasks: list[dict[str, Any]]) -> None:
    task = _task(tasks, 101)
    result = _first_completed(task)["result"]
    result.remove(_result_by(task, "r-students-1", "transcript"))
    assert "at 6.80s" in _refusal(task)


def test_refuses_silence_with_text(tasks: list[dict[str, Any]]) -> None:
    task = _task(tasks, 101)
    _first_completed(task)["result"].append(
        {
            "value": {"start": 12.5, "end": 15.0005, "channel": 0, "text": ["[inaudible]"]},
            "id": "r-silence-1",
            "from_name": "transcript",
            "to_name": "audio",
            "type": "textarea",
        }
    )
    assert "Silence region has text" in _refusal(task)


def test_refuses_text_without_label_region(tasks: list[dict[str, Any]]) -> None:
    task = _task(tasks, 101)
    _first_completed(task)["result"].append(
        {
            "value": {"start": 25.0, "end": 26.0, "channel": 0, "text": ["orphan"]},
            "id": "r-orphan",
            "from_name": "transcript",
            "to_name": "audio",
            "type": "textarea",
        }
    )
    assert "has no speaker label region" in _refusal(task)


@pytest.mark.parametrize("labels", [["Teacher", "Other"], [], ["Principal"]])
def test_refuses_bad_labels(tasks: list[dict[str, Any]], labels: list[str]) -> None:
    task = _task(tasks, 101)
    _result_by(task, "r-teacher-1", "speaker")["value"]["labels"] = labels
    assert "label" in _refusal(task)


def test_refuses_region_that_rounds_to_zero_length(tasks: list[dict[str, Any]]) -> None:
    task = _task(tasks, 101)
    _result_by(task, "r-teacher-1", "speaker")["value"].update({"start": 1.0001, "end": 1.0004})
    assert "ends at or before its start" in _refusal(task)


def test_refuses_results_from_other_tags(tasks: list[dict[str, Any]]) -> None:
    task = _task(tasks, 101)
    _first_completed(task)["result"].append(
        {"id": "c1", "from_name": "quality", "to_name": "audio", "type": "choices", "value": {"choices": ["ok"]}}
    )
    assert "transcript_config.xml" in _refusal(task)


def test_refuses_two_completed_annotations_without_ground_truth(tasks: list[dict[str, Any]]) -> None:
    task = _task(tasks, 102)
    for annotation in task["annotations"]:
        annotation["ground_truth"] = False
    assert "none is marked ground truth" in _refusal(task)


def test_refuses_two_ground_truth_annotations(tasks: list[dict[str, Any]]) -> None:
    task = _task(tasks, 102)
    for annotation in task["annotations"]:
        annotation["ground_truth"] = True
    assert "marked ground truth" in _refusal(task)


def test_refuses_unknown_type_in_task_data(tasks: list[dict[str, Any]]) -> None:
    task = _task(tasks, 101)
    task["data"]["type"] = "sales"
    assert "type" in _refusal(task)


def test_refuses_two_tasks_with_same_recording_id(tasks: list[dict[str, Any]], tmp_path: Path) -> None:
    twin = _task(tasks, 101)
    twin["id"] = 999
    twin["data"]["audio"] = "/data/local-files/?d=audio/other-folder/demo-teaching-001.wav"
    report = export_tasks([_task(tasks, 101), twin], tmp_path, EXPORTED_AT)
    assert report.written == []
    assert len(report.refused) == 2 and all("share recording id" in r for r in report.refused)


# --- schema and hand-written check agree --------------------------------------------------------


def _valid_doc() -> dict[str, Any]:
    return {
        "recording_id": "demo-1",
        "tenant": "demo-school",
        "type": "teaching",
        "language_mix": "english",
        "consent_ref": "CONSENT-DEMO-9",
        "source": {"annotator": "ls-user-1", "annotation_id": 1, "exported_at": EXPORTED_AT},
        "segments": [
            {"speaker_role": "teacher", "start_ms": 0, "end_ms": 1000, "text": "good morning"},
            {"speaker_role": "silence", "start_ms": 1000, "end_ms": 4000, "text": ""},
        ],
    }


def _mutations() -> list[tuple[str, Any]]:
    def seg(i: int, **changes: Any) -> Any:
        def apply(doc: dict[str, Any]) -> None:
            doc["segments"][i].update(changes)

        return apply

    return [
        ("silence with text", seg(1, text="[inaudible]")),
        ("speech without text", seg(0, text=" ")),
        ("role not snake_case", seg(0, speaker_role="Teacher")),
        ("float ms", seg(0, end_ms=1000.5)),
        ("negative start", seg(0, start_ms=-1)),
        ("empty consent", lambda d: d.update(consent_ref=" ")),
        ("missing consent", lambda d: d.pop("consent_ref")),
        ("extra key", lambda d: d.update(room_type="classroom")),
        ("annotator email", lambda d: d["source"].update(annotator="someone@example.com")),
        ("non-UTC time", lambda d: d["source"].update(exported_at="2026-10-14T11:30:00+05:30")),
    ]


def test_valid_doc_passes_both_checks() -> None:
    assert check_transcript(_valid_doc()) == []
    assert list(_validator().iter_errors(_valid_doc())) == []


@pytest.mark.parametrize(("name", "mutate"), _mutations(), ids=[m[0] for m in _mutations()])
def test_schema_and_check_reject_the_same_bad_docs(name: str, mutate: Any) -> None:
    doc = _valid_doc()
    mutate(doc)
    assert list(_validator().iter_errors(doc)), f"schema accepted: {name}"
    assert check_transcript(doc), f"check_transcript accepted: {name}"


def test_check_enforces_rules_the_schema_cannot() -> None:
    reversed_span = _valid_doc()
    reversed_span["segments"][0].update(start_ms=2000, end_ms=1000)
    assert any("less than end_ms" in e for e in check_transcript(reversed_span))

    unsorted = _valid_doc()
    unsorted["segments"].reverse()
    assert any("sorted" in e for e in check_transcript(unsorted))
