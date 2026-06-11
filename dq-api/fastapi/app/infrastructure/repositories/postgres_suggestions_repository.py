from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from uuid import uuid4

import redis
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.otel_metrics import record_suggestions_redis_failure
from app.core.otel_metrics import record_suggestions_redis_request
from app.domain.entities import SuggestionActionResultEntity
from app.domain.entities import SuggestionDataSourceEntity
from app.domain.entities import NaturalLanguageDraftRequestEntity
from app.domain.entities import NaturalLanguageDraftRequestHistoryEntity
from app.domain.entities import SuggestionEntity
from app.domain.entities import SuggestionMetricsClearResultEntity
from app.domain.interfaces.v1.suggestions_repository import SuggestionDataSourceNotFoundError
from app.domain.interfaces.v1.suggestions_repository import SuggestionNotFoundError
from app.domain.interfaces.v1.suggestions_repository import NaturalLanguageDraftRequestNotFoundError
from app.domain.interfaces.v1.suggestions_repository import SuggestionsRepository
from app.domain.user_names import normalize_user_name_parts
from app.infrastructure.orm.models import DataSourceMetadataRow
from app.infrastructure.orm.models import NaturalLanguageAnalysisRequestHistoryRow
from app.infrastructure.orm.models import NaturalLanguageAnalysisRequestRow
from app.infrastructure.orm.models import SuggestionInteractionRow
from app.infrastructure.orm.models import SuggestionPreviewInteractionRow
from app.infrastructure.orm.models import SuggestionRow
from app.infrastructure.orm.models import UserRow
from app.infrastructure.orm.session import session_scope


def _is_natural_language_preview_suggestion(data_source_id: str | None) -> bool:
    return str(data_source_id or "").startswith("nl-preview:")


def _preview_event_action_for_status(status: str) -> str | None:
    normalized_status = str(status or "").strip().lower()
    if normalized_status == "accepted":
        return "suggestion_accepted"
    if normalized_status == "dismissed":
        return "suggestion_rejected"
    if normalized_status == "applied":
        return "suggestion_applied"
    return None


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.isoformat()


def _to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _to_natural_language_request_entity(
    row: NaturalLanguageAnalysisRequestRow,
    *,
    requested_by_email: str | None = None,
) -> NaturalLanguageDraftRequestEntity:
    return NaturalLanguageDraftRequestEntity(
        request_id=row.request_id,
        job_id=row.job_id,
        current_workspace_id=row.current_workspace_id,
        search_scope=row.search_scope,
        analysis_provider=row.analysis_provider,
        analysis_type=row.analysis_type,
        prompt=row.prompt,
        selected_attribute_ids=[str(item).strip() for item in list(row.selected_attribute_ids or []) if str(item).strip()],
        accessible_workspace_ids=[str(item).strip() for item in list(row.accessible_workspace_ids or []) if str(item).strip()],
        requested_by_user_id=row.requested_by_user_id,
        requested_by_email=requested_by_email,
        requested_at=_to_iso(row.requested_at),
        started_at=_to_iso(row.started_at),
        completed_at=_to_iso(row.completed_at),
        status=row.status or "pending",
        error_message=row.error_message,
        suggestion_id=row.suggestion_id,
        result=row.result_json,
        correlation_id=row.correlation_id,
    )


def _to_natural_language_request_history_entity(
    row: NaturalLanguageAnalysisRequestHistoryRow,
) -> NaturalLanguageDraftRequestHistoryEntity:
    return NaturalLanguageDraftRequestHistoryEntity(
        id=row.id,
        request_id=row.request_id,
        action=row.action,
        from_status=row.from_status,
        to_status=row.to_status,
        actor_id=row.actor_id,
        changed_at=_to_iso(row.changed_at) or "",
        details=dict(row.details_json or {}),
    )


