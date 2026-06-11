#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import gzip
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

from sqlalchemy import and_
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select

from app.application.services.exception_backfill import build_object_storage_exception_backfill_plan
from app.application.services.exception_backfill import build_repository_exception_backfill_decision
from app.application.services.exception_backfill import build_violation_create_entity
from app.core.config import get_settings
from app.infrastructure.orm.models import GxExecutionViolationRow
from app.infrastructure.orm.session import session_scope
from app.infrastructure.repositories.postgres_gx_execution_violation_repository import PostgresGxExecutionViolationRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill legacy GX exception facts into the canonical contract where possible.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override the database URL used to update or replay canonical exception facts.",
    )
    parser.add_argument(
        "--source",
        choices=["auto", "object-storage", "repository"],
        default="auto",
        help="Backfill source. 'auto' follows the configured GX exception storage backend.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Repository batch size per iteration.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Persist updates. Without this flag the script only reports eligible and unresolved work.",
    )
    return parser.parse_args()


def require_database_url(explicit_value: str | None) -> tuple[Any, str]:
    get_settings.cache_clear()
    settings = get_settings()
    database_url = str(explicit_value or settings.database_url or "").strip()
    if not database_url:
        raise SystemExit("DQ_DB_LOCAL_URL or DQ_DB_INTERNAL_URL is required for exception backfill maintenance")
    return settings, database_url


def _json_text(key: str):
    return func.jsonb_extract_path_text(GxExecutionViolationRow.ops_metadata_json, key)


def _present_json_text(key: str):
    return and_(_json_text(key).is_not(None), _json_text(key) != "")


def _missing_json_text(key: str):
    return or_(_json_text(key).is_(None), _json_text(key) == "")


def _numeric_json_text(key: str):
    return _json_text(key).op("~")(r"^[0-9]+$")


def _repository_missing_canonical_fields_condition():
    return or_(
        _missing_json_text("engine_type"),
        _missing_json_text("validation_artifact_id"),
        _missing_json_text("validation_artifact_version"),
        _missing_json_text("record_identifier_type"),
        _missing_json_text("record_identifier_value"),
        _missing_json_text("reason_code"),
        _missing_json_text("reason_text"),
    )


def _repository_backfillable_condition():
    validation_artifact_id_present = or_(
        _present_json_text("validation_artifact_id"),
        _present_json_text("suite_id"),
    )
    validation_artifact_version_present = or_(
        and_(_present_json_text("validation_artifact_version"), _numeric_json_text("validation_artifact_version")),
        and_(_present_json_text("suite_version"), _numeric_json_text("suite_version")),
    )
    return and_(
        _repository_missing_canonical_fields_condition(),
        GxExecutionViolationRow.data_primary_key != "",
        GxExecutionViolationRow.violation_reason != "",
        _present_json_text("rule_version_id"),
        validation_artifact_id_present,
        validation_artifact_version_present,
    )


def count_repository_rows(database_url: str, *, eligible: bool) -> int:
    condition = _repository_backfillable_condition() if eligible else and_(
        _repository_missing_canonical_fields_condition(),
        ~_repository_backfillable_condition(),
    )
    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count())
            .select_from(GxExecutionViolationRow)
            .where(condition)
        ).scalar_one()
    return int(count or 0)


def execute_repository_backfill(database_url: str, *, limit: int) -> dict[str, Any]:
    updated_rows = 0
    skipped_rows = 0
    while True:
        with session_scope(database_url) as session:
            rows = session.execute(
                select(GxExecutionViolationRow)
                .where(_repository_backfillable_condition())
                .order_by(
                    GxExecutionViolationRow.detected_at.asc(),
                    GxExecutionViolationRow.data_object_version_id.asc(),
                    GxExecutionViolationRow.id.asc(),
                )
                .limit(limit)
            ).scalars().all()
            if not rows:
                break
            batch_updates = 0
            for row in rows:
                decision = build_repository_exception_backfill_decision(
                    {
                        "id": row.id,
                        "dataObjectVersionId": row.data_object_version_id,
                        "executionRunId": row.execution_run_id,
                        "ruleId": row.rule_id,
                        "dataPrimaryKey": row.data_primary_key,
                        "violationReason": row.violation_reason,
                        "opsMetadata": dict(row.ops_metadata_json or {}),
                        "detectedAt": row.detected_at.isoformat(),
                    }
                )
                if decision.status == "skipped":
                    skipped_rows += 1
                    continue
                if decision.updated_ops_metadata is None:
                    continue
                row.ops_metadata_json = dict(decision.updated_ops_metadata)
                row.updated_at = datetime.now(UTC)
                batch_updates += 1
            if batch_updates == 0:
                break
            updated_rows += batch_updates
    return {
        "updated_rows": updated_rows,
        "skipped_rows": skipped_rows,
    }


