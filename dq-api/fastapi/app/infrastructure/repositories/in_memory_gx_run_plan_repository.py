from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.domain.entities import GxRunPlanEntity
from app.domain.entities.gx_run_plan import build_gx_run_plan_entity
from app.domain.entities.gx_run_plan_governance import is_run_plan_version_pending_state
from app.domain.entities.gx_run_plan_governance import is_valid_run_plan_version_transition
from app.domain.interfaces.v1.gx_run_plan_repository import GxRunPlanRepository


def _select_pending_version(versions: list[dict]) -> dict | None:
    for version in reversed(versions):
        if is_run_plan_version_pending_state(str(version.get("governanceState") or "")):
            return version
    return None


def _format_iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


class InMemoryGxRunPlanRepository(GxRunPlanRepository):
    def __init__(self) -> None:
        self._plans: dict[str, dict] = {}
        self._versions_by_plan: dict[str, list[dict]] = {}
        self._transition_events_by_plan: dict[str, list[dict]] = {}

    def _append_transition_event(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str | None,
        action: str,
        from_state: str | None,
        to_state: str | None,
        actor_id: str | None,
        correlation_id: str | None,
        effective_from: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        now_iso = datetime.now(UTC).isoformat()
        self._transition_events_by_plan.setdefault(run_plan_id, []).append(
            {
                "id": f"gx-run-plan-transition-{uuid4().hex}",
                "runPlanId": run_plan_id,
                "runPlanVersionId": run_plan_version_id,
                "action": action,
                "fromState": from_state,
                "toState": to_state,
                "actorId": actor_id,
                "correlationId": correlation_id,
                "effectiveFrom": effective_from,
                "details": deepcopy(details or {}),
                "occurredAt": now_iso,
            }
        )

    async def create_plan(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        workspace_id: str,
        scope_selector: dict,
        planning_mode: str,
        status: str,
        created_by: str | None,
        gx_suite_selection: dict,
        suite_id: str | None,
        suite_version: int | None,
        suite_snapshot: dict | None,
        execution_contract_snapshot: dict | None,
        schedule_definition: dict,
        effective_from: str | None = None,
        validation_status: str | None = None,
        review_status: str | None = None,
        supersedes_version_id: str | None = None,
        correlation_id: str | None = None,
    ) -> GxRunPlanEntity:
        if run_plan_id in self._plans:
            raise ValueError(f"GX run plan '{run_plan_id}' already exists")

        now_iso = datetime.now(UTC).isoformat()
        self._plans[run_plan_id] = {
            "runPlanId": run_plan_id,
            "businessKey": run_plan_id,
            "workspaceId": workspace_id,
            "scopeSelector": deepcopy(scope_selector),
            "planningMode": planning_mode,
            "currentActiveVersionId": None,
            "status": status,
            "createdBy": created_by,
            "createdAt": now_iso,
            "updatedAt": now_iso,
            "activatedBy": None,
            "activatedAt": None,
            "lastDispatchedRunId": None,
        }
        self._versions_by_plan[run_plan_id] = [
            {
                "runPlanVersionId": run_plan_version_id,
                "runPlanId": run_plan_id,
                "governanceState": status,
                "gxSuiteSelection": deepcopy(gx_suite_selection),
                "suiteId": suite_id,
                "suiteVersion": suite_version,
                "suiteSnapshot": deepcopy(suite_snapshot),
                "executionContractSnapshot": deepcopy(execution_contract_snapshot),
                "scheduleDefinition": deepcopy(schedule_definition),
                "validationStatus": validation_status or "not_requested",
                "reviewStatus": review_status,
                "effectiveFrom": effective_from,
                "supersedesVersionId": supersedes_version_id,
                "createdBy": created_by,
                "createdAt": now_iso,
            }
        ]
        self._append_transition_event(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            action="created",
            from_state=None,
            to_state=status,
            actor_id=created_by,
            correlation_id=correlation_id,
            effective_from=effective_from,
            details={
                "planning_mode": planning_mode,
                "workspace_id": workspace_id,
                "supersedes_version_id": supersedes_version_id,
            },
        )
        plan = await self.get_plan(run_plan_id)
        if plan is None:
            raise RuntimeError(f"GX run plan '{run_plan_id}' was not persisted")
        return plan

    async def get_plan(self, run_plan_id: str) -> GxRunPlanEntity | None:
        plan = self._plans.get(run_plan_id)
        if plan is None:
            return None
        versions = self._serialize_versions(plan_id=run_plan_id)
        transition_events = [deepcopy(item) for item in self._transition_events_by_plan.get(run_plan_id, [])]
        pending_version = _select_pending_version(versions)
        return build_gx_run_plan_entity({
            **deepcopy(plan),
            "pendingVersionId": pending_version.get("runPlanVersionId") if pending_version is not None else None,
            "pendingVersionGovernanceState": pending_version.get("governanceState") if pending_version is not None else None,
            "versions": versions,
            "transitionEvents": transition_events,
        })

    async def create_plan_version(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        gx_suite_selection: dict,
        suite_id: str | None,
        suite_version: int | None,
        suite_snapshot: dict | None,
        execution_contract_snapshot: dict | None,
        schedule_definition: dict,
        created_by: str | None,
        effective_from: str | None = None,
        validation_status: str | None = None,
        review_status: str | None = None,
        supersedes_version_id: str | None = None,
        correlation_id: str | None = None,
    ) -> GxRunPlanEntity:
        plan = self._plans.get(run_plan_id)
        if plan is None:
            raise ValueError(f"GX run plan '{run_plan_id}' not found")

        now_iso = datetime.now(UTC).isoformat()
        self._versions_by_plan.setdefault(run_plan_id, []).append(
            {
                "runPlanVersionId": run_plan_version_id,
                "runPlanId": run_plan_id,
                "governanceState": "draft",
                "gxSuiteSelection": deepcopy(gx_suite_selection),
                "suiteId": suite_id,
                "suiteVersion": suite_version,
                "suiteSnapshot": deepcopy(suite_snapshot),
                "executionContractSnapshot": deepcopy(execution_contract_snapshot),
                "scheduleDefinition": deepcopy(schedule_definition),
                "validationStatus": validation_status or "not_requested",
                "reviewStatus": review_status,
                "effectiveFrom": effective_from,
                "supersedesVersionId": supersedes_version_id,
                "createdBy": created_by,
                "createdAt": now_iso,
            }
        )
        if plan.get("currentActiveVersionId") is None:
            plan["status"] = "draft"
        plan["updatedAt"] = now_iso
        self._append_transition_event(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            action="version_created",
            from_state=None,
            to_state="draft",
            actor_id=created_by,
            correlation_id=correlation_id,
            effective_from=effective_from,
            details={"supersedes_version_id": supersedes_version_id},
        )
        plan = await self.get_plan(run_plan_id)
        if plan is None:
            raise RuntimeError(f"GX run plan '{run_plan_id}' was not persisted")
        return plan

    async def list_plans(
        self,
        *,
        workspace_id: str | None = None,
        business_key: str | None = None,
        status: str | None = None,
        suite_id: str | None = None,
    ) -> list[GxRunPlanEntity]:
        rows: list[GxRunPlanEntity] = []
        for plan_id, plan in self._plans.items():
            if workspace_id is not None and str(plan.get("workspaceId") or "") != workspace_id:
                continue
            if business_key is not None and str(plan.get("businessKey") or "") != business_key:
                continue
            versions = self._serialize_versions(plan_id=plan_id)
            pending_version = _select_pending_version(versions)
            if status is not None and str(plan.get("status") or "") != status:
                continue
            if suite_id is not None and not any(str(version.get("suiteId") or "") == suite_id for version in versions):
                continue
            rows.append(
                build_gx_run_plan_entity({
                    **deepcopy(plan),
                    "pendingVersionId": pending_version.get("runPlanVersionId") if pending_version is not None else None,
                    "pendingVersionGovernanceState": pending_version.get("governanceState") if pending_version is not None else None,
                    "versions": versions,
                    "transitionEvents": [deepcopy(item) for item in self._transition_events_by_plan.get(plan_id, [])],
                })
            )
        rows.sort(key=lambda item: item.updatedAt or item.createdAt or "", reverse=True)
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
    ) -> GxRunPlanEntity:
        plan = self._plans.get(run_plan_id)
        if plan is None:
            raise ValueError(f"GX run plan '{run_plan_id}' not found")

        versions = self._versions_by_plan.get(run_plan_id, [])
        version = next((item for item in versions if str(item.get("runPlanVersionId") or "") == run_plan_version_id), None)
        if version is None:
            raise ValueError(f"GX run plan version '{run_plan_version_id}' not found")

        current_state = str(version.get("governanceState") or "").strip()
        if not current_state:
            raise ValueError(f"GX run plan version '{run_plan_version_id}' is missing governance state")
        if not is_valid_run_plan_version_transition(current_state, target_state):
            raise ValueError(f"Invalid GX run plan version transition '{current_state}' -> '{target_state}'")

        if target_state == "pending_validation":
            version["validationStatus"] = "pending"
            version["reviewStatus"] = None
        elif target_state == "validation_failed":
            version["validationStatus"] = "failed"
            version["reviewStatus"] = None
        elif target_state == "pending_review":
            version["validationStatus"] = "passed"
            version["reviewStatus"] = "pending"
        elif target_state == "approved_pending_activation":
            version["validationStatus"] = "passed"
            version["reviewStatus"] = "approved"
            if effective_from is not None:
                version["effectiveFrom"] = effective_from
        elif target_state == "cancelled":
            version["reviewStatus"] = "cancelled"

        version["governanceState"] = target_state
        plan["status"] = "active" if plan.get("currentActiveVersionId") is not None else target_state
        plan["updatedAt"] = datetime.now(UTC).isoformat()
        self._append_transition_event(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            action="transitioned",
            from_state=current_state,
            to_state=target_state,
            actor_id=updated_by,
            correlation_id=correlation_id,
            effective_from=effective_from,
            details={"target_state": target_state},
        )
        plan = await self.get_plan(run_plan_id)
        if plan is None:
            raise RuntimeError(f"GX run plan '{run_plan_id}' was not persisted")
        return plan

    async def activate_plan(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        activated_by: str | None,
        dispatched_run_id: str | None = None,
        correlation_id: str | None = None,
    ) -> GxRunPlanEntity:
        plan = self._plans.get(run_plan_id)
        if plan is None:
            raise ValueError(f"GX run plan '{run_plan_id}' not found")

        versions = self._versions_by_plan.get(run_plan_id, [])
        target_version = next((version for version in versions if str(version.get("runPlanVersionId") or "") == run_plan_version_id), None)
        if target_version is None:
            raise ValueError(f"GX run plan version '{run_plan_version_id}' not found")
        current_state = str(target_version.get("governanceState") or "").strip()
        if current_state != "approved_pending_activation":
            raise ValueError(f"GX run plan version '{run_plan_version_id}' is not approved for activation")

        now_iso = datetime.now(UTC).isoformat()
        previous_active_version_id = str(plan.get("currentActiveVersionId") or "") or None
        if previous_active_version_id and previous_active_version_id != run_plan_version_id:
            previous_version = next(
                (item for item in versions if str(item.get("runPlanVersionId") or "") == previous_active_version_id),
                None,
            )
            if previous_version is not None:
                previous_version["governanceState"] = "superseded"
                previous_version["reviewStatus"] = "superseded"
                self._append_transition_event(
                    run_plan_id=run_plan_id,
                    run_plan_version_id=previous_active_version_id,
                    action="superseded",
                    from_state="active",
                    to_state="superseded",
                    actor_id=activated_by,
                    correlation_id=correlation_id,
                    details={"superseded_by": run_plan_version_id},
                )
        target_version["governanceState"] = "active"
        plan["status"] = "active"
        plan["currentActiveVersionId"] = run_plan_version_id
        plan["updatedAt"] = now_iso
        plan["activatedBy"] = activated_by
        plan["activatedAt"] = now_iso
        plan["lastDispatchedRunId"] = dispatched_run_id
        self._append_transition_event(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            action="activated",
            from_state=current_state,
            to_state="active",
            actor_id=activated_by,
            correlation_id=correlation_id,
            details={"dispatched_run_id": dispatched_run_id},
        )
        plan = await self.get_plan(run_plan_id)
        if plan is None:
            raise RuntimeError(f"GX run plan '{run_plan_id}' was not persisted")
        return plan

    async def deactivate_plan(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        deactivated_by: str | None,
        correlation_id: str | None = None,
    ) -> GxRunPlanEntity:
        plan = self._plans.get(run_plan_id)
        if plan is None:
            raise ValueError(f"GX run plan '{run_plan_id}' not found")

        versions = self._versions_by_plan.get(run_plan_id, [])
        target_version = next((version for version in versions if str(version.get("runPlanVersionId") or "") == run_plan_version_id), None)
        if target_version is None:
            raise ValueError(f"GX run plan version '{run_plan_version_id}' not found")

        current_state = str(target_version.get("governanceState") or "").strip()
        if current_state != "deactivation-requested":
            raise ValueError(f"GX run plan version '{run_plan_version_id}' is not pending deactivation")

        now_iso = datetime.now(UTC).isoformat()
        target_version["governanceState"] = "deactivated"
        plan["status"] = "deactivated"
        if str(plan.get("currentActiveVersionId") or "") == run_plan_version_id:
            plan["currentActiveVersionId"] = None
        plan["updatedAt"] = now_iso
        self._append_transition_event(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            action="deactivated",
            from_state=current_state,
            to_state="deactivated",
            actor_id=deactivated_by,
            correlation_id=correlation_id,
        )
        plan = await self.get_plan(run_plan_id)
        if plan is None:
            raise RuntimeError(f"GX run plan '{run_plan_id}' was not persisted")
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
    ) -> GxRunPlanEntity:
        plan = self._plans.get(run_plan_id)
        if plan is None:
            raise ValueError(f"GX run plan '{run_plan_id}' not found")

        versions = self._versions_by_plan.get(run_plan_id, [])
        target_version = next((version for version in versions if str(version.get("runPlanVersionId") or "") == run_plan_version_id), None)
        if target_version is None:
            raise ValueError(f"GX run plan version '{run_plan_version_id}' not found")

        current_state = str(target_version.get("governanceState") or "").strip()
        if current_state != "active" or str(plan.get("currentActiveVersionId") or "") != run_plan_version_id:
            raise ValueError(f"GX run plan version '{run_plan_version_id}' is not active")

        now_iso = datetime.now(UTC).isoformat()
        plan["lastDispatchedRunId"] = dispatched_run_id
        plan["updatedAt"] = now_iso
        self._append_transition_event(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            action="dispatched",
            from_state="active",
            to_state="active",
            actor_id=dispatched_by,
            correlation_id=correlation_id,
            details={
                "dispatched_run_id": dispatched_run_id,
                **deepcopy(details or {}),
            },
        )
        plan = await self.get_plan(run_plan_id)
        if plan is None:
            raise RuntimeError(f"GX run plan '{run_plan_id}' was not persisted")
        return plan

    def _serialize_versions(self, *, plan_id: str) -> list[dict]:
        return [deepcopy(raw_version) for raw_version in self._versions_by_plan.get(plan_id, [])]