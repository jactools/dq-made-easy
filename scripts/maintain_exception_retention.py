#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
FASTAPI_DIR = REPO_ROOT / "dq-api" / "fastapi"

if str(FASTAPI_DIR) not in sys.path:
    sys.path.insert(0, str(FASTAPI_DIR))

os.chdir(REPO_ROOT)

from sqlalchemy import func, select

from app.application.services.exception_retention import purge_repository_exception_facts_for_data_object_version
from app.application.services.exception_retention import resolve_data_object_retention_policy
from app.core.config import get_settings
from app.infrastructure.orm.models import GxExecutionViolationRow
from app.infrastructure.orm.session import session_scope
from app.infrastructure.repositories.postgres_data_catalog_repository import PostgresDataCatalogRepository
from app.infrastructure.repositories.postgres_gx_execution_violation_repository import PostgresGxExecutionViolationRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply the canonical retention policy for persisted exception facts.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override the database URL used to load data-catalog metadata and purge repository-backed facts.",
    )
    parser.add_argument(
        "--now",
        default=None,
        help="Evaluate retention windows at this UTC timestamp (ISO-8601). Defaults to the current time.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Delete matching rows or objects. Without this flag the script only reports what would be removed.",
    )
    return parser.parse_args()


def normalize_timestamp(raw_value: str | None) -> datetime:
    if raw_value is None:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(str(raw_value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def require_database_url(explicit_value: str | None) -> tuple[Any, str]:
    get_settings.cache_clear()
    settings = get_settings()
    database_url = str(explicit_value or settings.database_url or "").strip()
    if not database_url:
        raise SystemExit("DQ_DB_LOCAL_URL or DQ_DB_INTERNAL_URL is required for exception retention maintenance")
    return settings, database_url


def count_repository_violations_before_for_version(
    database_url: str,
    *,
    data_object_version_id: str,
    cutoff: datetime,
) -> int:
    normalized_data_object_version_id = str(data_object_version_id or "").strip()
    if not normalized_data_object_version_id:
        raise SystemExit("data_object_version_id is required for exception retention counting")

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count())
            .select_from(GxExecutionViolationRow)
            .where(GxExecutionViolationRow.data_object_version_id == normalized_data_object_version_id)
            .where(GxExecutionViolationRow.detected_at < cutoff)
        ).scalar_one()
    return int(count or 0)


def build_s3_client(settings: Any):
    try:
        import boto3
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit("Python package 'boto3' is required for object-storage exception retention maintenance") from exc

    endpoint = str(getattr(settings, "gx_exception_storage_endpoint", "") or "").strip()
    access_key = str(getattr(settings, "gx_exception_storage_access_key", "") or "").strip()
    secret_key = str(getattr(settings, "gx_exception_storage_secret_key", "") or "").strip()
    region = str(getattr(settings, "gx_exception_storage_region", "us-east-1") or "us-east-1").strip() or "us-east-1"
    ssl_enabled = bool(getattr(settings, "gx_exception_storage_ssl_enabled", True))
    if not endpoint:
        raise SystemExit("GX_EXCEPTION_STORAGE_ENDPOINT is required for object-storage exception retention maintenance")
    if not access_key or not secret_key:
        raise SystemExit(
            "GX_EXCEPTION_STORAGE_ACCESS_KEY and GX_EXCEPTION_STORAGE_SECRET_KEY are required for object-storage exception retention maintenance"
        )

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        verify=ssl_enabled,
    )


def collect_archive_keys_for_version(settings: Any, *, data_object_version_id: str, cutoff: datetime) -> tuple[Any, str, list[str]]:
    bucket = str(getattr(settings, "gx_exception_storage_bucket", "") or "").strip()
    prefix = str(getattr(settings, "gx_exception_storage_prefix", "") or "").strip().strip("/")
    normalized_data_object_version_id = str(data_object_version_id or "").strip()
    if not bucket:
        raise SystemExit("GX_EXCEPTION_STORAGE_BUCKET is required for object-storage exception retention maintenance")
    if not normalized_data_object_version_id:
        raise SystemExit("data_object_version_id is required for object-storage exception retention maintenance")

    client = build_s3_client(settings)
    paginator = client.get_paginator("list_objects_v2")
    keys: list[str] = []
    object_prefix = "/".join([part for part in [prefix, f"data_object_version_id={normalized_data_object_version_id}"] if part]) + "/"

    for page in paginator.paginate(Bucket=bucket, Prefix=object_prefix):
        for item in page.get("Contents") or []:
            key = str(item.get("Key") or "").strip()
            last_modified = item.get("LastModified")
            if not key:
                continue
            if last_modified is None:
                raise SystemExit(f"Object '{key}' is missing LastModified metadata")
            normalized_last_modified = (
                last_modified.replace(tzinfo=UTC)
                if getattr(last_modified, "tzinfo", None) is None
                else last_modified.astimezone(UTC)
            )
            if normalized_last_modified < cutoff:
                keys.append(key)

    return client, bucket, keys


