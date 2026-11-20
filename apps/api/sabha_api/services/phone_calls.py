"""Phone calls from MyOperator (ADR 0017): the list, playback and "Analyse".

Calls are copied in by a worker (sabha_workers.phone_calls) into one workspace, MYOPERATOR_TENANT_ID. Any other
workspace gets 404 `phone_calls_not_set_up`.

Who (owner's decision, 2026-11-20): owners and admins see every call; managers see the calls of people in their
units (a call's unit is its first agent's matched person's home unit, so a call whose agent is not matched yet is
for owners and admins only). Everyone else gets 403. A call the caller may not see is 404.

- Playback: MyOperator gives a link to the MP3 that is valid for 24 hours. The API asks for it and hands it to the
  browser, which plays it from MyOperator; the API never touches the audio (golden rule 2). Audited as
  `phone_call.play`.
- Analyse: makes a Recording of the call (support or sales, for its agent's person, with the call-recording notice
  as consent, golden rule 9) and writes a `phone_call.import` event in the same transaction. The relay starts the
  worker that copies the audio into storage and moves the recording to UPLOADED, so the pipeline runs as for an
  upload. Choosing a person for a call also matches its agent to that person for every call they answered. If the
  audio could not be fetched, Analyse again sends the same recording again.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Annotated, Any, Literal, Self
from zoneinfo import ZoneInfo

import httpx
from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from sabha_api.audit import audit
from sabha_api.auth import Principal, Role
from sabha_api.deps import Transactions
from sabha_api.errors import ApiError, BadRequestError, ConflictError, ForbiddenError, NotFoundError
from sabha_api.services.recordings import (
    AsrChoiceNotAllowedError,
    AsrModelUnavailableError,
    TransferNotAllowedError,
)
from sabha_asr.registry import AsrConfigError, chosen_spec
from sabha_core.models import (
    SPEAKER_COUNT_MAX,
    SPEAKER_COUNT_MIN,
    TRANSFERRED_SPEAKERS,
    AuditEntry,
    CostEstimate,
    OutboxEvent,
    Person,
    PhoneCall,
    Recording,
    SpeakerModel,
    Tenant,
    Unit,
    new_id,
    utc_now,
)
from sabha_core.profiles import ConversationType
from sabha_core.repo import TenantRepo
from sabha_core.settings import Settings
from sabha_core.state import RecordingStatus
from sabha_core.storage import original_key

ALLOWED = (Role.OWNER, Role.ADMIN, Role.MANAGER)
EVERY_CALL = frozenset({Role.OWNER, Role.ADMIN})
MAX_LIMIT = 100
ANALYSE_ROUTE = "POST /v1/phone-calls/{call_id}/analyse"
IMPORT_EVENT = "phone_call.import"
DOWNLOAD_FAILED = "phone_call_download_failed"
INDIA = ZoneInfo("Asia/Kolkata")
LINK_TIMEOUT_S = 15.0


class NotSetUpError(NotFoundError):
    code, title = "phone_calls_not_set_up", "Phone calls are not set up"


class PhoneSystemError(ApiError):
    status, code, title = 502, "phone_system_unavailable", "The phone system did not answer"


class AlreadyAnalysedError(ConflictError):
    code, title = "already_analysed", "Already analysed"


class PersonRequiredError(ApiError):
    status, code, title = 422, "person_required", "Choose whose call this is"


class TypeNotAllowedError(ApiError):
    status, code, title = 422, "type_not_allowed", "Not a type for phone calls"


class PersonNotAllowedError(ForbiddenError):
    code, title = "person_not_allowed", "Person not allowed"


class UnknownUnitError(ApiError):
    status, code, title = 422, "unknown_unit", "Unknown unit"


def check_set_up(principal: Principal, settings: Settings) -> None:
    if not is_set_up(principal.tenant_id, settings):
        raise NotSetUpError("Phone calls are not set up for your organisation.")


def is_set_up(tenant_id: str, settings: Settings) -> bool:
    return settings.myoperator_api_token is not None and settings.myoperator_tenant_id == tenant_id


def visible(principal: Principal) -> dict[str, Any]:
    """The calls the caller may see (module docstring)."""
    if principal.role in EVERY_CALL:
        return {}
    return {"unit_id": {"$in": list(principal.unit_ids)}}


# --- The list ---


class AgentOut(BaseModel):
    user_id: str
    name: str
    extension: str | None


class PersonRef(BaseModel):
    id: str
    name: str


class AnalysisRef(BaseModel):
    recording_id: str
    status: RecordingStatus
    status_reason: str | None


class PhoneCallOut(BaseModel):
    id: str
    started_at: datetime
    duration_s: int
    direction: Literal["incoming", "outgoing"]
    department: str | None
    customer: str
    agents: list[AgentOut]
    person: PersonRef | None  # who the first agent is matched to
    analysis: AnalysisRef | None  # the recording made when someone pressed Analyse
    import_error: str | None


class PhoneCallPage(BaseModel):
    items: list[PhoneCallOut]
    next_cursor: str | None


class AgentOption(BaseModel):
    user_id: str
    name: str
    extension: str | None
    calls: int
    analysed: int  # calls someone asked to analyse
    person: PersonRef | None


def _encode(at: datetime, call_id: str) -> str:
    return base64.urlsafe_b64encode(f"{at.isoformat()}|{call_id}".encode()).decode().rstrip("=")


def _after(cursor: str | None) -> dict[str, Any]:
    if not cursor:
        return {}
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        stamp, call_id = raw.split("|", 1)
        at = datetime.fromisoformat(stamp)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise BadRequestError("The cursor is not valid; start again without it.") from exc
    return {"$or": [{"started_at": {"$lt": at}}, {"started_at": at, "_id": {"$lt": call_id}}]}


async def list_calls(
    principal: Principal,
    *,
    calls: TenantRepo[PhoneCall],
    people: TenantRepo[Person],
    recordings: TenantRepo[Recording],
    cursor: str | None,
    limit: int,
    agent: str | None = None,
    direction: str | None = None,
    analysed: bool | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> PhoneCallPage:
    conditions: list[dict[str, Any]] = [visible(principal), _after(cursor)]
    if agent:
        conditions.append({"agents.0.user_id": agent})
    if direction in ("incoming", "outgoing"):
        conditions.append({"direction": direction})
    if analysed is not None:
        conditions.append({"recording_id": {"$ne": None}} if analysed else {"recording_id": None})
    if since or until:
        conditions.append({"started_at": {**({"$gte": since} if since else {}), **({"$lt": until} if until else {})}})
    kept = [c for c in conditions if c]
    found = await calls.find({"$and": kept} if kept else {}, sort=[("started_at", -1), ("_id", -1)], limit=limit + 1)
    page, more = found[:limit], len(found) > limit
    names = await _people(people, [c.person_id for c in page if c.person_id])
    made = {r.id: r for r in await recordings.find({"_id": {"$in": [c.recording_id for c in page if c.recording_id]}})}
    return PhoneCallPage(
        items=[_out(c, names, made) for c in page],
        next_cursor=_encode(page[-1].started_at, page[-1].id) if more and page else None,
    )


async def _people(people: TenantRepo[Person], ids: list[str]) -> dict[str, str]:
    return {p.id: p.name for p in await people.find({"_id": {"$in": list(set(ids))}})} if ids else {}


def _out(call: PhoneCall, names: dict[str, str], made: dict[str, Recording]) -> PhoneCallOut:
    recording = made.get(call.recording_id) if call.recording_id else None
    person = PersonRef(id=call.person_id, name=names[call.person_id]) if call.person_id in names else None
    return PhoneCallOut(
        id=call.id,
        started_at=call.started_at,
        duration_s=call.duration_s,
        direction=call.direction,
        department=call.department,
        customer=call.customer,
        agents=[AgentOut(user_id=a.user_id, name=a.name, extension=a.extension) for a in call.agents],
        person=person,
        analysis=(
            AnalysisRef(recording_id=recording.id, status=recording.status, status_reason=recording.status_reason)
            if recording
            else None
        ),
        import_error=call.import_error,
    )


async def agents(
    principal: Principal, *, calls: TenantRepo[PhoneCall], people: TenantRepo[Person]
) -> list[AgentOption]:
    """Everyone who has answered a call the caller may see, with how many and who they are matched to."""
    match = visible(principal)
    rows = await calls.aggregate(
        [
            *([{"$match": match}] if match else []),
            {
                "$group": {
                    "_id": {"$arrayElemAt": ["$agents.user_id", 0]},
                    "name": {"$last": {"$arrayElemAt": ["$agents.name", 0]}},
                    "extension": {"$last": {"$arrayElemAt": ["$agents.extension", 0]}},
                    "calls": {"$sum": 1},
                    "analysed": {"$sum": {"$cond": [{"$gt": ["$recording_id", None]}, 1, 0]}},
                }
            },
            {"$sort": {"name": 1}},
        ]
    )
    matched = {
        a: p
        for p in await people.find({"phone_agent_ids": {"$in": [r["_id"] for r in rows]}})
        for a in p.phone_agent_ids
    }
    return [
        AgentOption(
            user_id=str(r["_id"]),
            name=str(r["name"] or "Unknown"),
            extension=r.get("extension"),
            calls=r["calls"],
            analysed=r["analysed"],
            person=PersonRef(id=matched[r["_id"]].id, name=matched[r["_id"]].name) if r["_id"] in matched else None,
        )
        for r in rows
        if r["_id"]
    ]


async def _call(principal: Principal, call_id: str, calls: TenantRepo[PhoneCall]) -> PhoneCall:
    call = await calls.find_one({"_id": call_id, **visible(principal)})
    if call is None:
        raise NotFoundError("Phone call not found.")
    return call


# --- Playback ---


class AudioOut(BaseModel):
    url: str


async def recording_link(settings: Settings, file: str) -> str:
    """MyOperator's 24-hour link to the recording (sabha_workers.phone_calls has the same call for the worker)."""
    assert settings.myoperator_api_token is not None  # noqa: S101  # checked by check_set_up
    try:
        async with httpx.AsyncClient(timeout=LINK_TIMEOUT_S) as http:
            response = await http.get(
                f"{settings.myoperator_base_url.rstrip('/')}/recordings/link",
                params={"token": settings.myoperator_api_token.get_secret_value(), "file": file},
            )
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise PhoneSystemError("MyOperator could not be reached. Try again in a moment.") from exc
    url = body.get("url") if isinstance(body, dict) and body.get("status") == "success" else None
    if not isinstance(url, str) or not url.startswith("https://"):
        raise PhoneSystemError("MyOperator has no recording for this call.")
    return url


