"""Notification rules, email templates and webhook signing (P2.7), without SES or a queue."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from sabha_workers.notifications.emails import Recipient, plan_emails, render_email
from sabha_workers.notifications.webhooks import (
    MAX_RETRY_WINDOW_S,
    SIGNATURE_HEADER,
    InvalidSignature,
    retry_schedule,
    sign,
    verify,
)

LABELS = {"person": "Teacher", "recording": "Lesson"}
LINK = "https://app.example.in/recordings/rec_123"


def recipients() -> list[Recipient]:
    return [
        Recipient("u_teacher", "teacher@example.in", "staff", "en", wants_report_emails=True, is_subject=True),
        Recipient("u_manager", "head@example.in", "manager", "hi", wants_report_emails=True),
        Recipient("u_admin", "admin@example.in", "admin", "en", wants_report_emails=True),
        Recipient("u_other", "other@example.in", "staff", "en", wants_report_emails=True),
    ]


# --- who gets an email ---------------------------------------------------------------------------------------------


def test_completed_goes_to_the_person_analysed_and_their_manager() -> None:
    emails = plan_emails("evt_1", "COMPLETED", recipients())
    assert sorted(e.recipient.user_id for e in emails) == ["u_manager", "u_teacher"]


def test_the_person_can_opt_out_of_report_emails() -> None:
    people = recipients()
    people[0] = Recipient("u_teacher", "teacher@example.in", "staff", "en", wants_report_emails=False, is_subject=True)
    assert [e.recipient.user_id for e in plan_emails("evt_1", "COMPLETED", people)] == ["u_manager"]


@pytest.mark.parametrize("status", ["FAILED", "NEEDS_REVIEW"])
def test_problems_go_to_tenant_admins_only(status: str) -> None:
    assert [e.recipient.user_id for e in plan_emails("evt_1", status, recipients())] == ["u_admin"]


def test_each_email_has_a_stable_delivery_key_so_retries_never_send_twice() -> None:
    first = {e.recipient.user_id: e.delivery_key for e in plan_emails("evt_1", "COMPLETED", recipients())}
    again = {e.recipient.user_id: e.delivery_key for e in plan_emails("evt_1", "COMPLETED", recipients())}
    other_event = {e.recipient.user_id: e.delivery_key for e in plan_emails("evt_2", "COMPLETED", recipients())}
    assert first == again
    assert len(set(first.values())) == 2
    assert first["u_manager"] != other_event["u_manager"]


def test_other_statuses_send_nothing() -> None:
    assert plan_emails("evt_1", "TRANSCRIBING", recipients()) == []


# --- templates -----------------------------------------------------------------------------------------------------


def test_report_ready_email_has_the_link_and_tenant_words() -> None:
    email = render_email("report_ready", "en", labels=LABELS, link=LINK, recording_title="Class 8 Science")
    assert "lesson" in email.subject.lower()  # the tenant's word, lower-cased mid-sentence
    assert LINK in email.text and LINK in email.html
    assert "Class 8 Science" in email.text


def test_hindi_template_renders_in_devanagari() -> None:
    email = render_email("report_ready", "hi", labels=LABELS, link=LINK, recording_title="Class 8 Science")
    assert any("ऀ" <= ch <= "ॿ" for ch in email.subject + email.text)
    assert LINK in email.text


def test_templates_cannot_carry_scores_or_quotes() -> None:
    with pytest.raises(TypeError):
        render_email("report_ready", "en", labels=LABELS, link=LINK, recording_title="x", score=3.5)  # type: ignore[call-arg]  # the point of the test
    with pytest.raises(TypeError):
        render_email("report_ready", "en", labels=LABELS, link=LINK, recording_title="x", quote="...")  # type: ignore[call-arg]  # the point of the test


def test_problem_email_states_the_reason() -> None:
    email = render_email(
        "needs_attention", "en", labels=LABELS, link=LINK, recording_title="Class 8 Science", reason="unclear_roles"
    )
    assert "unclear_roles" in email.text or "speakers" in email.text


def test_html_escapes_untrusted_text() -> None:
    email = render_email("report_ready", "en", labels=LABELS, link=LINK, recording_title="<script>x</script>")
    assert "<script>" not in email.html
    assert "&lt;script&gt;" in email.html


def test_unknown_language_falls_back_to_english_explicitly() -> None:
    email = render_email("report_ready", "ta", labels=LABELS, link=LINK, recording_title="x")
    assert email.language == "en"


# --- webhooks ------------------------------------------------------------------------------------------------------


SECRET = "whsec_test_only"  # pragma: allowlist secret  (fake test value)
BODY = json.dumps({"type": "recording.completed", "recording_id": "rec_123"}).encode()


def test_signature_matches_the_documented_algorithm() -> None:
    header = sign(BODY, SECRET, timestamp=1_760_000_000)
    expected = hmac.new(SECRET.encode(), b"1760000000." + BODY, hashlib.sha256).hexdigest()
    assert header == f"t=1760000000,v1={expected}"
    assert SIGNATURE_HEADER == "Sabha-Signature"


def test_a_valid_signature_verifies() -> None:
    header = sign(BODY, SECRET, timestamp=1_760_000_000)
    verify(BODY, header, SECRET, now=1_760_000_100)  # must not raise


@pytest.mark.parametrize(
    ("body", "secret", "now"),
    [
        (BODY + b" ", SECRET, 1_760_000_100),  # body changed
        (BODY, "another-secret", 1_760_000_100),  # wrong secret
        (BODY, SECRET, 1_760_000_000 + 301),  # older than 5 minutes (replay)
    ],
)
def test_tampered_wrong_or_stale_signatures_fail(body: bytes, secret: str, now: int) -> None:
    header = sign(BODY, SECRET, timestamp=1_760_000_000)
    with pytest.raises(InvalidSignature):
        verify(body, header, secret, now=now)


def test_malformed_signature_header_fails() -> None:
    with pytest.raises(InvalidSignature):
        verify(BODY, "v1=abc", SECRET, now=1_760_000_000)


def test_retry_schedule_backs_off_and_stops_within_24_hours() -> None:
    delays = retry_schedule()
    assert delays == sorted(delays)
    assert delays[0] <= 60
    assert sum(delays) <= MAX_RETRY_WINDOW_S == 24 * 3600
    assert len(delays) >= 8
