from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.domain.interfaces import ExceptionAnalysisSessionRepository
from app.infrastructure.orm.models import GxExceptionAnalysisSliceRow
from app.infrastructure.orm.session import session_scope


def _format_iso_datetime(value: datetime | None) -> str:
    return value.isoformat() if value is not None else datetime.now(UTC).isoformat()


class PostgresExceptionAnalysisSessionRepository(ExceptionAnalysisSessionRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def save_slice(self, slice_row: Mapping[str, Any]) -> Mapping[str, Any]:
        now = datetime.now(UTC)
        payload = dict(slice_row)
        record = {
            "analysis_session_id": str(payload["analysisSessionId"]),
            "analysis_slice_id": str(payload["analysisSliceId"]),
            "slice_index": int(payload["sliceIndex"]),
            "data_object_version_id": str(payload["dataObjectVersionId"]),
            "execution_run_id": str(payload["executionRunId"]),
            "rule_id": str(payload["ruleId"]),
            "slice_limit": int(payload["sliceLimit"]),
            "anchor_total_count": int(payload["anchorTotalCount"]),
            "total_matching_count": int(payload["totalMatchingCount"]),
            "returned_count": int(payload["returnedCount"]),
            "truncated": bool(payload.get("truncated", False)),
            "filters_json": dict(payload.get("filters") or {}),
            "next_slice_json": dict(payload.get("nextSliceSuggestion") or {}) if payload.get("nextSliceSuggestion") is not None else None,
            "analysis_pack_uri": str(payload["analysisPackUri"]),
            "analysis_pack_sha256": str(payload["analysisPackSha256"]),
            "analysis_manifest_uri": str(payload["analysisManifestUri"]),
            "analysis_manifest_sha256": str(payload["analysisManifestSha256"]),
            "created_at": now,
            "updated_at": now,
        }

        with session_scope(self.database_url) as session:
            stmt = pg_insert(GxExceptionAnalysisSliceRow).values(record)
            stmt = stmt.on_conflict_do_nothing(index_elements=["analysis_session_id", "analysis_slice_id"])
            session.execute(stmt)
            session.commit()

        return self._serialize_row(record)

    async def list_slices(self, analysis_session_id: str) -> list[Mapping[str, Any]]:
        with session_scope(self.database_url) as session:
            rows = session.execute(
                select(GxExceptionAnalysisSliceRow)
                .where(GxExceptionAnalysisSliceRow.analysis_session_id == analysis_session_id)
                .order_by(GxExceptionAnalysisSliceRow.slice_index.asc(), GxExceptionAnalysisSliceRow.analysis_slice_id.asc())
            ).scalars().all()
        return [self._serialize_row(row) for row in rows]

    async def get_slice(self, analysis_session_id: str, analysis_slice_id: str) -> Mapping[str, Any] | None:
        with session_scope(self.database_url) as session:
            row = session.get(GxExceptionAnalysisSliceRow, (analysis_session_id, analysis_slice_id))
        return self._serialize_row(row) if row is not None else None

    @staticmethod
    def _serialize_row(row: Any) -> dict[str, Any]:
        if isinstance(row, Mapping):
            payload = dict(row)
            created_at = payload.get("created_at")
            updated_at = payload.get("updated_at")
        else:
            payload = {
                "analysisSessionId": getattr(row, "analysis_session_id", None),
                "analysisSliceId": getattr(row, "analysis_slice_id", None),
                "sliceIndex": getattr(row, "slice_index", None),
                "dataObjectVersionId": getattr(row, "data_object_version_id", None),
                "executionRunId": getattr(row, "execution_run_id", None),
                "ruleId": getattr(row, "rule_id", None),
                "sliceLimit": getattr(row, "slice_limit", None),
                "anchorTotalCount": getattr(row, "anchor_total_count", None),
                "totalMatchingCount": getattr(row, "total_matching_count", None),
                "returnedCount": getattr(row, "returned_count", None),
                "truncated": getattr(row, "truncated", None),
                "filters": getattr(row, "filters_json", None) or {},
                "nextSliceSuggestion": getattr(row, "next_slice_json", None),
                "analysisPackUri": getattr(row, "analysis_pack_uri", None),
                "analysisPackSha256": getattr(row, "analysis_pack_sha256", None),
                "analysisManifestUri": getattr(row, "analysis_manifest_uri", None),
                "analysisManifestSha256": getattr(row, "analysis_manifest_sha256", None),
            }
            created_at = getattr(row, "created_at", None)
            updated_at = getattr(row, "updated_at", None)
        payload["createdAt"] = _format_iso_datetime(created_at if isinstance(created_at, datetime) else None)
        payload["updatedAt"] = _format_iso_datetime(updated_at if isinstance(updated_at, datetime) else None)
        payload["filters"] = dict(payload.get("filters") or {})
        if payload.get("nextSliceSuggestion") is None:
            payload["nextSliceSuggestion"] = None
        elif isinstance(payload["nextSliceSuggestion"], Mapping):
            payload["nextSliceSuggestion"] = dict(payload["nextSliceSuggestion"])
        return payload