class PostgresSuggestionsRepository(SuggestionsRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def list_data_sources(self) -> list[SuggestionDataSourceEntity]:
        with session_scope(self.database_url) as session:
            rows = (
                session.execute(select(DataSourceMetadataRow).order_by(DataSourceMetadataRow.name.asc()))
                .scalars()
                .all()
            )

        return [
            SuggestionDataSourceEntity(
                data_source_id=row.data_source_id,
                name=row.name,
                source_type=row.source_type,
                record_count=row.record_count,
                last_profiled_at=_to_iso(row.last_profiled_at),
            )
            for row in rows
        ]

    def create_suggestion(
        self,
        *,
        user_id: str,
        data_source_id: str,
        suggested_rule: dict,
        confidence_score: float | None,
        reason: str | None,
        rule_type: str | None,
        created_from_profiling_request_id: str | None = None,
    ) -> SuggestionEntity:
        suggestion_id = str(uuid4())
        created_at = datetime.now(UTC)

        with session_scope(self.database_url) as session:
            actor_id = self._resolve_or_create_user_id(session, user_id)
            row = SuggestionRow(
                id=suggestion_id,
                user_id=actor_id,
                data_source_id=data_source_id,
                suggested_rule=dict(suggested_rule),
                confidence_score=confidence_score,
                reason=reason,
                rule_type=rule_type,
                created_from_profiling_request_id=created_from_profiling_request_id,
                status="pending",
                created_at=created_at,
                expires_at=None,
            )
            session.add(row)
            session.commit()

        return SuggestionEntity(
            id=suggestion_id,
            user_id=actor_id,
            data_source_id=data_source_id,
            suggested_rule=dict(suggested_rule),
            confidence_score=confidence_score,
            reason=reason,
            rule_type=rule_type,
            created_from_profiling_request_id=created_from_profiling_request_id,
            status="pending",
            created_at=_to_iso(created_at),
            expires_at=None,
        )

    def list_suggestions(
        self,
        *,
        user_id: str | None,
        data_source_id: str | None,
        status: str,
    ) -> list[SuggestionEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(SuggestionRow)
            if user_id:
                stmt = stmt.where(SuggestionRow.user_id == user_id)
            if data_source_id:
                stmt = stmt.where(SuggestionRow.data_source_id == data_source_id)
            if status:
                stmt = stmt.where(SuggestionRow.status == status)

            rows = session.execute(stmt.order_by(SuggestionRow.created_at.desc())).scalars().all()

        return [
            SuggestionEntity(
                id=row.id,
                user_id=row.user_id,
                data_source_id=row.data_source_id,
                suggested_rule=row.suggested_rule,
                confidence_score=_to_float(row.confidence_score),
                reason=row.reason,
                rule_type=row.rule_type,
                created_from_profiling_request_id=row.created_from_profiling_request_id,
                status=row.status,
                created_at=_to_iso(row.created_at),
                expires_at=_to_iso(row.expires_at),
            )
            for row in rows
        ]

    def record_natural_language_request(
        self,
        *,
        request: NaturalLanguageDraftRequestEntity,
    ) -> NaturalLanguageDraftRequestEntity:
        requested_at = datetime.fromisoformat(request.requested_at) if request.requested_at else datetime.now(UTC)
        started_at = datetime.fromisoformat(request.started_at) if request.started_at else None
        completed_at = datetime.fromisoformat(request.completed_at) if request.completed_at else None
        with session_scope(self.database_url) as session:
            requester_id = self._resolve_or_create_user_id(session, request.requested_by_user_id or "")
            row = NaturalLanguageAnalysisRequestRow(
                request_id=request.request_id,
                job_id=request.job_id,
                requested_by_user_id=requester_id,
                current_workspace_id=request.current_workspace_id,
                search_scope=request.search_scope,
                analysis_provider=request.analysis_provider,
                analysis_type=request.analysis_type,
                prompt=request.prompt,
                selected_attribute_ids=list(request.selected_attribute_ids),
                accessible_workspace_ids=list(request.accessible_workspace_ids),
                status=request.status,
                requested_at=requested_at,
                started_at=started_at,
                completed_at=completed_at,
                error_message=request.error_message,
                suggestion_id=request.suggestion_id,
                result_json=dict(request.result) if request.result is not None else None,
                correlation_id=request.correlation_id,
                created_at=requested_at,
                updated_at=requested_at,
            )
            session.add(row)
            self._append_natural_language_request_history_row(
                session,
                request_id=request.request_id,
                action="created",
                from_status=None,
                to_status=request.status,
                actor_id=requester_id,
                details={
                    "job_id": request.job_id,
                    "analysis_type": request.analysis_type,
                    "analysis_provider": request.analysis_provider,
                    "current_workspace_id": request.current_workspace_id,
                    "selected_attribute_ids": list(request.selected_attribute_ids),
                    "accessible_workspace_ids": list(request.accessible_workspace_ids),
                    "correlation_id": request.correlation_id,
                },
            )
            session.commit()

            row = session.execute(
                select(NaturalLanguageAnalysisRequestRow).where(NaturalLanguageAnalysisRequestRow.request_id == request.request_id)
            ).scalar_one()

        return _to_natural_language_request_entity(row)

    def update_natural_language_request(
        self,
        *,
        request_id: str,
        status: str,
        job_id: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        error_message: str | None = None,
        suggestion_id: str | None = None,
        result: dict | None = None,
    ) -> NaturalLanguageDraftRequestEntity:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(NaturalLanguageAnalysisRequestRow).where(NaturalLanguageAnalysisRequestRow.request_id == request_id)
            ).scalar_one_or_none()
            if row is None:
                raise NaturalLanguageDraftRequestNotFoundError("Natural-language request not found")

            previous_status = str(row.status or "pending")
            row.status = status
            row.job_id = job_id or row.job_id
            row.started_at = datetime.fromisoformat(started_at) if started_at else row.started_at
            row.completed_at = datetime.fromisoformat(completed_at) if completed_at else row.completed_at
            row.error_message = error_message
            row.suggestion_id = suggestion_id
            row.result_json = dict(result) if result is not None else row.result_json
            row.updated_at = datetime.now(UTC)
            self._append_natural_language_request_history_row(
                session,
                request_id=request_id,
                action="status_changed",
                from_status=previous_status,
                to_status=status,
                actor_id=row.requested_by_user_id,
                details={
                    "job_id": row.job_id,
                    "started_at": _to_iso(row.started_at),
                    "completed_at": _to_iso(row.completed_at),
                    "error_message": error_message,
                    "suggestion_id": suggestion_id,
                    "result": dict(result) if result is not None else row.result_json,
                },
            )
            session.add(row)
            session.commit()

        return _to_natural_language_request_entity(row)

    def record_natural_language_request_history_event(
        self,
        *,
        request_id: str,
        action: str,
        from_status: str | None = None,
        to_status: str | None = None,
        actor_id: str | None = None,
        details: dict | None = None,
    ) -> NaturalLanguageDraftRequestHistoryEntity:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(NaturalLanguageAnalysisRequestRow).where(NaturalLanguageAnalysisRequestRow.request_id == request_id)
            ).scalar_one_or_none()
            if row is None:
                raise NaturalLanguageDraftRequestNotFoundError("Natural-language request not found")

            history_row = self._append_natural_language_request_history_row(
                session,
                request_id=request_id,
                action=action,
                from_status=from_status,
                to_status=to_status,
                actor_id=actor_id,
                details=details,
            )
            session.commit()

        return _to_natural_language_request_history_entity(history_row)

    def list_natural_language_request_history(
        self,
        *,
        request_id: str,
        limit: int,
        offset: int,
    ) -> list[NaturalLanguageDraftRequestHistoryEntity] | None:
        normalized_limit = max(1, min(limit, 100))
        normalized_offset = max(0, offset)

        with session_scope(self.database_url) as session:
            request_row = session.execute(
                select(NaturalLanguageAnalysisRequestRow).where(NaturalLanguageAnalysisRequestRow.request_id == request_id)
            ).scalar_one_or_none()
            if request_row is None:
                return None

            rows = session.execute(
                select(NaturalLanguageAnalysisRequestHistoryRow)
                .where(NaturalLanguageAnalysisRequestHistoryRow.request_id == request_id)
                .order_by(NaturalLanguageAnalysisRequestHistoryRow.changed_at.desc(), NaturalLanguageAnalysisRequestHistoryRow.id.desc())
            ).scalars().all()

        window = rows[normalized_offset : normalized_offset + normalized_limit]
        return [_to_natural_language_request_history_entity(row) for row in window]

    def list_natural_language_requests(
        self,
        *,
        user_id: str,
        workspace_id: str | None,
        limit: int,
    ) -> list[NaturalLanguageDraftRequestEntity]:
        normalized_limit = max(1, min(limit, 100))

        with session_scope(self.database_url) as session:
            requester_ids = self._resolve_requester_ids(session, user_id)
            stmt = select(NaturalLanguageAnalysisRequestRow, UserRow.email).join(
                UserRow,
                NaturalLanguageAnalysisRequestRow.requested_by_user_id == UserRow.id,
                isouter=True,
            ).where(
                NaturalLanguageAnalysisRequestRow.requested_by_user_id.in_(sorted(requester_ids))
            )
            if workspace_id:
                stmt = stmt.where(NaturalLanguageAnalysisRequestRow.current_workspace_id == workspace_id)

            rows = session.execute(
                stmt.order_by(NaturalLanguageAnalysisRequestRow.requested_at.desc()).limit(normalized_limit)
            ).all()

        return [
            _to_natural_language_request_entity(
                row,
                requested_by_email=(str(email).strip() if email is not None else None),
            )
            for row, email in rows
        ]

    def update_suggestion_status(
        self,
        *,
        user_id: str,
        suggestion_id: str,
        action: str,
        rule_id: str | None = None,
    ) -> SuggestionActionResultEntity:
        status_map = {
            "accept": "accepted",
            "dismiss": "dismissed",
            "apply": "applied",
        }
        next_status = status_map[action]

        with session_scope(self.database_url) as session:
            actor_id = self._resolve_or_create_user_id(session, user_id)

            suggestion = session.execute(
                select(SuggestionRow).where(SuggestionRow.id == suggestion_id)
            ).scalar_one_or_none()
            if suggestion is None:
                raise SuggestionNotFoundError("Suggestion not found")

            suggestion.status = next_status
            session.add(
                SuggestionInteractionRow(
                    id=str(uuid4()),
                    suggestion_id=suggestion_id,
                    user_id=actor_id,
                    action=next_status,
                    rule_created_from_suggestion_id=rule_id,
                    created_at=datetime.now(UTC),
                )
            )
            preview_action = _preview_event_action_for_status(next_status)
            if preview_action and _is_natural_language_preview_suggestion(suggestion.data_source_id):
                session.add(
                    SuggestionPreviewInteractionRow(
                        id=str(uuid4()),
                        user_id=actor_id,
                        workspace_id=str(suggestion.data_source_id.removeprefix("nl-preview:")),
                        action=preview_action,
                        result="success",
                        error_code=None,
                        details_json={"suggestion_id": suggestion_id},
                        created_at=datetime.now(UTC),
                    )
                )
            session.commit()

        return SuggestionActionResultEntity(message=f"Suggestion {next_status}")

    def record_preview_event(
        self,
        *,
        user_id: str,
        workspace_id: str,
        action: str,
        result: str = "success",
        error_code: str | None = None,
        details: dict | None = None,
    ) -> None:
        with session_scope(self.database_url) as session:
            actor_id = self._resolve_or_create_user_id(session, user_id)
            session.add(
                SuggestionPreviewInteractionRow(
                    id=str(uuid4()),
                    user_id=actor_id,
                    workspace_id=str(workspace_id or "").strip(),
                    action=str(action or "unknown").strip().lower() or "unknown",
                    result=str(result or "success").strip().lower() or "success",
                    error_code=str(error_code or "").strip().lower() or None,
                    details_json=dict(details) if details is not None else None,
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()

    def clear_metrics(self) -> SuggestionMetricsClearResultEntity:
        with session_scope(self.database_url) as session:
            interaction_result = session.execute(delete(SuggestionInteractionRow))
            preview_result = session.execute(delete(SuggestionPreviewInteractionRow))
            session.commit()

        return SuggestionMetricsClearResultEntity(
            message="Suggestions metrics cleared",
            deleted_count=int(interaction_result.rowcount or 0) + int(preview_result.rowcount or 0),
        )

    def _resolve_or_create_user_id(self, session, user_id: str) -> str:
        requester = session.execute(select(UserRow).where(UserRow.id == user_id)).scalar_one_or_none()
        if requester is None:
            requester = session.execute(select(UserRow).where(UserRow.external_id == user_id)).scalar_one_or_none()
        if requester is None and "@" in user_id:
            requester = session.execute(select(UserRow).where(UserRow.email == user_id)).scalar_one_or_none()
        if requester is not None:
            return requester.id

        first_name, last_name = normalize_user_name_parts("", "", fallback=user_id)
        email = user_id if "@" in user_id else None
        session.add(UserRow(id=user_id, first_name=first_name, last_name=last_name, email=email, external_id=user_id))
        return user_id

    def _resolve_requester_ids(self, session, user_id: str) -> set[str]:
        requester_ids = {user_id}
        requester = session.execute(select(UserRow).where(UserRow.id == user_id)).scalar_one_or_none()
        if requester is None:
            requester = session.execute(select(UserRow).where(UserRow.external_id == user_id)).scalar_one_or_none()
        if requester is None and "@" in user_id:
            requester = session.execute(select(UserRow).where(UserRow.email == user_id)).scalar_one_or_none()
        if requester is not None:
            requester_ids.add(requester.id)
            if requester.external_id:
                requester_ids.add(requester.external_id)
        return requester_ids

    def _append_natural_language_request_history_row(
        self,
        session,
        *,
        request_id: str,
        action: str,
        from_status: str | None,
        to_status: str | None,
        actor_id: str | None,
        details: dict | None,
    ) -> NaturalLanguageAnalysisRequestHistoryRow:
        history_row = NaturalLanguageAnalysisRequestHistoryRow(
            id=str(uuid4()),
            request_id=request_id,
            action=str(action or "unknown").strip().lower() or "unknown",
            from_status=from_status,
            to_status=to_status,
            actor_id=actor_id,
            details_json=dict(details) if details is not None else {},
            changed_at=datetime.now(UTC),
        )
        session.add(history_row)
        return history_row
