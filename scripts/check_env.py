"""Check that every backing service in the current environment is reachable and set up as Sabha needs.

Usage (from the repo root):

    uv run python scripts/check_env.py

Reads settings exactly as the app does (environment variables, then `.env`), then checks MongoDB (must be a
replica set), Redis, S3/RustFS (put, get and delete one object under `healthcheck/` in each of the three
buckets) and the OIDC discovery
document. Prints PASS or FAIL per service and exits 1 if anything failed, 2 if the settings themselves are
invalid. Secret values are never printed.
"""

from __future__ import annotations

import json
import sys
import urllib.request
import uuid
from collections.abc import Callable

import boto3
import redis
from botocore.config import Config
from pymongo import MongoClient

from sabha_core.settings import Settings, SettingsError, load_settings

TIMEOUT_S = 5


def check_mongo(settings: Settings) -> str:
    client: MongoClient[dict[str, object]] = MongoClient(
        settings.mongo_uri.get_secret_value(), serverSelectionTimeoutMS=TIMEOUT_S * 1000
    )
    try:
        hello = client.admin.command("hello")
    finally:
        client.close()
    if "setName" not in hello:
        raise RuntimeError("connected, but the server is not a replica set (transactions need one)")
    return f"replica set {hello['setName']!r}"


def check_redis(settings: Settings) -> str:
    client = redis.Redis.from_url(
        settings.redis_url.get_secret_value(), socket_connect_timeout=TIMEOUT_S, socket_timeout=TIMEOUT_S
    )
    try:
        if not client.ping():
            raise RuntimeError("PING did not return PONG")
    finally:
        client.close()
    return "PING ok"


def check_storage(settings: Settings) -> str:
    credentials = {}
    if settings.s3_access_key_id is not None and settings.s3_secret_access_key is not None:
        credentials = {
            "aws_access_key_id": settings.s3_access_key_id.get_secret_value(),
            "aws_secret_access_key": settings.s3_secret_access_key.get_secret_value(),
        }
    s3 = boto3.client(
        "s3",
        region_name=settings.s3_region,
        endpoint_url=settings.s3_endpoint_url,
        config=Config(connect_timeout=TIMEOUT_S, read_timeout=TIMEOUT_S, retries={"max_attempts": 2}),
        **credentials,
    )
    buckets = (settings.s3_bucket_audio, settings.s3_bucket_artefacts, settings.s3_bucket_backups)
    body = b"sabha healthcheck"
    for bucket in buckets:
        key = f"healthcheck/{uuid.uuid4()}.txt"
        try:
            s3.put_object(Bucket=bucket, Key=key, Body=body)
        except Exception as exc:
            raise RuntimeError(f"cannot write to bucket {bucket!r}: {exc}") from exc
        try:
            if s3.get_object(Bucket=bucket, Key=key)["Body"].read() != body:
                raise RuntimeError(f"object read back from {bucket!r} did not match what was written")
        finally:
            s3.delete_object(Bucket=bucket, Key=key)
    where = settings.s3_endpoint_url or settings.s3_region
    return f"put/get/delete in {', '.join(repr(b) for b in buckets)} ({where})"


def check_oidc(settings: Settings) -> str:
    url = f"{settings.oidc_issuer}/.well-known/openid-configuration"
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as response:  # noqa: S310  # http(s) only, checked in settings
        document = json.load(response)
    if str(document.get("issuer", "")).rstrip("/") != settings.oidc_issuer:
        raise RuntimeError("discovery document 'issuer' does not match OIDC_ISSUER")
    if "jwks_uri" not in document:
        raise RuntimeError("discovery document has no 'jwks_uri'")
    return "discovery document ok"


CHECKS: list[tuple[str, Callable[[Settings], str]]] = [
    ("MongoDB", check_mongo),
    ("Redis", check_redis),
    ("Object storage", check_storage),
    ("OIDC", check_oidc),
]


def _secret_values(settings: Settings) -> list[str]:
    values = []
    for field in (
        settings.mongo_uri,
        settings.redis_url,
        settings.s3_access_key_id,
        settings.s3_secret_access_key,
        settings.sentry_dsn,
        settings.langfuse_secret_key,
    ):
        if field is not None and field.get_secret_value():
            values.append(field.get_secret_value())
    return values


def _scrub(text: str, secrets: list[str]) -> str:
    # Driver errors can quote connection strings; never let one reach the terminal.
    for secret in secrets:
        text = text.replace(secret, "***")
    return text


def main() -> int:
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"FAIL  settings\n{exc}")
        return 2

    print(f"Checking services for APP_ENV={settings.app_env}\n")
    secrets = _secret_values(settings)
    failed = 0
    for name, check in CHECKS:
        try:
            detail = check(settings)
        except Exception as exc:  # report every failure and keep checking the rest
            failed += 1
            reason = _scrub(str(exc), secrets).splitlines()[0][:300] if str(exc) else ""
            print(f"FAIL  {name:<15} {type(exc).__name__}: {reason}")
        else:
            print(f"PASS  {name:<15} {detail}")

    print(f"\n{len(CHECKS) - failed} of {len(CHECKS)} services passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
