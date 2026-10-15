"""freeze.py and report.py (P4.2) on fictional fixture files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from freeze import EXIT_FAILED, EXIT_NOT_AVAILABLE, EXIT_OK
from freeze import main as freeze
from manifest import ManifestError, read_manifest
from report import main as report

HEADER = "recording_id,file,type,language_mix,room_type,duration_s,consent_ref,split,annotator,status\n"


def gold(
    rid: str, *, tenant: str = "demo-school", segments: list[dict[str, object]] | None = None
) -> dict[str, object]:
    return {
        "recording_id": rid,
        "tenant": tenant,
        "type": "teaching",
        "language_mix": "hinglish",
        "consent_ref": "CONSENT-DEMO",
        "source": {"annotator": "ls-user-1", "annotation_id": 1, "exported_at": "2026-10-15T00:00:00Z"},
        "segments": segments
        if segments is not None
        else [{"speaker_role": "teacher", "start_ms": 0, "end_ms": 5000, "text": "चलो शुरू करते हैं"}],
    }


@pytest.fixture
def base(tmp_path: Path) -> Path:
    (tmp_path / "gold").mkdir()
    for rid in ("h1", "h2", "d1"):
        (tmp_path / "gold" / f"{rid}.json").write_text(json.dumps(gold(rid), ensure_ascii=False), encoding="utf-8")
    (tmp_path / "manifest.csv").write_text(
        HEADER
        + "h1,h1.wav,teaching,hinglish,classroom,36000,C1,holdout,a1,completed\n"  # 10 h
        + "h2,h2.wav,reception,hindi,front_desk,18000,C2,holdout,a2,completed\n"  # 5 h
        + "d1,d1.wav,teaching,english,lab,3600,C3,dev,a1,completed\n",
        encoding="utf-8",
    )
    (tmp_path / "targets.yaml").write_text("goldset:\n  holdout_hours_min: 15\n", encoding="utf-8")
    return tmp_path


def run_freeze(base: Path, *extra: str) -> int:
    return freeze([
        "--manifest", str(base / "manifest.csv"), "--gold-dir", str(base / "gold"), "--audio-dir", str(base / "audio"),
        "--frozen", str(base / "FROZEN.json"), "--targets", str(base / "targets.yaml"), *extra,
    ])  # fmt: skip


def test_freezes_a_complete_holdout_and_records_hashes(base: Path) -> None:
    assert run_freeze(base) == EXIT_OK
    frozen = json.loads((base / "FROZEN.json").read_text())
    assert frozen["holdout_hours"] == 15.0
    assert frozen["hours_by_language_mix"] == {"hindi": 5.0, "hinglish": 10.0}
    assert [f["recording_id"] for f in frozen["files"]] == ["h1", "h2"]  # dev files are not frozen
    assert all(len(f["gold_sha256"]) == 64 for f in frozen["files"])
    assert "चलो" not in (base / "FROZEN.json").read_text(encoding="utf-8")  # hashes only, never transcript text


def test_refuses_when_the_target_is_not_set(base: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (base / "targets.yaml").write_text("goldset:\n  holdout_hours_min: null\n", encoding="utf-8")
    assert run_freeze(base) == EXIT_FAILED
    assert "set goldset.holdout_hours_min" in capsys.readouterr().out
    assert not (base / "FROZEN.json").exists()


def test_refuses_below_the_hours_target(base: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (base / "targets.yaml").write_text("goldset:\n  holdout_hours_min: 20\n", encoding="utf-8")
    assert run_freeze(base) == EXIT_FAILED
    assert "15.00 h, below the target of 20 h" in capsys.readouterr().out


def test_refuses_an_incomplete_holdout_file(base: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (base / "gold" / "h2.json").unlink()
    assert run_freeze(base) == EXIT_FAILED
    assert "h2 (manifest line 3): no gold transcript" in capsys.readouterr().out


def test_refuses_a_holdout_file_without_labelled_speech(base: Path, capsys: pytest.CaptureFixture[str]) -> None:
    silent = gold("h1", segments=[{"speaker_role": "silence", "start_ms": 0, "end_ms": 5000, "text": ""}])
    (base / "gold" / "h1.json").write_text(json.dumps(silent), encoding="utf-8")
    assert run_freeze(base) == EXIT_FAILED
    assert "no labelled speech" in capsys.readouterr().out


def test_will_not_overwrite_a_freeze_by_accident(base: Path) -> None:
    assert run_freeze(base) == EXIT_OK
    assert run_freeze(base) == EXIT_FAILED
    assert run_freeze(base, "--replace") == EXIT_OK


def test_check_passes_when_nothing_changed(base: Path) -> None:
    run_freeze(base)
    assert run_freeze(base, "--check") == EXIT_OK


def test_check_fails_when_a_holdout_transcript_changes(base: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_freeze(base)
    edited = gold("h1", segments=[{"speaker_role": "teacher", "start_ms": 0, "end_ms": 5000, "text": "edited"}])
    (base / "gold" / "h1.json").write_text(json.dumps(edited), encoding="utf-8")
    assert run_freeze(base, "--check") == EXIT_FAILED
    assert "h1: gold transcript changed after freezing" in capsys.readouterr().out


def test_check_fails_when_the_holdout_membership_changes(base: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_freeze(base)
    manifest = (base / "manifest.csv").read_text().replace("d1,d1.wav,teaching,english,lab,3600,C3,dev",
                                                          "d1,d1.wav,teaching,english,lab,3600,C3,holdout")  # fmt: skip
    (base / "manifest.csv").write_text(manifest)
    assert run_freeze(base, "--check") == EXIT_FAILED
    assert "d1: added to the hold-out after freezing" in capsys.readouterr().out


def test_check_reports_files_not_available_here(base: Path) -> None:
    run_freeze(base)
    (base / "gold" / "h2.json").unlink()
    assert run_freeze(base, "--check") == EXIT_NOT_AVAILABLE


def test_manifest_rejects_a_row_without_consent(tmp_path: Path) -> None:
    path = tmp_path / "manifest.csv"
    path.write_text(HEADER + "x1,x1.wav,teaching,hindi,classroom,60,,holdout,a1,completed\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="consent_ref is empty"):
        read_manifest(path)


def test_report_shows_hours_by_school_and_language(base: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (base / "gold" / "h2.json").write_text(json.dumps(gold("h2", tenant="other-school")), encoding="utf-8")
    args = ["--manifest", str(base / "manifest.csv"), "--gold-dir", str(base / "gold"), "--split", "holdout"]
    assert report(args) == 0
    out = capsys.readouterr().out
    assert "| hinglish | 1 | 10.00 | 10.00 |" in out
    assert "| other-school | 1 | 5.00 | 5.00 |" in out
    assert "| **Total** | 2 | 15.00 | 15.00 |" in out
