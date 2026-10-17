"""sabha-asr-transcribe: one WAV through the configured provider (the fake one here)."""

from __future__ import annotations

import json
import wave
from pathlib import Path
from typing import Any

import pytest

from sabha_asr import cli
from sabha_core.settings import Settings

BASE: dict[str, Any] = {
    "app_env": "test",
    "mongo_uri": "mongodb://localhost:27017/?replicaSet=rs0",
    "redis_url": "redis://localhost:6380/0",
    "s3_bucket_audio": "a",
    "s3_bucket_artefacts": "b",
    "s3_bucket_backups": "c",
    "oidc_issuer": "https://auth.example.com",
    "oidc_audience": "https://api.example.com",
    "oidc_client_id": "web",
    "asr_provider": "fake",
}


def write_wav(path: Path, seconds: float, *, rate: int = 16_000, channels: int = 1) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * channels * int(rate * seconds))


@pytest.fixture(autouse=True)
def fake_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda: Settings(_env_file=None, **BASE))  # type: ignore[call-arg]


def test_long_file_is_chunked_and_words_come_out_in_order(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    audio = tmp_path / "lesson.wav"
    write_wav(audio, 70)
    assert cli.main([str(audio)]) == 0
    out, err = capsys.readouterr()
    words = [json.loads(line) for line in out.splitlines()]
    assert words and all(set(w) == {"text", "start_ms", "end_ms", "confidence"} for w in words)
    assert [w["start_ms"] for w in words] == sorted(w["start_ms"] for w in words)
    assert words[-1]["end_ms"] <= 70_000
    assert "provider=fake" in err and "word_timing=approximate" in err and "fallback=None" in err


def test_refuses_audio_that_is_not_16k_mono(tmp_path: Path) -> None:
    stereo = tmp_path / "stereo.wav"
    write_wav(stereo, 1, channels=2)
    with pytest.raises(SystemExit, match="16 kHz mono"):
        cli.main([str(stereo)])
