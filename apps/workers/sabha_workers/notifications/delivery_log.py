"""The delivery log in MongoDB: one `deliveries` document per delivery key, per tenant (plan task P2.7).

Implements sabha_workers.notifications.ses.DeliveryLog. Keys are unique per (tenant_id, key) (sabha_core.indexes),
so two tenants never share one (/tenant-check finding 3). A claim left by a worker that died is taken over once it
is older than `stale_after`. `mark_failed` records a delivery refused for good, which is never retried.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal

from pymongo.errors import DuplicateKeyError

from sabha_core.models import Delivery, new_id, utc_now
from sabha_core.repo import SyncTenantRepo


class MongoDeliveryLog:
    def __init__(
        self,
        deliveries: SyncTenantRepo[Delivery],
        *,
        channel: Literal["email", "webhook"] = "email",
        stale_after: timedelta = timedelta(minutes=10),
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._deliveries = deliveries
        self._channel = channel
        self._stale_after = stale_after
        self._now = now

    def claim(self, key: str) -> bool:
        """True if this caller may send `key` now."""
        try:
            self._deliveries.insert_one(Delivery(key=key, channel=self._channel, claimed_at=self._now()))
            return True
        except DuplicateKeyError:
            pass
        existing = self._deliveries.find_one({"key": key})
        if existing is None or existing.status != "claimed" or existing.claimed_at > self._now() - self._stale_after:
            return False
        taken = self._deliveries.update_one(
            {"key": key, "status": "claimed", "claimed_at": existing.claimed_at}, {"$set": {"claimed_at": self._now()}}
        )
        return taken == 1

    def release(self, key: str) -> None:
        self._deliveries.delete_one({"key": key, "status": "claimed"})

    def mark_sent(self, key: str, message_id: str) -> None:
        self._deliveries.update_one(
            {"key": key}, {"$set": {"status": "sent", "message_id": message_id, "sent_at": self._now()}}
        )

    def mark_failed(self, key: str, reason: str) -> None:
        self._deliveries.update_one(
            {"key": key},
            {
                "$set": {"status": "failed", "last_error": reason[:500]},
                "$setOnInsert": {"_id": new_id(), "channel": self._channel, "claimed_at": self._now()},
            },
            upsert=True,
        )

    def status(self, key: str) -> str | None:
        found = self._deliveries.find_one({"key": key})
        return found.status if found else None
