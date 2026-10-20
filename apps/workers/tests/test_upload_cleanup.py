"""abort_stale_uploads against RustFS: stale multipart uploads are aborted, fresh ones kept."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from sabha_workers.upload_cleanup import abort_stale_uploads

pytestmark = pytest.mark.integration

BUCKET = "sabha-audio"


def open_uploads(s3: Any) -> set[str]:
    return {u["Key"] for u in s3.list_multipart_uploads(Bucket=BUCKET).get("Uploads", [])}


def test_only_stale_uploads_are_aborted(s3_storage: Any) -> None:
    s3 = s3_storage.client()
    key = f"t1/{uuid.uuid4().hex}/original/lesson.mp3"
    s3.create_multipart_upload(Bucket=BUCKET, Key=key)

    assert abort_stale_uploads(s3, BUCKET) == []  # started just now
    assert key in open_uploads(s3)

    later = datetime.now(UTC) + timedelta(hours=25)
    assert key in abort_stale_uploads(s3, BUCKET, now=later)
    assert key not in open_uploads(s3)
