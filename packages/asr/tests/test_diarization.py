"""The diarization interface (plan task P3.4a): labels, clamping, input checks, telemetry, and the real model.

The real pyannote test needs the optional install (`make setup-speech`) and the model (`make models-speech`); it is
skipped where they are missing, as in CI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from sabha_asr.diarization import DEFAULT_MODEL_DIR, PyannoteDiarizer, ScriptedDiarizer, Turn, read_pcm, relabel


def write_wav(path: Path, ms: int, rate: int = 16_000, channels: int = 1) -> Path:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"\x00\x00" * channels * (rate * ms // 1000))
    return path


def test_labels_follow_first_appearance_not_the_models_names() -> None:
    raw = [("SPEAKER_07", 5_000, 6_000), ("SPEAKER_02", 0, 4_000), ("SPEAKER_07", 4_000, 5_000)]
    assert relabel(raw, 10_000) == [Turn("S0", 0, 4_000), Turn("S1", 4_000, 5_000), Turn("S1", 5_000, 6_000)]


def test_turns_are_clamped_to_the_file_and_empty_ones_dropped() -> None:
    raw = [("a", -50, 300), ("b", 900, 1_200), ("c", 1_000, 1_100)]
    assert relabel(raw, 1_000) == [Turn("S0", 0, 300), Turn("S1", 900, 1_000)]


def test_overlapping_turns_are_kept() -> None:
    raw = [("a", 0, 2_000), ("b", 1_500, 3_000)]
    assert [(t.speaker, t.start_ms) for t in relabel(raw, 3_000)] == [("S0", 0), ("S1", 1_500)]


def test_a_turn_must_have_length() -> None:
    with pytest.raises(ValueError, match="start_ms < end_ms"):
        Turn("S0", 500, 500)


def test_the_scripted_diarizer_records_calls(tmp_path: Path) -> None:
    wav = write_wav(tmp_path / "a.wav", 2_000)
    diarizer = ScriptedDiarizer([("x", 0, 10_000)])
    assert diarizer.diarize(wav, max_speakers=3) == [Turn("S0", 0, 2_000)]
    assert diarizer.calls[0]["max_speakers"] == 3


def test_only_normalised_audio_is_accepted(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="16 kHz mono"):
        read_pcm(write_wav(tmp_path / "s.wav", 100, rate=44_100, channels=2))
    samples, ms = read_pcm(write_wav(tmp_path / "m.wav", 1_250))
    assert (len(samples), ms) == (20_000, 1_250)


def test_a_missing_model_says_how_to_fetch_it(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="make models-speech"):
        PyannoteDiarizer(tmp_path / "nothing-here")


# --- Network (golden rule 12; docs/security/findings.md #8) ---


def test_telemetry_is_forced_off_on_import() -> None:
    assert os.environ["PYANNOTE_METRICS_ENABLED"] == "false"
    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"


def test_only_the_diarization_module_imports_pyannote() -> None:
    # Any other import could run before diarization.py turns pyannote's telemetry off.
    root = Path(__file__).resolve().parents[3]
    offenders = [
        str(path.relative_to(root))
        for folder in ("apps", "packages")
        for path in (root / folder).rglob("*.py")
        if ("import pyannote" in (text := path.read_text(encoding="utf-8")) or "from pyannote" in text)
        and path.name != "diarization.py"
        and path.parent.name != "tests"
        and ".venv" not in path.parts
    ]
    assert offenders == []


# --- The real model (where installed) ---


def flite(path: Path, text: str, voice: str) -> Path:
    command = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"flite=text='{text}':voice={voice}",
               "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(path)]  # fmt: skip
    subprocess.run(command, check=True)  # noqa: S603  # fixed test command
    return path


@pytest.mark.skipif(not (DEFAULT_MODEL_DIR / "config.yaml").exists(), reason="pyannote model not fetched")
def test_pyannote_tells_two_voices_apart(tmp_path: Path) -> None:
    pytest.importorskip("pyannote.audio", reason="optional install: make setup-speech")
    lines = [
        ("Good morning. Today we will talk about the water cycle and why it matters.", "slt"),
        ("Is it the same as evaporation, or is that only one part of it?", "rms"),
        ("Good question. Evaporation is one step. Then the vapour cools and forms clouds.", "slt"),
        ("So the rain we get in the monsoon comes from those clouds?", "rms"),
    ]
    pieces = [flite(tmp_path / f"{i}.wav", text, voice) for i, (text, voice) in enumerate(lines)]
    joined = tmp_path / "dialogue.wav"
    with wave.open(str(joined), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16_000)
        for piece in pieces:
            with wave.open(str(piece), "rb") as part:
                out.writeframes(part.readframes(part.getnframes()))
            out.writeframes(b"\x00\x00" * 8_000)  # 0.5 s between lines
    assert shutil.which("ffmpeg")

    turns = PyannoteDiarizer().diarize(joined)

    assert {t.speaker for t in turns} == {"S0", "S1"}
    longest = sorted(turns, key=lambda t: t.end_ms - t.start_ms, reverse=True)[:4]
    by_start = sorted(longest, key=lambda t: t.start_ms)
    assert [t.speaker for t in by_start] == ["S0", "S1", "S0", "S1"]  # the voices alternate
