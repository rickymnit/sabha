"""The preprocess stage, step 1 of 2: check and normalise the uploaded audio (plan task P3.2).

`work(ctx)`:

1. Downloads the original from the audio bucket to a temporary directory. The original object is never changed.
2. Probes it with ffprobe and rejects it (PermanentError, code `invalid_audio`; the detail says why) when it is not
   readable, ffprobe reports errors reading its start (damaged data can be mistaken for a lenient format such as
   AMR and decode to minutes of noise), has no audio stream, uses a codec outside ALLOWED_CODECS, or lasts less
   than 30 s or more than 3 h.
   Only the first audio stream is used: video, cover art (an mp3's embedded picture) and subtitles are ignored.
3. Writes to `{tenant}/{recording}/preprocess@{version}/`:
   - `normalised.wav`: 16 kHz mono 16-bit PCM, high-pass at 80 Hz, EBU R128 loudness normalisation (ffmpeg
     `loudnorm`, one pass, target -23 LUFS). Later stages (VAD, diarization, ASR) read this. One pass does not land
     exactly on the target (a 21-minute lecture came out at -25.9 LUFS); two passes would, at twice the time. ASR
     and VAD need consistent levels, not an exact figure, so one pass is used until the gold set says otherwise.
   - `playback.opus`: a 32 kbps Opus copy of it for the web player (same timeline: nothing is trimmed).
   - `audio.json`: what was probed and the normalised length, for audit and debugging.
4. Records `duration_ms` (from the normalised file's sample count, exact) and `audio` on the recording.

ffmpeg and ffprobe read local files only (`-protocol_whitelist file`, P7.6: a crafted playlist cannot make them
fetch URLs or read other files), never read stdin, and run under a time limit. A file ffmpeg cannot decode is
`invalid_audio`; a run over the time limit is `preprocess_timeout` (permanent: retrying the same file would take as
long again; the dead letter allows a replay).

Step 2 (P3.3, Silero VAD and the segment map) will add to this stage.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import time
import wave
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from sabha_core.models import AudioInfo
from sabha_workers.stages.runner import PermanentError, StageContext, Work

log = logging.getLogger("sabha.workers.preprocess")

MIN_DURATION_MS = 30_000
MAX_DURATION_MS = 3 * 3600 * 1000
SAMPLE_RATE = 16_000
HIGH_PASS_HZ = 80
LOUDNORM = "loudnorm=I=-23:TP=-2:LRA=11"  # EBU R128 target: -23 LUFS
PLAYBACK_BITRATE = "32k"
ALLOWED_CODECS = frozenset(
    {
        "aac", "alac", "amr_nb", "amr_wb", "flac", "mp2", "mp3", "opus", "vorbis", "wmav2",
        "pcm_alaw", "pcm_f32le", "pcm_mulaw", "pcm_s16be", "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_u8",
    }
)  # fmt: skip
PROBE_TIMEOUT_S = 60.0
INVALID_AUDIO = "invalid_audio"
TIMEOUT = "preprocess_timeout"
_SAFE = ["-protocol_whitelist", "file"]  # input option: local files only


def ffmpeg_timeout_s(duration_ms: int) -> float:
    """Generous: two minutes plus real time (ffmpeg runs far faster than real time on these filters)."""
    return 120.0 + duration_ms / 1000


@dataclass(frozen=True, slots=True)
class Probe:
    """The original's first audio stream and length, from ffprobe."""

    format_name: str
    codec: str
    sample_rate: int
    channels: int
    duration_ms: int
    other_streams: tuple[str, ...]
    """Codec types of the streams that are ignored (video, attached pictures, a second audio track, ...)."""

    def audio_info(self) -> AudioInfo:
        return AudioInfo(codec=self.codec, sample_rate=self.sample_rate, channels=self.channels)


class InvalidAudio(PermanentError):
    def __init__(self, detail: str) -> None:
        super().__init__(INVALID_AUDIO, detail)