def build_s3_client(settings: Any):
    try:
        import boto3
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit("Python package 'boto3' is required for object-storage exception backfill maintenance") from exc

    endpoint = str(getattr(settings, "gx_exception_storage_endpoint", "") or "").strip()
    access_key = str(getattr(settings, "gx_exception_storage_access_key", "") or "").strip()
    secret_key = str(getattr(settings, "gx_exception_storage_secret_key", "") or "").strip()
    region = str(getattr(settings, "gx_exception_storage_region", "us-east-1") or "us-east-1").strip() or "us-east-1"
    ssl_enabled = bool(getattr(settings, "gx_exception_storage_ssl_enabled", True))
    if not endpoint:
        raise SystemExit("GX_EXCEPTION_STORAGE_ENDPOINT is required for object-storage exception backfill maintenance")
    if not access_key or not secret_key:
        raise SystemExit(
            "GX_EXCEPTION_STORAGE_ACCESS_KEY and GX_EXCEPTION_STORAGE_SECRET_KEY are required for object-storage exception backfill maintenance"
        )

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        verify=ssl_enabled,
    )


def _read_payload_bytes(body: bytes) -> bytes:
    if body[:2] == b"\x1f\x8b":
        return gzip.decompress(body)
    return body


async def collect_object_storage_backfill_summary(settings: Any, database_url: str, *, execute: bool) -> dict[str, Any]:
    bucket = str(getattr(settings, "gx_exception_storage_bucket", "") or "").strip()
    prefix = str(getattr(settings, "gx_exception_storage_prefix", "") or "").strip()
    if not bucket:
        raise SystemExit("GX_EXCEPTION_STORAGE_BUCKET is required for object-storage exception backfill maintenance")

    client = build_s3_client(settings)
    paginator = client.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents") or []:
            key = str(item.get("Key") or "").strip()
            if key:
                keys.append(key)
    keys.sort()

    repository = PostgresGxExecutionViolationRepository(database_url)
    summary = {
        "bucket": bucket,
        "prefix": prefix,
        "objects_scanned": len(keys),
        "objects_requiring_replay": 0,
        "rows_replayed": 0,
        "rows_skipped": 0,
    }

    for key in keys:
        response = client.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
        payload = json.loads(_read_payload_bytes(body).decode("utf-8"))
        if not isinstance(payload, dict):
            raise SystemExit(f"Object '{key}' does not contain a JSON object payload")
        decisions, requires_replay = build_object_storage_exception_backfill_plan(payload)
        summary["rows_skipped"] += sum(1 for decision in decisions if decision.status == "skipped")
        if not requires_replay:
            continue
        eligible = [
            build_violation_create_entity(decision.canonical_violation)
            for decision in decisions
            if decision.status != "skipped" and decision.canonical_violation is not None
        ]
        if not eligible:
            continue
        summary["objects_requiring_replay"] += 1
        summary["rows_replayed"] += len(eligible)
        if execute:
            await repository.save_violations(eligible)

    return summary


def resolve_source(settings: Any, requested_source: str) -> str:
    if requested_source != "auto":
        return requested_source
    backend = str(getattr(settings, "gx_exception_storage_backend", "s3") or "s3").strip().lower()
    if backend in {"repository", "db"}:
        return "repository"
    if backend == "s3":
        return "object-storage"
    raise SystemExit(f"Unsupported GX exception storage backend '{backend}'")


def main() -> int:
    args = parse_args()
    settings, database_url = require_database_url(args.database_url)
    source = resolve_source(settings, args.source)

    summary: dict[str, Any] = {
        "dry_run": not args.execute,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "source": source,
    }

    if source == "repository":
        summary["repository"] = {
            "eligible_rows": count_repository_rows(database_url, eligible=True),
            "unresolved_rows": count_repository_rows(database_url, eligible=False),
            "updated_rows": 0,
            "skipped_rows": 0,
        }
        if args.execute:
            summary["repository"].update(execute_repository_backfill(database_url, limit=max(args.limit, 1)))
    elif source == "object-storage":
        summary["object_storage"] = asyncio.run(
            collect_object_storage_backfill_summary(settings, database_url, execute=args.execute)
        )
        summary["repository"] = {
            "target": "postgres_gx_execution_violation_repository",
        }
    else:
        raise SystemExit(f"Unsupported exception backfill source '{source}'")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())