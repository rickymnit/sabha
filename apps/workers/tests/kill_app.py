"""A Celery app for test_worker_kill.py: the real StageRunner with one slow stage. Configured by environment."""

from __future__ import annotations

import os
import time
from typing import Any

import boto3
from botocore.config import Config
from pymongo import MongoClient

from sabha_core.settings import Settings
from sabha_core.state import RecordingStatus
from sabha_workers.celery_app import create_app
from sabha_workers.stages.runner import S3Artefacts, StageContext, StageRunner, StageSpec

E = os.environ
settings = Settings(  # type: ignore[call-arg]  # pydantic-settings
    _env_file=None,
    app_env="test",
    mongo_uri=E["KILL_MONGO_URI"],
    redis_url=E["KILL_REDIS_URL"],
    s3_bucket_audio="sabha-audio",
    s3_bucket_artefacts="sabha-artefacts",
    s3_bucket_backups="sabha-backups",
    oidc_issuer="https://auth.example.com",
    oidc_audience="https://api.example.com",
    oidc_client_id="web",
    celery_visibility_timeout_s=int(E["KILL_VISIBILITY_S"]),
)
app = create_app(settings)
client: MongoClient[dict[str, Any]] = MongoClient(E["KILL_MONGO_URI"], tz_aware=True)
database = client.get_database(E["KILL_DB"])
s3 = boto3.client(
    "s3", endpoint_url=E["KILL_S3_URL"], region_name="ap-south-1", aws_access_key_id=E["KILL_S3_KEY"],
    aws_secret_access_key=E["KILL_S3_SECRET"], config=Config(s3={"addressing_style": "path"}),
)  # fmt: skip
runner = StageRunner(
    db=database, artefacts=S3Artefacts(s3, "sabha-artefacts"), versions={"preprocess": "v1"}, worker=str(os.getpid())
)
SPEC = StageSpec("preprocess", working=RecordingStatus.PREPROCESSING, done_to=RecordingStatus.DIARIZING,
                 entry_from=RecordingStatus.UPLOADED)  # fmt: skip


def work(ctx: StageContext) -> dict[str, Any]:
    database.work_log.insert_one({"recording_id": ctx.recording.id, "pid": os.getpid()})
    time.sleep(float(E["KILL_WORK_S"]))
    return {}


@app.task(bind=True, name="sabha.preprocess", acks_late=True, reject_on_worker_lost=True)
def preprocess(self: Any, tenant_id: str, recording_id: str) -> str:
    return runner.run(SPEC, work, tenant_id, recording_id, attempt=self.request.retries + 1).result
