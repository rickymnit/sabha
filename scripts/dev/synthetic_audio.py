"""Voice a fictional conversation script (eval/synthetic/*.yaml) with Sarvam text-to-speech, for testing the pipeline.

Usage: uv run python scripts/dev/synthetic_audio.py eval/synthetic/sales_meeting_01.yaml out.mp3

Each line is spoken by its speaker's voice (bulbul:v3), lines are joined with short natural pauses, and quiet room
noise is mixed in so it sounds like a phone on a meeting table. Every word in the scripts is made up, so no consent
or personal data is involved. Costs Sarvam's published text-to-speech price per character (the script prints the
character count). Needs SARVAM_API_KEY and ffmpeg.
"""

from __future__ import annotations

import base64
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
import yaml

from sabha_core.settings import load_settings

MODEL = "bulbul:v3"
SAMPLE_RATE = 22_050


def ffmpeg(*args: str) -> None:
    binary = shutil.which("ffmpeg")
    if binary is None:
        raise SystemExit("ffmpeg is not installed")
    subprocess.run([binary, "-loglevel", "error", "-y", *args], check=True)  # noqa: S603  # fixed arguments; our temp files


def speak(client: httpx.Client, base_url: str, key: str, text: str, voice: str, language: str, out: Path) -> None:
    response = client.post(
        f"{base_url}/text-to-speech",
        headers={"api-subscription-key": key},
        json={
            "text": text,
            "language_code": language,
            "speaker": voice,
            "model": MODEL,
            "speech_sample_rate": SAMPLE_RATE,
        },
    )
    response.raise_for_status()
    out.write_bytes(base64.b64decode(response.json()["audios"][0]))


def main() -> int:
    script_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    script = yaml.safe_load(script_path.read_text(encoding="utf-8"))
    settings = load_settings()
    if settings.sarvam_api_key is None:
        print("SARVAM_API_KEY is not set", file=sys.stderr)
        return 2
    key = settings.sarvam_api_key.get_secret_value()
    chars = sum(len(text) for _, text in script["lines"])
    print(f"{len(script['lines'])} lines, {chars} characters")
    rng = random.Random(1)  # noqa: S311  # the same pauses every run; not security
    with tempfile.TemporaryDirectory() as tmp, httpx.Client(timeout=120) as client:
        parts = []
        for i, (who, text) in enumerate(script["lines"]):
            wav = Path(tmp) / f"{i:03d}.wav"
            speak(client, settings.sarvam_base_url, key, text, script["speakers"][who]["voice"],
                  script["language_code"], wav)  # fmt: skip
            pause = Path(tmp) / f"{i:03d}p.wav"
            ffmpeg(
                "-f",
                "lavfi",
                "-t",
                f"{rng.uniform(0.35, 0.9):.2f}",
                "-i",
                f"anullsrc=r={SAMPLE_RATE}:cl=mono",
                str(pause),
            )
            parts += [wav, pause]
        listing = Path(tmp) / "list.txt"
        listing.write_text("".join(f"file '{p}'\n" for p in parts))
        joined = Path(tmp) / "joined.wav"
        ffmpeg("-f", "concat", "-safe", "0", "-i", str(listing), "-ar", str(SAMPLE_RATE), "-ac", "1", str(joined))
        # Quiet pink noise, like a phone recording a meeting room.
        ffmpeg("-i", str(joined), "-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude=0.012:r={SAMPLE_RATE}",
               "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:normalize=0", "-ac", "1", "-b:a", "96k",
               str(out_path))  # fmt: skip
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
