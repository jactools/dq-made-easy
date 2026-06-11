from __future__ import annotations

import hashlib
from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities import (
    GxExecutionViolationCreateEntity,
    GxExecutionViolationEntity,
    GxExecutionViolationListEntity,
    GxExecutionViolationSummaryEntity,
)
from app.domain.entities.gx_execution_violation import (
    build_gx_execution_violation_entity,
    build_gx_execution_violation_list_entity,
    build_gx_execution_violation_summary_entity,
)
from app.domain.interfaces import ExceptionFactRepository


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


def _hash_stripe(value: str, stripe_count: int) -> int:
    normalized_count = max(int(stripe_count), 1)
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % normalized_count


class InMemoryGxExecutionViolationRepository(ExceptionFactRepository):
    def __init__(self) -> None:
        self._violations: dict[tuple[str, str], dict] = {}

    async def save_violation(
        self,
        *,
        data_object_version_id: str,
        execution_run_id: str,
        rule_id: str,
        data_primary_key: str,
        violation_reason: str,
        ops_metadata: dict | None = None,
        detected_at: str | None = None,
        violation_id: str | None = None,
    ) -> GxExecutionViolationEntity:
        saved = await self.save_violations([
            GxExecutionViolationCreateEntity(
                id=violation_id,
                dataObjectVersionId=data_object_version_id,
                executionRunId=execution_run_id,
                ruleId=rule_id,
                dataPrimaryKey=data_primary_key,
                violationReason=violation_reason,
                opsMetadata=dict(ops_metadata or {}),
                detectedAt=detected_at,
            )
        ])
        if not saved:
            raise RuntimeError("GX execution violation was not persisted")
        return saved[0]

    async def save_violations(
        self,
        violations: Sequence[GxExecutionViolationCreateEntity],
    ) -> list[GxExecutionViolationEntity]:
        saved: list[GxExecutionViolationEntity] = []
        for violation in violations:
            payload = violation.model_dump(mode="python", by_alias=False, exclude_none=False)
            violation_id = str(payload.get("id") or f"gx-violation-{uuid4().hex}")
            timestamp = payload.get("detectedAt") or datetime.now(UTC).isoformat()
            ops_metadata = dict(payload.get("opsMetadata") or {})
            record = {
                "id": violation_id,
                "dataObjectVersionId": payload["dataObjectVersionId"],
                "executionRunId": payload["executionRunId"],
                "ruleId": payload["ruleId"],
                "dataPrimaryKey": str(payload["dataPrimaryKey"]),
                "violationReason": str(payload["violationReason"]),
                "opsMetadata": deepcopy(ops_metadata),
                "detectedAt": timestamp,
                "createdAt": timestamp,
                "updatedAt": timestamp,
            }
            self._violations[(payload["dataObjectVersionId"], violation_id)] = record
            saved.append(build_gx_execution_violation_entity(deepcopy(record)))
        return saved

    async def get_violation(self, data_object_version_id: str, violation_id: str) -> GxExecutionViolationEntity | None:
        record = self._violations.get((data_object_version_id, violation_id))
        return build_gx_execution_violation_entity(deepcopy(record)) if record is not None else None

    async def list_violations(
        self,
        data_object_version_id: str,
        execution_run_id: str | None = None,
        rule_id: str | None = None,
        reason_codes: Sequence[str] | None = None,
        failure_class: str | None = None,
        record_identifier_type: str | None = None,
        record_identifier_value_contains: str | None = None,
        search: str | None = None,
        detected_after: str | None = None,
        detected_before: str | None = None,
        hash_stripe: int | None = None,
        hash_stripe_count: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> GxExecutionViolationListEntity:
        normalized_reason_codes = {str(value).strip() for value in (reason_codes or []) if str(value).strip()}
        normalized_failure_class = str(failure_class or "").strip() or None
        normalized_record_identifier_type = str(record_identifier_type or "").strip() or None
        normalized_record_identifier_value_contains = str(record_identifier_value_contains or "").strip().lower() or None
        normalized_search = str(search or "").strip().lower() or None
        detected_after_dt = _parse_iso_datetime(detected_after)
        detected_before_dt = _parse_iso_datetime(detected_before)
        normalized_hash_stripe = int(hash_stripe) if hash_stripe is not None else None
        normalized_hash_stripe_count = max(int(hash_stripe_count or 0), 1) if hash_stripe is not None else None

        rows = [
            deepcopy(record)
            for (scope, _), record in self._violations.items()
            if scope == data_object_version_id
            and (execution_run_id is None or record["executionRunId"] == execution_run_id)
            and (rule_id is None or record["ruleId"] == rule_id)
        ]
        filtered_rows: list[dict] = []
        for record in rows:
            ops_metadata = dict(record.get("opsMetadata") or {})
            reason_code = str(ops_metadata.get("reason_code") or "").strip()
            failure_class_value = str(ops_metadata.get("failure_class") or "").strip() or None
            identifier_type = str(ops_metadata.get("record_identifier_type") or "").strip() or None
            identifier_value = str(ops_metadata.get("record_identifier_value") or "").strip()
            detected_at = _parse_iso_datetime(record.get("detectedAt"))
            haystack = " ".join(
                [
                    str(record.get("violationReason") or ""),
                    reason_code,
                    str(ops_metadata.get("reason_text") or ""),
                    identifier_value,
                ]
            ).lower()
            if normalized_reason_codes and reason_code not in normalized_reason_codes:
                continue
            if normalized_failure_class is not None and failure_class_value != normalized_failure_class:
                continue
            if normalized_record_identifier_type is not None and identifier_type != normalized_record_identifier_type:
                continue
            if normalized_record_identifier_value_contains is not None and normalized_record_identifier_value_contains not in identifier_value.lower():
                continue
            if normalized_search is not None and normalized_search not in haystack:
                continue
            if detected_after_dt is not None and (detected_at is None or detected_at < detected_after_dt):
                continue
            if detected_before_dt is not None and (detected_at is None or detected_at > detected_before_dt):
                continue
            if normalized_hash_stripe is not None:
                record_identifier = identifier_value or str(record.get("id") or "")
                if _hash_stripe(record_identifier, normalized_hash_stripe_count or 1) != normalized_hash_stripe:
                    continue
            filtered_rows.append(record)

        rows = filtered_rows
        rows.sort(key=lambda item: item.get("detectedAt") or "")
        total = len(rows)
        return build_gx_execution_violation_list_entity({"data": rows[offset : offset + limit], "total": total})

    async def summarize_violations(
        self,
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
            return build_gx_execution_violation_summary_entity({
                "total_failed_records": 0,
                "runs_with_failures": 0,
                "trend_totals": [],
                "rule_totals": [],
                "data_object_totals": [],
                "reason_totals": [],
                "reason_trend_totals": [],
            })

        detected_after_dt = _parse_iso_datetime(detected_after)
        detected_before_dt = _parse_iso_datetime(detected_before)
        bucket_origin_dt = _parse_iso_datetime(bucket_origin)
        normalized_reason_codes = {
            str(value).strip()
            for value in (reason_codes or [])
            if str(value).strip()
        }

        filtered_rows: list[dict] = []
        for (scope, _), record in self._violations.items():
            if scope not in normalized_scope_ids:
                continue
            run_id = str(record.get("executionRunId") or "").strip()
            if run_id not in normalized_run_ids:
                continue

            detected_at = _parse_iso_datetime(record.get("detectedAt"))
            if detected_after_dt is not None and (detected_at is None or detected_at < detected_after_dt):
                continue
            if detected_before_dt is not None and (detected_at is None or detected_at > detected_before_dt):
                continue

            filtered_rows.append(record)

        rule_totals: dict[str, int] = {}
        data_object_totals: dict[str, int] = {}
        trend_totals: dict[str, int] = {}
        runs_with_failures: set[str] = set()
        reason_totals: dict[tuple[str, str], int] = {}
        reason_trend_totals: dict[tuple[str, str, str], int] = {}

        for record in filtered_rows:
            rule_id = str(record.get("ruleId") or "").strip()
            data_object_version_id = str(record.get("dataObjectVersionId") or "").strip()
            run_id = str(record.get("executionRunId") or "").strip()
            ops_metadata = dict(record.get("opsMetadata") or {})
            reason_code = str(ops_metadata.get("reason_code") or "").strip()
            reason_text = str(ops_metadata.get("reason_text") or "").strip()
            if not reason_code or not reason_text:
                raise RuntimeError(
                    "GX exception reason analytics require canonical reason_code and reason_text metadata"
                )
            if normalized_reason_codes and reason_code not in normalized_reason_codes:
                continue
            if run_id:
                runs_with_failures.add(run_id)
            if rule_id:
                rule_totals[rule_id] = rule_totals.get(rule_id, 0) + 1
            if data_object_version_id:
                data_object_totals[data_object_version_id] = data_object_totals.get(data_object_version_id, 0) + 1
            reason_key = (reason_code, reason_text)
            reason_totals[reason_key] = reason_totals.get(reason_key, 0) + 1

            if (
                bucket_origin_dt is not None
                and bucket_size_seconds is not None
                and bucket_size_seconds > 0
                and bucket_count is not None
                and bucket_count > 0
            ):
                detected_at = _parse_iso_datetime(record.get("detectedAt"))
                if detected_at is None:
                    continue
                offset_seconds = (detected_at - bucket_origin_dt).total_seconds()
                bucket_index = int(offset_seconds // bucket_size_seconds)
                bucket_index = max(0, min(bucket_count - 1, bucket_index))
                bucket_start = (bucket_origin_dt.timestamp() + (bucket_index * bucket_size_seconds))
                bucket_key = datetime.fromtimestamp(bucket_start, tz=UTC).isoformat()
                trend_totals[bucket_key] = trend_totals.get(bucket_key, 0) + 1
                reason_bucket_key = (bucket_key, reason_code, reason_text)
                reason_trend_totals[reason_bucket_key] = reason_trend_totals.get(reason_bucket_key, 0) + 1

        return build_gx_execution_violation_summary_entity({
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
        })

    async def delete_violations_detected_before(
        self,
        *,
        detected_before: str,
        limit: int = 1000,
        data_object_version_id: str | None = None,
    ) -> int:
        cutoff = _parse_iso_datetime(detected_before)
        if cutoff is None:
            raise ValueError("detected_before is required")
        if limit <= 0:
            raise ValueError("limit must be positive")

        normalized_data_object_version_id = str(data_object_version_id or "").strip() or None

        eligible_keys = [
            key
            for key, record in sorted(
                self._violations.items(),
                key=lambda item: (
                    item[1].get("detectedAt") or "",
                    item[0][0],
                    item[0][1],
                ),
            )
            if (_parse_iso_datetime(item_detected := record.get("detectedAt")) is not None)
            and _parse_iso_datetime(item_detected) < cutoff
            and (
                normalized_data_object_version_id is None
                or str(record.get("dataObjectVersionId") or "").strip() == normalized_data_object_version_id
            )
        ]

        deleted = 0
        for key in eligible_keys[:limit]:
            self._violations.pop(key, None)
            deleted += 1
        return deleted
