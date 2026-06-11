from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any
from time import perf_counter

from pydantic import ValidationError

from app.application.services.execution_engine_capabilities import ExecutionEngineCapabilityError
from app.application.services.execution_engine_capabilities import get_execution_engine_capability
from app.core.otel_metrics import record_execution_planner_choice
from app.core.otel_metrics import record_execution_runtime_cost
from app.domain.entities import GxArtifactEnvelopeEntity
from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.domain.entities import build_gx_artifact_envelope_from_validation_artifact


class GroupedExecutionPlanError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class GroupedExecutionPlanner:
    async def build_plan(
        self,
        suites: Sequence[ValidationArtifactEnvelopeEntity | GxArtifactEnvelopeEntity | Mapping[str, Any] | object],
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._build_plan_sync, suites)

    def _build_plan_sync(
        self,
        suites: Sequence[ValidationArtifactEnvelopeEntity | GxArtifactEnvelopeEntity | Mapping[str, Any] | object],
    ) -> dict[str, Any]:
        started_at = perf_counter()
        normalized_suites = [self._coerce_suite(item) for item in suites]
        if not normalized_suites:
            record_execution_planner_choice(
                planner="grouped_execution",
                choice="empty",
                execution_path="empty_plan",
                batch_count=0,
                suite_count=0,
            )
            record_execution_runtime_cost(
                executor="grouped_execution_planner",
                execution_path="empty_plan",
                planner_choice="empty",
                runtime_ms=(perf_counter() - started_at) * 1000.0,
                batch_count=0,
                suite_count=0,
            )
            return {"suiteCount": 0, "batchCount": 0, "batches": []}

        grouped_batches: dict[str, dict[str, Any]] = {}
        suite_count = 0
        for suite, suite_payload in normalized_suites:
            target_ids = self._extract_target_ids(suite)
            incremental_selection = self._extract_incremental_selection(suite)
            if incremental_selection is not None:
                selected_ids = incremental_selection["selectedDataObjectVersionIds"]
                missing_selected_ids = [target_id for target_id in selected_ids if target_id not in target_ids]
                if missing_selected_ids:
                    raise GroupedExecutionPlanError(
                        f"GROUPED_EXECUTION suite '{suite.suiteId}' declares incremental selection outside its resolved execution scope"
                    )
                target_ids = [target_id for target_id in target_ids if target_id in selected_ids]
                if not target_ids:
                    raise GroupedExecutionPlanError(
                        f"GROUPED_EXECUTION suite '{suite.suiteId}' declares incremental selection without matching targets"
                    )
            normalized_suite_payload = self._with_target_ids(suite_payload, target_ids)
            suite_count += 1
            suite_entry = {
                "suiteId": str(suite.suiteId or "").strip(),
                "suiteVersion": int(suite.suiteVersion),
                "resolvedExecutionScope": {"dataObjectVersionIds": list(target_ids)},
                "suiteEnvelope": normalized_suite_payload,
            }
            for target_id in target_ids:
                batch_payload = grouped_batches.setdefault(
                    target_id,
                    {
                        "dataObjectVersionId": target_id,
                        "incrementalSelection": incremental_selection,
                        "suiteEntries": [],
                        "supportsSqlPushdown": self._suite_supports_sql_pushdown(suite),
                    },
                )
                if batch_payload["incrementalSelection"] != incremental_selection:
                    raise GroupedExecutionPlanError(
                        f"GROUPED_EXECUTION suite '{suite.suiteId}' declares a conflicting incremental selection for target '{target_id}'"
                    )
                if batch_payload["supportsSqlPushdown"]:
                    batch_payload["supportsSqlPushdown"] = self._suite_supports_sql_pushdown(suite)
                batch_payload["suiteEntries"].append(suite_entry)

        batches = []
        for target_id in sorted(grouped_batches):
            batch_payload = grouped_batches[target_id]
            suites_for_target = batch_payload["suiteEntries"]
            suites_for_target.sort(key=lambda item: (item["suiteId"], item["suiteVersion"]))
            batch_execution_path = "sql_pushdown_grouped_execution" if batch_payload["supportsSqlPushdown"] and batch_payload["incrementalSelection"] is None else (
                "incremental_grouped_execution" if batch_payload["incrementalSelection"] is not None else "grouped_execution"
            )
            batches.append(
                {
                    "dataObjectVersionId": batch_payload["dataObjectVersionId"],
                    "incrementalSelection": batch_payload["incrementalSelection"],
                    "suiteCount": len(suites_for_target),
                    "suiteIds": [item["suiteId"] for item in suites_for_target],
                    "suites": [item["suiteEnvelope"] for item in suites_for_target],
                    "plannerChoice": "incremental_scope" if batch_payload["incrementalSelection"] is not None else "full_scope",
                    "executionPath": batch_execution_path,
                }
            )

        incremental_batch_count = sum(1 for batch in batches if batch.get("incrementalSelection") is not None)
        execution_paths = {batch["executionPath"] for batch in batches if isinstance(batch.get("executionPath"), str) and batch.get("executionPath")}
        if len(execution_paths) > 1:
            aggregate_execution_path = "mixed_grouped_execution"
        else:
            aggregate_execution_path = next(iter(execution_paths), "grouped_execution")

        if incremental_batch_count == 0:
            planner_choice = "full_scope"
        elif incremental_batch_count == len(batches):
            planner_choice = "incremental_scope"
        else:
            planner_choice = "mixed_scope"

        record_execution_planner_choice(
            planner="grouped_execution",
            choice=planner_choice,
            execution_path=aggregate_execution_path,
            batch_count=len(batches),
            suite_count=suite_count,
            execution_shape="grouped_scope",
        )
        record_execution_runtime_cost(
            executor="grouped_execution_planner",
            execution_path=aggregate_execution_path,
            planner_choice=planner_choice,
            runtime_ms=(perf_counter() - started_at) * 1000.0,
            batch_count=len(batches),
            suite_count=suite_count,
            execution_shape="grouped_scope",
        )

        execution_paths = {batch["executionPath"] for batch in batches if isinstance(batch.get("executionPath"), str) and batch.get("executionPath")}
        return {
            "suiteCount": suite_count,
            "batchCount": len(batches),
            "executionPath": next(iter(execution_paths)) if len(execution_paths) == 1 else "mixed_grouped_execution",
            "plannerChoice": planner_choice,
            "batches": batches,
        }

    def _coerce_suite(
        self,
        suite: ValidationArtifactEnvelopeEntity | GxArtifactEnvelopeEntity | Mapping[str, Any] | object,
    ) -> tuple[GxArtifactEnvelopeEntity, dict[str, Any]]:
        if isinstance(suite, GxArtifactEnvelopeEntity):
            return suite, suite.model_dump(mode="python", by_alias=False, exclude_none=False)

        if isinstance(suite, ValidationArtifactEnvelopeEntity):
            try:
                return (
                    build_gx_artifact_envelope_from_validation_artifact(suite),
                    suite.model_dump(mode="python", by_alias=False, exclude_none=False),
                )
            except ValueError as exc:
                raise GroupedExecutionPlanError("GROUPED_EXECUTION suite envelope is invalid") from exc

        if hasattr(suite, "model_dump"):
            suite = getattr(suite, "model_dump")(by_alias=False, exclude_none=False)

        if isinstance(suite, Mapping) and (
            suite.get("validationArtifactId") is not None or suite.get("validation_artifact_id") is not None
        ):
            try:
                return build_gx_artifact_envelope_from_validation_artifact(suite), dict(suite)
            except ValueError as exc:
                raise GroupedExecutionPlanError("GROUPED_EXECUTION suite envelope is invalid") from exc

        try:
            normalized_suite = GxArtifactEnvelopeEntity.model_validate(dict(suite))
            return normalized_suite, normalized_suite.model_dump(mode="python", by_alias=False, exclude_none=False)
        except ValidationError as exc:
            if self._has_empty_target_list_error(exc.errors()):
                raise GroupedExecutionPlanError(
                    "GROUPED_EXECUTION suite does not define any dataObjectVersionId targets"
                ) from exc
            raise GroupedExecutionPlanError("GROUPED_EXECUTION suite envelope is invalid") from exc

    @staticmethod
    def _suite_engine_type(suite: GxArtifactEnvelopeEntity) -> str | None:
        if suite.executionContract is not None and str(suite.executionContract.engineType or "").strip():
            return str(suite.executionContract.engineType or "").strip().lower()
        if suite.executionHints is not None and str(suite.executionHints.recommendedEngine or "").strip():
            return str(suite.executionHints.recommendedEngine or "").strip().lower()
        if suite.executionContract is not None and str(suite.executionContract.engineTarget or "").strip():
            return str(suite.executionContract.engineTarget or "").strip().lower()
        return None

    @staticmethod
    def _suite_has_sql_pushdown_hint(suite: GxArtifactEnvelopeEntity) -> bool:
        evidence = getattr(suite.executionHints, "evidence", None)
        if evidence is None:
            return False
        return bool(getattr(evidence, "emitGeneratedSql", False))

    def _suite_supports_sql_pushdown(self, suite: GxArtifactEnvelopeEntity) -> bool:
        engine_type = self._suite_engine_type(suite)
        if engine_type is None:
            return False
        try:
            capability = get_execution_engine_capability(engine_type)
        except ExecutionEngineCapabilityError:
            return False
        return bool(capability.sql_pushdown_supported and self._suite_has_sql_pushdown_hint(suite))

    def _extract_incremental_selection(self, suite: GxArtifactEnvelopeEntity) -> dict[str, Any] | None:
        execution_hints = getattr(suite, "executionHints", None)
        if execution_hints is None:
            return None

        incremental_selection = getattr(execution_hints, "incrementalSelection", None)
        if incremental_selection is None:
            return None

        if hasattr(incremental_selection, "model_dump"):
            normalized_selection = incremental_selection.model_dump(mode="python", by_alias=False, exclude_none=True)
        elif isinstance(incremental_selection, Mapping):
            normalized_selection = dict(incremental_selection)
        else:
            raise GroupedExecutionPlanError(
                f"GROUPED_EXECUTION suite '{suite.suiteId}' declares an invalid incremental selection"
            )

        selection_mode = str(normalized_selection.get("selectionMode") or "").strip()
        if selection_mode not in {"new_partitions", "changed_slices"}:
            raise GroupedExecutionPlanError(
                f"GROUPED_EXECUTION suite '{suite.suiteId}' declares an unsupported incremental selection mode '{selection_mode}'"
            )

        selected_ids = [
            str(value).strip()
            for value in (normalized_selection.get("selectedDataObjectVersionIds") or [])
            if str(value).strip()
        ]
        if not selected_ids:
            raise GroupedExecutionPlanError(
                f"GROUPED_EXECUTION suite '{suite.suiteId}' declares incremental selection without selectedDataObjectVersionIds"
            )

        return {
            "selectionMode": selection_mode,
            "selectedDataObjectVersionIds": selected_ids,
        }

    @staticmethod
    def _with_target_ids(payload: dict[str, Any], target_ids: list[str]) -> dict[str, Any]:
        normalized_payload = dict(payload)
        resolved_scope = normalized_payload.get("resolvedExecutionScope")
        if isinstance(resolved_scope, Mapping):
            normalized_payload["resolvedExecutionScope"] = {
                **dict(resolved_scope),
                "dataObjectVersionIds": list(target_ids),
            }
        else:
            normalized_payload["resolvedExecutionScope"] = {"dataObjectVersionIds": list(target_ids)}
        return normalized_payload

    def _extract_target_ids(self, suite: GxArtifactEnvelopeEntity) -> list[str]:
        resolved_scope = suite.resolvedExecutionScope
        raw_target_ids = list(resolved_scope.dataObjectVersionIds or [])
        if not raw_target_ids:
            raise GroupedExecutionPlanError(
                "GROUPED_EXECUTION suite does not define any dataObjectVersionId targets"
            )
        target_ids = [
            str(target_id or "").strip()
            for target_id in raw_target_ids
            if str(target_id or "").strip()
        ]
        if not target_ids:
            raise GroupedExecutionPlanError(
                f"GROUPED_EXECUTION suite '{suite.suiteId}' does not define any dataObjectVersionId targets"
            )
        return list(dict.fromkeys(target_ids))

    @staticmethod
    def _has_empty_target_list_error(errors: list[dict[str, Any]]) -> bool:
        for error in errors:
            loc = error.get("loc")
            if isinstance(loc, tuple) and "resolvedExecutionScope" in loc and "dataObjectVersionIds" in loc:
                return True
        return False