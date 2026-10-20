"""Voice activity detection with Silero VAD and the compact (speech-only) audio (plan task P3.3).

- The model is Silero VAD's ONNX file (MIT licence), run with onnxruntime: the official Python package needs PyTorch
  (~2 GB), which the CPU worker does not otherwise need. MODEL_URL and MODEL_SHA256 pin the file. It is fetched
  ahead of time, never while a recording is processed: `make models` in development, the CPU worker Dockerfile at
  build time, and a test fixture into the same cache. `python -m sabha_workers.stages.vad fetch <path>` does it.
- `speech_probabilities` reads 16 kHz mono 16-bit PCM in blocks (a 3-hour file is ~700 MB as floats, too much to
  hold) and returns one probability per 32 ms window, as Silero's own OnnxWrapper computes them: 512 samples per
  window plus the previous window's last 64 samples as context, with the model's state carried along.
- `speech_regions` turns probabilities into speech regions with Silero's rule (get_speech_timestamps): speech
  starts at a window >= threshold and ends after `min_silence_ms` below threshold - 0.15; regions shorter than
  `min_speech_ms` are dropped; each start is moved 30 ms earlier (Silero's default speech_pad_ms). Silero's end pad
  and max-length splitting are not used: sabha_core.timemap.build_segment_map adds our end padding and merges.
- Telemetry is off. onnxruntime's Linux build (1.30) contains Microsoft's telemetry client, which uploads to
  mobile.events.data.microsoft.com; `disable_telemetry_events()` did not stop it (strace showed HTTPS connections to
  Microsoft addresses). ORT_DISABLE_TELEMETRY=1, set before onnxruntime is imported, does (no connections). Golden
  rule 12: nothing leaves India without a decision. This module forces it; the worker image sets it too.
- `write_compact` copies the speech samples of the segment map into compact.wav. Segments are whole milliseconds and
  a millisecond is 16 samples, so compact time maps exactly onto samples.
"""

from __future__ import annotations

import hashlib
import os
import sys
import urllib.request
import wave
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from sabha_core.timemap import SegmentMap

os.environ["ORT_DISABLE_TELEMETRY"] = "1"  # before onnxruntime is imported anywhere (module docstring)

MODEL_VERSION = "v6.2.3"
MODEL_URL = f"https://raw.githubusercontent.com/snakers4/silero-vad/{MODEL_VERSION}/src/silero_vad/data/silero_vad.onnx"
# A public checksum of the public model file, not a secret.
MODEL_SHA256 = "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"  # pragma: allowlist secret
DEFAULT_MODEL_PATH = Path.home() / ".cache" / "sabha" / "models" / f"silero_vad-{MODEL_VERSION}.onnx"

SAMPLE_RATE = 16_000
SAMPLES_PER_MS = SAMPLE_RATE // 1000
WINDOW = 512  # samples: 32 ms
WINDOW_MS = WINDOW // SAMPLES_PER_MS
CONTEXT = 64
START_PAD_MS = 30
_BLOCK_WINDOWS = 1875  # 60 s of audio per read


