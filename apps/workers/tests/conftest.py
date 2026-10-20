"""Shared fixtures for the worker tests: the pinned VAD model and a synthetic spoken lesson with known speech times."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from sabha_workers.stages.vad import DEFAULT_MODEL_PATH, SileroVad, fetch_model


def ffmpeg(*args: str) -> None:
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", *args]
    subprocess.run(command, check=True)  # noqa: S603  # fixed test commands; ffmpeg from PATH as in the workers


def duration_ms(path: Path) -> int:
    command = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
    out = subprocess.run(command, check=True, capture_output=True, text=True).stdout  # noqa: S603  # as above
    return round(float(out) * 1000)


@pytest.fixture(scope="session")
def vad() -> SileroVad:
    """The pinned Silero model, fetched once into ~/.cache/sabha/models (the same place `make models` uses)."""
    return SileroVad(fetch_model(DEFAULT_MODEL_PATH))


SENTENCES = (
    "Good morning everyone. Today we will learn how plants make their own food.",
    "Can anyone tell me what chlorophyll does? Think about the colour of a leaf.",
)
SILENCES_MS = (8_000, 6_000, 10_000)  # before, between and after the two sentences


@dataclass(frozen=True)
class SpokenLesson:
    """16 kHz mono WAV: silence, sentence, silence, sentence, silence. `speech_ms` is where each sentence is."""

    wav: Path
    mp3: Path
    total_ms: int
    speech_ms: tuple[tuple[int, int], ...]


@pytest.fixture(scope="session")
def spoken_lesson(tmp_path_factory: pytest.TempPathFactory) -> SpokenLesson:
    folder = tmp_path_factory.mktemp("spoken")
    pieces: list[Path] = []
    for index, text in enumerate(SENTENCES):
        piece = folder / f"sentence{index}.wav"
        ffmpeg("-f", "lavfi", "-i", f"flite=text='{text}':voice=slt", "-ar", "16000", "-ac", "1", str(piece))
        pieces.append(piece)
    lengths = [duration_ms(piece) for piece in pieces]
    silences = [folder / f"silence{index}.wav" for index in range(3)]
    for path, ms in zip(silences, SILENCES_MS, strict=True):
        ffmpeg("-f", "lavfi", "-i", f"anullsrc=r=16000:cl=mono:d={ms / 1000}", "-c:a", "pcm_s16le", str(path))
    order = [silences[0], pieces[0], silences[1], pieces[1], silences[2]]
    inputs = [arg for path in order for arg in ("-i", str(path))]
    joined = "".join(f"[{i}]" for i in range(len(order)))
    wav = folder / "lesson.wav"
    ffmpeg(*inputs, "-filter_complex", f"{joined}concat=n={len(order)}:v=0:a=1", "-ar", "16000", "-ac", "1",
           "-c:a", "pcm_s16le", str(wav))  # fmt: skip
    mp3 = folder / "lesson.mp3"
    ffmpeg("-i", str(wav), "-c:a", "libmp3lame", "-b:a", "64k", str(mp3))
    first = (SILENCES_MS[0], SILENCES_MS[0] + lengths[0])
    second_start = first[1] + SILENCES_MS[1]
    return SpokenLesson(wav, mp3, duration_ms(wav), (first, (second_start, second_start + lengths[1])))