def _seconds(value: object) -> float | None:
    try:
        seconds = float(str(value))
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def parse_probe(data: object) -> Probe:
    """ffprobe's JSON (-show_format -show_streams) to a Probe; InvalidAudio when there is no usable audio stream."""
    if not isinstance(data, dict):
        raise InvalidAudio("ffprobe gave no description of the file")
    streams = [s for s in data.get("streams", []) if isinstance(s, dict)]
    fmt = data.get("format")
    if not isinstance(fmt, dict):
        fmt = {}
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    if not audio:
        raise InvalidAudio("the file has no audio stream")
    first = audio[0]
    others = tuple(str(s.get("codec_type", "unknown")) for s in streams if s is not first)
    try:
        sample_rate, channels = int(first.get("sample_rate", 0)), int(first.get("channels", 0))
    except (TypeError, ValueError):
        sample_rate, channels = 0, 0
    if sample_rate <= 0 or channels <= 0:
        raise InvalidAudio("the audio stream has no sample rate or channel count")
    seconds = _seconds(first.get("duration", "")) or _seconds(fmt.get("duration", ""))
    if seconds is None:
        raise InvalidAudio("the length of the audio is unknown")
    return Probe(str(fmt.get("format_name", "")), str(first.get("codec_name", "")), sample_rate, channels,
                 round(seconds * 1000), others)  # fmt: skip


def check(probe: Probe) -> None:
    """The acceptance rules (module docstring); InvalidAudio says which one failed."""
    if probe.codec not in ALLOWED_CODECS:
        raise InvalidAudio(f"unsupported audio codec {probe.codec or 'unknown'!r}")
    if probe.duration_ms < MIN_DURATION_MS:
        raise InvalidAudio(f"too short: {probe.duration_ms / 1000:.1f} s; the minimum is {MIN_DURATION_MS // 1000} s")
    if probe.duration_ms > MAX_DURATION_MS:
        hours = MAX_DURATION_MS // 3_600_000
        raise InvalidAudio(f"too long: {probe.duration_ms / 3_600_000:.2f} h; the maximum is {hours} h")


Runner = Callable[[Sequence[str], float], "subprocess.CompletedProcess[bytes]"]


