"""Creating recordings and their direct-to-storage multipart uploads (plan task P2.1).

The API never touches audio bytes (golden rule 2). It checks the request, records the recording (status CREATED),
starts an S3 multipart upload for `{tenant_id}/{recording_id}/original/<safe name>` (sabha_core.storage) and hands
back presigned URLs, one per part. The browser PUTs each part to its URL, then calls complete (P2.2).

Rules:
- The type must be enabled for the tenant (422 `type_not_enabled`).
- File extension and content type: mp3, m4a, wav, ogg, webm or mp4 with a matching type (422 `unsupported_format`).
- At most UPLOAD_MAX_BYTES, 1 GiB by default (422 `file_too_large`).
- Person and unit must exist in the tenant (422 `unknown_person` / `unknown_unit`).
- Staff upload only their own recordings: the person defaults to the one linked to their user and may not be
  anyone else (403 `person_not_allowed`; 403 `no_linked_person` if none is linked). Other roles may name any
  person in the tenant. Unit-level limits for managers come with the permission matrix (P7.4).
- Fresh part URLs for a resumed upload: only while the recording is CREATED, only part numbers it has, and staff
  only for recordings they created. Another tenant's recording, or a colleague's for staff, is 404.

Every create writes an audit entry (recording.create) in the same transaction as the recording.

Completing (P2.2, `complete`): every part 1..part_count with its ETag; the stored object must have the announced
size (otherwise it is deleted, the upload closed, and 422 `size_mismatch`: start a new recording). The browser's
SHA-256 is stored. CREATED -> UPLOADED goes through sabha_core.state.transition_async. Then:
- the same hash in another recording of the tenant that has not FAILED: duplicate_of is set and the recording is
  held; 409 `duplicate_recording` (with `duplicate_of`) unless `force=true`; calling again with force confirms;
- no consent_ref: awaiting_consent is set; the recording waits (golden rule 9; consent is added in P6.9);
- calling complete again with the same hash returns the current state, so a client may retry safely.
The status change and its outbox event (`recording.uploaded`, with meta.ready) are written in one transaction
(P2.5); the relay starts preprocessing only for a ready recording. Confirming a held duplicate later writes
`recording.ready`.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta
from typing import Annotated, Any

from botocore.exceptions import ClientError
from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from sabha_api.audit import audit
from sabha_api.auth import Principal, Role
from sabha_api.deps import Transactions
from sabha_api.errors import ApiError, ConflictError, ForbiddenError, NotFoundError
from sabha_core.models import AuditEntry, OutboxEvent, Person, Recording, Tenant, Unit, new_id, utc_now
from sabha_core.outbox import READY, record_event_async, record_transition_async
from sabha_core.profiles import ConversationType
from sabha_core.repo import TenantRepo
from sabha_core.settings import Settings
from sabha_core.state import RecordingStatus
from sabha_core.storage import original_key

ROUTE = "POST /v1/recordings"
MAX_PARTS = 10_000  # S3's limit per multipart upload

ALLOWED_FORMATS: dict[str, frozenset[str]] = {
    "mp3": frozenset({"audio/mpeg", "audio/mp3"}),
    "m4a": frozenset({"audio/mp4", "audio/x-m4a", "audio/m4a", "audio/aac"}),
    "wav": frozenset({"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"}),
    "ogg": frozenset({"audio/ogg", "application/ogg"}),
    "webm": frozenset({"audio/webm", "video/webm"}),
    "mp4": frozenset({"video/mp4", "audio/mp4"}),
}


class RecordingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # no id, status or storage key from clients

    type: ConversationType
    person_id: str | None = None
    unit_id: str | None = None
    file_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    size_bytes: int = Field(ge=1)
    content_type: str
    consent_ref: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    recorded_at: datetime | None = None

    @field_validator("content_type")
    @classmethod
    def _media_type(cls, value: str) -> str:
        return value.split(";", 1)[0].strip().lower()  # "audio/webm;codecs=opus" -> "audio/webm"

    @field_validator("consent_ref")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value or None


class PartUrl(BaseModel):
    part_number: int
    url: str


class UploadOut(BaseModel):
    recording_id: str
    status: RecordingStatus
    upload_id: str
    part_size: int
    part_count: int
    parts: list[PartUrl]
    urls_expire_at: datetime


class PartsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_numbers: list[Annotated[int, Field(ge=1, le=MAX_PARTS)]] = Field(min_length=1, max_length=100)


class PartsOut(BaseModel):
    parts: list[PartUrl]
    urls_expire_at: datetime


class TypeNotEnabledError(ApiError):
    status, code, title = 422, "type_not_enabled", "Type not enabled"


class UnsupportedFormatError(ApiError):
    status, code, title = 422, "unsupported_format", "Unsupported format"


class FileTooLargeError(ApiError):
    status, code, title = 422, "file_too_large", "File too large"


class UnknownPersonError(ApiError):
    status, code, title = 422, "unknown_person", "Unknown person"


class UnknownUnitError(ApiError):
    status, code, title = 422, "unknown_unit", "Unknown unit"


class PersonNotAllowedError(ForbiddenError):
    code, title = "person_not_allowed", "Person not allowed"


class NoLinkedPersonError(ForbiddenError):
    code, title = "no_linked_person", "No linked person"


class UploadNotOpenError(ConflictError):
    code, title = "upload_not_open", "Upload not open"


class InvalidPartNumberError(ApiError):
    status, code, title = 422, "invalid_part_number", "Invalid part number"


class StorageError(Exception):
    """S3 refused a request; `code` is S3's error code (e.g. InvalidPart, NoSuchUpload)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class UploadStorage:
    """The audio bucket, through the API's boto3 client. Only metadata calls: no audio passes through the API."""

    def __init__(self, s3: Any, settings: Settings) -> None:
        self._s3 = s3
        self._bucket = settings.s3_bucket_audio
        self._expiry = settings.upload_url_expiry_s

    async def start(self, key: str, content_type: str) -> str:
        response = await asyncio.to_thread(
            self._s3.create_multipart_upload, Bucket=self._bucket, Key=key, ContentType=content_type
        )
        return str(response["UploadId"])

    async def abort(self, key: str, upload_id: str) -> None:
        await asyncio.to_thread(self._s3.abort_multipart_upload, Bucket=self._bucket, Key=key, UploadId=upload_id)

    async def complete(self, key: str, upload_id: str, parts: list[PartIn]) -> None:
        listing = [{"PartNumber": p.part_number, "ETag": p.etag} for p in sorted(parts, key=lambda p: p.part_number)]
        try:
            await asyncio.to_thread(
                self._s3.complete_multipart_upload,
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": listing},
            )
        except ClientError as exc:
            raise StorageError(str(exc.response.get("Error", {}).get("Code", "unknown"))) from exc

    async def size(self, key: str) -> int | None:
        """The object's size in bytes, or None if it does not exist."""
        try:
            head = await asyncio.to_thread(self._s3.head_object, Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise
        return int(head["ContentLength"])

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._s3.delete_object, Bucket=self._bucket, Key=key)

    def part_urls(self, key: str, upload_id: str, numbers: list[int]) -> tuple[list[PartUrl], datetime]:
        expires = utc_now() + timedelta(seconds=self._expiry)
        urls = [
            PartUrl(
                part_number=n,
                url=self._s3.generate_presigned_url(
                    "upload_part",
                    Params={"Bucket": self._bucket, "Key": key, "UploadId": upload_id, "PartNumber": n},
                    ExpiresIn=self._expiry,
                ),
            )
            for n in numbers
        ]
        return urls, expires


