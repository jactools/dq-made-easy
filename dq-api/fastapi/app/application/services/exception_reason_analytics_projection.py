from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from app.domain.entities import ExceptionRecordCreateEntity
from app.domain.entities.gx_execution_violation import build_gx_execution_violation_summary_entity
from app.domain.entities import GxExecutionViolationSummaryEntity


def _record_payload(record: ExceptionRecordCreateEntity | Mapping[str, Any]) -> dict[str, Any]:
    if hasattr(record, "model_dump"):
        payload = record.model_dump(mode="python", by_alias=False, exclude_none=False)
        return payload if isinstance(payload, dict) else {}
    if isinstance(record, Mapping):
        return dict(record)
    return {}


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    payload = str(value).strip()
    if not payload:
        return None
    parsed = datetime.fromisoformat(payload.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.isoformat()


def _truncate_to_hour(value: datetime) -> datetime:
    normalized = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.replace(minute=0, second=0, microsecond=0)


def _read_text(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        normalized = str(payload.get(key) or "").strip()
        if normalized:
            return normalized
    return None


def _build_projection_key(*, row: Mapping[str, Any]) -> str:
    parts = [
        str(row.get("bucket_start") or ""),
        str(row.get("engine_type") or ""),
        str(row.get("delivery_id") or ""),
        str(row.get("execution_plan_id") or ""),
        str(row.get("execution_plan_version_id") or ""),
        str(row.get("suite_id") or ""),
        str(row.get("data_object_version_id") or ""),
        str(row.get("rule_id") or ""),
        str(row.get("rule_version_id") or ""),
        str(row.get("reason_code") or ""),
        str(row.get("reason_text_snapshot") or ""),
    ]
    digest = sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"exception-reason-analytics-{digest}"


def build_reason_analytics_projection_rows(
    exception_records: Sequence[ExceptionRecordCreateEntity | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped_rows: dict[str, dict[str, Any]] = {}
    for record in exception_records:
        payload = _record_payload(record)
        ops_metadata = dict(payload.get("opsMetadata") or {})
        detected_at = _parse_iso_datetime(str(payload.get("detectedAt") or ""))
        if detected_at is None:
            raise ValueError("Exception record is missing detected_at")

        reason_code = _read_text(payload, "reasonCode", "reason_code")
        reason_text = _read_text(payload, "reasonText", "reason_text")
        data_object_version_id = _read_text(payload, "dataObjectVersionId", "data_object_version_id")
        execution_run_id = _read_text(payload, "executionRunId", "execution_run_id")
        rule_id = _read_text(payload, "ruleId", "rule_id")
        record_identifier_value = _read_text(payload, "recordIdentifierValue", "record_identifier_value")
        record_identifier_type = _read_text(payload, "recordIdentifierType", "record_identifier_type")
        engine_type = _read_text(ops_metadata, "engine_type", "engineType")
        if (
            not reason_code
            or not reason_text
            or not data_object_version_id
            or not execution_run_id
            or not rule_id
            or not record_identifier_value
            or not record_identifier_type
            or not engine_type
        ):
            raise ValueError("Exception record is missing canonical projection metadata")

        bucket_start = _truncate_to_hour(detected_at)
        row = {
            "bucket_start": _format_iso_datetime(bucket_start),
            "engine_type": engine_type,
            "delivery_id": _read_text(ops_metadata, "delivery_id", "deliveryId"),
            "execution_plan_id": _read_text(ops_metadata, "execution_plan_id", "executionPlanId"),
            "execution_plan_version_id": _read_text(ops_metadata, "execution_plan_version_id", "executionPlanVersionId"),
            "suite_id": _read_text(ops_metadata, "suite_id", "validation_artifact_id", "suiteId"),
            "data_object_version_id": data_object_version_id,
            "rule_id": rule_id,
            "rule_version_id": _read_text(ops_metadata, "rule_version_id", "ruleVersionId"),
            "reason_code": reason_code,
            "reason_text_snapshot": reason_text,
            "record_identifier_values": [record_identifier_value],
            "execution_run_ids": [execution_run_id],
            "failed_record_count": 1,
            "distinct_record_identifier_count": 1,
            "distinct_execution_run_count": 1,
            "detected_at": _format_iso_datetime(detected_at),
        }
        projection_key = _build_projection_key(row=row)
        existing = grouped_rows.get(projection_key)
        if existing is None:
            grouped_rows[projection_key] = {**row, "id": projection_key}
            continue

        existing["failed_record_count"] += 1
        existing["record_identifier_values"].append(record_identifier_value)
        existing["execution_run_ids"].append(execution_run_id)
        if row["detected_at"] and (existing.get("detected_at") is None or str(row["detected_at"]) < str(existing["detected_at"])):
            existing["detected_at"] = row["detected_at"]

    projection_rows: list[dict[str, Any]] = []
    for row in grouped_rows.values():
        unique_record_identifiers = sorted({str(value).strip() for value in row["record_identifier_values"] if str(value).strip()})
        unique_execution_run_ids = sorted({str(value).strip() for value in row["execution_run_ids"] if str(value).strip()})
        projection_rows.append(
            {
                **row,
                "record_identifier_values": unique_record_identifiers,
                "execution_run_ids": unique_execution_run_ids,
                "distinct_record_identifier_count": len(unique_record_identifiers),
                "distinct_execution_run_count": len(unique_execution_run_ids),
            }
        )
    projection_rows.sort(key=lambda item: (item["bucket_start"] or "", item["reason_code"] or "", item["reason_text_snapshot"] or ""))
    return projection_rows


def summarize_reason_analytics_projection_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    data_object_version_ids: Sequence[str],
    execution_run_ids: Sequence[str],
    reason_codes: Sequence[str] | None = None,
    detected_after: str | None = None,
    detected_before: str | None = None,
    bucket_origin: str | None = None,
    bucket_size_seconds: int | None = None,
    bucket_count: int | None = None,
) -> GxExecutionViolationSummaryEntity:
    normalized_scope_ids = {str(value).strip() for value in data_object_version_ids if str(value).strip()}
    normalized_run_ids = {str(value).strip() for value in execution_run_ids if str(value).strip()}
    if not normalized_scope_ids or not normalized_run_ids:
        return build_gx_execution_violation_summary_entity(
            {
                "total_failed_records": 0,
                "runs_with_failures": 0,
                "trend_totals": [],
                "rule_totals": [],
                "data_object_totals": [],
                "reason_totals": [],
                "reason_trend_totals": [],
            }
        )

    detected_after_dt = _parse_iso_datetime(detected_after)
    detected_before_dt = _parse_iso_datetime(detected_before)
    bucket_origin_dt = _parse_iso_datetime(bucket_origin)
    normalized_reason_codes = {str(value).strip() for value in (reason_codes or []) if str(value).strip()}

    filtered_rows: list[dict[str, Any]] = []
    for row in rows:
        data_object_version_id = str(row.get("data_object_version_id") or "").strip()
        row_execution_run_ids = {
            str(value).strip()
            for value in (row.get("execution_run_ids") or [])
            if str(value).strip()
        }
        if data_object_version_id not in normalized_scope_ids or not row_execution_run_ids.intersection(normalized_run_ids):
            continue

        row_detected_at = _parse_iso_datetime(str(row.get("detected_at") or ""))
        if detected_after_dt is not None and (row_detected_at is None or row_detected_at < detected_after_dt):
            continue
        if detected_before_dt is not None and (row_detected_at is None or row_detected_at > detected_before_dt):
            continue

        reason_code = str(row.get("reason_code") or "").strip()
        if normalized_reason_codes and reason_code not in normalized_reason_codes:
            continue

        filtered_rows.append(dict(row))

    rule_totals: dict[str, int] = defaultdict(int)
    data_object_totals: dict[str, int] = defaultdict(int)
    trend_totals: dict[str, int] = defaultdict(int)
    reason_totals: dict[tuple[str, str], int] = defaultdict(int)
    reason_trend_totals: dict[tuple[str, str, str], int] = defaultdict(int)
    runs_with_failures: set[str] = set()

    for row in filtered_rows:
        rule_id = str(row.get("rule_id") or "").strip()
        data_object_version_id = str(row.get("data_object_version_id") or "").strip()
        execution_run_ids = {
            str(value).strip()
            for value in (row.get("execution_run_ids") or [])
            if str(value).strip()
        }
        bucket_start = str(row.get("bucket_start") or "").strip()
        reason_code = str(row.get("reason_code") or "").strip()
        reason_text = str(row.get("reason_text_snapshot") or "").strip()
        if not rule_id or not data_object_version_id or not execution_run_ids or not bucket_start or not reason_code or not reason_text:
            raise RuntimeError("GX exception reason analytics projection is missing canonical metadata")

        runs_with_failures.update(execution_run_ids)
        failed_record_count = int(row.get("failed_record_count") or 0)
        rule_totals[rule_id] += failed_record_count
        data_object_totals[data_object_version_id] += failed_record_count
        trend_totals[bucket_start] += failed_record_count
        reason_totals[(reason_code, reason_text)] += failed_record_count
        reason_trend_totals[(bucket_start, reason_code, reason_text)] += failed_record_count

    if bucket_origin_dt is not None and bucket_size_seconds is not None and bucket_size_seconds > 0 and bucket_count is not None and bucket_count > 0:
        bucketed_trend_totals: dict[str, int] = defaultdict(int)
        bucketed_reason_trend_totals: dict[tuple[str, str, str], int] = defaultdict(int)
        for row in filtered_rows:
            row_detected_at = _parse_iso_datetime(str(row.get("detected_at") or ""))
            if row_detected_at is None:
                continue
            offset_seconds = (row_detected_at - bucket_origin_dt).total_seconds()
            bucket_index = int(offset_seconds // bucket_size_seconds)
            bucket_index = max(0, min(bucket_count - 1, bucket_index))
            bucket_start_dt = bucket_origin_dt + timedelta(seconds=bucket_index * bucket_size_seconds)
            bucket_start = _format_iso_datetime(bucket_start_dt) or ""
            failed_record_count = int(row.get("failed_record_count") or 0)
            reason_code = str(row.get("reason_code") or "").strip()
            reason_text = str(row.get("reason_text_snapshot") or "").strip()
            bucketed_trend_totals[bucket_start] += failed_record_count
            bucketed_reason_trend_totals[(bucket_start, reason_code, reason_text)] += failed_record_count
        trend_totals = bucketed_trend_totals
        reason_trend_totals = bucketed_reason_trend_totals

    return build_gx_execution_violation_summary_entity(
        {
            "total_failed_records": sum(reason_totals.values()),
            "runs_with_failures": len(runs_with_failures),
            "trend_totals": [
                {"bucket_start": bucket_start, "total": total}
                for bucket_start, total in sorted(trend_totals.items())
            ],
            "rule_totals": [
                {"rule_id": rule_id, "total": total}
                for rule_id, total in sorted(rule_totals.items(), key=lambda item: (-item[1], item[0]))[:5]
            ],
            "data_object_totals": [
                {"data_object_version_id": data_object_version_id, "total": total}
                for data_object_version_id, total in sorted(data_object_totals.items(), key=lambda item: (-item[1], item[0]))[:5]
            ],
            "reason_totals": [
                {"reason_code": reason_code, "reason_text": reason_text, "total": total}
                for (reason_code, reason_text), total in sorted(
                    reason_totals.items(),
                    key=lambda item: (-item[1], item[0][0], item[0][1]),
                )[:5]
            ],
            "reason_trend_totals": [
                {
                    "bucket_start": bucket_start,
                    "reason_code": reason_code,
                    "reason_text": reason_text,
                    "total": total,
                }
                for (bucket_start, reason_code, reason_text), total in sorted(
                    reason_trend_totals.items(),
                    key=lambda item: (item[0][0], -item[1], item[0][1], item[0][2]),
                )
            ],
        }
    )
