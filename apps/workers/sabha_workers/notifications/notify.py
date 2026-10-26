"""The notify step (plan task P2.7): emails about a recording's status change, once per recipient.

Started by the relay for recording.completed, recording.failed and recording.needs_review events, and for
dispute.resolved (P6.7), which emails whoever raised the dispute and the person analysed. It reads the
event (new status and reason), finds the recipients through the tenant-scoped repositories, plans who gets what
(sabha_workers.notifications.emails.plan_emails), renders each email in the recipient's language with the tenant's
own words for its nouns, and sends each one once (delivery log in `deliveries`).

Recipients: the person analysed (through the user linked to the person, if they keep report emails on), the
managers whose units include the recording's unit, and the tenant's admins and owners. Disabled users get nothing.

A refused email (PermanentSendError) is marked failed and not retried; throttling or an SES outage
(RetryableSendError) is raised so the Celery task retries it. Without SES_SENDER nothing is sent: the step logs it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pymongo.database import Database

from sabha_core.models import Delivery, Dispute, OutboxEvent, Person, Recording, User
from sabha_core.repo import SyncTenantRepo, own_tenant
from sabha_workers.notifications.delivery_log import MongoDeliveryLog
from sabha_workers.notifications.emails import (
    PlannedEmail,
    Recipient,
    plan_dispute_emails,
    plan_emails,
    render_email,
)
from sabha_workers.notifications.ses import EmailSender, PermanentSendError, deliver

log = logging.getLogger("sabha.workers.notify")
DISPUTE_RESOLVED = "dispute.resolved"


@dataclass(frozen=True)
class NotifyResult:
    planned: int = 0
    sent: int = 0
    skipped: int = 0  # already sent (a retried event)
    failed: int = 0  # refused for good


def _recipient(user: User, *, is_subject: bool = False) -> Recipient:
    return Recipient(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        language=user.language,
        wants_report_emails=user.report_emails,
        is_subject=is_subject,
    )


def recipients(
    db: Database[dict[str, Any]], tenant_id: str, recording: Recording, *, also: str | None = None
) -> list[Recipient]:
    """The person analysed, their unit's managers, the admins and owners, and `also` (a user id) if active."""
    users = SyncTenantRepo(db, "users", tenant_id, User)
    people = SyncTenantRepo(db, "people", tenant_id, Person)
    active = {"status": {"$ne": "disabled"}}
    found: dict[str, Recipient] = {}
    person = people.find_one({"_id": recording.person_id}) if recording.person_id else None
    if person is not None and person.user_id:
        subject = users.find_one({"_id": person.user_id, **active})
        if subject is not None:
            found[subject.id] = _recipient(subject, is_subject=True)
    if recording.unit_id:
        for manager in users.find({"role": "manager", "unit_ids": recording.unit_id, **active}):
            found.setdefault(manager.id, _recipient(manager))
    for admin in users.find({"role": {"$in": ["admin", "owner"]}, **active}):
        found.setdefault(admin.id, _recipient(admin))
    if also is not None and also not in found:
        extra = users.find_one({"_id": also, **active})
        if extra is not None:
            found[extra.id] = _recipient(extra)
    return list(found.values())


def notify(
    db: Database[dict[str, Any]],
    *,
    tenant_id: str,
    recording_id: str,
    event_id: str,
    sender: EmailSender | None,
    web_base_url: str,
) -> NotifyResult:
    outbox = SyncTenantRepo(db, "outbox", tenant_id, OutboxEvent)
    recordings = SyncTenantRepo(db, "recordings", tenant_id, Recording)
    event = outbox.find_one({"_id": event_id})
    recording = recordings.find_one({"_id": recording_id})
    tenant = own_tenant(db, tenant_id)
    if event is None or recording is None or tenant is None:
        log.warning("nothing to notify about", extra={"event_id": event_id, "recording_id": recording_id})
        return NotifyResult()
    status, reason = event.payload.get("to_status"), event.payload.get("reason")
    decision = None
    planned: list[PlannedEmail]
    if event.type == DISPUTE_RESOLVED:
        dispute = SyncTenantRepo(db, "disputes", tenant_id, Dispute).find_one({"_id": event.payload["dispute_id"]})
        if dispute is None or dispute.status == "open":
            log.warning("no decided dispute to notify about", extra={"event_id": event_id})
            return NotifyResult()
        decision = dispute.status
        planned = plan_dispute_emails(event_id, dispute.raised_by, recipients(db, tenant_id, recording,
                                                                              also=dispute.raised_by))  # fmt: skip
    else:
        planned = plan_emails(event_id, str(status), recipients(db, tenant_id, recording))
    if not planned:
        return NotifyResult()
    if sender is None:
        log.warning(
            "email is not configured (SES_SENDER); not sending", extra={"event_id": event_id, "count": len(planned)}
        )
        return NotifyResult(planned=len(planned))

    delivery_log = MongoDeliveryLog(SyncTenantRepo(db, "deliveries", tenant_id, Delivery))
    labels = tenant.labels.model_dump()
    link = f"{web_base_url.rstrip('/')}/recordings/{recording.id}"
    title = recording.file_name or recording.id
    sent = skipped = failed = 0
    for item in planned:
        email = render_email(
            item.kind,
            item.recipient.language,
            labels=labels,
            link=link,
            recording_title=title,
            reason=str(reason) if item.kind == "needs_attention" else None,
            decision=decision,
        )
        try:
            if deliver(item, email, sender=sender, delivery_log=delivery_log):
                sent += 1
            else:
                skipped += 1
        except PermanentSendError as exc:
            delivery_log.mark_failed(item.delivery_key, str(exc))
            failed += 1
    return NotifyResult(planned=len(planned), sent=sent, skipped=skipped, failed=failed)
