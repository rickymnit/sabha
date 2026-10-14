"""Create the local RustFS buckets and their CORS rules. Safe to run repeatedly.

Usage (from the repo root; `make dev` runs it after the containers are up):

    uv run python scripts/dev_storage.py

Reads only the storage variables from the environment and `.env`, so it works before the rest of the settings
(OIDC and so on) are filled in. Refuses to run against anything but a local S3_ENDPOINT_URL: AWS buckets are
created by hand or by Terraform, never by this script.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlsplit

import boto3
from dotenv import dotenv_values

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
BUCKET_VARS = ("S3_BUCKET_AUDIO", "S3_BUCKET_ARTEFACTS", "S3_BUCKET_BACKUPS")


def main() -> int:
    env = {**dotenv_values(".env"), **os.environ}
    endpoint = env.get("S3_ENDPOINT_URL") or ""
    if urlsplit(endpoint).hostname not in LOCAL_HOSTS:
        print("S3_ENDPOINT_URL must point at local RustFS (localhost); refusing to touch any other storage.")
        return 2
    missing = [name for name in (*BUCKET_VARS, "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY") if not env.get(name)]
    if missing:
        print(f"Missing in .env: {', '.join(missing)}. Run `make env` first.")
        return 2

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=env.get("S3_REGION") or "ap-south-1",
        aws_access_key_id=env["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=env["S3_SECRET_ACCESS_KEY"],
    )
    existing = {bucket["Name"] for bucket in s3.list_buckets().get("Buckets", [])}
    origins = [o.strip().rstrip("/") for o in (env.get("CORS_ORIGINS") or "").split(",") if o.strip()]
    for var in BUCKET_VARS:
        bucket = env[var]
        if bucket not in existing:
            s3.create_bucket(Bucket=bucket)
        if origins:
            # Browsers upload straight to storage with presigned URLs (golden rule 2); multipart completion needs ETag.
            rule = {
                "AllowedOrigins": origins,
                "AllowedMethods": ["PUT", "GET"],
                "AllowedHeaders": ["*"],
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 3000,
            }
            s3.put_bucket_cors(Bucket=bucket, CORSConfiguration={"CORSRules": [rule]})
        print(f"ok  {bucket}{' (created)' if bucket not in existing else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
