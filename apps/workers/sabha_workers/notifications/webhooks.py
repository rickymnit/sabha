"""Signed webhooks for integrations (plan task P2.7). The algorithm is documented for receivers in docs/webhooks.md.

Signing: the header `Sabha-Signature: t=<unix seconds>,v1=<hex>` where hex is
HMAC-SHA256(key = the endpoint's secret, message = "<t>." + raw request body). Receivers recompute it over the raw
bytes they received, compare in constant time, and reject timestamps more than 5 minutes from their clock (replay
protection).

Retries: failed deliveries are retried with exponential backoff (doubling from 30 s, capped at 2 h per wait) until
the total wait would pass 24 hours; then the delivery is marked failed in the delivery log.
"""

from __future__ import annotations

import hashlib
import hmac
import time

SIGNATURE_HEADER = "Sabha-Signature"
TOLERANCE_S = 300
MAX_RETRY_WINDOW_S = 24 * 3600
FIRST_RETRY_S = 30
MAX_RETRY_WAIT_S = 2 * 3600


class InvalidSignature(ValueError):
    """The webhook signature is missing, malformed, wrong or too old."""


def _digest(body: bytes, secret: str, timestamp: int) -> str:
    return hmac.new(secret.encode("utf-8"), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def sign(body: bytes, secret: str, *, timestamp: int | None = None) -> str:
    """The Sabha-Signature header value for `body`."""
    t = int(time.time()) if timestamp is None else timestamp
    return f"t={t},v1={_digest(body, secret, t)}"


def verify(body: bytes, header: str, secret: str, *, now: int | None = None, tolerance_s: int = TOLERANCE_S) -> None:
    """Raise InvalidSignature unless `header` is a valid, fresh signature of `body` (the receiver's side)."""
    parts = dict(part.split("=", 1) for part in header.split(",") if "=" in part)
    try:
        timestamp = int(parts["t"])
        signature = parts["v1"]
    except (KeyError, ValueError):
        raise InvalidSignature("malformed signature header") from None
    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > tolerance_s:
        raise InvalidSignature("signature timestamp outside the allowed window")
    if not hmac.compare_digest(signature, _digest(body, secret, timestamp)):
        raise InvalidSignature("signature does not match")


def retry_schedule() -> list[int]:
    """Seconds to wait before each retry: doubling from 30 s, each at most 2 h, all together at most 24 h."""
    delays: list[int] = []
    wait = FIRST_RETRY_S
    while sum(delays) + wait <= MAX_RETRY_WINDOW_S:
        delays.append(wait)
        wait = min(wait * 2, MAX_RETRY_WAIT_S)
    return delays
