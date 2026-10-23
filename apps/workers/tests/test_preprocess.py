"""The preprocess stage, step 1 (plan task P3.2): probing, the acceptance rules, normalisation and the whole stage.

Fixture files are made with ffmpeg at the start of the session (tones, a test picture), so no audio is committed.
The stage tests run against MongoDB and RustFS through StageRunner.
"""

from __future__ import annotations

import json
import random
import subprocess
import uuid
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.indexes import ensure_indexes
from sabha_core.models import AudioInfo, Recording
from sabha_core.profiles import ConversationType
from sabha_core.repo import SyncTenantRepo
from sabha_core.state import RecordingStatus
from sabha_core.timemap import SegmentMap
from sabha_workers.stages.preprocess import (
    INVALID_AUDIO,
    MAX_DURATION_MS,
    TIMEOUT,
    TOO_LONG,
    TOO_SHORT,
    InvalidAudio,
    Probe,
    S3Originals,
    check,
    make_work,
    normalise,
    parse_probe,
    playback_copy,
    probe,
    run_tool,
    wav_duration_ms,
)
from sabha_workers.stages.runner import DONE_MARKER, PermanentError, S3Artefacts, StageRunner, StageSpec
from sabha_workers.stages.vad import SileroVad

S = RecordingStatus
PREPROCESS = StageSpec("preprocess", working=S.PREPROCESSING, done_to=S.DIARIZING, entry_from=S.UPLOADED)
TONE_S = 35


def ffmpeg(*args: str) -> None:
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", *args]
    subprocess.run(command, check=True)  # noqa: S603  # fixed test commands; ffmpeg from PATH as in the workers


def tone(seconds: int = TONE_S) -> list[str]:
    return ["-f", "lavfi", "-i", f"sine=frequency=300:sample_rate=44100:duration={seconds}"]


@pytest.fixture(scope="session")
def media(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    folder = tmp_path_factory.mktemp("media")
    files = {name: folder / name for name in (
        "tone.mp3", "tone.m4a", "tone.wav", "tone.webm", "video.mp4", "cover.mp3", "short.mp3", "silent_video.mp4",
        "random.mp3", "garbled.mp3", "cover.png",
    )}  # fmt: skip
    ffmpeg(*tone(), "-c:a", "libmp3lame", "-ac", "2", str(files["tone.mp3"]))
    ffmpeg(*tone(), "-c:a", "aac", str(files["tone.m4a"]))
    ffmpeg(*tone(), "-c:a", "pcm_s16le", str(files["tone.wav"]))
    ffmpeg(*tone(), "-c:a", "libopus", str(files["tone.webm"]))
    picture = ["-f", "lavfi", "-i", f"testsrc=size=64x64:rate=5:duration={TONE_S}"]
    ffmpeg(*picture, *tone(), "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(files["video.mp4"]))
    ffmpeg(*picture, "-c:v", "mpeg4", str(files["silent_video.mp4"]))
    ffmpeg("-f", "lavfi", "-i", "color=c=red:size=32x32", "-frames:v", "1", str(files["cover.png"]))
    ffmpeg("-i", str(files["tone.mp3"]), "-i", str(files["cover.png"]), "-map", "0:a", "-map", "1:v", "-c", "copy",
           "-id3v2_version", "3", "-disposition:v", "attached_pic", str(files["cover.mp3"]))  # fmt: skip
    ffmpeg(*tone(10), "-c:a", "libmp3lame", str(files["short.mp3"]))
    id3 = b"ID3\x03\x00\x00\x00\x00\x00\x00"
    files["random.mp3"].write_bytes(id3 + random.Random(7).randbytes(2_000_000))  # noqa: S311  # test data, not security
    # Probes as AMR with "Corrupt bitstream" errors; decoded, it would be 20 minutes of noise.
    files["garbled.mp3"].write_bytes(id3 + b"\xde\xad\xbe\xef" * 500_000)
    return files


# --- Probing and the acceptance rules ---


@pytest.mark.parametrize("name", ["tone.mp3", "tone.m4a", "tone.wav", "tone.webm", "video.mp4", "cover.mp3"])
def test_supported_files_are_accepted(media: dict[str, Path], name: str) -> None:
    probed = probe(media[name])
    check(probed)
    assert abs(probed.duration_ms - TONE_S * 1000) < 100


def test_cover_art_and_video_are_ignored_streams(media: dict[str, Path]) -> None:
    cover = probe(media["cover.mp3"])
    assert (cover.codec, cover.channels, cover.other_streams) == ("mp3", 2, ("video",))
    assert probe(media["video.mp4"]).codec == "aac"


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("random.mp3", None),  # any reason: what ffprobe makes of random bytes varies
        ("garbled.mp3", "the start of the file is damaged"),
        ("silent_video.mp4", "no audio stream"),
    ],
)
def test_bad_files_are_invalid_audio(media: dict[str, Path], name: str, reason: str | None) -> None:
    with pytest.raises(InvalidAudio, match=reason) as caught:
        check(probe(media[name]))
    assert caught.value.code == INVALID_AUDIO


