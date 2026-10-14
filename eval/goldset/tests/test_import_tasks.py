"""import_tasks.py manifest validation (no network: pure functions and --dry-run).

Audio files here are a few placeholder bytes made in a temp folder; nothing real is used."""

from __future__ import annotations

import json
from pathlib import Path

import import_tasks
import pytest
from goldset_common import (
    LabelStudioClient,
    LabelStudioError,
    audio_path_from_url,
    check_base_url,
    is_personal_access_token,
    local_files_url,
    recording_id_from_audio,
    resolve_connection,
)
from import_tasks import ManifestError, build_task, read_manifest, storage_covers

HEADER = "file,tenant,type,language_mix,room_type,consent_ref"


@pytest.fixture
def audio_dir(tmp_path: Path) -> Path:
    root = tmp_path / "audio"
    for name in ("demo-school/demo-teaching-001.wav", "demo-school/demo-reception-001.mp3", "demo-3.wav"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"placeholder, not audio")
    return root


def write_manifest(tmp_path: Path, *lines: str, header: str = HEADER) -> Path:
    path = tmp_path / "manifest.csv"
    path.write_text("\n".join([header, *lines]) + "\n", encoding="utf-8")
    return path


GOOD_ROWS = (
    "demo-school/demo-teaching-001.wav,demo-school,teaching,hinglish,classroom,CONSENT-DEMO-0001",
    "demo-school/demo-reception-001.mp3,demo-school,reception,english,front_desk,CONSENT-DEMO-0002",
)


def test_valid_manifest(tmp_path: Path, audio_dir: Path) -> None:
    rows, refusals = read_manifest(write_manifest(tmp_path, *GOOD_ROWS), audio_dir)
    assert refusals == []
    assert [r.recording_id for r in rows] == ["demo-teaching-001", "demo-reception-001"]
    task = build_task(rows[0])
    assert task == {
        "data": {
            "audio": "/data/local-files/?d=audio/demo-school/demo-teaching-001.wav",
            "tenant": "demo-school",
            "type": "teaching",
            "language_mix": "hinglish",
            "room_type": "classroom",
            "consent_ref": "CONSENT-DEMO-0001",
        }
    }


def test_columns_in_any_order_and_values_trimmed_and_lowercased(tmp_path: Path, audio_dir: Path) -> None:
    manifest = write_manifest(
        tmp_path,
        " CONSENT-DEMO-0003 , Hinglish ,demo-3.wav, demo-school ,Teaching, Classroom",
        header="consent_ref,language_mix,file,tenant,type,room_type",
    )
    rows, refusals = read_manifest(manifest, audio_dir)
    assert refusals == []
    assert (rows[0].consent_ref, rows[0].language_mix, rows[0].type, rows[0].room_type) == (
        "CONSENT-DEMO-0003",
        "hinglish",
        "teaching",
        "classroom",
    )


@pytest.mark.parametrize("consent", ["", "   "])
def test_missing_consent_ref_refused(tmp_path: Path, audio_dir: Path, consent: str) -> None:
    manifest = write_manifest(tmp_path, GOOD_ROWS[0], f"demo-3.wav,demo-school,teaching,english,classroom,{consent}")
    rows, refusals = read_manifest(manifest, audio_dir)
    assert len(rows) == 1
    assert len(refusals) == 1
    assert refusals[0].line == 3
    assert "consent_ref" in str(refusals[0])


def test_missing_file_refused(tmp_path: Path, audio_dir: Path) -> None:
    manifest = write_manifest(tmp_path, "demo-school/not-there.wav,demo-school,teaching,hindi,classroom,CONSENT-X")
    rows, refusals = read_manifest(manifest, audio_dir)
    assert rows == []
    assert "file not found" in str(refusals[0])


