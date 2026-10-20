"""Abort browser uploads that were started but never completed (plan task P2.2; P2.4 schedules it hourly).

An abandoned multipart upload keeps its parts in the audio bucket, costing storage, until aborted. This aborts
every multipart upload in the bucket started more than `older_than` ago (24 h by default). The bucket's own
lifecycle rule (abort after 7 days, docs/setup/cloud-checklist.md) remains as a backstop. Storage maintenance only:
recordings left in CREATED are not changed here (their parts endpoint answers 409 once the upload is gone).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

log = logging.getLogger("sabha.workers.upload_cleanup")

DEFAULT_MAX_AGE = timedelta(hours=24)


def abort_stale_uploads(
    s3: Any, bucket: str, *, older_than: timedelta = DEFAULT_MAX_AGE, now: datetime | None = None
) -> list[str]:
    """Abort stale multipart uploads in `bucket`; returns the keys whose uploads were aborted."""
    cutoff = (now or datetime.now(UTC)) - older_than
    aborted = []
    for page in s3.get_paginator("list_multipart_uploads").paginate(Bucket=bucket):
        for upload in page.get("Uploads", []):
            if upload["Initiated"] < cutoff:
                s3.abort_multipart_upload(Bucket=bucket, Key=upload["Key"], UploadId=upload["UploadId"])
                aborted.append(upload["Key"])
    if aborted:
        log.info("aborted stale multipart uploads", extra={"count": len(aborted), "bucket": bucket})
    return aborted
