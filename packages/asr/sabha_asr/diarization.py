"""Speaker diarization ("who spoke when") behind one interface (plan task P3.4a).

`Diarizer.diarize(wav)` takes 16 kHz mono 16-bit PCM (the preprocess stage's compact.wav) and returns speaker turns
on THAT file's timeline, in whole milliseconds. Labels are S0, S1, ... in order of first appearance, so they do not
depend on the model's own naming. Turns may overlap (two people talking at once); P3.4b decides how to mark that.
Mapping turns to the original recording is the stage's job (sabha_core.timemap), not the diarizer's.

Implementations:

- `PyannoteDiarizer`: pyannote.audio 4 with the `pyannote/speaker-diarization-community-1` pipeline (CC-BY-4.0:
  attribution in apps/workers/README.md), pinned to MODEL_REVISION. It runs on CPU now and on a GPU by setting the
  device. The model is fetched ahead of time with a Hugging Face token (`make models-speech`) into a local folder
  and loaded from there: no network while a recording is processed. pyannote.audio and torch are an optional
  install (`sabha-asr[diarization]`), imported only when this class is used.
- `ScriptedDiarizer`: returns given turns; for tests (settings allow it only when APP_ENV=test).
- NVIDIA NeMo Sortformer: not built yet; it needs a GPU (P3.4b compares the two).

Network (golden rule 12). pyannote.audio 4 sends usage telemetry to https://otel.pyannote.ai by default (model and
pipeline loads, each file's duration and speaker counts). This module turns it off before pyannote is imported
(PYANNOTE_METRICS_ENABLED=false), along with Hugging Face Hub telemetry, and loads the model from a local path with
the hub offline. pyannote also imports onnxruntime (speaker embeddings), so onnxruntime's Microsoft telemetry is
turned off here too (ORT_DISABLE_TELEMETRY=1; found with strace). See docs/security/findings.md #7 and #8.
"""

from __future__ import annotations

import os
import sys
import warnings
import wave
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

os.environ["PYANNOTE_METRICS_ENABLED"] = "false"  # before pyannote is imported anywhere (module docstring)
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
# pyannote's speaker embedding code imports onnxruntime, whose Linux build has Microsoft telemetry (findings #7).
os.environ["ORT_DISABLE_TELEMETRY"] = "1"

MODEL_REPO = "pyannote/speaker-diarization-community-1"
MODEL_REVISION = "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee"  # pragma: allowlist secret  (a git commit, not a secret)
MODEL_FILES = ["config.yaml", "embedding/*", "plda/*", "segmentation/*"]
DEFAULT_MODEL_DIR = Path.home() / ".cache" / "sabha" / "models" / f"pyannote-community-1-{MODEL_REVISION[:8]}"
SAMPLE_RATE = 16_000


@dataclass(frozen=True, slots=True)
class Turn:
    speaker: str
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if not 0 <= self.start_ms < self.end_ms:
            raise ValueError(f"a turn needs 0 <= start_ms < end_ms: {self}")


class Diarizer(Protocol):
    @property
    def model_id(self) -> str:
        """Recorded with the output, e.g. 'pyannote/speaker-diarization-community-1@3533c8cf'."""
        ...

    def diarize(self, wav: Path, *, min_speakers: int | None = None, max_speakers: int | None = None) -> list[Turn]: ...


def relabel(raw: Sequence[tuple[str, int, int]], duration_ms: int) -> list[Turn]:
    """Model output (label, start_ms, end_ms) -> sorted turns labelled S0, S1, ... by first appearance; turns are
    clamped to the file and dropped if nothing is left."""
    ordered = sorted(raw, key=lambda item: (item[1], item[2], item[0]))
    names: dict[str, str] = {}
    turns = []
    for label, start, end in ordered:
        start, end = max(0, start), min(end, duration_ms)
        if start >= end:
            continue
        name = names.setdefault(label, f"S{len(names)}")
        turns.append(Turn(name, start, end))
    return turns