async def audio(
    principal: Principal,
    call_id: str,
    request: Request,
    *,
    settings: Settings,
    calls: TenantRepo[PhoneCall],
    entries: TenantRepo[AuditEntry],
) -> AudioOut:
    call = await _call(principal, call_id, calls)
    url = await recording_link(settings, call.recording_file)
    await audit(entries, principal, request, action="phone_call.play", target_type="phone_call", target_id=call.id)
    return AudioOut(url=url)


# --- Analyse ---

PHONE_TYPES = frozenset({ConversationType.SUPPORT, ConversationType.SALES})


class NewPersonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    unit_id: str


class AnalyseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ConversationType
    # Whose call it is. Left out: the person the call's agent is already matched to. Given: that person, and the
    # agent is matched to them from now on. `new_person` (owners and admins): add the agent to Sabha as a new person
    # in that unit, matched to them, in the same transaction.
    person_id: str | None = None
    new_person: NewPersonIn | None = None
    # The models, as at upload (ADR 0012, 0014, 0015). asr_model: owners and admins only; left out, the configured
    # model. transferred: left out, yes for a support call MyOperator shows a second agent answering.
    asr_model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None
    speaker_count: int | None = Field(default=None, ge=SPEAKER_COUNT_MIN, le=SPEAKER_COUNT_MAX)
    speaker_model: SpeakerModel = "pyannote"
    transferred: bool | None = None

    @model_validator(mode="after")
    def _one_person(self) -> Self:
        if self.person_id is not None and self.new_person is not None:
            raise ValueError("give person_id or new_person, not both")
        return self


