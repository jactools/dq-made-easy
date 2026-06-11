from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.domain.entities import GxExecutionContractEntity
from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.domain.entities import ValidationRunPlanArtifactSelectionEntity
from app.domain.entities import ValidationRunPlanEntity
from app.domain.entities import ValidationRunPlanGroupedArtifactSnapshotEntity
from app.domain.entities import ValidationRunPlanScheduleDefinitionEntity
from app.domain.entities import ValidationRunPlanScopeSelectorEntity
from app.domain.entities import build_validation_artifact_snapshot_payload_from_gx_snapshot
from app.domain.entities import build_validation_run_plan_artifact_selection_entity
from app.domain.entities import build_validation_run_plan_entity
from app.domain.entities.gx_run_plan_governance import is_run_plan_version_pending_state
from app.domain.entities.gx_run_plan_governance import is_valid_run_plan_version_transition
from app.domain.interfaces.v1.validation_run_plan_repository import ValidationRunPlanRepository
from app.infrastructure.orm.models import ValidationRunPlanRow
from app.infrastructure.orm.models import ValidationRunPlanTransitionRow
from app.infrastructure.orm.models import ValidationRunPlanVersionRow
from app.infrastructure.orm.session import session_scope


def _select_pending_version(versions: list[dict[str, Any]]) -> dict[str, Any] | None:
    for version in reversed(versions):
        state = str(version.get("governanceState") or "").strip()
        if is_run_plan_version_pending_state(state):
            return version
    return None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    payload = str(value).strip()
    if not payload:
        return None
    return datetime.fromisoformat(payload.replace("Z", "+00:00"))