class ModelMissing(FileNotFoundError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_model(path: Path = DEFAULT_MODEL_PATH) -> Path:
    """Download the pinned model to `path` unless it is already there; ValueError if the checksum differs."""
    if path.exists() and _sha256(path) == MODEL_SHA256:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    with urllib.request.urlopen(MODEL_URL, timeout=60) as response, partial.open("wb") as out:  # pinned https URL
        while chunk := response.read(1 << 20):
            out.write(chunk)
    found = _sha256(partial)
    if found != MODEL_SHA256:
        partial.unlink()
        raise ValueError(f"the downloaded VAD model has SHA-256 {found}, expected {MODEL_SHA256}")
    partial.replace(path)
    return path


class SileroVad:
    """One onnxruntime session (one thread, as Silero recommends); safe to reuse for many files, not concurrently."""

    def __init__(self, model_path: Path = DEFAULT_MODEL_PATH) -> None:
        import onnxruntime  # imported here: only the preprocess worker loads the model

        onnxruntime.disable_telemetry_events()  # not enough on its own (module docstring), but costs nothing

        if not model_path.exists():
            raise ModelMissing(f"VAD model not found at {model_path}; run `make models`")
        if _sha256(model_path) != MODEL_SHA256:
            raise ValueError(f"the VAD model at {model_path} is not the pinned file (SHA-256 differs)")
        options = onnxruntime.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        self._session: Any = onnxruntime.InferenceSession(
            str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
        )

    def speech_probabilities(self, wav_path: Path) -> npt.NDArray[np.float32]:
        """One speech probability per 32 ms window of a 16 kHz mono 16-bit WAV (the last window zero-padded)."""
        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros((1, CONTEXT), dtype=np.float32)
        rate = np.array(SAMPLE_RATE, dtype=np.int64)
        out: list[float] = []
        for block in _blocks(wav_path):
            for start in range(0, len(block), WINDOW):
                window = block[start : start + WINDOW]
                if len(window) < WINDOW:
                    window = np.pad(window, (0, WINDOW - len(window)))
                frame = np.concatenate([context, window[np.newaxis, :]], axis=1)
                probability, state = self._session.run(None, {"input": frame, "state": state, "sr": rate})
                context = frame[:, -CONTEXT:]
                out.append(float(probability[0][0]))
        return np.asarray(out, dtype=np.float32)


def _check_format(wav: wave.Wave_read) -> None:
    if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (SAMPLE_RATE, 1, 2):
        raise ValueError("VAD needs 16 kHz mono 16-bit PCM")


def _blocks(wav_path: Path) -> Iterator[npt.NDArray[np.float32]]:
    with wave.open(str(wav_path), "rb") as wav:
        _check_format(wav)
        while frames := wav.readframes(WINDOW * _BLOCK_WINDOWS):
            yield np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def speech_regions(
    probabilities: Sequence[float] | npt.NDArray[np.float32],
    total_ms: int,
    *,
    threshold: float = 0.5,
    min_speech_ms: int = 250,
    min_silence_ms: int = 100,
) -> list[tuple[int, int]]:
    """Speech regions [(start_ms, end_ms), ...] from per-window probabilities (module docstring)."""
    low = max(threshold - 0.15, 0.01)
    regions: list[tuple[int, int]] = []
    start: int | None = None
    silence_from: int | None = None  # where a possible end of speech began
    for index, probability in enumerate(probabilities):
        now = index * WINDOW_MS
        if probability >= threshold:
            silence_from = None
            if start is None:
                start = now
        elif start is not None and probability < low:
            if silence_from is None:
                silence_from = now
            if now - silence_from >= min_silence_ms:
                if silence_from - start > min_speech_ms:
                    regions.append((start, silence_from))
                start, silence_from = None, None
    if start is not None and total_ms - start > min_speech_ms:
        regions.append((start, total_ms))
    return [(max(0, begin - START_PAD_MS), min(end, total_ms)) for begin, end in regions]


def write_compact(source: Path, target: Path, segment_map: SegmentMap) -> int:
    """Copy each segment's samples from `source` into `target`, in order; returns the compact length in ms."""
    with wave.open(str(source), "rb") as wav, wave.open(str(target), "wb") as out:
        _check_format(wav)
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        available = wav.getnframes()
        for segment in segment_map.segments:
            first = segment.orig_start_ms * SAMPLES_PER_MS
            count = segment.duration_ms * SAMPLES_PER_MS
            if first + count > available:
                raise ValueError(f"segment {segment} runs past the end of the audio ({available} samples)")
            wav.setpos(first)
            out.writeframes(wav.readframes(count))
    with wave.open(str(target), "rb") as written:
        frames = written.getnframes()
    expected = segment_map.compact_length_ms * SAMPLES_PER_MS
    if frames != expected:
        raise ValueError(f"compact.wav has {frames} samples, expected {expected}")
    return frames // SAMPLES_PER_MS


def main(argv: Sequence[str]) -> int:
    if len(argv) not in (1, 2) or argv[0] != "fetch":
        print("usage: python -m sabha_workers.stages.vad fetch [path]", file=sys.stderr)
        return 2
    path = fetch_model(Path(argv[1]) if len(argv) == 2 else DEFAULT_MODEL_PATH)
    print(f"Silero VAD {MODEL_VERSION} at {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
