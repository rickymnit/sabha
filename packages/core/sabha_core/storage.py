"""Object-storage keys: the only place they are built (golden rules 1 and 3).

Every key starts with the tenant id, so a tenant's objects share one prefix (for erasure, P7.3, and for checking
presigned URLs, P7.4):

- originals (audio bucket):        {tenant_id}/{recording_id}/original/{safe file name}
- pipeline outputs (artefacts):    {tenant_id}/{recording_id}/{stage}@{version}/{name}

Ids are server-generated hex strings and are checked here, so no key can climb out of its prefix ("..", "/").
File names from users are reduced to a safe form that keeps the extension.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from typing import Any

_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_STAGE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_VERSION = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
MAX_FILE_NAME = 100


def _check(value: str, pattern: re.Pattern[str], what: str) -> str:
    if not pattern.match(value) or value in (".", ".."):
        raise ValueError(f"{what} {value!r} cannot be part of a storage key")
    return value


def safe_file_name(name: str) -> str:
    """A storage-safe version of a user's file name: no folders, plain ASCII, at most 100 characters, extension kept.

    A Windows path "C:\\Users\\Asha\\Class 7B (Fractions).M4A" becomes "Class_7B_Fractions.m4a". Names with nothing
    usable left become "recording" plus the extension.
    """
    base = re.split(r"[\\/]", name)[-1]
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    stem, dot, extension = base.rpartition(".")
    if not dot:
        stem, extension = base, ""
    extension = _UNSAFE.sub("", extension).lower()[:10]
    stem = _UNSAFE.sub("_", stem).strip("._-")[: MAX_FILE_NAME - len(extension) - 1] or "recording"
    return f"{stem}.{extension}" if extension else stem


def tenant_prefix(tenant_id: str) -> str:
    return f"{_check(tenant_id, _ID, 'tenant id')}/"


def recording_prefix(tenant_id: str, recording_id: str) -> str:
    """{tenant_id}/{recording_id}/: everything stored for one recording, in either bucket (retention, erasure)."""
    return f"{tenant_prefix(tenant_id)}{_check(recording_id, _ID, 'recording id')}/"


# Audio files among a recording's objects: the original upload and the pipeline's working copies (normalised.wav,
# compact.wav, playback.opus). Retention deletes these and keeps the JSON outputs (transcripts, reports).
AUDIO_SUFFIXES = (".wav", ".opus", ".ogg", ".mp3", ".m4a", ".aac", ".flac", ".webm", ".mp4", ".amr", ".wma")


def is_audio_key(key: str) -> bool:
    return key.lower().endswith(AUDIO_SUFFIXES) or "/original/" in key


def delete_objects(s3: Any, bucket: str, prefix: str, *, only: Callable[[str], bool] | None = None,
                   dry_run: bool = False) -> int:  # fmt: skip
    """Delete the objects under `prefix` (all, or those `only` accepts); returns how many matched. The prefix must
    be a whole recording's or tenant's folder, so nothing outside it can match."""
    if not prefix.endswith("/") or prefix.count("/") < 1:
        raise ValueError(f"{prefix!r} is not a folder prefix")
    keys = [
        obj["Key"]
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
        for obj in page.get("Contents", [])
        if only is None or only(obj["Key"])
    ]
    if not dry_run:
        for start in range(0, len(keys), 1000):  # S3's batch limit
            batch = [{"Key": key} for key in keys[start : start + 1000]]
            s3.delete_objects(Bucket=bucket, Delete={"Objects": batch, "Quiet": True})
    return len(keys)


def original_key(tenant_id: str, recording_id: str, file_name: str) -> str:
    recording = _check(recording_id, _ID, "recording id")
    return f"{tenant_prefix(tenant_id)}{recording}/original/{safe_file_name(file_name)}"


def artefact_prefix(tenant_id: str, recording_id: str, stage: str, version: str) -> str:
    """{tenant_id}/{recording_id}/{stage}@{version}/: a stage's output folder; its presence means the stage ran."""
    recording = _check(recording_id, _ID, "recording id")
    stage, version = _check(stage, _STAGE, "stage"), _check(version, _VERSION, "version")
    return f"{tenant_prefix(tenant_id)}{recording}/{stage}@{version}/"


def run_version(version: str, run: int) -> str:
    """The artefact version of a stage's n-th run: "v1" for the first, "v1-run2" for a re-analysis (P2.8)."""
    return version if run <= 1 else f"{version}-run{run}"


def belongs_to(tenant_id: str, key: str) -> bool:
    """True if `key` is under the tenant's prefix (and does not climb out of it)."""
    return key.startswith(tenant_prefix(tenant_id)) and ".." not in key.split("/")
