"""SES delivery: the request sent, one email per delivery key across retries, and how errors are classified."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber

from sabha_core.settings import Settings
from sabha_workers.notifications.emails import Recipient, plan_emails, render_email
from sabha_workers.notifications.ses import (
    MemoryDeliveryLog,
    PermanentSendError,
    RetryableSendError,
    SendError,
    SesSender,
    deliver,
)

SENDER = "no-reply@example.in"
TEACHER = Recipient("u_teacher", "teacher@example.in", "staff", "en", wants_report_emails=True, is_subject=True)
LABELS = {"person": "Teacher", "recording": "Lesson", "unit": "Department", "manager": "Head of department"}


@pytest.fixture
def ses() -> Iterator[tuple[Any, Stubber]]:
    client = boto3.client(
        "sesv2",
        region_name="ap-south-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",  # pragma: allowlist secret  (fake test value)
    )
    with Stubber(client) as stubber:
        yield client, stubber
        stubber.assert_no_pending_responses()


def planned_and_rendered() -> tuple[Any, Any]:
    [planned] = plan_emails("evt_1", "COMPLETED", [TEACHER])
    email = render_email(
        "report_ready", "en", labels=LABELS, link="https://app.example.in/r/rec_1", recording_title="Fractions, 7B"
    )
    return planned, email


def expected_request(planned: Any, email: Any) -> dict[str, Any]:
    return {
        "FromEmailAddress": SENDER,
        "Destination": {"ToAddresses": ["teacher@example.in"]},
        "Content": {
            "Simple": {
                "Subject": {"Data": email.subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": email.text, "Charset": "UTF-8"},
                    "Html": {"Data": email.html, "Charset": "UTF-8"},
                },
            }
        },
        "EmailTags": [{"Name": "delivery_key", "Value": planned.delivery_key}],
    }


def test_sends_text_and_html_with_the_delivery_key_tag(ses: tuple[Any, Stubber]) -> None:
    client, stubber = ses
    planned, email = planned_and_rendered()
    stubber.add_response("send_email", {"MessageId": "m-1"}, expected_request(planned, email))
    log = MemoryDeliveryLog()
    assert deliver(planned, email, sender=SesSender(client, SENDER), delivery_log=log) is True
    assert log.sent(planned.delivery_key) == "m-1"


def test_a_retried_event_sends_nothing_twice(ses: tuple[Any, Stubber]) -> None:
    client, stubber = ses
    planned, email = planned_and_rendered()
    stubber.add_response("send_email", {"MessageId": "m-1"}, expected_request(planned, email))  # exactly one
    log, sender = MemoryDeliveryLog(), SesSender(client, SENDER)
    assert deliver(planned, email, sender=sender, delivery_log=log) is True
    # The task is retried (worker restart, acks_late): the same event plans the same keys.
    [again] = plan_emails("evt_1", "COMPLETED", [TEACHER])
    assert deliver(again, email, sender=sender, delivery_log=log) is False


def test_throttling_is_retryable_and_releases_the_key(ses: tuple[Any, Stubber]) -> None:
    client, stubber = ses
    planned, email = planned_and_rendered()
    stubber.add_client_error("send_email", "TooManyRequestsException", http_status_code=429)
    stubber.add_response("send_email", {"MessageId": "m-2"}, expected_request(planned, email))
    log, sender = MemoryDeliveryLog(), SesSender(client, SENDER)
    with pytest.raises(RetryableSendError, match="TooManyRequestsException"):
        deliver(planned, email, sender=sender, delivery_log=log)
    assert log.sent(planned.delivery_key) is None
    assert deliver(planned, email, sender=sender, delivery_log=log) is True  # the retry can send
    assert log.sent(planned.delivery_key) == "m-2"


@pytest.mark.parametrize("code", ["MessageRejected", "MailFromDomainNotVerifiedException", "AccountSuspendedException"])
def test_rejections_are_permanent(ses: tuple[Any, Stubber], code: str) -> None:
    client, stubber = ses
    planned, email = planned_and_rendered()
    stubber.add_client_error("send_email", code, http_status_code=400)
    with pytest.raises(PermanentSendError, match=code):
        deliver(planned, email, sender=SesSender(client, SENDER), delivery_log=MemoryDeliveryLog())


def test_connection_problems_are_retryable() -> None:
    class Down:
        def send_email(self, **_: Any) -> Any:
            raise EndpointConnectionError(endpoint_url="https://email.ap-south-1.amazonaws.com")

    planned, email = planned_and_rendered()
    with pytest.raises(RetryableSendError, match="EndpointConnectionError"):
        deliver(planned, email, sender=SesSender(Down(), SENDER), delivery_log=MemoryDeliveryLog())


def test_the_recipient_address_is_never_logged(ses: tuple[Any, Stubber], caplog: pytest.LogCaptureFixture) -> None:
    client, stubber = ses
    planned, email = planned_and_rendered()
    stubber.add_client_error("send_email", "MessageRejected", http_status_code=400)
    with caplog.at_level(logging.INFO), pytest.raises(SendError):
        deliver(planned, email, sender=SesSender(client, SENDER), delivery_log=MemoryDeliveryLog())
    text = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert "u_teacher" in text
    assert "teacher@example.in" not in text


def test_a_missing_sender_is_a_clear_error() -> None:
    values: dict[str, Any] = {
        "app_env": "test",
        "mongo_uri": "mongodb://localhost:27017/?replicaSet=rs0",
        "redis_url": "redis://localhost:6380/0",
        "s3_bucket_audio": "a",
        "s3_bucket_artefacts": "b",
        "s3_bucket_backups": "c",
        "oidc_issuer": "https://auth.example.com",
        "oidc_audience": "api",
        "oidc_client_id": "web",
    }
    settings = Settings(_env_file=None, **values)  # type: ignore[call-arg]  # _env_file is a settings option
    with pytest.raises(SendError, match="SES_SENDER"):
        SesSender.from_settings(settings, client=object())
    assert isinstance(
        SesSender.from_settings(settings.model_copy(update={"ses_sender": SENDER}), client=object()), SesSender
    )
