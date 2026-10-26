"""PUT /v1/recordings/{id}/voices: names for the anonymous voices of a meeting ("S1" -> "Riya").

Meetings only: in a meeting the diarizer's voice labels are shown, and people want to see who owns an action item.
Anyone who may see the recording may name its voices. The names are for display only: they are stored on the
recording, never sent to a model, and never used to score anyone (a meeting is scored as a whole). The body replaces
all names; an empty name removes one. Audited as `recording.voices`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Request
from pydantic import BaseModel, StringConstraints

from sabha_api.audit import audit
from sabha_api.auth import Principal
from sabha_api.errors import BadRequestError, ConflictError, NotFoundError
from sabha_api.services.results import visible_recording
from sabha_core.models import AuditEntry, Person, Recording, Transcript
from sabha_core.profiles import ConversationType
from sabha_core.repo import TenantRepo

Name = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]


class NotAMeetingError(ConflictError):
    code, title = "not_a_meeting", "Not a meeting"


class UnknownVoiceError(BadRequestError):
    code, title = "unknown_voice", "Unknown voice"


class VoicesIn(BaseModel):
    names: dict[str, Name]


class VoicesOut(BaseModel):
    recording_id: str
    voice_names: dict[str, str]


async def name_voices(
    principal: Principal, recording_id: str, body: VoicesIn, request: Request, *, recordings: TenantRepo[Recording],
    people: TenantRepo[Person], transcripts: TenantRepo[Transcript], entries: TenantRepo[AuditEntry],
) -> VoicesOut:  # fmt: skip
    recording = await visible_recording(principal, recording_id, recordings, people)
    if recording.type is not ConversationType.MEETING:
        raise NotAMeetingError("Voices can be named only in a meeting.")
    transcript = await transcripts.find_one({"recording_id": recording.id})
    if transcript is None:
        raise NotFoundError("This meeting has no transcript yet.")
    unknown = sorted(set(body.names) - set(transcript.roles))
    if unknown:
        raise UnknownVoiceError(f"{', '.join(unknown)} did not speak in this meeting.")
    names = {voice: name for voice, name in body.names.items() if name}
    await recordings.update_one({"_id": recording.id}, {"$set": {"voice_names": names}})
    await audit(entries, principal, request, action="recording.voices", target_type="recording",
                target_id=recording.id, meta={"voices": sorted(names)})  # fmt: skip
    return VoicesOut(recording_id=recording.id, voice_names=names)
