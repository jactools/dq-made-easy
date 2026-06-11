from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Integer, case, cast, delete, desc, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert

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
from app.infrastructure.orm.models import GxExecutionViolationRow
from app.infrastructure.orm.session import session_scope


def _parse_iso_datetime(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    payload = str(value).strip()
    if not payload:
        return datetime.now(UTC)
    return datetime.fromisoformat(payload.replace("Z", "+00:00"))


def _format_iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


class PostgresGxExecutionViolationRepository(ExceptionFactRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

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
        if not violations:
            return []

        now = datetime.now(UTC)
        rows: list[dict[str, Any]] = []
        serialized_rows: list[dict[str, Any]] = []
        for violation in violations:
            payload = violation.model_dump(mode="python", by_alias=False, exclude_none=False)
            violation_id = str(payload.get("id") or f"gx-violation-{uuid4().hex}")
            detected_timestamp = _parse_iso_datetime(payload.get("detectedAt"))
            ops_metadata = dict(payload.get("opsMetadata") or {})
            row = {
                "data_object_version_id": str(payload["dataObjectVersionId"]),
                "id": violation_id,
                "execution_run_id": str(payload["executionRunId"]),
                "rule_id": str(payload["ruleId"]),
                "data_primary_key": str(payload["dataPrimaryKey"]),
                "violation_reason": str(payload["violationReason"]),
                "ops_metadata_json": ops_metadata,
                "detected_at": detected_timestamp,
                "created_at": now,
                "updated_at": now,
            }
            rows.append(row)
            serialized_rows.append(self._serialize_row_dict(row))

        with session_scope(self.database_url) as session:
            stmt = pg_insert(GxExecutionViolationRow).values(rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["data_object_version_id", "id"])
            session.execute(stmt)
            session.commit()

        return [build_gx_execution_violation_entity(row) for row in serialized_rows]

    async def get_violation(self, data_object_version_id: str, violation_id: str) -> GxExecutionViolationEntity | None:
        with session_scope(self.database_url) as session:
            row = session.get(GxExecutionViolationRow, (data_object_version_id, violation_id))
            if row is None:
                return None
        return build_gx_execution_violation_entity(self._serialize_row(row))

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
        with session_scope(self.database_url) as session:
            stmt = select(GxExecutionViolationRow).where(
                GxExecutionViolationRow.data_object_version_id == data_object_version_id
            )
            if execution_run_id is not None:
                stmt = stmt.where(GxExecutionViolationRow.execution_run_id == execution_run_id)
            if rule_id is not None:
                stmt = stmt.where(GxExecutionViolationRow.rule_id == rule_id)
            if detected_after is not None:
                stmt = stmt.where(GxExecutionViolationRow.detected_at >= _parse_iso_datetime(detected_after))
            if detected_before is not None:
                stmt = stmt.where(GxExecutionViolationRow.detected_at <= _parse_iso_datetime(detected_before))

            reason_code_expr = func.jsonb_extract_path_text(GxExecutionViolationRow.ops_metadata_json, "reason_code")
            failure_class_expr = func.jsonb_extract_path_text(GxExecutionViolationRow.ops_metadata_json, "failure_class")
            identifier_type_expr = func.jsonb_extract_path_text(GxExecutionViolationRow.ops_metadata_json, "record_identifier_type")
            identifier_value_expr = func.jsonb_extract_path_text(GxExecutionViolationRow.ops_metadata_json, "record_identifier_value")
            normalized_reason_codes = [str(value).strip() for value in (reason_codes or []) if str(value).strip()]
            if normalized_reason_codes:
                stmt = stmt.where(reason_code_expr.in_(normalized_reason_codes))
            if failure_class is not None and str(failure_class).strip():
                stmt = stmt.where(failure_class_expr == str(failure_class).strip())
            if record_identifier_type is not None and str(record_identifier_type).strip():
                stmt = stmt.where(identifier_type_expr == str(record_identifier_type).strip())
            if record_identifier_value_contains is not None and str(record_identifier_value_contains).strip():
                stmt = stmt.where(identifier_value_expr.ilike(f"%{str(record_identifier_value_contains).strip()}%"))
            if search is not None and str(search).strip():
                normalized_search = f"%{str(search).strip()}%"
                stmt = stmt.where(
                    or_(
                        GxExecutionViolationRow.violation_reason.ilike(normalized_search),
                        identifier_value_expr.ilike(normalized_search),
                        reason_code_expr.ilike(normalized_search),
                        func.coalesce(failure_class_expr, "").ilike(normalized_search),
                    )
                )
            if hash_stripe is not None:
                normalized_hash_stripe_count = max(int(hash_stripe_count or 0), 1)
                hash_expr = func.mod(func.abs(func.hashtext(func.coalesce(GxExecutionViolationRow.data_primary_key, ""))), normalized_hash_stripe_count)
                stmt = stmt.where(hash_expr == int(hash_stripe))
            stmt = stmt.order_by(GxExecutionViolationRow.detected_at.asc())
            all_rows = session.execute(stmt).scalars().all()
            total = len(all_rows)
            rows = session.execute(stmt.limit(limit).offset(offset)).scalars().all()
        return build_gx_execution_violation_list_entity({"data": [self._serialize_row(row) for row in rows], "total": total})

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
        normalized_scope_ids = [str(value).strip() for value in data_object_version_ids if str(value).strip()]
        normalized_run_ids = [str(value).strip() for value in execution_run_ids if str(value).strip()]
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

        conditions = [
            GxExecutionViolationRow.data_object_version_id.in_(normalized_scope_ids),
            GxExecutionViolationRow.execution_run_id.in_(normalized_run_ids),
        ]
        if detected_after is not None:
            conditions.append(GxExecutionViolationRow.detected_at >= _parse_iso_datetime(detected_after))
        if detected_before is not None:
            conditions.append(GxExecutionViolationRow.detected_at <= _parse_iso_datetime(detected_before))

        reason_code_expr = func.jsonb_extract_path_text(GxExecutionViolationRow.ops_metadata_json, "reason_code")
        reason_text_expr = func.jsonb_extract_path_text(GxExecutionViolationRow.ops_metadata_json, "reason_text")
        normalized_reason_codes = [str(value).strip() for value in (reason_codes or []) if str(value).strip()]
        if normalized_reason_codes:
            conditions.append(reason_code_expr.in_(normalized_reason_codes))

        with session_scope(self.database_url) as session:
            totals_row = session.execute(
                select(
                    func.count().label("total_failed_records"),
                    func.count(func.distinct(GxExecutionViolationRow.execution_run_id)).label("runs_with_failures"),
                ).where(*conditions)
            ).one()

            if int(totals_row.total_failed_records or 0) > 0:
                missing_reason_rows = session.execute(
                    select(func.count().label("missing_reason_count")).where(
                        *conditions,
                        or_(
                            reason_code_expr.is_(None),
                            reason_code_expr == "",
                            reason_text_expr.is_(None),
                            reason_text_expr == "",
                        ),
                    )
                ).one()
                if int(missing_reason_rows.missing_reason_count or 0) > 0:
                    raise RuntimeError(
                        "GX exception reason analytics require canonical reason_code and reason_text metadata"
                    )

            rule_rows = session.execute(
                select(
                    GxExecutionViolationRow.rule_id.label("rule_id"),
                    func.count().label("total"),
                )
                .where(*conditions)
                .group_by(GxExecutionViolationRow.rule_id)
                .order_by(desc("total"), GxExecutionViolationRow.rule_id.asc())
                .limit(5)
            ).all()

            data_object_rows = session.execute(
                select(
                    GxExecutionViolationRow.data_object_version_id.label("data_object_version_id"),
                    func.count().label("total"),
                )
                .where(*conditions)
                .group_by(GxExecutionViolationRow.data_object_version_id)
                .order_by(desc("total"), GxExecutionViolationRow.data_object_version_id.asc())
                .limit(5)
            ).all()

            reason_rows = session.execute(
                select(
                    reason_code_expr.label("reason_code"),
                    reason_text_expr.label("reason_text"),
                    func.count().label("total"),
                )
                .where(*conditions)
                .group_by(reason_code_expr, reason_text_expr)
                .order_by(desc("total"), reason_code_expr.asc(), reason_text_expr.asc())
                .limit(5)
            ).all()

            trend_rows: list[dict[str, Any]] = []
            trend_rows: list[dict[str, Any]] = []
            reason_trend_rows: list[dict[str, Any]] = []
            if bucket_origin is not None and bucket_size_seconds is not None and bucket_size_seconds > 0 and bucket_count is not None and bucket_count > 0:
                bucket_origin_dt = _parse_iso_datetime(bucket_origin)
                bucket_origin_epoch = bucket_origin_dt.timestamp()
                raw_bucket_index = cast(
                    func.floor(
                        (func.extract("epoch", GxExecutionViolationRow.detected_at) - bucket_origin_epoch)
                        / float(bucket_size_seconds)
                    ),
                    Integer,
                )
                clamped_bucket_index = case(
                    (raw_bucket_index < 0, 0),
                    (raw_bucket_index >= bucket_count, bucket_count - 1),
                    else_=raw_bucket_index,
                )
                bucket_start_expr = func.to_timestamp((clamped_bucket_index * bucket_size_seconds) + bucket_origin_epoch)
                trend_result = session.execute(
                    select(
                        bucket_start_expr.label("bucket_start"),
                        func.count().label("total"),
                    )
                    .where(*conditions)
                    .group_by(bucket_start_expr)
                    .order_by(bucket_start_expr.asc())
                ).all()
                trend_rows = [
                    {
                        "bucket_start": _format_iso_datetime(row.bucket_start),
                        "total": int(row.total or 0),
                    }
                    for row in trend_result
                ]
                reason_trend_result = session.execute(
                    select(
                        bucket_start_expr.label("bucket_start"),
                        reason_code_expr.label("reason_code"),
                        reason_text_expr.label("reason_text"),
                        func.count().label("total"),
                    )
                    .where(*conditions)
                    .group_by(bucket_start_expr, reason_code_expr, reason_text_expr)
                    .order_by(bucket_start_expr.asc(), desc("total"), reason_code_expr.asc(), reason_text_expr.asc())
                ).all()
                reason_trend_rows = [
                    {
                        "bucket_start": _format_iso_datetime(row.bucket_start),
                        "reason_code": str(row.reason_code),
                        "reason_text": str(row.reason_text),
                        "total": int(row.total or 0),
                    }
                    for row in reason_trend_result
                    if str(row.reason_code or "").strip() and str(row.reason_text or "").strip()
                ]

        return build_gx_execution_violation_summary_entity({
            "total_failed_records": int(totals_row.total_failed_records or 0),
            "runs_with_failures": int(totals_row.runs_with_failures or 0),
            "trend_totals": trend_rows,
            "rule_totals": [
                {"rule_id": str(row.rule_id), "total": int(row.total or 0)}
                for row in rule_rows
                if str(row.rule_id or "").strip()
            ],
            "data_object_totals": [
                {"data_object_version_id": str(row.data_object_version_id), "total": int(row.total or 0)}
                for row in data_object_rows
                if str(row.data_object_version_id or "").strip()
            ],
            "reason_totals": [
                {
                    "reason_code": str(row.reason_code),
                    "reason_text": str(row.reason_text),
                    "total": int(row.total or 0),
                }
                for row in reason_rows
                if str(row.reason_code or "").strip() and str(row.reason_text or "").strip()
            ],
            "reason_trend_totals": reason_trend_rows,
        })

    async def delete_violations_detected_before(
        self,
        *,
        detected_before: str,
        limit: int = 1000,
        data_object_version_id: str | None = None,
    ) -> int:
        cutoff = _parse_iso_datetime(detected_before)
        normalized_limit = max(int(limit), 1)
        normalized_data_object_version_id = str(data_object_version_id or "").strip() or None

        with session_scope(self.database_url) as session:
            stmt = select(
                GxExecutionViolationRow.data_object_version_id,
                GxExecutionViolationRow.id,
            ).where(GxExecutionViolationRow.detected_at < cutoff)
            if normalized_data_object_version_id is not None:
                stmt = stmt.where(GxExecutionViolationRow.data_object_version_id == normalized_data_object_version_id)
            rows = session.execute(
                stmt.order_by(
                    GxExecutionViolationRow.detected_at.asc(),
                    GxExecutionViolationRow.data_object_version_id.asc(),
                    GxExecutionViolationRow.id.asc(),
                ).limit(normalized_limit)
            ).all()
            if not rows:
                return 0

            deleted = session.execute(
                delete(GxExecutionViolationRow).where(
                    tuple_(
                        GxExecutionViolationRow.data_object_version_id,
                        GxExecutionViolationRow.id,
                    ).in_([(row.data_object_version_id, row.id) for row in rows])
                )
            )
            session.commit()

        return int(deleted.rowcount or 0)

    @staticmethod
    def _serialize_row(row: GxExecutionViolationRow) -> dict[str, Any]:
        ops_metadata = dict(row.ops_metadata_json or {})
        return {
            "id": row.id,
            "dataObjectVersionId": row.data_object_version_id,
            "executionRunId": row.execution_run_id,
            "ruleId": row.rule_id,
            "dataPrimaryKey": row.data_primary_key,
            "violationReason": row.violation_reason,
            "opsMetadata": ops_metadata,
            "detectedAt": _format_iso_datetime(row.detected_at),
            "createdAt": _format_iso_datetime(row.created_at) or "",
            "updatedAt": _format_iso_datetime(row.updated_at) or "",
        }

    @staticmethod
    def _serialize_row_dict(row: dict[str, Any]) -> dict[str, Any]:
        ops_metadata = dict(row.get("ops_metadata_json") or {})
        return {
            "id": row["id"],
            "dataObjectVersionId": row["data_object_version_id"],
            "executionRunId": row["execution_run_id"],
            "ruleId": row["rule_id"],
            "dataPrimaryKey": row["data_primary_key"],
            "violationReason": row["violation_reason"],
            "opsMetadata": ops_metadata,
            "detectedAt": _format_iso_datetime(row["detected_at"]),
            "createdAt": _format_iso_datetime(row["created_at"]) or "",
            "updatedAt": _format_iso_datetime(row["updated_at"]) or "",
        }
