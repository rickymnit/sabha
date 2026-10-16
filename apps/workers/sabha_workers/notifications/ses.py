"""Sending planned emails through Amazon SES, once per delivery key (plan task P2.7).

`deliver` is what the io.notify task calls for each planned and rendered email:

1. claim the delivery key in the delivery log; if it was already sent, or another worker holds it, do nothing;
2. send through SES (API v2, region from settings: ap-south-1 in staging and production, golden rule 12);
3. record the SES message id against the key.

So a retried task never sends the same email twice. If sending fails the claim is released and the error is raised,
so Celery's retry (with its backoff) can try again: throttling and SES outages are RetryableSendError, a rejected
message or an unverified sender is PermanentSendError and is not retried. There is no other provider to fall back
to (golden rule 7).

Recipient addresses are personal data: logs carry the user id and the delivery key, never the address.

The delivery log lives in MongoDB once the tenant-scoped repository exists (P1.6); `MemoryDeliveryLog` is for tests.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from sabha_core.settings import Settings
from sabha_workers.notifications.emails import PlannedEmail, RenderedEmail

log = logging.getLogger("sabha.workers.email")

# SESv2 error codes worth retrying; everything else from SES is treated as permanent.
_RETRYABLE_CODES = frozenset(
    {"TooManyRequestsException", "Throttling", "ThrottlingException", "LimitExceededException", "InternalFailure"}
)


class SendError(RuntimeError):
    """Sending failed. The message names the SES error code, never the recipient."""


class RetryableSendError(SendError):
    pass


class PermanentSendError(SendError):
    pass


class DeliveryLog(Protocol):
    def claim(self, key: str) -> bool:
        """Take `key` for sending. False if it was already sent or another worker is sending it."""

    def release(self, key: str) -> None:
        """Give `key` back after a failed send, so a retry can claim it."""

    def mark_sent(self, key: str, message_id: str) -> None: ...


@dataclass
class _Entry:
    state: Literal["sending", "sent"]
    message_id: str | None = None
    sent_at: datetime | None = None


class MemoryDeliveryLog:
    """In-process delivery log for tests and local runs."""

    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def claim(self, key: str) -> bool:
        with self._lock:
            if key in self._entries:
                return False
            self._entries[key] = _Entry("sending")
            return True

    def release(self, key: str) -> None:
        with self._lock:
            if self._entries.get(key, _Entry("sent")).state == "sending":
                del self._entries[key]

    def mark_sent(self, key: str, message_id: str) -> None:
        with self._lock:
            self._entries[key] = _Entry("sent", message_id, datetime.now(UTC))

    def sent(self, key: str) -> str | None:
        entry = self._entries.get(key)
        return entry.message_id if entry and entry.state == "sent" else None


class SesSender:
    def __init__(self, client: Any, sender: str, *, configuration_set: str | None = None) -> None:
        self._client = client
        self._sender = sender
        self._configuration_set = configuration_set

    @classmethod
    def from_settings(cls, settings: Settings, client: Any | None = None) -> SesSender:
        if settings.ses_sender is None:
            raise SendError("SES_SENDER is not set; emails cannot be sent")
        return cls(client or boto3.client("sesv2", region_name=settings.ses_region), settings.ses_sender)

    def send(self, to: str, email: RenderedEmail, delivery_key: str) -> str:
        """Send one email; returns the SES message id."""
        request: dict[str, Any] = {
            "FromEmailAddress": self._sender,
            "Destination": {"ToAddresses": [to]},
            "Content": {
                "Simple": {
                    "Subject": {"Data": email.subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": email.text, "Charset": "UTF-8"},
                        "Html": {"Data": email.html, "Charset": "UTF-8"},
                    },
                }
            },
            # Lets bounce and complaint notifications be matched back to the delivery log.
            "EmailTags": [{"Name": "delivery_key", "Value": delivery_key}],
        }
        if self._configuration_set:
            request["ConfigurationSetName"] = self._configuration_set
        try:
            response = self._client.send_email(**request)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", "Unknown"))
            error = RetryableSendError if code in _RETRYABLE_CODES else PermanentSendError
            raise error(f"SES refused the email: {code}") from None
        except BotoCoreError as exc:  # connection and timeout problems
            raise RetryableSendError(f"SES could not be reached: {type(exc).__name__}") from None
        return str(response["MessageId"])


class EmailSender(Protocol):
    def send(self, to: str, email: RenderedEmail, delivery_key: str) -> str: ...


def deliver(planned: PlannedEmail, email: RenderedEmail, *, sender: EmailSender, delivery_log: DeliveryLog) -> bool:
    """Send `email` unless its delivery key was already handled. True if this call sent it."""
    key = planned.delivery_key
    context = {"user_id": planned.recipient.user_id, "delivery_key": key, "kind": planned.kind}
    if not delivery_log.claim(key):
        log.info("email already sent or in progress; skipping", extra=context)
        return False
    try:
        message_id = sender.send(planned.recipient.email, email, key)
    except BaseException as exc:
        delivery_log.release(key)
        if isinstance(exc, SendError):
            retryable = isinstance(exc, RetryableSendError)
            log.warning("email not sent", extra={**context, "reason": str(exc), "retryable": retryable})
        raise
    delivery_log.mark_sent(key, message_id)
    log.info("email sent", extra={**context, "message_id": message_id})
    return True
