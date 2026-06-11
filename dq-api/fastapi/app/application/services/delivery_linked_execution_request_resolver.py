from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from app.application.services.grouped_execution_planner import GroupedExecutionPlanner
from app.core.otel_metrics import increment_gx_failure
from app.domain.entities import build_validation_artifact_envelope_entity
from app.domain.entities import build_validation_run_plan_entity
from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.domain.entities import ValidationRunPlanEntity
from app.domain.entities.gx_execution_run import build_gx_grouped_execution_plan_entity
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import ValidationArtifactRepository
from app.domain.interfaces import ValidationRunPlanRepository


class DeliveryLinkedExecutionRequestError(RuntimeError):
    def __init__(self, message: str, *, reason: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.reason = reason
        self.status_code = status_code


class DeliveryLinkedExecutionRequestResolver:
    def __init__(
        self,
        *,
        catalog_repository: DataCatalogRepository,
        validation_artifact_repository: ValidationArtifactRepository,
        validation_run_plan_repository: ValidationRunPlanRepository,
    ) -> None:
        self._catalog_repository = catalog_repository
        self._validation_artifact_repository = validation_artifact_repository
        self._validation_run_plan_repository = validation_run_plan_repository

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _row_value(row: Any, field_name: str) -> Any:
        if isinstance(row, Mapping):
            return row.get(field_name)
        return getattr(row, field_name, None)

    def _error(self, message: str, *, reason: str, status_code: int = 422) -> DeliveryLinkedExecutionRequestError:
        increment_gx_failure(surface="data_catalog", operation="submit_delivery_linked_execution", reason=reason)
        return DeliveryLinkedExecutionRequestError(message, reason=reason, status_code=status_code)

    @staticmethod
    def _coerce_artifact(row: Any) -> ValidationArtifactEnvelopeEntity:
        if isinstance(row, ValidationArtifactEnvelopeEntity):
            return row
        if hasattr(row, "model_dump"):
            row = getattr(row, "model_dump")(by_alias=False, exclude_none=False)
        return build_validation_artifact_envelope_entity(row)

    @staticmethod
    def _coerce_run_plan(row: Any) -> ValidationRunPlanEntity:
        if isinstance(row, ValidationRunPlanEntity):
            return row
        if hasattr(row, "model_dump"):
            row = getattr(row, "model_dump")(by_alias=False, exclude_none=False)
        return build_validation_run_plan_entity(row)

    @staticmethod
    def _artifact_engine_type(artifact: ValidationArtifactEnvelopeEntity | Mapping[str, Any] | None) -> str | None:
        if isinstance(artifact, ValidationArtifactEnvelopeEntity):
            engine_type = artifact.engineType
        elif isinstance(artifact, Mapping):
            engine_type = artifact.get("engineType") or artifact.get("engine_type")
        else:
            engine_type = None
        normalized = str(engine_type or "").strip().lower()
        return normalized or None

    @staticmethod
    def _suite_target_ids(suite: ValidationArtifactEnvelopeEntity) -> list[str]:
        return [
            str(target_id or "").strip()
            for target_id in suite.resolvedExecutionScope.dataObjectVersionIds
            if str(target_id or "").strip()
        ]

    @staticmethod
    def _suite_candidate_payload(suite: ValidationArtifactEnvelopeEntity) -> dict[str, Any]:
        return {
            "suite_id": suite.validationArtifactId,
            "suite_version": suite.validationArtifactVersion,
            "engine_type": DeliveryLinkedExecutionRequestResolver._artifact_engine_type(suite),
            "status": str(suite.status or "active"),
            "assignment_scope": suite.assignmentScope.model_dump(),
            "resolved_execution_scope": suite.resolvedExecutionScope.model_dump(),
            "execution_hints": suite.executionHints.model_dump(),
        }

    @staticmethod
    def _active_run_plan_version(plan: ValidationRunPlanEntity) -> Any:
        active_version_id = str(plan.currentActiveVersionId or "").strip()
        if not active_version_id:
            return None
        return next(
            (version for version in plan.versions if str(version.runPlanVersionId or "").strip() == active_version_id),
            None,
        )

    @staticmethod
    def _run_plan_version_engine_type(
        active_version: Any,
        artifact_lookup: Mapping[tuple[str, int], ValidationArtifactEnvelopeEntity],
    ) -> str | None:
        snapshot = getattr(active_version, "artifactSnapshot", None)
        if isinstance(snapshot, Mapping):
            engine_type = DeliveryLinkedExecutionRequestResolver._artifact_engine_type(snapshot)
            if engine_type:
                return engine_type
            envelopes = snapshot.get("artifactEnvelopes") if isinstance(snapshot.get("artifactEnvelopes"), list) else []
            engine_types = {
                engine_type
                for engine_type in (
                    DeliveryLinkedExecutionRequestResolver._artifact_engine_type(item)
                    for item in envelopes
                    if isinstance(item, Mapping)
                )
                if engine_type
            }
            if len(engine_types) == 1:
                return next(iter(engine_types))

        artifact_id = str(getattr(active_version, "artifactId", None) or "").strip()
        artifact_version = getattr(active_version, "artifactVersion", None)
        if not artifact_id or artifact_version in (None, ""):
            return None

        try:
            normalized_version = int(artifact_version)
        except (TypeError, ValueError):
            return None

        artifact = artifact_lookup.get((artifact_id, normalized_version))
        return DeliveryLinkedExecutionRequestResolver._artifact_engine_type(artifact)

    @staticmethod
    def _run_plan_candidate_payload(
        plan: ValidationRunPlanEntity,
        active_version: Any,
        artifact_lookup: Mapping[tuple[str, int], ValidationArtifactEnvelopeEntity],
    ) -> dict[str, Any]:
        scope_selector = getattr(plan, "scopeSelector", None)
        if isinstance(scope_selector, Mapping):
            serialized_scope_selector = dict(scope_selector)
        elif hasattr(scope_selector, "model_dump"):
            serialized_scope_selector = scope_selector.model_dump(by_alias=True, exclude_none=True)
        else:
            serialized_scope_selector = {}

        return {
            "run_plan_id": plan.runPlanId,
            "workspace_id": plan.workspaceId,
            "planning_mode": plan.planningMode,
            "status": plan.status,
            "scope_selector": serialized_scope_selector,
            "current_active_version_id": plan.currentActiveVersionId,
            "active_version": {
                "run_plan_version_id": DeliveryLinkedExecutionRequestResolver._row_value(active_version, "runPlanVersionId"),
                "governance_state": DeliveryLinkedExecutionRequestResolver._row_value(active_version, "governanceState"),
                "engine_type": DeliveryLinkedExecutionRequestResolver._run_plan_version_engine_type(active_version, artifact_lookup),
                "suite_id": DeliveryLinkedExecutionRequestResolver._row_value(active_version, "artifactId"),
                "suite_version": DeliveryLinkedExecutionRequestResolver._row_value(active_version, "artifactVersion"),
            },
        }

    @staticmethod
    def _grouped_run_plan_engine_supported(candidate_payload: Mapping[str, Any]) -> bool:
        active_version = candidate_payload.get("active_version") if isinstance(candidate_payload, Mapping) else {}
        if not isinstance(active_version, Mapping):
            return False
        engine_type = str(active_version.get("engine_type") or "").strip().lower()
        return engine_type == "gx"

    async def _resolve_applicable_gx_suites(
        self,
        *,
        data_object_version_id: str,
    ) -> list[ValidationArtifactEnvelopeEntity]:
        rows = await self._validation_artifact_repository.list_artifacts(
            data_object_version_id=data_object_version_id,
            status="active",
            latest_only=False,
        )

        suites: list[ValidationArtifactEnvelopeEntity] = []
        for row in rows:
            try:
                suite = self._coerce_artifact(row)
            except ValidationError as exc:
                raise self._error(
                    "GX suite envelope is invalid",
                    reason="invalid_gx_suite_envelope",
                ) from exc

            if self._artifact_engine_type(suite) != "gx":
                continue
            if data_object_version_id not in self._suite_target_ids(suite):
                continue
            suites.append(suite)

        suites.sort(key=lambda item: (str(item.validationArtifactId or ""), int(item.validationArtifactVersion)))
        if not suites:
            raise self._error(
                f"No active GX suites are applicable to dataObjectVersionId '{data_object_version_id}'",
                reason="no_executable_gx_suites",
                status_code=404,
            )
        return suites

    async def _resolve_applicable_run_plans(
        self,
        *,
        data_object_version_id: str,
        applicable_suites: list[ValidationArtifactEnvelopeEntity],
    ) -> list[dict[str, Any]]:
        rows = await self._validation_run_plan_repository.list_plans(status="active")
        suite_refs = {
            (suite.validationArtifactId, suite.validationArtifactVersion)
            for suite in applicable_suites
        }
        artifact_lookup = {
            (suite.validationArtifactId, suite.validationArtifactVersion): suite
            for suite in applicable_suites
        }
        plans: list[dict[str, Any]] = []

        for row in rows:
            try:
                plan = self._coerce_run_plan(row)
            except ValidationError as exc:
                raise self._error(
                    "GX run plan envelope is invalid",
                    reason="invalid_run_plan_envelope",
                ) from exc

            active_version = self._active_run_plan_version(plan)
            if active_version is None:
                continue
            if str(getattr(active_version, "governanceState", None) or "").strip() != "active":
                continue

            if plan.planningMode == "grouped_scope":
                if self._text(self._row_value(getattr(plan, "scopeSelector", None), "dataObjectVersionId")) != data_object_version_id:
                    continue
                candidate_payload = self._run_plan_candidate_payload(plan, active_version, artifact_lookup)
                if not self._grouped_run_plan_engine_supported(candidate_payload):
                    continue
            elif (active_version.artifactId, active_version.artifactVersion) not in suite_refs:
                continue

            plans.append(candidate_payload if plan.planningMode == "grouped_scope" else self._run_plan_candidate_payload(plan, active_version, artifact_lookup))

        plans.sort(
            key=lambda item: (
                str(item["run_plan_id"] or ""),
                str(item["current_active_version_id"] or ""),
            )
        )
        return plans

    @staticmethod
    def _select_suite_candidate(
        *,
        applicable_suites: list[ValidationArtifactEnvelopeEntity],
        suite_id: str,
        suite_version: int | None,
    ) -> ValidationArtifactEnvelopeEntity | None:
        matches = [suite for suite in applicable_suites if str(suite.validationArtifactId or "") == suite_id]
        if suite_version is not None:
            matches = [suite for suite in matches if int(suite.validationArtifactVersion) == suite_version]
        if not matches:
            return None
        return max(matches, key=lambda item: int(item.validationArtifactVersion))

    @staticmethod
    def _select_run_plan_candidate(
        *,
        applicable_run_plans: list[dict[str, Any]],
        run_plan_id: str,
        run_plan_version_id: str | None,
    ) -> dict[str, Any] | None:
        matches = [plan for plan in applicable_run_plans if str(plan.get("run_plan_id") or "") == run_plan_id]
        if run_plan_version_id is not None:
            matches = [
                plan
                for plan in matches
                if str(plan.get("active_version", {}).get("run_plan_version_id") or "") == run_plan_version_id
            ]
        if not matches:
            return None
        return matches[0]

    async def resolve_submission(
        self,
        *,
        data_delivery_id: str,
        execution_selector: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        delivery_id = self._text(data_delivery_id)
        if not delivery_id:
            raise self._error("data_delivery_id is required", reason="missing_data_delivery_id")

        note = self._catalog_repository.get_data_delivery_note(delivery_id)
        if note is None:
            raise self._error(
                f"Data delivery '{delivery_id}' not found",
                reason="data_delivery_not_found",
                status_code=404,
            )

        data_object_version_id = self._text(self._row_value(note, "data_object_version_id"))
        if not data_object_version_id:
            raise self._error(
                f"Data delivery '{delivery_id}' does not define data_object_version_id",
                reason="missing_data_object_version_id",
            )

        delivery_location = self._text(self._row_value(note, "delivery_location"))
        if not delivery_location:
            raise self._error(
                f"Data delivery '{delivery_id}' does not define delivery_location",
                reason="missing_delivery_location",
            )

        applicable_suites = await self._resolve_applicable_gx_suites(data_object_version_id=data_object_version_id)
        applicable_run_plans = await self._resolve_applicable_run_plans(
            data_object_version_id=data_object_version_id,
            applicable_suites=applicable_suites,
        )
        grouped_execution_plan = build_gx_grouped_execution_plan_entity(
            await GroupedExecutionPlanner().build_plan(applicable_suites)
        )

        selector_payload = dict(execution_selector or {})
        result: dict[str, Any] = {
            "data_delivery_id": delivery_id,
            "resolved_data_object_version_id": data_object_version_id,
            "resolved_delivery_location": delivery_location,
            "delivery_note": note.model_dump(),
            "execution_resolution": {
                "applicable_gx_suites": [self._suite_candidate_payload(suite) for suite in applicable_suites],
                "applicable_run_plans": list(applicable_run_plans),
                "grouped_execution_plan": (
                    grouped_execution_plan.model_dump(exclude_none=True)
                    if grouped_execution_plan is not None
                    else {}
                ),
            },
            "execution_selector": selector_payload or None,
            "resolved_gx_suite_id": None,
            "resolved_gx_suite_version": None,
            "resolved_run_plan_id": None,
            "resolved_run_plan_version_id": None,
            "resolved_engine_type": None,
            "execution_request_status": "accepted",
        }

        selector_type = self._text(selector_payload.get("selector_type"))
        if not selector_type:
            engine_types = {
                str(item.get("engine_type") or "").strip().lower()
                for item in result["execution_resolution"]["applicable_gx_suites"]
                if isinstance(item, Mapping) and str(item.get("engine_type") or "").strip()
            }
            if len(engine_types) == 1:
                result["resolved_engine_type"] = next(iter(engine_types))
            return result

        if selector_type == "gx_suite":
            suite_result = await self._resolve_gx_suite_selector(
                applicable_suites=applicable_suites,
                data_object_version_id=data_object_version_id,
                selector_payload=selector_payload,
            )
            result.update(suite_result)
            return result

        if selector_type == "run_plan":
            run_plan_result = await self._resolve_run_plan_selector(
                applicable_run_plans=applicable_run_plans,
                data_object_version_id=data_object_version_id,
                selector_payload=selector_payload,
            )
            result.update(run_plan_result)
            return result

        raise self._error(
            f"execution_selector.selector_type '{selector_type}' is not supported",
            reason="invalid_execution_selector_type",
        )

    async def _resolve_gx_suite_selector(
        self,
        *,
        applicable_suites: list[ValidationArtifactEnvelopeEntity],
        data_object_version_id: str,
        selector_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        suite_id = self._text(selector_payload.get("gx_suite_id"))
        if not suite_id:
            raise self._error(
                "gx_suite_id is required when selector_type is gx_suite",
                reason="missing_gx_suite_id",
            )

        suite_version_raw = selector_payload.get("suite_version")
        suite_version = int(suite_version_raw) if suite_version_raw not in (None, "") else None
        suite = self._select_suite_candidate(
            applicable_suites=applicable_suites,
            suite_id=suite_id,
            suite_version=suite_version,
        )
        if suite is None:
            suite_row = await self._validation_artifact_repository.get_artifact_by_id(
                artifact_id=suite_id,
                artifact_version=suite_version,
                status="active",
            )
            if suite_row is None:
                raise self._error(
                    f"GX suite '{suite_id}' not found",
                    reason="gx_suite_not_found",
                    status_code=404,
                )
            raise self._error(
                f"GX suite '{suite_id}' is not applicable to dataObjectVersionId '{data_object_version_id}'",
                reason="gx_suite_not_applicable",
            )

        return {
            "resolved_gx_suite_id": suite.validationArtifactId,
            "resolved_gx_suite_version": suite.validationArtifactVersion,
            "resolved_engine_type": self._artifact_engine_type(suite),
        }

    async def _resolve_run_plan_selector(
        self,
        *,
        applicable_run_plans: list[dict[str, Any]],
        data_object_version_id: str,
        selector_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        run_plan_id = self._text(selector_payload.get("run_plan_id"))
        if not run_plan_id:
            raise self._error(
                "run_plan_id is required when selector_type is run_plan",
                reason="missing_run_plan_id",
            )

        requested_version_id = self._text(selector_payload.get("run_plan_version_id")) or None
        candidate = self._select_run_plan_candidate(
            applicable_run_plans=applicable_run_plans,
            run_plan_id=run_plan_id,
            run_plan_version_id=requested_version_id,
        )
        if candidate is not None:
            return {
                "resolved_gx_suite_id": candidate["active_version"]["suite_id"],
                "resolved_gx_suite_version": candidate["active_version"]["suite_version"],
                "resolved_run_plan_id": candidate["run_plan_id"],
                "resolved_run_plan_version_id": candidate["active_version"]["run_plan_version_id"],
                "resolved_engine_type": candidate["active_version"].get("engine_type"),
            }

        plan_row = await self._validation_run_plan_repository.get_plan(run_plan_id)
        if plan_row is None:
            raise self._error(
                f"GX run plan '{run_plan_id}' not found",
                reason="run_plan_not_found",
                status_code=404,
            )

        versions = self._row_value(plan_row, "versions") or []
        if not isinstance(versions, list):
            versions = []
        if requested_version_id is not None and not any(
            self._text(self._row_value(item, "runPlanVersionId")) == requested_version_id for item in versions
        ):
            raise self._error(
                f"GX run plan version '{requested_version_id}' not found for plan '{run_plan_id}'",
                reason="run_plan_version_not_found",
                status_code=404,
            )

        raise self._error(
            f"GX run plan '{run_plan_id}' is not applicable to dataObjectVersionId '{data_object_version_id}'",
            reason="run_plan_not_applicable",
        )
