"""The notify step (plan task P2.7) against MongoDB with a fake email sender: who is emailed, in which language,
exactly once per recipient, and what happens when sending fails.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any, Literal

import pytest
from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.indexes import ensure_indexes
from sabha_core.models import Delivery, Dispute, OutboxEvent, Person, Recording, Role, Tenant, User, utc_now
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.repo import SyncTenantRepo
from sabha_core.state import RecordingStatus
from sabha_workers.notifications.delivery_log import MongoDeliveryLog
from sabha_workers.notifications.emails import RenderedEmail
from sabha_workers.notifications.notify import notify
from sabha_workers.notifications.ses import PermanentSendError, RetryableSendError

pytestmark = pytest.mark.integration
BASE_URL = "https://app.example.in"


class FakeSender:
    def __init__(self, error: Exception | None = None) -> None:
        self.sent: list[tuple[str, RenderedEmail]] = []
        self.error = error

    def send(self, to: str, email: RenderedEmail, delivery_key: str) -> str:
        if self.error is not None:
            raise self.error
        self.sent.append((to, email))
        return f"msg-{len(self.sent)}"


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"notify_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield name
    mongo_replica_set.drop_database(name)


def repo(db: Database[dict[str, Any]], collection: str, model: type[Any], tenant: str = "t1") -> SyncTenantRepo[Any]:
    return SyncTenantRepo(db, collection, tenant, model)


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]], shared_db: str) -> Database[dict[str, Any]]:
    database = mongo_replica_set[shared_db]
    for collection in ("tenants", "users", "people", "recordings", "outbox", "deliveries", "disputes"):
        database[collection].delete_many({})
    for tenant_id in ("t1", "t2"):
        tenant = Tenant.from_profile("school", name=tenant_id, plan=Plan.PILOT, id=tenant_id)
        database.tenants.insert_one(tenant.model_dump(by_alias=True))
    users = [
        User(id="u-teacher", email="teacher@example.com", name="T", role=Role.STAFF, status="active", language="hi"),
        User(id="u-manager", email="manager@example.com", name="M", role=Role.MANAGER, unit_ids=["unit-1"],
             status="active"),
        User(id="u-other-mgr", email="other@example.com", name="O", role=Role.MANAGER, unit_ids=["unit-2"],
             status="active"),
        User(id="u-admin", email="admin@example.com", name="A", role=Role.ADMIN, status="active"),
        User(id="u-gone", email="gone@example.com", name="G", role=Role.OWNER, status="disabled"),
    ]  # fmt: skip
    repo(database, "users", User).insert_many(users)
    repo(database, "people", Person).insert_one(Person(id="p-teacher", name="T", unit_id="unit-1", user_id="u-teacher"))
    return database


def recording(db: Database[dict[str, Any]], status: RecordingStatus, reason: str = "x") -> tuple[str, str]:
    rec = Recording(type=ConversationType.TEACHING, status=status, consent_ref="c", person_id="p-teacher",
                    unit_id="unit-1", file_name="Class 7B fractions.mp3")  # fmt: skip
    rid = repo(db, "recordings", Recording).insert_one(rec).id
    event = OutboxEvent(type=f"recording.{status.lower()}", payload={"recording_id": rid, "to_status": status.value,
                                                                     "reason": reason})  # fmt: skip
    return rid, repo(db, "outbox", OutboxEvent).insert_one(event).id


def run(db: Database[dict[str, Any]], rid: str, event_id: str, sender: FakeSender | None) -> Any:
    return notify(db, tenant_id="t1", recording_id=rid, event_id=event_id, sender=sender, web_base_url=BASE_URL)


def test_completed_emails_the_teacher_and_their_manager(db: Database[dict[str, Any]]) -> None:
    rid, event_id = recording(db, RecordingStatus.COMPLETED)
    sender = FakeSender()
    result = run(db, rid, event_id, sender)
    assert (result.planned, result.sent) == (2, 2)
    by_address = {to: email for to, email in sender.sent}
    assert set(by_address) == {"teacher@example.com", "manager@example.com"}  # not the other unit's manager, admins
    assert by_address["teacher@example.com"].language == "hi"  # the teacher's own language
    assert f"{BASE_URL}/recordings/{rid}" in by_address["manager@example.com"].text
    assert "Class 7B fractions.mp3" in by_address["manager@example.com"].subject


def test_failures_email_the_active_admins_with_the_reason(db: Database[dict[str, Any]]) -> None:
    rid, event_id = recording(db, RecordingStatus.FAILED, reason="invalid_audio")
    sender = FakeSender()
    run(db, rid, event_id, sender)
    assert [to for to, _ in sender.sent] == ["admin@example.com"]  # the disabled owner gets nothing
    assert "invalid_audio" in sender.sent[0][1].text


def test_a_retried_event_never_emails_twice(db: Database[dict[str, Any]]) -> None:
    rid, event_id = recording(db, RecordingStatus.COMPLETED)
    sender = FakeSender()
    run(db, rid, event_id, sender)
    again = run(db, rid, event_id, sender)
    assert (again.sent, again.skipped) == (0, 2) and len(sender.sent) == 2


def test_teachers_can_turn_report_emails_off(db: Database[dict[str, Any]]) -> None:
    db.users.update_one({"_id": "u-teacher"}, {"$set": {"report_emails": False}})
    rid, event_id = recording(db, RecordingStatus.COMPLETED)
    sender = FakeSender()
    run(db, rid, event_id, sender)
    assert [to for to, _ in sender.sent] == ["manager@example.com"]


def test_a_refused_email_is_recorded_and_not_retried(db: Database[dict[str, Any]]) -> None:
    rid, event_id = recording(db, RecordingStatus.FAILED)
    result = run(db, rid, event_id, FakeSender(PermanentSendError("SES refused the email: MessageRejected")))
    assert result.failed == 1
    (delivery,) = db.deliveries.find()
    assert delivery["status"] == "failed" and "MessageRejected" in delivery["last_error"]
    later = FakeSender()
    assert run(db, rid, event_id, later).skipped == 1 and later.sent == []


def test_throttling_is_raised_for_the_task_to_retry(db: Database[dict[str, Any]]) -> None:
    rid, event_id = recording(db, RecordingStatus.FAILED)
    with pytest.raises(RetryableSendError):
        run(db, rid, event_id, FakeSender(RetryableSendError("SES refused the email: TooManyRequestsException")))
    assert db.deliveries.count_documents({}) == 0  # the claim was released for the retry
    retry = FakeSender()
    assert run(db, rid, event_id, retry).sent == 1


def test_without_ses_nothing_is_sent(db: Database[dict[str, Any]]) -> None:
    rid, event_id = recording(db, RecordingStatus.COMPLETED)
    result = run(db, rid, event_id, None)
    assert (result.planned, result.sent) == (2, 0) and db.deliveries.count_documents({}) == 0


def test_statuses_without_emails_send_nothing(db: Database[dict[str, Any]]) -> None:
    rid, event_id = recording(db, RecordingStatus.TRANSCRIBING)
    assert run(db, rid, event_id, FakeSender()).planned == 0


def test_an_unknown_event_or_another_tenants_recording_sends_nothing(db: Database[dict[str, Any]]) -> None:
    rid, _ = recording(db, RecordingStatus.COMPLETED)
    sender = FakeSender()
    assert run(db, rid, "missing-event", sender).planned == 0
    result = notify(db, tenant_id="t2", recording_id=rid, event_id="x", sender=sender, web_base_url=BASE_URL)
    assert result.planned == 0 and sender.sent == []


# --- The delivery log ---


def test_delivery_keys_are_per_tenant(db: Database[dict[str, Any]]) -> None:
    # /tenant-check finding 3: the same key in two tenants are two deliveries.
    a = MongoDeliveryLog(repo(db, "deliveries", Delivery, "t1"))
    b = MongoDeliveryLog(repo(db, "deliveries", Delivery, "t2"))
    assert a.claim("k") and b.claim("k")
    assert not a.claim("k")


def test_a_dead_workers_claim_is_taken_over_once_stale(db: Database[dict[str, Any]]) -> None:
    clock = [utc_now()]
    log = MongoDeliveryLog(repo(db, "deliveries", Delivery), stale_after=timedelta(minutes=10), now=lambda: clock[0])
    assert log.claim("k")
    assert not log.claim("k")  # still fresh: someone is sending it
    clock[0] += timedelta(minutes=11)
    assert log.claim("k")
    log.mark_sent("k", "msg-1")
    clock[0] += timedelta(hours=1)
    assert not log.claim("k") and log.status("k") == "sent"


# --- A decided dispute (P6.7) ---


def decided_dispute(
    db: Database[dict[str, Any]], raised_by: str, status: Literal["open", "accepted", "rejected"] = "accepted"
) -> tuple[str, str]:
    rid, _ = recording(db, RecordingStatus.COMPLETED)
    dispute = Dispute(analysis_id="an-1", recording_id=rid, person_id="p-teacher", unit_id="unit-1",
                      dimension="concept_clarity", dimension_name="Concept clarity", ai_score=4, current_score=4,
                      proposed_score=2, comment="The explanation was wrong.", raised_by=raised_by, status=status,
                      final_score=2 if status == "accepted" else None, resolution_note="Agreed.")  # fmt: skip
    did = repo(db, "disputes", Dispute).insert_one(dispute).id
    event = OutboxEvent(type="dispute.resolved", payload={"dispute_id": did, "recording_id": rid, "decision": status})
    return rid, repo(db, "outbox", OutboxEvent).insert_one(event).id


def test_a_decided_dispute_emails_who_raised_it_and_the_person_analysed(db: Database[dict[str, Any]]) -> None:
    rid, event_id = decided_dispute(db, raised_by="u-manager")
    sender = FakeSender()
    assert run(db, rid, event_id, sender).sent == 2
    by_address = {to: email for to, email in sender.sent}
    assert set(by_address) == {"manager@example.com", "teacher@example.com"}  # not the admin
    manager = by_address["manager@example.com"]
    assert "accepted and the score was changed" in manager.text and f"{BASE_URL}/recordings/{rid}" in manager.text
    assert "2" not in manager.text.replace(f"{BASE_URL}/recordings/{rid}", "")  # never the score itself
    assert by_address["teacher@example.com"].language == "hi"
    assert run(db, rid, event_id, FakeSender()).sent == 0  # a retried event never emails twice


def test_a_rejected_dispute_says_the_score_stays(db: Database[dict[str, Any]]) -> None:
    rid, event_id = decided_dispute(db, raised_by="u-admin", status="rejected")
    sender = FakeSender()
    run(db, rid, event_id, sender)
    admin = {to: email for to, email in sender.sent}["admin@example.com"]
    assert "not accepted; the score stays as it was" in admin.text


def test_an_open_dispute_sends_nothing(db: Database[dict[str, Any]]) -> None:
    rid, event_id = decided_dispute(db, raised_by="u-manager", status="open")
    assert run(db, rid, event_id, FakeSender()).planned == 0