def _check_format(file_name: str, content_type: str) -> None:
    extension = file_name.rpartition(".")[2].lower() if "." in file_name else ""
    allowed = ALLOWED_FORMATS.get(extension)
    if allowed is None:
        raise UnsupportedFormatError(f"Upload {', '.join(ALLOWED_FORMATS)} files.")
    if content_type not in allowed:
        raise UnsupportedFormatError(f"A .{extension} file should have content type {' or '.join(sorted(allowed))}.")


async def _person_for(principal: Principal, person_id: str | None, people: TenantRepo[Person]) -> Person | None:
    if principal.role is Role.STAFF:
        own = await people.find_one({"user_id": principal.user_id})
        if own is None:
            raise NoLinkedPersonError("Your account is not linked to a person yet. Ask your administrator.")
        if person_id is not None and person_id != own.id:
            raise PersonNotAllowedError("You can upload only your own recordings.")
        return own
    if person_id is None:
        return None
    person = await people.find_one({"_id": person_id})
    if person is None:
        raise UnknownPersonError("This person does not exist in your organisation.")
    return person


async def create(
    principal: Principal,
    body: RecordingIn,
    request: Request,
    *,
    tenant: Tenant,
    settings: Settings,
    storage: UploadStorage,
    recordings: TenantRepo[Recording],
    people: TenantRepo[Person],
    units: TenantRepo[Unit],
    entries: TenantRepo[AuditEntry],
    transactions: Transactions,
) -> UploadOut:
    if body.type not in tenant.enabled_types:
        raise TypeNotEnabledError(f"{body.type} recordings are not enabled for your organisation.")
    _check_format(body.file_name, body.content_type)
    if body.size_bytes > settings.upload_max_bytes:
        raise FileTooLargeError(f"Files may be at most {settings.upload_max_bytes} bytes.")
    part_size = settings.upload_part_size_bytes
    part_count = math.ceil(body.size_bytes / part_size)
    if part_count > MAX_PARTS:
        raise FileTooLargeError("This file needs more upload parts than storage allows.")
    person = await _person_for(principal, body.person_id, people)
    unit_id = body.unit_id or (person.unit_id if person else None)
    if body.unit_id is not None and await units.find_one({"_id": body.unit_id}) is None:
        raise UnknownUnitError("This unit does not exist in your organisation.")

    recording_id = new_id()
    key = original_key(tenant.id, recording_id, body.file_name)
    upload_id = await storage.start(key, body.content_type)
    recording = Recording(
        id=recording_id,
        type=body.type,
        consent_ref=body.consent_ref,
        person_id=person.id if person else None,
        unit_id=unit_id,
        file_name=body.file_name,
        size_bytes=body.size_bytes,
        content_type=body.content_type,
        recorded_at=body.recorded_at,
        storage_key=key,
        upload_id=upload_id,
        part_size=part_size,
        part_count=part_count,
        created_by=principal.user_id,
    )
    try:
        async with transactions.run() as session:
            await recordings.insert_one(recording, session=session)
            await audit(
                entries,
                principal,
                request,
                action="recording.create",
                target_type="recording",
                target_id=recording_id,
                meta={"type": body.type.value, "size_bytes": body.size_bytes},
                session=session,
            )
    except BaseException:
        await storage.abort(key, upload_id)  # otherwise the bucket's lifecycle rule removes it after 7 days
        raise
    parts, expires = storage.part_urls(key, upload_id, list(range(1, part_count + 1)))
    return UploadOut(
        recording_id=recording_id,
        status=recording.status,
        upload_id=upload_id,
        part_size=part_size,
        part_count=part_count,
        parts=parts,
        urls_expire_at=expires,
    )