class AnalyseOut(BaseModel):
    recording_id: str
    status: RecordingStatus


def title(call: PhoneCall) -> str:
    """What the recording is called: "Call with ••••4821, 20 Nov 2026 12:46" (India time)."""
    when = call.started_at.astimezone(INDIA).strftime("%d %b %Y %H:%M").lstrip("0")
    return f"Call with {call.customer}, {when}.mp3"


async def analyse(
    principal: Principal,
    call_id: str,
    body: AnalyseIn,
    request: Request,
    *,
    tenant: Tenant,
    settings: Settings,
    calls: TenantRepo[PhoneCall],
    people: TenantRepo[Person],
    units: TenantRepo[Unit],
    recordings: TenantRepo[Recording],
    outbox: TenantRepo[OutboxEvent],
    entries: TenantRepo[AuditEntry],
    transactions: Transactions,
    cost_estimate: CostEstimate | None = None,
) -> AnalyseOut:
    call = await _call(principal, call_id, calls)
    if call.recording_id is not None:
        existing = await recordings.find_one({"_id": call.recording_id})
        if existing is not None:
            if existing.status is RecordingStatus.CREATED and existing.status_reason == DOWNLOAD_FAILED:
                return await _send_again(
                    principal,
                    call,
                    existing,
                    request,
                    calls=calls,
                    recordings=recordings,
                    outbox=outbox,
                    entries=entries,
                    transactions=transactions,
                )
            raise AlreadyAnalysedError("This call is already being analysed.", extra={"recording_id": existing.id})

    if body.type not in PHONE_TYPES:
        raise TypeNotAllowedError("Phone calls are analysed as support or sales calls.")
    if body.type not in tenant.enabled_types:
        raise TypeNotAllowedError(f"{body.type} recordings are not enabled for your organisation.")
    agent = call.agents[0]
    created = body.new_person is not None
    if body.new_person is not None:
        if principal.role not in EVERY_CALL:
            raise PersonNotAllowedError("Only owners and admins add people.")
        if await units.find_one({"_id": body.new_person.unit_id}) is None:
            raise UnknownUnitError("This unit does not exist in your organisation.")
        person = Person(name=body.new_person.name, unit_ids=[body.new_person.unit_id])
    else:
        person_id = body.person_id or call.person_id
        if person_id is None:
            raise PersonRequiredError(f"Choose who {agent.name} is in Sabha.")
        found = await people.find_one({"_id": person_id})
        if found is None:
            raise PersonRequiredError("This person does not exist in your organisation.")
        person = found
    if principal.role not in EVERY_CALL and person.unit_id not in principal.unit_ids:
        raise PersonNotAllowedError("You can analyse calls only for people in your units.")
    match = created or (body.person_id is not None and agent.user_id not in person.phone_agent_ids)

    # A colleague who also answered (ADR 0015): support calls only, and named only if they are matched already.
    helpers = [a for a in call.agents[1:] if a.user_id != agent.user_id]
    support = body.type is ConversationType.SUPPORT
    transferred = (support and bool(helpers)) if body.transferred is None else body.transferred
    if transferred and not support:
        raise TransferNotAllowedError("Only support calls can be marked as helped by a colleague.")
    if transferred and body.speaker_count not in (None, TRANSFERRED_SPEAKERS):
        raise TransferNotAllowedError("A call a colleague helped on has three speakers: two agents and the customer.")
    asr_choice = None
    if body.asr_model is not None:
        if principal.role not in EVERY_CALL:
            raise AsrChoiceNotAllowedError("Only owners and admins choose the speech-to-text model.")
        try:
            asr_choice = chosen_spec(body.asr_model, settings)
        except AsrConfigError as exc:
            raise AsrModelUnavailableError(str(exc)) from exc
    helper = await people.find_one({"phone_agent_ids": helpers[0].user_id}) if transferred and helpers else None
    if helper is not None and (
        helper.id == person.id or (principal.role not in EVERY_CALL and helper.unit_id not in principal.unit_ids)
    ):
        helper = None

    recording_id = new_id()
    name = title(call)
    recording = Recording(
        id=recording_id,
        type=body.type,
        source="audio",
        consent_ref=settings.myoperator_consent_ref,
        person_id=person.id,
        unit_id=person.unit_id,
        file_name=name,
        content_type="audio/mpeg",
        recorded_at=call.started_at,
        storage_key=original_key(tenant.id, recording_id, "call.mp3"),
        created_by=principal.user_id,
        cost_estimate=cost_estimate,
        interaction="call" if body.type is ConversationType.SALES else None,
        transferred=transferred,
        asr_choice=asr_choice,
        speaker_count=body.speaker_count,
        speaker_model=body.speaker_model,
        transfer_person_id=helper.id if helper else None,
        phone_call_id=call.id,
    )
    async with transactions.run() as session:
        await recordings.insert_one(recording, session=session)
        claimed = await calls.update_one(
            {"_id": call.id, "recording_id": call.recording_id},
            {
                "$set": {
                    "recording_id": recording_id,
                    "analyse_requested_by": principal.user_id,
                    "analyse_requested_at": utc_now(),
                    "import_error": None,
                }
            },
            session=session,
        )
        if not claimed:  # someone else pressed Analyse at the same moment; the transaction is undone
            raise AlreadyAnalysedError("This call is already being analysed.")
        if created:
            await people.insert_one(person, session=session)
            await audit(
                entries,
                principal,
                request,
                action="person.create",
                target_type="person",
                target_id=person.id,
                meta={"name": person.name, "unit_ids": person.unit_ids, "from": "phone_call"},
                session=session,
            )
        if match:
            await _match(agent.user_id, person, calls, people, session=session)
            await audit(
                entries,
                principal,
                request,
                action="phone_agent.match",
                target_type="person",
                target_id=person.id,
                meta={"agent_name": agent.name},
                session=session,
            )
        await outbox.insert_one(OutboxEvent(type=IMPORT_EVENT, payload={"recording_id": recording_id}), session=session)
        await audit(
            entries,
            principal,
            request,
            action="recording.create",
            target_type="recording",
            target_id=recording_id,
            session=session,
            meta={
                "type": body.type.value,
                "source": "phone_call",
                "phone_call_id": call.id,
                **({"transferred": True} if transferred else {}),
                **({"asr_model": asr_choice} if asr_choice else {}),
                **({"speaker_count": body.speaker_count} if body.speaker_count else {}),
                **({"speaker_model": body.speaker_model} if body.speaker_model != "pyannote" else {}),
            },
        )
    return AnalyseOut(recording_id=recording_id, status=RecordingStatus.CREATED)