def test_readable_audio_outside_the_limits_says_which_limit(media: dict[str, Path]) -> None:
    with pytest.raises(InvalidAudio, match=r"too short: 10\.0 s; the minimum is 30 s") as short:
        check(probe(media["short.mp3"]))
    assert short.value.code == TOO_SHORT  # people read "too short", not "could not be read"
    with pytest.raises(InvalidAudio, match="too long") as long:
        check(probed(duration_ms=MAX_DURATION_MS + 1))
    assert long.value.code == TOO_LONG


def probed(**change: Any) -> Probe:
    base: dict[str, Any] = {"format_name": "mp3", "codec": "mp3", "sample_rate": 44_100, "channels": 2,
                            "duration_ms": 60_000, "other_streams": ()}  # fmt: skip
    return Probe(**{**base, **change})


def test_the_limits_are_inclusive() -> None:
    check(probed(duration_ms=30_000))
    check(probed(duration_ms=MAX_DURATION_MS))
    with pytest.raises(InvalidAudio, match=r"too long: 3\.00 h"):
        check(probed(duration_ms=MAX_DURATION_MS + 1))


def test_unsupported_codecs_are_refused() -> None:
    with pytest.raises(InvalidAudio, match="unsupported audio codec 'dts'"):
        check(probed(codec="dts"))


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        ([], "no description"),
        ({"streams": [{"codec_type": "video"}], "format": {"duration": "40"}}, "no audio stream"),
        ({"streams": [{"codec_type": "audio", "codec_name": "mp3", "sample_rate": "0", "channels": 1}]},
         "no sample rate"),
        ({"streams": [{"codec_type": "audio", "codec_name": "mp3", "sample_rate": "8000", "channels": 1}],
          "format": {"duration": "N/A"}}, "length of the audio is unknown"),
    ],
)  # fmt: skip
def test_odd_probe_output_is_invalid_audio(data: object, reason: str) -> None:
    with pytest.raises(InvalidAudio, match=reason):
        parse_probe(data)


def test_the_stream_length_wins_over_the_container_length() -> None:
    data = {"streams": [{"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 1,
                         "duration": "40.5"}], "format": {"duration": "90.0", "format_name": "mov,mp4"}}  # fmt: skip
    assert parse_probe(data).duration_ms == 40_500


# --- Safety ---


def test_playlists_cannot_reach_the_network(tmp_path: Path) -> None:
    playlist = tmp_path / "evil.m3u8"
    playlist.write_text("#EXTM3U\n#EXTINF:10,\nhttp://127.0.0.1:9/secret.mp3\n#EXT-X-ENDLIST\n")
    with pytest.raises(InvalidAudio, match="could not read the file"):
        probe(playlist)


def test_a_tool_over_its_time_limit_is_stopped() -> None:
    with pytest.raises(PermanentError) as caught:
        run_tool(["sleep", "5"], 0.2)
    assert caught.value.code == TIMEOUT


# --- Normalisation ---


@pytest.mark.parametrize("name", ["tone.mp3", "tone.webm", "video.mp4", "cover.mp3"])
def test_normalised_audio_is_16k_mono_pcm_on_the_same_timeline(media: dict[str, Path], name: str,
                                                                tmp_path: Path) -> None:  # fmt: skip
    target = tmp_path / "normalised.wav"
    normalise(media[name], target, TONE_S * 1000)
    with wave.open(str(target), "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16_000, 1, 2)
    assert abs(wav_duration_ms(target) - TONE_S * 1000) < 100  # nothing trimmed


def test_the_playback_copy_is_opus(media: dict[str, Path], tmp_path: Path) -> None:
    normalised, playback = tmp_path / "n.wav", tmp_path / "p.opus"
    normalise(media["tone.wav"], normalised, TONE_S * 1000)
    playback_copy(normalised, playback, TONE_S * 1000)
    found = probe(playback)
    assert (found.codec, found.channels) == ("opus", 1)
    assert abs(found.duration_ms - TONE_S * 1000) < 100


# --- The whole stage (MongoDB, RustFS) ---


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"prep_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield name
    mongo_replica_set.drop_database(name)


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]], shared_db: str) -> Database[dict[str, Any]]:
    database = mongo_replica_set[shared_db]
    for collection in ("recordings", "stage_runs", "outbox", "dlq"):
        database[collection].delete_many({})
    return database