def _format_iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _coerce_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normalize_artifact_snapshot(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if any(key in payload for key in ("suiteId", "suiteVersion", "gxSuite", "artifactVersion", "suiteEnvelopes")):
        return build_validation_artifact_snapshot_payload_from_gx_snapshot(payload)
    return dict(payload)


def _serialize_transition_event(row: ValidationRunPlanTransitionRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "runPlanId": row.run_plan_id,
        "runPlanVersionId": row.run_plan_version_id,
        "action": row.action,
        "fromState": row.from_state,
        "toState": row.to_state,
        "actorId": row.actor_id,
        "correlationId": row.correlation_id,
        "effectiveFrom": _format_iso_datetime(row.effective_from),
        "details": dict(row.details_json or {}),
        "occurredAt": _format_iso_datetime(row.occurred_at) or "",
    }


def _append_transition_event(
    session,
    *,
    run_plan_id: str,
    run_plan_version_id: str | None,
    action: str,
    from_state: str | None,
    to_state: str | None,
    actor_id: str | None,
    correlation_id: str | None,
    effective_from: datetime | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        ValidationRunPlanTransitionRow(
            id=f"validation-run-plan-transition-{uuid4().hex}",
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            action=str(action or ""),
            from_state=from_state,
            to_state=to_state,
            actor_id=actor_id,
            correlation_id=correlation_id,
            effective_from=effective_from,
            details_json=dict(details or {}),
            occurred_at=datetime.now(UTC),
        )
    )


class PostgresValidationRunPlanRepository(ValidationRunPlanRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def create_plan(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        workspace_id: str,
        scope_selector: ValidationRunPlanScopeSelectorEntity,
        planning_mode: str,
        status: str,
        created_by: str | None,
        validation_artifact_selection: ValidationRunPlanArtifactSelectionEntity,
        artifact_id: str | None,
        artifact_version: int | None,
        artifact_snapshot: ValidationArtifactEnvelopeEntity | ValidationRunPlanGroupedArtifactSnapshotEntity | dict | None,
        execution_contract_snapshot: GxExecutionContractEntity | None,
        schedule_definition: ValidationRunPlanScheduleDefinitionEntity,
        effective_from: str | None = None,
        validation_status: str | None = None,
        review_status: str | None = None,
        supersedes_version_id: str | None = None,
        correlation_id: str | None = None,
    ) -> ValidationRunPlanEntity:
        with session_scope(self.database_url) as session:
            if session.get(ValidationRunPlanRow, run_plan_id) is not None:
                raise ValueError(f"Validation run plan '{run_plan_id}' already exists")

            now = datetime.now(UTC)
            effective_from_dt = _parse_iso_datetime(effective_from)
            selection_payload = build_validation_run_plan_artifact_selection_entity(
                validation_artifact_selection
            ).model_dump(mode="python", by_alias=False, exclude_none=True)
            schedule_payload = schedule_definition.model_dump(mode="python", by_alias=False, exclude_none=True)
            artifact_snapshot_payload = (
                artifact_snapshot.model_dump(mode="python", by_alias=False, exclude_none=True)
                if hasattr(artifact_snapshot, "model_dump")
                else dict(artifact_snapshot)
                if isinstance(artifact_snapshot, dict)
                else None
            )
            execution_contract_payload = (
                execution_contract_snapshot.model_dump(mode="python", by_alias=False, exclude_none=True)
                if execution_contract_snapshot is not None
                else None
            )

            session.add(
                ValidationRunPlanRow(
                    id=run_plan_id,
                    business_key=run_plan_id,
                    workspace_id=workspace_id,
                    scope_selector_json=scope_selector.model_dump(mode="python", by_alias=False, exclude_none=True),
                    planning_mode=planning_mode,
                    current_active_version_id=None,
                    status=status,
                    created_by=created_by,
                    created_at=now,
                    updated_at=now,
                    activated_by=None,
                    activated_at=None,
                    last_dispatched_run_id=None,
                )
            )
            session.add(
                ValidationRunPlanVersionRow(
                    id=run_plan_version_id,
                    run_plan_id=run_plan_id,
                    validation_artifact_selection_json=selection_payload,
                    artifact_id=artifact_id,
                    artifact_version=artifact_version,
                    artifact_snapshot_json=artifact_snapshot_payload,
                    execution_contract_snapshot_json=execution_contract_payload,
                    schedule_definition_json=schedule_payload,
                    governance_state=status,
                    validation_status=validation_status or "not_requested",
                    review_status=review_status,
                    effective_from=effective_from_dt,
                    supersedes_version_id=supersedes_version_id,
                    created_by=created_by,
                    created_at=now,
                )
            )
            _append_transition_event(
                session,
                run_plan_id=run_plan_id,
                run_plan_version_id=run_plan_version_id,
                action="created",
                from_state=None,
                to_state=status,
                actor_id=created_by,
                correlation_id=correlation_id,
                effective_from=effective_from_dt,
                details={
                    "planning_mode": planning_mode,
                    "workspace_id": workspace_id,
                    "supersedes_version_id": supersedes_version_id,
                },
            )
            session.flush()
            session.commit()

        plan = await self.get_plan(run_plan_id)
        if plan is None:
            raise RuntimeError(f"Validation run plan '{run_plan_id}' was not persisted")
        return plan

    async def get_plan(self, run_plan_id: str) -> ValidationRunPlanEntity | None:
        with session_scope(self.database_url) as session:
            plan_row = session.get(ValidationRunPlanRow, run_plan_id)
            if plan_row is None:
                return None
            version_rows = session.execute(
                select(ValidationRunPlanVersionRow)
                .where(ValidationRunPlanVersionRow.run_plan_id == run_plan_id)
                .order_by(ValidationRunPlanVersionRow.created_at.asc())
            ).scalars().all()
            transition_rows = session.execute(
                select(ValidationRunPlanTransitionRow)
                .where(ValidationRunPlanTransitionRow.run_plan_id == run_plan_id)
                .order_by(ValidationRunPlanTransitionRow.occurred_at.asc())
            ).scalars().all()

        return build_validation_run_plan_entity(self._serialize_plan(plan_row, version_rows, transition_rows))

    async def create_plan_version(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        validation_artifact_selection: ValidationRunPlanArtifactSelectionEntity,
        artifact_id: str | None,
        artifact_version: int | None,
        artifact_snapshot: ValidationArtifactEnvelopeEntity | ValidationRunPlanGroupedArtifactSnapshotEntity | dict | None,
        execution_contract_snapshot: GxExecutionContractEntity | None,
        schedule_definition: ValidationRunPlanScheduleDefinitionEntity,
        created_by: str | None,
        effective_from: str | None = None,
        validation_status: str | None = None,
        review_status: str | None = None,
        supersedes_version_id: str | None = None,
        correlation_id: str | None = None,
    ) -> ValidationRunPlanEntity:
        with session_scope(self.database_url) as session:
            plan_row = session.get(ValidationRunPlanRow, run_plan_id)
            if plan_row is None:
                raise ValueError(f"Validation run plan '{run_plan_id}' not found")

            now = datetime.now(UTC)
            effective_from_dt = _parse_iso_datetime(effective_from)
            session.add(
                ValidationRunPlanVersionRow(
                    id=run_plan_version_id,
                    run_plan_id=run_plan_id,
                    validation_artifact_selection_json=build_validation_run_plan_artifact_selection_entity(
                        validation_artifact_selection
                    ).model_dump(mode="python", by_alias=False, exclude_none=True),
                    artifact_id=artifact_id,
                    artifact_version=artifact_version,
                    artifact_snapshot_json=(
                        artifact_snapshot.model_dump(mode="python", by_alias=False, exclude_none=True)
                        if hasattr(artifact_snapshot, "model_dump")
                        else dict(artifact_snapshot)
                        if isinstance(artifact_snapshot, dict)
                        else None
                    ),
                    execution_contract_snapshot_json=(
                        execution_contract_snapshot.model_dump(mode="python", by_alias=False, exclude_none=True)
                        if execution_contract_snapshot is not None
                        else None
                    ),
                    schedule_definition_json=schedule_definition.model_dump(
                        mode="python", by_alias=False, exclude_none=True
                    ),
                    governance_state="draft",
                    validation_status=validation_status or "not_requested",
                    review_status=review_status,
                    effective_from=effective_from_dt,
                    supersedes_version_id=supersedes_version_id,
                    created_by=created_by,
                    created_at=now,
                )
            )
            _append_transition_event(
                session,
                run_plan_id=run_plan_id,
                run_plan_version_id=run_plan_version_id,
                action="version_created",
                from_state=None,
                to_state="draft",
                actor_id=created_by,
                correlation_id=correlation_id,
                effective_from=effective_from_dt,
                details={"supersedes_version_id": supersedes_version_id},
            )
            plan_row.updated_at = now
            if plan_row.current_active_version_id is None:
                plan_row.status = "draft"
            session.commit()

        plan = await self.get_plan(run_plan_id)
        if plan is None:
            raise RuntimeError(f"Validation run plan '{run_plan_id}' was not persisted")
        return plan

    async def list_plans(
        self,
        *,
        workspace_id: str | None = None,
        business_key: str | None = None,
        status: str | None = None,
        artifact_id: str | None = None,
    ) -> list[ValidationRunPlanEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(ValidationRunPlanRow)
            if workspace_id is not None:
                stmt = stmt.where(ValidationRunPlanRow.workspace_id == workspace_id)
            if business_key is not None:
                stmt = stmt.where(ValidationRunPlanRow.business_key == business_key)
            if status is not None:
                stmt = stmt.where(ValidationRunPlanRow.status == status)
            stmt = stmt.order_by(ValidationRunPlanRow.updated_at.desc(), ValidationRunPlanRow.created_at.desc())
            plan_rows = session.execute(stmt).scalars().all()

            plan_ids = [row.id for row in plan_rows]
            version_map: dict[str, list[ValidationRunPlanVersionRow]] = {plan_id: [] for plan_id in plan_ids}
            transition_map: dict[str, list[ValidationRunPlanTransitionRow]] = {plan_id: [] for plan_id in plan_ids}
            if plan_ids:
                version_rows = session.execute(
                    select(ValidationRunPlanVersionRow)
                    .where(ValidationRunPlanVersionRow.run_plan_id.in_(plan_ids))
                    .order_by(ValidationRunPlanVersionRow.created_at.asc())
                ).scalars().all()
                for row in version_rows:
                    version_map.setdefault(row.run_plan_id, []).append(row)
                transition_rows = session.execute(
                    select(ValidationRunPlanTransitionRow)
                    .where(ValidationRunPlanTransitionRow.run_plan_id.in_(plan_ids))
                    .order_by(ValidationRunPlanTransitionRow.occurred_at.asc())
                ).scalars().all()
                for row in transition_rows:
                    transition_map.setdefault(row.run_plan_id, []).append(row)

        rows = [
            build_validation_run_plan_entity(
                self._serialize_plan(row, version_map.get(row.id, []), transition_map.get(row.id, []))
            )
            for row in plan_rows
        ]
        if artifact_id is not None:
            rows = [
                row for row in rows if any(str(version.artifactId or "") == artifact_id for version in row.versions)
            ]
        return rows

    async def transition_plan_version(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        target_state: str,
        updated_by: str | None,
        effective_from: str | None = None,
        correlation_id: str | None = None,
    ) -> ValidationRunPlanEntity:
        with session_scope(self.database_url) as session:
            plan_row = session.get(ValidationRunPlanRow, run_plan_id)
            if plan_row is None:
                raise ValueError(f"Validation run plan '{run_plan_id}' not found")

            version_row = session.get(ValidationRunPlanVersionRow, run_plan_version_id)
            if version_row is None or version_row.run_plan_id != run_plan_id:
                raise ValueError(f"Validation run plan version '{run_plan_version_id}' not found")

            current_state = str(version_row.governance_state or "").strip()
            if not current_state:
                raise ValueError(f"Validation run plan version '{run_plan_version_id}' is missing governance state")
            if not is_valid_run_plan_version_transition(current_state, target_state):
                raise ValueError(
                    f"Invalid validation run plan version transition '{current_state}' -> '{target_state}'"
                )

            if target_state == "pending_validation":
                version_row.validation_status = "pending"
                version_row.review_status = None
            elif target_state == "validation_failed":
                version_row.validation_status = "failed"
                version_row.review_status = None
            elif target_state == "pending_review":
                version_row.validation_status = "passed"
                version_row.review_status = "pending"
            elif target_state == "approved_pending_activation":
                version_row.validation_status = "passed"
                version_row.review_status = "approved"
                if effective_from is not None:
                    version_row.effective_from = _parse_iso_datetime(effective_from)
            elif target_state == "cancelled":
                version_row.review_status = "cancelled"

            version_row.governance_state = target_state
            plan_row.status = "active" if plan_row.current_active_version_id is not None else target_state
            _append_transition_event(
                session,
                run_plan_id=run_plan_id,
                run_plan_version_id=run_plan_version_id,
                action="transitioned",
                from_state=current_state,
                to_state=target_state,
                actor_id=updated_by,
                correlation_id=correlation_id,
                effective_from=_parse_iso_datetime(effective_from),
                details={"target_state": target_state},
            )

            plan_row.updated_at = datetime.now(UTC)
            session.commit()

        plan = await self.get_plan(run_plan_id)
        if plan is None:
            raise RuntimeError(f"Validation run plan '{run_plan_id}' was not persisted")
        return plan

    async def activate_plan(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        activated_by: str | None,
        dispatched_run_id: str | None = None,
        correlation_id: str | None = None,
    ) -> ValidationRunPlanEntity:
        with session_scope(self.database_url) as session:
            plan_row = session.get(ValidationRunPlanRow, run_plan_id)
            if plan_row is None:
                raise ValueError(f"Validation run plan '{run_plan_id}' not found")

            version_row = session.get(ValidationRunPlanVersionRow, run_plan_version_id)
            if version_row is None or version_row.run_plan_id != run_plan_id:
                raise ValueError(f"Validation run plan version '{run_plan_version_id}' not found")
            current_state = str(version_row.governance_state or "").strip()
            if current_state != "approved_pending_activation":
                raise ValueError(
                    f"Validation run plan version '{run_plan_version_id}' is not approved for activation"
                )

            now = datetime.now(UTC)
            previous_active_version_id = plan_row.current_active_version_id
            if previous_active_version_id and previous_active_version_id != run_plan_version_id:
                previous_row = session.get(ValidationRunPlanVersionRow, previous_active_version_id)
                if previous_row is not None and previous_row.run_plan_id == run_plan_id:
                    previous_row.governance_state = "superseded"
                    previous_row.review_status = "superseded"
                    _append_transition_event(
                        session,
                        run_plan_id=run_plan_id,
                        run_plan_version_id=previous_active_version_id,
                        action="superseded",
                        from_state="active",
                        to_state="superseded",
                        actor_id=activated_by,
                        correlation_id=correlation_id,
                        details={"superseded_by": run_plan_version_id},
                    )
            version_row.governance_state = "active"
            plan_row.status = "active"
            plan_row.current_active_version_id = run_plan_version_id
            plan_row.updated_at = now
            plan_row.activated_by = activated_by
            plan_row.activated_at = now
            plan_row.last_dispatched_run_id = dispatched_run_id
            _append_transition_event(
                session,
                run_plan_id=run_plan_id,
                run_plan_version_id=run_plan_version_id,
                action="activated",
                from_state=current_state,
                to_state="active",
                actor_id=activated_by,
                correlation_id=correlation_id,
                details={"dispatched_run_id": dispatched_run_id},
            )
            session.commit()

        plan = await self.get_plan(run_plan_id)
        if plan is None:
            raise RuntimeError(f"Validation run plan '{run_plan_id}' was not persisted")
        return plan

    async def deactivate_plan(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        deactivated_by: str | None,
        correlation_id: str | None = None,
    ) -> ValidationRunPlanEntity:
        with session_scope(self.database_url) as session:
            plan_row = session.get(ValidationRunPlanRow, run_plan_id)
            if plan_row is None:
                raise ValueError(f"Validation run plan '{run_plan_id}' not found")

            version_row = session.get(ValidationRunPlanVersionRow, run_plan_version_id)
            if version_row is None or version_row.run_plan_id != run_plan_id:
                raise ValueError(f"Validation run plan version '{run_plan_version_id}' not found")

            current_state = str(version_row.governance_state or "").strip()
            if current_state != "deactivation-requested":
                raise ValueError(
                    f"Validation run plan version '{run_plan_version_id}' is not pending deactivation"
                )

            now = datetime.now(UTC)
            version_row.governance_state = "deactivated"
            plan_row.status = "deactivated"
            if str(plan_row.current_active_version_id or "") == run_plan_version_id:
                plan_row.current_active_version_id = None
            plan_row.updated_at = now
            _append_transition_event(
                session,
                run_plan_id=run_plan_id,
                run_plan_version_id=run_plan_version_id,
                action="deactivated",
                from_state=current_state,
                to_state="deactivated",
                actor_id=deactivated_by,
                correlation_id=correlation_id,
            )
            session.commit()

        plan = await self.get_plan(run_plan_id)
        if plan is None:
            raise RuntimeError("Failed to deactivate validation run plan")
        return plan

    async def record_plan_dispatch(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        dispatched_run_id: str,
        dispatched_by: str | None,
        correlation_id: str | None = None,
        details: dict | None = None,
    ) -> ValidationRunPlanEntity:
        with session_scope(self.database_url) as session:
            plan_row = session.get(ValidationRunPlanRow, run_plan_id)
            if plan_row is None:
                raise ValueError(f"Validation run plan '{run_plan_id}' not found")

            version_row = session.get(ValidationRunPlanVersionRow, run_plan_version_id)
            if version_row is None or version_row.run_plan_id != run_plan_id:
                raise ValueError(f"Validation run plan version '{run_plan_version_id}' not found")

            current_state = str(version_row.governance_state or "").strip()
            if current_state != "active" or str(plan_row.current_active_version_id or "") != run_plan_version_id:
                raise ValueError(f"Validation run plan version '{run_plan_version_id}' is not active")

            plan_row.last_dispatched_run_id = dispatched_run_id
            plan_row.updated_at = datetime.now(UTC)
            _append_transition_event(
                session,
                run_plan_id=run_plan_id,
                run_plan_version_id=run_plan_version_id,
                action="dispatched",
                from_state="active",
                to_state="active",
                actor_id=dispatched_by,
                correlation_id=correlation_id,
                details={
                    "dispatched_run_id": dispatched_run_id,
                    **dict(details or {}),
                },
            )
            session.commit()

        plan = await self.get_plan(run_plan_id)
        if plan is None:
            raise RuntimeError("Failed to record validation run plan dispatch")
        return plan

    @staticmethod
    def _serialize_version(row: ValidationRunPlanVersionRow) -> dict[str, Any]:
        return {
            "runPlanVersionId": row.id,
            "runPlanId": row.run_plan_id,
            "governanceState": str(row.governance_state or "draft"),
            "validationArtifactSelection": dict(row.validation_artifact_selection_json or {}),
            "artifactId": row.artifact_id,
            "artifactVersion": row.artifact_version,
            "artifactSnapshot": _normalize_artifact_snapshot(row.artifact_snapshot_json),
            "executionContractSnapshot": (
                dict(row.execution_contract_snapshot_json or {})
                if row.execution_contract_snapshot_json is not None
                else None
            ),
            "scheduleDefinition": dict(row.schedule_definition_json or {}),
            "validationStatus": row.validation_status,
            "reviewStatus": row.review_status,
            "effectiveFrom": _format_iso_datetime(row.effective_from),
            "supersedesVersionId": row.supersedes_version_id,
            "createdBy": row.created_by,
            "createdAt": _format_iso_datetime(row.created_at) or "",
        }

    def _serialize_plan(
        self,
        row: ValidationRunPlanRow,
        version_rows: list[ValidationRunPlanVersionRow],
        transition_rows: list[ValidationRunPlanTransitionRow],
    ) -> dict[str, Any]:
        versions = [self._serialize_version(version_row) for version_row in version_rows]
        pending_version = _select_pending_version(versions)
        return {
            "runPlanId": row.id,
            "businessKey": str(getattr(row, "business_key", None) or row.id),
            "workspaceId": row.workspace_id,
            "scopeSelector": _coerce_mapping(row.scope_selector_json),
            "planningMode": row.planning_mode,
            "currentActiveVersionId": row.current_active_version_id,
            "status": str(row.status or "draft"),
            "pendingVersionId": pending_version.get("runPlanVersionId") if pending_version is not None else None,
            "pendingVersionGovernanceState": (
                pending_version.get("governanceState") if pending_version is not None else None
            ),
            "createdBy": row.created_by,
            "createdAt": _format_iso_datetime(row.created_at) or "",
            "updatedAt": _format_iso_datetime(row.updated_at) or "",
            "activatedBy": row.activated_by,
            "activatedAt": _format_iso_datetime(row.activated_at),
            "lastDispatchedRunId": row.last_dispatched_run_id,
            "versions": versions,
            "transitionEvents": [_serialize_transition_event(item) for item in transition_rows],
        }