async def part_urls(
    principal: Principal,
    recording_id: str,
    body: PartsIn,
    *,
    storage: UploadStorage,
    recordings: TenantRepo[Recording],
) -> PartsOut:
    recording = await recordings.find_one({"_id": recording_id})
    if recording is None or (principal.role is Role.STAFF and recording.created_by != principal.user_id):
        raise NotFoundError("Recording not found.")
    if recording.status is not RecordingStatus.CREATED or not recording.upload_id or not recording.storage_key:
        raise UploadNotOpenError("This recording's upload is already complete or was never started.")
    count = recording.part_count or 0
    wrong = sorted({n for n in body.part_numbers if n > count})
    if wrong:
        raise InvalidPartNumberError(f"This upload has parts 1 to {count}; not {wrong}.")
    parts, expires = storage.part_urls(recording.storage_key, recording.upload_id, sorted(set(body.part_numbers)))
    return PartsOut(parts=parts, urls_expire_at=expires)


# --- Completing an upload (plan task P2.2) ---


class PartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_number: int = Field(ge=1, le=MAX_PARTS)
    etag: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class CompleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parts: list[PartIn] = Field(min_length=1, max_length=MAX_PARTS)
    sha256: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[0-9a-f]{64}$")]
    force: bool = False  # upload even though the same file is already in the organisation


class CompleteOut(BaseModel):
    recording_id: str
    status: RecordingStatus
    awaiting_consent: bool
    duplicate_of: str | None


class InvalidPartsError(ApiError):
    status, code, title = 422, "invalid_parts", "Invalid parts"


class SizeMismatchError(ApiError):
    status, code, title = 422, "size_mismatch", "Size mismatch"


class DuplicateRecordingError(ConflictError):
    code, title = "duplicate_recording", "Duplicate recording"