def read_pcm(wav: Path) -> tuple[Any, int]:
    """(float32 samples in [-1, 1), duration_ms) of a 16 kHz mono 16-bit WAV."""
    import numpy as np

    with wave.open(str(wav), "rb") as handle:
        if (handle.getframerate(), handle.getnchannels(), handle.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise ValueError("diarization needs 16 kHz mono 16-bit PCM")
        frames = handle.readframes(handle.getnframes())
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    return samples, len(samples) * 1000 // SAMPLE_RATE


class PyannoteDiarizer:
    """pyannote.audio community-1 (module docstring). Load once per worker process; not thread-safe."""

    def __init__(self, model_dir: Path = DEFAULT_MODEL_DIR, device: str = "cpu", batch_size: int = 8) -> None:
        """`batch_size` for segmentation and embeddings: 8 used half the memory of pyannote's 32 on CPU (1.15 GB vs
        2.3 GB peak on 5 minutes of speech) with the same turns and speed."""
        os.environ["HF_HUB_OFFLINE"] = "1"  # the model is local; never reach the hub while processing
        if not (model_dir / "config.yaml").exists():
            raise FileNotFoundError(f"pyannote model not found in {model_dir}; run `make models-speech`")
        with warnings.catch_warnings():
            # torchcodec (pyannote's file decoder) is not used: audio is passed in memory.
            warnings.filterwarnings("ignore", message=r"(?s).*torchcodec is not installed correctly")
            import torch
            from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained(str(model_dir))
        if pipeline is None:
            raise RuntimeError(f"pyannote could not load the pipeline in {model_dir}")
        pipeline.to(torch.device(device))
        pipeline.segmentation_batch_size = batch_size
        pipeline.embedding_batch_size = batch_size
        self._torch: Any = torch
        self._pipeline: Any = pipeline
        self.device = device

    @property
    def model_id(self) -> str:
        return f"{MODEL_REPO}@{MODEL_REVISION[:8]}"

    def diarize(self, wav: Path, *, min_speakers: int | None = None, max_speakers: int | None = None) -> list[Turn]:
        samples, duration_ms = read_pcm(wav)
        audio = {"waveform": self._torch.from_numpy(samples)[None, :], "sample_rate": SAMPLE_RATE}
        output = self._pipeline(audio, min_speakers=min_speakers, max_speakers=max_speakers)
        annotation = output.speaker_diarization
        raw = [
            (str(label), round(segment.start * 1000), round(segment.end * 1000))
            for segment, _, label in annotation.itertracks(yield_label=True)
        ]
        return relabel(raw, duration_ms)


@dataclass
class ScriptedDiarizer:
    """For tests: returns `turns` (clamped to the file) and records each call."""

    turns: list[tuple[str, int, int]]
    model_id: str = "scripted-diarizer@1"
    calls: list[dict[str, Any]] = field(default_factory=list)

    def diarize(self, wav: Path, *, min_speakers: int | None = None, max_speakers: int | None = None) -> list[Turn]:
        _, duration_ms = read_pcm(wav)
        self.calls.append({"wav": wav, "min_speakers": min_speakers, "max_speakers": max_speakers})
        return relabel(self.turns, duration_ms)


def fetch_model(token: str, model_dir: Path = DEFAULT_MODEL_DIR) -> Path:
    """Download the pinned pipeline into `model_dir` (needs a token that accepted the model's conditions)."""
    from huggingface_hub import snapshot_download

    snapshot_download(MODEL_REPO, revision=MODEL_REVISION, token=token, local_dir=model_dir,
                      allow_patterns=MODEL_FILES)  # fmt: skip
    return model_dir


def main(argv: Sequence[str]) -> int:
    """`python -m sabha_asr.diarization fetch [dir]`: the token is HF_TOKEN from the environment or .env."""
    if len(argv) not in (1, 2) or argv[0] != "fetch":
        print("usage: python -m sabha_asr.diarization fetch [dir]", file=sys.stderr)
        return 2
    from sabha_core.settings import get_settings

    token = get_settings().hf_token
    if token is None:
        print("HF_TOKEN is not set (.env); see apps/workers/README.md", file=sys.stderr)
        return 1
    path = fetch_model(token.get_secret_value(), Path(argv[1]) if len(argv) == 2 else DEFAULT_MODEL_DIR)
    print(f"{MODEL_REPO}@{MODEL_REVISION[:8]} at {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
