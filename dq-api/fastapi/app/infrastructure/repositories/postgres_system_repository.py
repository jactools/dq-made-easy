from app.domain.entities import SuggestionsMetricsOperationEntity
from app.domain.entities import SuggestionsMetricsSummaryEntity
from app.domain.entities import SystemDatabaseInfoEntity
from app.domain.interfaces.v1.system_repository import SystemRepository
from app.infrastructure.orm.models import SuggestionInteractionRow
from app.infrastructure.orm.models import SuggestionPreviewInteractionRow
from app.infrastructure.orm.models import SuggestionRow
from app.infrastructure.orm.models import SystemInfoRow
from app.infrastructure.orm.session import session_scope
from sqlalchemy import select


def _record_operation(
    totals_by_operation: dict[str, dict[str, int]],
    *,
    operation: str,
    is_failure: bool,
    created_at,
) -> None:
    metric = totals_by_operation.setdefault(
        operation,
        {
            "count": 0,
            "success_count": 0,
            "failure_count": 0,
            "last_seen_at": 0,
        },
    )
    metric["count"] = int(metric["count"]) + 1
    if is_failure:
        metric["failure_count"] = int(metric["failure_count"]) + 1
    else:
        metric["success_count"] = int(metric["success_count"]) + 1

    if created_at is not None:
        last_seen = int(created_at.timestamp() * 1000)
        metric["last_seen_at"] = max(int(metric["last_seen_at"]), last_seen)


def _preview_operation_name(action: str) -> str:
    normalized = str(action or "unknown").strip().lower() or "unknown"
    return f"suggestions.natural_language.{normalized}"


def _suggestion_operation_name(*, action: str, data_source_id: str | None) -> str:
    normalized_action = str(action or "unknown").strip().lower() or "unknown"
    if str(data_source_id or "").startswith("nl-preview:"):
        preview_action_map = {
            "accepted": "suggestion_accepted",
            "dismissed": "suggestion_rejected",
            "applied": "suggestion_applied",
        }
        return _preview_operation_name(preview_action_map.get(normalized_action, normalized_action))
    return f"suggestions.{normalized_action}"


class PostgresSystemRepository(SystemRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def get_system_info(self) -> SystemDatabaseInfoEntity:
        rows = self._fetch_all()

        info_map: dict[str, str | None] = {
            str(row["info_key"]): str(row["info_value"]) if row.get("info_value") is not None else None
            for row in rows
        }
        return SystemDatabaseInfoEntity(
            db_schema_version=info_map.get("db_schema_version") or "unknown",
            db_schema_updated=info_map.get("db_schema_updated"),
            db_git_commit=info_map.get("db_git_commit"),
        )

    def _fetch_all(self) -> list[dict]:
        with session_scope(self.database_url) as session:
            stmt = select(SystemInfoRow).where(
                SystemInfoRow.info_key.in_(("db_schema_version", "db_schema_updated", "db_git_commit"))
            )
            rows = session.execute(stmt).scalars().all()
            return [
                {
                    "info_key": row.info_key,
                    "info_value": row.info_value,
                    "description": row.description,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    def get_suggestions_metrics_summary(self) -> SuggestionsMetricsSummaryEntity:
        with session_scope(self.database_url) as session:
            interaction_rows = session.execute(select(SuggestionInteractionRow)).scalars().all()
            suggestion_rows = session.execute(select(SuggestionRow)).scalars().all()
            preview_rows = session.execute(select(SuggestionPreviewInteractionRow)).scalars().all()

        totals_by_operation: dict[str, dict[str, int]] = {}
        data_source_by_suggestion_id = {str(row.id): row.data_source_id for row in suggestion_rows}

        for row in interaction_rows:
            _record_operation(
                totals_by_operation,
                operation=_suggestion_operation_name(
                    action=row.action,
                    data_source_id=data_source_by_suggestion_id.get(str(row.suggestion_id)),
                ),
                is_failure=False,
                created_at=row.created_at,
            )

        for row in preview_rows:
            _record_operation(
                totals_by_operation,
                operation=_preview_operation_name(row.action),
                is_failure=str(row.result or "success").strip().lower() == "failure",
                created_at=row.created_at,
            )

        operations = [
            SuggestionsMetricsOperationEntity(
                operation=operation,
                count=int(metric["count"]),
                success_count=int(metric["success_count"]),
                failure_count=int(metric["failure_count"]),
                success_rate=(
                    int(metric["success_count"]) / int(metric["count"])
                    if int(metric["count"])
                    else 1
                ),
                avg_duration_ms=0,
                min_duration_ms=0,
                max_duration_ms=0,
                last_seen_at=int(metric["last_seen_at"]),
            )
            for operation, metric in sorted(
                totals_by_operation.items(),
                key=lambda item: int(item[1]["count"]),
                reverse=True,
            )
        ]

        total = sum(int(row.count) for row in operations)
        successful = sum(int(row.success_count) for row in operations)
        failed = sum(int(row.failure_count) for row in operations)
        return SuggestionsMetricsSummaryEntity(
            total=total,
            successful=successful,
            failed=failed,
            success_rate=(successful / total) if total else 1,
            operations=operations,
        )