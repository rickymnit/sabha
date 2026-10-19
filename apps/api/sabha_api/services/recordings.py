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
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from sabha_api.audit import audit
from sabha_api.auth import Principal, Role
from sabha_api.deps import Transactions
from sabha_api.errors import ApiError, ConflictError, ForbiddenError, NotFoundError
from sabha_core.models import AuditEntry, Person, Recording, Tenant, Unit, new_id, utc_now
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