def delete_archive_keys(client: Any, *, bucket: str, keys: list[str]) -> int:
    deleted = 0
    for start_index in range(0, len(keys), 1000):
        batch = keys[start_index : start_index + 1000]
        response = client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
        )
        errors = response.get("Errors") or []
        if errors:
            messages = ", ".join(str(error.get("Message") or error.get("Code") or error) for error in errors)
            raise SystemExit(f"Object-storage exception retention purge failed: {messages}")
        deleted += len(batch)
    return deleted


def main() -> int:
    args = parse_args()
    settings, database_url = require_database_url(args.database_url)
    now = normalize_timestamp(args.now)
    backend = str(getattr(settings, "gx_exception_storage_backend", "s3") or "s3").strip().lower()

    data_catalog_repository = PostgresDataCatalogRepository(database_url)
    data_object_versions = data_catalog_repository.list_data_object_versions()
    if not data_object_versions:
        raise SystemExit("No data object versions were found for exception retention maintenance")

    summary: dict[str, Any] = {
        "analytics_projections": {
            "deleted_records": 0,
            "mode": "query_time_only",
            "status": "no_materialized_projection_store_configured",
        },
        "archive_facts": {
            "applies": backend == "s3",
            "bucket": str(getattr(settings, "gx_exception_storage_bucket", "") or "").strip(),
            "deleted_objects": 0,
            "matched_objects": 0,
            "prefix": str(getattr(settings, "gx_exception_storage_prefix", "") or "").strip(),
        },
        "backend": backend,
        "data_object_versions": [],
        "dry_run": not args.execute,
        "evaluated_at": now.isoformat(),
        "policy_source": "data_object_versions.storage_options_json.retention_policy",
        "repository_facts": {
            "applies": backend in {"repository", "db"},
            "deleted_records": 0,
            "matched_records": 0,
        },
    }

    violation_repository = PostgresGxExecutionViolationRepository(database_url)

    for version in data_object_versions:
        policy = resolve_data_object_retention_policy(version)
        summary["data_object_versions"].append(
            {
                "data_object_version_id": str(version.id),
                "exception_analytics_projection_retention_days": policy.analytics_projection_retention_days,
                "exception_fact_archive_retention_days": policy.archive_retention_days,
                "exception_fact_purge_batch_size": policy.purge_batch_size,
                "exception_fact_retention_days": policy.fact_retention_days,
            }
        )

        if backend in {"repository", "db"}:
            repository_cutoff = policy.fact_cutoff(now=now)
            summary["repository_facts"]["matched_records"] += count_repository_violations_before_for_version(
                database_url,
                data_object_version_id=str(version.id),
                cutoff=repository_cutoff,
            )
            if args.execute:
                summary["repository_facts"]["deleted_records"] += asyncio.run(
                    purge_repository_exception_facts_for_data_object_version(
                        violation_repository,
                        data_object_version_id=str(version.id),
                        policy=policy,
                        now=now,
                    )
                )
        elif backend == "s3":
            archive_cutoff = policy.archive_cutoff(now=now)
            client, bucket, keys = collect_archive_keys_for_version(
                settings,
                data_object_version_id=str(version.id),
                cutoff=archive_cutoff,
            )
            summary["archive_facts"]["bucket"] = bucket
            summary["archive_facts"]["matched_objects"] += len(keys)
            if args.execute:
                summary["archive_facts"]["deleted_objects"] += delete_archive_keys(client, bucket=bucket, keys=keys)
        else:
            raise SystemExit(f"Unsupported GX exception storage backend '{backend}'")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