@pytest.mark.parametrize(
    ("file", "reason"),
    [
        ("", "missing file"),
        ("../outside.wav", "plain path inside the audio folder"),
        ("/etc/demo.wav", "plain path inside the audio folder"),
        ("demo-school\\demo-teaching-001.wav", "use / as separator"),
        ("notes.txt", "extension"),
        ("bad name.wav", "cannot be a recording id"),
    ],
)
def test_bad_file_values_refused(tmp_path: Path, audio_dir: Path, file: str, reason: str) -> None:
    (audio_dir / "notes.txt").write_text("x", encoding="utf-8")
    (audio_dir / "bad name.wav").write_bytes(b"x")
    manifest = write_manifest(tmp_path, f"{file},demo-school,teaching,hindi,classroom,CONSENT-X")
    _, refusals = read_manifest(manifest, audio_dir)
    assert reason in str(refusals[0])


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ("demo-3.wav,demo-school,sales,english,classroom,C-1", "type 'sales' is not one of"),
        ("demo-3.wav,demo-school,teaching,tamil,classroom,C-1", "language_mix 'tamil' is not one of"),
        ("demo-3.wav,,teaching,english,classroom,C-1", "missing tenant"),
        ("demo-3.wav,demo school,teaching,english,classroom,C-1", "tenant"),
        ("demo-3.wav,demo-school,teaching,english,,C-1", "room_type"),
        ("demo-3.wav,demo-school,teaching,english,class room,C-1", "room_type"),
    ],
)
def test_bad_values_refused(tmp_path: Path, audio_dir: Path, row: str, reason: str) -> None:
    _, refusals = read_manifest(write_manifest(tmp_path, row), audio_dir)
    assert reason in str(refusals[0])


def test_every_problem_in_a_row_is_reported(tmp_path: Path, audio_dir: Path) -> None:
    _, refusals = read_manifest(write_manifest(tmp_path, "missing.wav,,sales,tamil,classroom,"), audio_dir)
    message = str(refusals[0])
    for part in ("consent_ref", "file not found", "missing tenant", "type", "language_mix"):
        assert part in message


@pytest.mark.parametrize(
    ("header", "problem"),
    [
        ("file,tenant,type,language_mix,room_type", "missing columns: consent_ref"),
        (HEADER + ",notes", "unknown columns: 'notes'"),
        ("file,tenant,type,language_mix,room_type,consent_ref,file", "repeated columns: file"),
    ],
)
def test_wrong_columns_reject_the_whole_manifest(tmp_path: Path, audio_dir: Path, header: str, problem: str) -> None:
    with pytest.raises(ManifestError, match=problem):
        read_manifest(write_manifest(tmp_path, GOOD_ROWS[0], header=header), audio_dir)


def test_empty_manifest_rejected(tmp_path: Path, audio_dir: Path) -> None:
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ManifestError, match="empty"):
        read_manifest(empty, audio_dir)


def test_row_with_wrong_number_of_values_refused(tmp_path: Path, audio_dir: Path) -> None:
    manifest = write_manifest(tmp_path, GOOD_ROWS[0], "demo-3.wav,demo-school,teaching,english,classroom,C-1,extra")
    rows, refusals = read_manifest(manifest, audio_dir)
    assert len(rows) == 1
    assert "7 values" in str(refusals[0])


def test_blank_lines_ignored_and_excel_bom_accepted(tmp_path: Path, audio_dir: Path) -> None:
    path = tmp_path / "bom.csv"
    path.write_text("﻿" + HEADER + "\n\n" + GOOD_ROWS[0] + "\n,,,,,\n", encoding="utf-8")
    rows, refusals = read_manifest(path, audio_dir)
    assert (len(rows), refusals) == (1, [])


def test_duplicate_file_and_recording_id_refused(tmp_path: Path, audio_dir: Path) -> None:
    (audio_dir / "demo-teaching-001.wav").write_bytes(b"x")  # same stem as demo-school/demo-teaching-001.wav
    manifest = write_manifest(
        tmp_path,
        GOOD_ROWS[0],
        "demo-teaching-001.wav,demo-school,teaching,hinglish,classroom,C-2",
        GOOD_ROWS[1],
        GOOD_ROWS[1],
    )
    rows, refusals = read_manifest(manifest, audio_dir)
    assert rows == []
    assert [r.line for r in refusals] == [2, 3, 4, 5]
    assert "recording id 'demo-teaching-001'" in str(refusals[0])
    assert "listed 2 times" in str(refusals[2])


# --- CLI -----------------------------------------------------------------------------------------