async def _finish_in_storage(storage: UploadStorage, recording: Recording, parts: list[PartIn]) -> int:
    """Complete the multipart upload and return the object's size. A retry after a completed upload is fine."""
    assert recording.storage_key is not None and recording.upload_id is not None  # noqa: S101  # checked by caller
    wanted = set(range(1, (recording.part_count or 0) + 1))
    numbers = [p.part_number for p in parts]
    if sorted(numbers) != sorted(wanted) or len(set(numbers)) != len(numbers):
        raise InvalidPartsError(f"Send every part from 1 to {recording.part_count} once, with its ETag.")
    try:
        await storage.complete(recording.storage_key, recording.upload_id, parts)
    except StorageError as exc:
        if exc.code != "NoSuchUpload":
            raise InvalidPartsError("Storage did not accept the parts; check their ETags.") from exc
        # The upload is gone: either an earlier call completed it (and then failed to record that) or it expired.
    size = await storage.size(recording.storage_key)
    if size is None:
        raise UploadNotOpenError("This upload no longer exists in storage. Start a new recording.")
    return size


async def complete(
    principal: Principal,
    recording_id: str,
    body: CompleteIn,
    *,
    storage: UploadStorage,
    recordings: TenantRepo[Recording],
    outbox: TenantRepo[OutboxEvent],
    transactions: Transactions,
) -> CompleteOut:
    recording = await recordings.find_one({"_id": recording_id})
    if recording is None or (principal.role is Role.STAFF and recording.created_by != principal.user_id):
        raise NotFoundError("Recording not found.")

    if recording.status is RecordingStatus.UPLOADED and recording.sha256 == body.sha256:
        return await _again(recording, body, recordings, outbox, transactions)  # a retry, or confirming a duplicate
    if recording.status is not RecordingStatus.CREATED or not recording.upload_id or not recording.storage_key:
        raise UploadNotOpenError("This recording's upload is already complete or was never started.")

    size = await _finish_in_storage(storage, recording, body.parts)
    if size != recording.size_bytes:
        await storage.delete(recording.storage_key)
        await recordings.update_one(
            {"_id": recording_id, "status": RecordingStatus.CREATED.value},
            {"$set": {"upload_id": None, "status_reason": "size_mismatch"}},
        )
        raise SizeMismatchError(
            f"The uploaded file has {size} bytes, not the {recording.size_bytes} announced. Start a new recording."
        )

    other = await recordings.find_one(
        {"sha256": body.sha256, "_id": {"$ne": recording_id}, "status": {"$ne": RecordingStatus.FAILED.value}}
    )
    awaiting_consent = not recording.consent_ref
    ready = not awaiting_consent and (other is None or body.force)  # the relay starts preprocessing only if ready
    async with transactions.run() as session:
        await record_transition_async(
            recordings,
            outbox,
            recording_id,
            RecordingStatus.CREATED,
            RecordingStatus.UPLOADED,
            reason="upload_complete",
            meta={"size_bytes": size, "duplicate_of": other.id if other else None, "ready": ready},
            session=session,
        )
        await recordings.update_one(
            {"_id": recording_id},
            {
                "$set": {
                    "sha256": body.sha256,
                    "duplicate_of": other.id if other else None,
                    "duplicate_confirmed": bool(other) and body.force,
                    "awaiting_consent": awaiting_consent,
                    "completed_at": utc_now(),
                }
            },
            session=session,
        )
    if other is not None and not body.force:
        raise _duplicate(other.id)
    return CompleteOut(
        recording_id=recording_id,
        status=RecordingStatus.UPLOADED,
        awaiting_consent=awaiting_consent,
        duplicate_of=other.id if other else None,
    )


async def _again(
    recording: Recording,
    body: CompleteIn,
    recordings: TenantRepo[Recording],
    outbox: TenantRepo[OutboxEvent],
    transactions: Transactions,
) -> CompleteOut:
    """Complete called again for an uploaded recording with the same checksum."""
    if recording.duplicate_of and not recording.duplicate_confirmed:
        if not body.force:
            raise _duplicate(recording.duplicate_of)
        async with transactions.run() as session:
            confirmed = await recordings.update_one(
                {"_id": recording.id, "duplicate_confirmed": False},
                {"$set": {"duplicate_confirmed": True}},
                session=session,
            )
            if confirmed and not recording.awaiting_consent:  # released: the relay starts preprocessing
                await record_event_async(outbox, READY, {"recording_id": recording.id}, session=session)
    return CompleteOut(
        recording_id=recording.id,
        status=recording.status,
        awaiting_consent=recording.awaiting_consent,
        duplicate_of=recording.duplicate_of,
    )


def _duplicate(original_id: str) -> DuplicateRecordingError:
    return DuplicateRecordingError(
        "This file was already uploaded to your organisation. Send force=true to process it again.",
        extra={"duplicate_of": original_id},
    )
