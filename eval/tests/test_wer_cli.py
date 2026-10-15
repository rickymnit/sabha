"""wer.py end to end on fictional fixture files: report contents, missing data and targets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from wer import main, target_status

MANIFEST_HEADER = "recording_id,file,type,language_mix,room_type,duration_s,consent_ref,split,annotator,status\n"


def write_gold(gold_dir: Path, rid: str, segments: list[tuple[str, int, int, str]]) -> None:
    gold_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "recording_id": rid,
        "tenant": "demo-school",
        "type": "teaching",
        "language_mix": "hinglish",
        "consent_ref": "CONSENT-DEMO",
        "source": {"annotator": "ls-user-1", "annotation_id": 1, "exported_at": "2026-10-15T00:00:00Z"},
        "segments": [{"speaker_role": r, "start_ms": s, "end_ms": e, "text": t} for r, s, e, t in segments],
    }
    (gold_dir / f"{rid}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def write_system(hyp_dir: Path, rid: str, utterances: list[tuple[str, str, int, int, str]]) -> None:
    hyp_dir.mkdir(parents=True, exist_ok=True)
    doc = {"utterances": [{"role": r, "speaker_label": sp, "start_ms": s, "end_ms": e, "text": t}
                          for r, sp, s, e, t in utterances]}  # fmt: skip
    (hyp_dir / f"{rid}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def setup(tmp_path: Path) -> Path:
    write_gold(tmp_path / "gold", "lesson-1", [
        ("teacher", 0, 4000, "आज हम photosynthesis पढ़ेंगे"),
        ("silence", 4000, 6000, ""),
        ("students", 6000, 7000, "yes ma'am"),
    ])  # fmt: skip
    write_gold(tmp_path / "gold", "lesson-2", [("teacher", 0, 3000, "[student] अपनी copy दिखाओ")])
    write_system(tmp_path / "hyp", "lesson-1", [
        ("teacher", "S0", 0, 4000, "aaj hum photosynthesis padhenge"),
        ("students", "S1", 6000, 7000, "yes mam"),
    ])  # fmt: skip
    write_system(tmp_path / "hyp", "lesson-2", [("teacher", "S0", 0, 3000, "Aman अपनी copy दिखाओ")])
    (tmp_path / "manifest.csv").write_text(
        MANIFEST_HEADER
        + "lesson-1,lesson-1.wav,teaching,hinglish,classroom,7,C1,holdout,a1,completed\n"
        + "lesson-2,lesson-2.wav,teaching,hindi,classroom,3,C2,holdout,a1,completed\n"
        + "lesson-3,lesson-3.wav,teaching,hindi,lab,60,C3,dev,a1,completed\n",
        encoding="utf-8",
    )
    return tmp_path


def run(base: Path, *extra: str) -> tuple[int, dict[str, Any], str]:
    code = main([
        "--hyp-dir", str(base / "hyp"), "--gold-dir", str(base / "gold"), "--manifest", str(base / "manifest.csv"),
        "--targets", str(base / "targets.yaml"), "--out-dir", str(base / "reports"), *extra,
    ])  # fmt: skip
    report_json = next((base / "reports").glob("wer-*.json"))
    report_md = next((base / "reports").glob("wer-*.md"))
    return code, json.loads(report_json.read_text(encoding="utf-8")), report_md.read_text(encoding="utf-8")


def test_scores_only_the_requested_split(setup: Path) -> None:
    code, data, _ = run(setup)
    assert code == 0
    assert [f["recording_id"] for f in data["files"]] == ["lesson-1", "lesson-2"]


def test_transliteration_rescues_hindi_written_in_roman(setup: Path) -> None:
    _, data, _ = run(setup)
    overall = data["overall"]
    assert isinstance(overall, dict)
    # Raw: the Devanagari reference words differ from the Roman hypothesis; transliterated they match.
    assert overall["wer_raw"] > 0
    assert overall["wer_transliterated"] == 0


def test_privacy_token_matches_the_real_name(setup: Path) -> None:
    _, data, _ = run(setup)
    lesson2 = next(f for f in data["files"] if f["recording_id"] == "lesson-2")
    assert lesson2["raw"]["wer"] == 0


def test_targets_not_set_are_reported_as_such(setup: Path) -> None:
    _, _, md = run(setup)
    assert "target not set" in md
    assert "| met |" not in md


def test_missing_system_transcript_makes_the_report_incomplete(setup: Path) -> None:
    (setup / "hyp" / "lesson-2.json").unlink()
    (setup / "targets.yaml").write_text("gate1:\n  wer_raw_max:\n    overall: 0.99\n", encoding="utf-8")
    code, data, md = run(setup)
    assert code == 1
    assert data["missing"] == ["lesson-2"]
    assert "MISSING system transcript: lesson-2" in md
    assert "not assessed" in md
    assert "| met |" not in md  # even though the scored file alone would be under 99%


def test_complete_data_compares_against_targets(setup: Path) -> None:
    (setup / "targets.yaml").write_text(
        "gate1:\n  wer_transliterated_max:\n    overall: 0.10\n  wer_raw_max:\n    overall: 0.10\n", encoding="utf-8"
    )
    _, data, _ = run(setup)
    statuses = {c["metric"]: c["status"] for c in data["targets"]}
    assert statuses["WER transliterated (overall)"] == "met"
    assert statuses["WER raw (overall)"] == "not met"


@pytest.mark.parametrize(
    ("value", "limit", "complete", "expected"),
    [
        (0.1, None, True, "target not set"),
        (None, 0.2, True, "not assessed (data missing)"),
        (0.1, 0.2, False, "not assessed (data missing)"),
        (0.1, 0.2, True, "met"),
        (0.3, 0.2, True, "not met"),
    ],
)
def test_target_status(value: float | None, limit: float | None, complete: bool, expected: str) -> None:
    assert target_status(value, limit, complete=complete) == expected