def test_dry_run_prints_tasks(tmp_path: Path, audio_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest = write_manifest(tmp_path, *GOOD_ROWS)
    code = import_tasks.main(["--manifest", str(manifest), "--audio-dir", str(audio_dir), "--dry-run"])
    out, err = capsys.readouterr()
    assert code == import_tasks.EXIT_OK
    tasks = json.loads(out)
    assert [t["data"]["audio"] for t in tasks] == [
        "/data/local-files/?d=audio/demo-school/demo-teaching-001.wav",
        "/data/local-files/?d=audio/demo-school/demo-reception-001.mp3",
    ]
    assert "2 task(s) would be imported" in err


def test_one_refused_row_aborts_everything(tmp_path: Path, audio_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest = write_manifest(
        tmp_path, GOOD_ROWS[0], "demo-3.wav,demo-school,teaching,english,classroom,", GOOD_ROWS[1]
    )
    code = import_tasks.main(["--manifest", str(manifest), "--audio-dir", str(audio_dir), "--dry-run"])
    out, err = capsys.readouterr()
    assert code == import_tasks.EXIT_REFUSED
    assert out == ""  # no tasks offered for import
    assert "REFUSED line 3 (demo-3.wav)" in err
    assert "Nothing imported" in err


def test_refusal_happens_before_contacting_label_studio(
    tmp_path: Path, audio_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("LABEL_STUDIO_API_KEY", raising=False)

    def no_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not contact Label Studio")

    monkeypatch.setattr(LabelStudioClient, "request", no_network)
    manifest = write_manifest(tmp_path, "missing.wav,demo-school,teaching,english,classroom,C-1")
    code = import_tasks.main(["--manifest", str(manifest), "--audio-dir", str(audio_dir), "--project", "1"])
    assert code == import_tasks.EXIT_REFUSED
    assert "file not found" in capsys.readouterr().err


def test_project_required_without_dry_run(tmp_path: Path, audio_dir: Path) -> None:
    manifest = write_manifest(tmp_path, *GOOD_ROWS)
    with pytest.raises(SystemExit) as info:
        import_tasks.main(["--manifest", str(manifest), "--audio-dir", str(audio_dir)])
    assert info.value.code == 2


def test_bad_header_exit_code(tmp_path: Path, audio_dir: Path) -> None:
    manifest = write_manifest(tmp_path, GOOD_ROWS[0], header="file,tenant")
    code = import_tasks.main(["--manifest", str(manifest), "--audio-dir", str(audio_dir), "--dry-run"])
    assert code == import_tasks.EXIT_USAGE


# --- helpers shared with export_gold -------------------------------------------------------------


def test_local_files_url_round_trip() -> None:
    url = local_files_url("audio", "Main Campus/demo-1.wav")
    assert url == "/data/local-files/?d=audio/Main%20Campus/demo-1.wav"
    assert audio_path_from_url(url) == "audio/Main Campus/demo-1.wav"
    assert recording_id_from_audio(url) == "demo-1"
    assert recording_id_from_audio("/data/upload/3/abc123-demo-2.mp3") == "abc123-demo-2"


def test_storage_covers() -> None:
    target = "/label-studio/files/audio"
    assert storage_covers([{"path": "/label-studio/files/audio"}], target)
    assert storage_covers([{"path": "/label-studio/files/audio/"}], target)
    assert not storage_covers([{"path": "/label-studio/files/audio-old"}], target)
    assert not storage_covers([{"path": "/label-studio/files/audio/school-a"}], target)
    assert not storage_covers([], target)


def test_token_handling_never_leaks() -> None:
    secret = "0123456789abcdef0123456789abcdef01234567"
    assert secret not in repr(LabelStudioClient("http://localhost:8080", secret))
    assert resolve_connection(None, None, env={"LABEL_STUDIO_API_KEY": secret})[1] == secret
    assert resolve_connection("http://x:1/", "flag-token", env={"LABEL_STUDIO_API_KEY": secret}) == (
        "http://x:1",
        "flag-token",
    )
    with pytest.raises(LabelStudioError) as info:
        resolve_connection(None, None, env={})
    assert "LABEL_STUDIO_API_KEY" in str(info.value)


def test_plain_http_only_to_this_machine() -> None:
    check_base_url("http://localhost:8080")
    check_base_url("http://127.0.0.1:8090")
    check_base_url("https://annotate.example.org")
    with pytest.raises(LabelStudioError):
        check_base_url("http://192.0.2.10:8080")
    check_base_url("http://192.0.2.10:8080", allow_insecure_http=True)


def test_personal_access_token_detection() -> None:
    assert is_personal_access_token("eyJhbGciOiJIUzI1NiJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCJ9.c2lnbmF0dXJl")
    assert not is_personal_access_token("0123456789abcdef0123456789abcdef01234567")
