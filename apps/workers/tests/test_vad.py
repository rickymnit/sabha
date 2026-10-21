"""Voice activity detection (plan task P3.3): Silero's start/end rule, the pinned model, and compact.wav."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sabha_core.timemap import build_segment_map, stats
from sabha_workers.stages import vad as vad_module
from sabha_workers.stages.preprocess import wav_duration_ms
from sabha_workers.stages.vad import (
    MODEL_SHA256,
    START_PAD_MS,
    WINDOW_MS,
    SileroVad,
    fetch_model,
    speech_regions,
    write_compact,
)

W = WINDOW_MS  # 32 ms per probability


def probs(*runs: tuple[float, int]) -> list[float]:
    """(probability, number of windows), ... -> a flat list."""
    return [p for p, n in runs for _ in range(n)]


# --- The start/end rule (no model) ---


def test_one_region_with_the_start_pulled_earlier() -> None:
    # Silence for 10 windows, speech for 20, silence for 10: speech starts at window 10 and ends where silence begins.
    regions = speech_regions(probs((0.0, 10), (0.9, 20), (0.0, 10)), total_ms=40 * W)
    assert regions == [(10 * W - START_PAD_MS, 30 * W)]


def test_a_dip_shorter_than_min_silence_does_not_end_speech() -> None:
    # Two silent windows (64 ms) inside speech: under min_silence_ms (100), so one region.
    p = probs((0.9, 10), (0.0, 2), (0.9, 10), (0.0, 10))
    assert speech_regions(p, total_ms=32 * W) == [(0, 22 * W)]


def test_between_the_two_thresholds_speech_continues() -> None:
    # 0.4 is under the start threshold (0.5) but over the end threshold (0.35): an ongoing region continues.
    p = probs((0.9, 10), (0.4, 20), (0.0, 10))
    assert speech_regions(p, total_ms=40 * W) == [(0, 30 * W)]
    assert speech_regions(probs((0.4, 30)), total_ms=30 * W) == []  # but it never starts one


def test_short_blips_are_dropped() -> None:
    p = probs((0.0, 10), (0.9, 5), (0.0, 10))  # 160 ms of "speech"
    assert speech_regions(p, total_ms=25 * W) == []
    assert speech_regions(p, total_ms=25 * W, min_speech_ms=100) == [(10 * W - START_PAD_MS, 15 * W)]


def test_speech_running_to_the_end_is_kept_and_clamped() -> None:
    regions = speech_regions(probs((0.0, 5), (0.9, 20)), total_ms=25 * W - 7)  # the last window was padded
    assert regions == [(5 * W - START_PAD_MS, 25 * W - 7)]


def test_the_start_pad_never_goes_below_zero() -> None:
    assert speech_regions(probs((0.9, 20), (0.0, 10)), total_ms=30 * W)[0][0] == 0


# --- The pinned model file ---


def test_a_wrong_download_is_refused_and_not_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bogus = tmp_path / "bogus.onnx"
    bogus.write_bytes(b"not the model")
    monkeypatch.setattr(vad_module, "MODEL_URL", bogus.as_uri())
    target = tmp_path / "models" / "silero.onnx"
    with pytest.raises(ValueError, match="expected " + MODEL_SHA256):
        fetch_model(target)
    assert not target.exists() and not target.with_suffix(".part").exists()


def test_a_changed_model_file_is_refused(tmp_path: Path) -> None:
    changed = tmp_path / "silero.onnx"
    changed.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="not the pinned file"):
        SileroVad(changed)
    with pytest.raises(FileNotFoundError, match="make models"):
        SileroVad(tmp_path / "missing.onnx")


# --- The model on synthetic speech ---


def test_vad_finds_the_two_sentences(vad: SileroVad, spoken_lesson: Any) -> None:
    probabilities = vad.speech_probabilities(spoken_lesson.wav)
    assert len(probabilities) == -(-spoken_lesson.total_ms // W)  # one per 32 ms window, rounded up
    segment_map = build_segment_map(speech_regions(probabilities, spoken_lesson.total_ms), spoken_lesson.total_ms)

    assert len(segment_map.segments) == 2
    for segment, (start, end) in zip(segment_map.segments, spoken_lesson.speech_ms, strict=True):
        assert abs(segment.orig_start_ms - start) <= 400  # flite clips start with ~0.2 s of their own silence
        assert end - 100 <= segment.orig_end_ms <= end + 300 + 250  # the 300 ms end pad, plus window rounding
    totals = stats(segment_map, spoken_lesson.total_ms)
    assert totals["speech_ms"] + totals["silence_ms"] == spoken_lesson.total_ms
    assert totals["longest_silence_ms"] >= 9_000  # the trailing 10 s, minus the end pad


def test_a_silent_file_has_no_speech(vad: SileroVad, tmp_path: Path) -> None:
    silent = tmp_path / "silent.wav"
    with wave.open(str(silent), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16_000)
        out.writeframes(np.zeros(16_000 * 5, dtype="<i2").tobytes())
    assert speech_regions(vad.speech_probabilities(silent), 5_000) == []


def test_vad_refuses_audio_that_was_not_normalised(vad: SileroVad, tmp_path: Path) -> None:
    stereo = tmp_path / "stereo.wav"
    with wave.open(str(stereo), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(44_100)
        out.writeframes(b"\x00" * 1000)
    with pytest.raises(ValueError, match="16 kHz mono"):
        vad.speech_probabilities(stereo)


# --- compact.wav ---


def test_compact_audio_is_exactly_the_segments_samples(spoken_lesson: Any, tmp_path: Path) -> None:
    segment_map = build_segment_map([(8_000, 9_000), (20_000, 20_500)], spoken_lesson.total_ms, end_pad_ms=0)
    compact = tmp_path / "compact.wav"
    assert write_compact(spoken_lesson.wav, compact, segment_map) == 1_500
    with wave.open(str(spoken_lesson.wav), "rb") as original, wave.open(str(compact), "rb") as cut:
        original.setpos(20_000 * 16)
        expected = original.readframes(500 * 16)
        cut.setpos(segment_map.original_to_compact(20_000) * 16)
        assert cut.readframes(500 * 16) == expected  # compact time maps onto the same samples


def test_a_segment_past_the_end_is_refused(spoken_lesson: Any, tmp_path: Path) -> None:
    beyond = build_segment_map([(0, spoken_lesson.total_ms + 5_000)], spoken_lesson.total_ms + 5_000)
    with pytest.raises(ValueError, match="past the end"):
        write_compact(spoken_lesson.wav, tmp_path / "compact.wav", beyond)


def test_a_length_that_is_not_whole_milliseconds_still_maps_to_samples(tmp_path: Path) -> None:
    # Found on a real 18-minute interview: 17,418,682 samples is 1,088,667.6 ms. Rounding the length up made the last
    # segment ask for samples that do not exist.
    odd = tmp_path / "odd.wav"
    with wave.open(str(odd), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16_000)
        out.writeframes(np.ones(16_000 + 10, dtype="<i2").tobytes())  # 1000.625 ms
    total = wav_duration_ms(odd)
    assert total == 1_000
    segment_map = build_segment_map([(500, 990)], total)  # the end pad reaches the very end
    assert segment_map.segments[-1].orig_end_ms == total
    assert write_compact(odd, tmp_path / "compact.wav", segment_map) == 500


# --- Telemetry (golden rule 12; docs/security/findings.md #7) ---


def test_onnxruntime_telemetry_is_forced_off_before_import() -> None:
    import os

    assert os.environ["ORT_DISABLE_TELEMETRY"] == "1"  # set when sabha_workers.stages.vad is imported


def test_only_the_vad_module_imports_onnxruntime() -> None:
    # Any other import could run before vad.py sets ORT_DISABLE_TELEMETRY, and telemetry would be on.
    root = Path(__file__).resolve().parents[3]
    offenders = [
        str(path.relative_to(root))
        for folder in ("apps", "packages")
        for path in (root / folder).rglob("*.py")
        if "onnxruntime" in path.read_text(encoding="utf-8")
        and path.name not in ("vad.py", "test_vad.py")
        and ".venv" not in path.parts
    ]
    assert offenders == []