def run_tool(args: Sequence[str], timeout_s: float) -> subprocess.CompletedProcess[bytes]:
    """Run ffmpeg or ffprobe: no stdin, output captured, killed after `timeout_s` (raises PermanentError)."""
    try:
        return subprocess.run(  # noqa: S603  # fixed argument lists; file paths are our own temp files
            list(args), stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout_s, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise PermanentError(TIMEOUT, f"{args[0]} ran for more than {timeout_s:.0f} s") from exc


def _error_text(result: subprocess.CompletedProcess[bytes]) -> str:
    text = result.stderr.decode("utf-8", errors="replace").strip()
    return " ".join(text.split())[-500:] or f"exit code {result.returncode}"


def probe(path: Path, run: Runner = run_tool) -> Probe:
    args = ["ffprobe", "-v", "error", *_SAFE, "-show_format", "-show_streams", "-of", "json", str(path)]
    result = run(args, PROBE_TIMEOUT_S)
    if result.returncode != 0:
        raise InvalidAudio(f"ffprobe could not read the file: {_error_text(result)}")
    if result.stderr.strip():  # with -v error, only errors are printed: a healthy file prints nothing
        raise InvalidAudio(f"the start of the file is damaged: {_error_text(result)}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise InvalidAudio("ffprobe gave no description of the file") from exc
    return parse_probe(data)


def normalise(source: Path, target: Path, duration_ms: int, run: Runner = run_tool) -> None:
    """First audio stream -> 16 kHz mono PCM WAV, high-passed and loudness-normalised."""
    args = [
        "ffmpeg", "-nostdin", "-hide_banner", "-v", "error", *_SAFE, "-i", str(source),
        "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-af", f"highpass=f={HIGH_PASS_HZ},{LOUDNORM}",
        "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", "-f", "wav", "-y", str(target),
    ]  # fmt: skip
    result = run(args, ffmpeg_timeout_s(duration_ms))
    if result.returncode != 0:
        raise InvalidAudio(f"ffmpeg could not decode the audio: {_error_text(result)}")


def playback_copy(source: Path, target: Path, duration_ms: int, run: Runner = run_tool) -> None:
    """The normalised WAV -> a small Opus file for the web player."""
    args = [
        "ffmpeg", "-nostdin", "-hide_banner", "-v", "error", *_SAFE, "-i", str(source),
        "-c:a", "libopus", "-b:a", PLAYBACK_BITRATE, "-application", "voip", "-f", "ogg", "-y", str(target),
    ]  # fmt: skip
    result = run(args, ffmpeg_timeout_s(duration_ms))
    if result.returncode != 0:
        raise PermanentError("playback_encode_failed", _error_text(result))


def wav_duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise PermanentError("normalise_failed", "the normalised file is not 16 kHz mono 16-bit")
        return round(wav.getnframes() * 1000 / SAMPLE_RATE)


class Originals(Protocol):
    def download(self, key: str, path: Path) -> None:
        """Copy the original to `path`; FileNotFoundError when it is not there."""
        ...


class S3Originals:
    """The audio bucket, read only."""

    def __init__(self, s3: Any, bucket: str) -> None:
        self._s3 = s3
        self._bucket = bucket

    def download(self, key: str, path: Path) -> None:
        try:
            self._s3.download_file(self._bucket, key, str(path))
        except self._s3.exceptions.ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                raise FileNotFoundError(key) from exc
            raise


RecordAudio = Callable[[str, str, int, AudioInfo], None]
"""(tenant_id, recording_id, duration_ms, audio): store them on the recording."""


def make_work(originals: Originals, record_audio: RecordAudio, run: Runner = run_tool) -> Work:
    """The preprocess `work` function for StageRunner (module docstring)."""

    def work(ctx: StageContext) -> dict[str, Any]:
        recording = ctx.recording
        if not recording.storage_key:
            raise PermanentError("missing_original", "the recording has no uploaded file")
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="sabha-preprocess-") as tmp:
            folder = Path(tmp)
            original = folder / "original"
            try:
                originals.download(recording.storage_key, original)
            except FileNotFoundError as exc:
                raise PermanentError("missing_original", "the uploaded file is not in storage") from exc
            probed = probe(original, run)
            check(probed)
            normalised, playback = folder / "normalised.wav", folder / "playback.opus"
            normalise(original, normalised, probed.duration_ms, run)
            duration_ms = wav_duration_ms(normalised)
            check(replace(probed, duration_ms=duration_ms))  # the header's length may have been wrong
            playback_copy(normalised, playback, duration_ms, run)
            ctx.artefacts.put_file(ctx.prefix + "normalised.wav", normalised, "audio/wav")
            ctx.artefacts.put_file(ctx.prefix + "playback.opus", playback, "audio/ogg")
            summary = {
                "original": {**asdict(probed), "size_bytes": original.stat().st_size},
                "normalised": {"sample_rate": SAMPLE_RATE, "channels": 1, "duration_ms": duration_ms,
                               "filters": f"highpass=f={HIGH_PASS_HZ},{LOUDNORM}"},
                "playback": {"codec": "opus", "bitrate": PLAYBACK_BITRATE, "size_bytes": playback.stat().st_size},
            }  # fmt: skip
            ctx.artefacts.put(ctx.prefix + "audio.json", json.dumps(summary, indent=2).encode(), "application/json")
        record_audio(ctx.tenant_id, recording.id, duration_ms, probed.audio_info())
        seconds = round(time.monotonic() - started, 1)
        log.info("preprocessed", extra={"recording_id": recording.id, "duration_ms": duration_ms, "seconds": seconds})
        return {"duration_ms": duration_ms, "codec": probed.codec, "processing_s": seconds}

    return work