async def _match(
    agent_id: str, person: Person, calls: TenantRepo[PhoneCall], people: TenantRepo[Person], *, session: Any
) -> None:
    """From now on, `agent_id`'s calls are `person`'s: move the match from anyone else, and update their calls."""
    await people.update_many(
        {"phone_agent_ids": agent_id, "_id": {"$ne": person.id}},
        {"$pull": {"phone_agent_ids": agent_id}},
        session=session,
    )
    await people.update_one({"_id": person.id}, {"$addToSet": {"phone_agent_ids": agent_id}}, session=session)
    await calls.update_many(
        {"agents.0.user_id": agent_id}, {"$set": {"person_id": person.id, "unit_id": person.unit_id}}, session=session
    )


async def _send_again(
    principal: Principal,
    call: PhoneCall,
    recording: Recording,
    request: Request,
    *,
    calls: TenantRepo[PhoneCall],
    recordings: TenantRepo[Recording],
    outbox: TenantRepo[OutboxEvent],
    entries: TenantRepo[AuditEntry],
    transactions: Transactions,
) -> AnalyseOut:
    """The audio could not be fetched last time: try the same recording again."""
    async with transactions.run() as session:
        await recordings.update_one(
            {"_id": recording.id, "status": RecordingStatus.CREATED.value},
            {"$set": {"status_reason": None}},
            session=session,
        )
        await calls.update_one({"_id": call.id}, {"$set": {"import_error": None}}, session=session)
        await outbox.insert_one(OutboxEvent(type=IMPORT_EVENT, payload={"recording_id": recording.id}), session=session)
        await audit(
            entries,
            principal,
            request,
            action="phone_call.fetch_again",
            target_type="recording",
            target_id=recording.id,
            session=session,
        )
    return AnalyseOut(recording_id=recording.id, status=RecordingStatus.CREATED)