class Stage:
    def __init__(self, db: Database[dict[str, Any]], s3_storage: Any, vad: SileroVad, tmp: Path) -> None:
        self.db = db
        self.s3 = s3_storage.client()
        self.artefacts = S3Artefacts(self.s3, "sabha-artefacts")

        def record_audio(tenant_id: str, recording_id: str, duration_ms: int, audio: AudioInfo) -> None:
            recordings = SyncTenantRepo(db, "recordings", tenant_id, Recording)
            recordings.update_one({"_id": recording_id},
                                  {"$set": {"duration_ms": duration_ms, "audio": audio.model_dump()}})  # fmt: skip

        self.work = make_work(S3Originals(self.s3, "sabha-audio"), record_audio, lambda: vad)
        self.runner = StageRunner(db=db, artefacts=self.artefacts, versions={"preprocess": "v1"}, worker="test")
        self.tmp = tmp

    def upload(self, path: Path | None) -> str:
        recording = Recording(type=ConversationType.TEACHING, status=S.UPLOADED, consent_ref="c")
        rid = SyncTenantRepo(self.db, "recordings", "t1", Recording).insert_one(recording).id
        key = f"t1/{rid}/original/lesson"
        if path is not None:
            self.s3.put_object(Bucket="sabha-audio", Key=key, Body=path.read_bytes())
        self.db.recordings.update_one({"_id": rid}, {"$set": {"storage_key": key}})
        return rid

    def run(self, rid: str) -> str:
        return self.runner.run(PREPROCESS, self.work, "t1", rid, attempt=1).result

    def artefacts_path(self, key: str) -> Path:
        path = self.tmp / key.replace("/", "_")
        self.s3.download_file("sabha-artefacts", key, str(path))
        return path

    def recording(self, rid: str) -> dict[str, Any]:
        doc = self.db.recordings.find_one({"_id": rid})
        assert doc is not None
        return doc


@pytest.fixture
def stage(db: Database[dict[str, Any]], s3_storage: Any, vad: SileroVad, tmp_path: Path) -> Stage:
    return Stage(db, s3_storage, vad, tmp_path)


@pytest.mark.integration
def test_the_stage_writes_its_files_maps_the_speech_and_moves_on(stage: Stage, spoken_lesson: Any) -> None:
    rid = stage.upload(spoken_lesson.mp3)
    assert stage.run(rid) == "done"

    recording = stage.recording(rid)
    assert recording["status"] == "DIARIZING"
    assert abs(recording["duration_ms"] - spoken_lesson.total_ms) < 100
    assert recording["audio"] == {"codec": "mp3", "sample_rate": 16_000, "channels": 1}
    prefix = f"t1/{rid}/preprocess@v1/"
    names = ("normalised.wav", "playback.opus", "audio.json", "compact.wav", "segments@v1.json", DONE_MARKER)
    for name in names:
        assert stage.artefacts.exists(prefix + name), name

    def read(name: str) -> bytes:
        body: bytes = stage.s3.get_object(Bucket="sabha-artefacts", Key=prefix + name)["Body"].read()
        return body

    segment_map = SegmentMap.from_json(read("segments@v1.json"))
    assert len(segment_map.segments) == 2  # the two sentences; the silences are cut out but indexed
    summary = json.loads(read("audio.json"))
    assert summary["speech"]["speech_ms"] == segment_map.compact_length_ms
    assert summary["speech"]["vad"]["model"].startswith("silero_vad@")
    compact = stage.artefacts_path(prefix + "compact.wav")
    with wave.open(str(compact), "rb") as wav:
        assert wav.getnframes() == segment_map.compact_length_ms * 16
    original = stage.s3.get_object(Bucket="sabha-audio", Key=recording["storage_key"])["Body"].read()
    assert original == spoken_lesson.mp3.read_bytes()  # never modified
    (run,) = stage.db.stage_runs.find({"recording_id": rid})
    assert run["meta"]["speech_ms"] == segment_map.compact_length_ms


@pytest.mark.integration
def test_a_recording_without_speech_asks_for_review(stage: Stage, media: dict[str, Path]) -> None:
    rid = stage.upload(media["cover.mp3"])  # a 35 s tone: valid audio, no speech
    assert stage.run(rid) == "needs_review"
    recording = stage.recording(rid)
    assert (recording["status"], recording["status_reason"]) == ("NEEDS_REVIEW", "no_speech")
    assert recording["duration_ms"] > 0  # recorded before the review was asked for
    prefix = f"t1/{rid}/preprocess@v1/"
    assert stage.artefacts.exists(prefix + "playback.opus")  # so a reviewer can listen
    assert not stage.artefacts.exists(prefix + "compact.wav") and not stage.artefacts.exists(prefix + DONE_MARKER)
    assert stage.db.dlq.count_documents({"recording_id": rid}) == 0  # a person decides; nothing to replay


@pytest.mark.integration
@pytest.mark.parametrize(("name", "code"), [("garbled.mp3", INVALID_AUDIO), ("short.mp3", TOO_SHORT),
                                            (None, "missing_original")])  # fmt: skip
def test_bad_input_fails_at_once_with_a_dead_letter(stage: Stage, media: dict[str, Path], name: str | None,
                                                    code: str) -> None:  # fmt: skip
    rid = stage.upload(media[name] if name else None)
    assert stage.run(rid) == "failed"
    recording = stage.recording(rid)
    assert (recording["status"], recording["status_reason"]) == ("FAILED", code)
    (letter,) = stage.db.dlq.find({"recording_id": rid})
    assert letter["error_code"] == code and letter["attempts"] == 1
    assert not stage.artefacts.exists(f"t1/{rid}/preprocess@v1/normalised.wav")
