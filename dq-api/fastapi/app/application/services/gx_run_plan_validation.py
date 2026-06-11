from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.services.gx_suite_validation import assert_gx_suite_runnable
from app.application.services.gx_suite_validation import GxSuiteValidationError
from app.domain.entities.gx_execution_run import GxExecutionContractEntity
from app.domain.entities.gx_run_plan import build_gx_run_plan_suite_selection_entity
from app.domain.entities.gx_suite import build_gx_artifact_envelope_entity
from app.domain.entities.gx_suite import GxArtifactEnvelopeEntity
from app.domain.entities.gx_run_plan import build_gx_run_plan_version_validation_snapshot_entity
from app.domain.entities.gx_run_plan import GxRunPlanGroupedSuiteSnapshotEntity
from app.domain.entities.gx_run_plan import GxRunPlanSingleSuiteSnapshotEntity
from app.domain.entities.gx_run_plan import GxRunPlanValidationDiagnosticEntity
from app.domain.entities.gx_run_plan import GxRunPlanVersionEntity


ALLOWED_EXECUTION_SHAPES = {"single_object", "join_pair", "streaming", "micro_batch"}


@dataclass(slots=True)
class GxRunPlanActivationSnapshotError(Exception):
    code: str
    message: str
    details: Any | None = None

    def __str__(self) -> str:
        return self.message



def _diagnostic(
    *,
    code: str,
    message: str,
    scope: str,
    details: Any | None = None,
) -> GxRunPlanValidationDiagnosticEntity:
    return GxRunPlanValidationDiagnosticEntity(
        scope=scope,
        severity="error",
        code=code,
        message=message,
        details=details,
    )



def _validate_execution_contract_snapshot(
    execution_contract_snapshot: GxExecutionContractEntity,
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    engine_target = str(execution_contract_snapshot.engineTarget or "").strip()
    if not engine_target:
        violations.append({"field": "engine_target", "message": "engine_target is required"})

    execution_shape = str(execution_contract_snapshot.executionShape or "").strip()
    if not execution_shape:
        violations.append({"field": "execution_shape", "message": "execution_shape is required"})
    elif execution_shape not in ALLOWED_EXECUTION_SHAPES:
        violations.append({"field": "execution_shape", "message": f"unsupported execution_shape '{execution_shape}'"})

    traceability = execution_contract_snapshot.traceability
    if traceability is None:
        violations.append({"field": "traceability", "message": "traceability is required"})
    else:
        if not str(traceability.ruleId or "").strip():
            violations.append({"field": "traceability.rule_id", "message": "rule_id is required"})
        if not str(traceability.ruleVersionId or "").strip():
            violations.append({"field": "traceability.rule_version_id", "message": "rule_version_id is required"})
        if not str(traceability.gxSuiteId or "").strip():
            violations.append({"field": "traceability.gx_suite_id", "message": "gx_suite_id is required"})
        if traceability.gxSuiteVersion is None or int(traceability.gxSuiteVersion) < 1:
            violations.append({"field": "traceability.gx_suite_version", "message": "gx_suite_version must be >= 1"})

    source_materialization = execution_contract_snapshot.sourceMaterialization
    if execution_shape == "single_object" and source_materialization is not None:
        violations.append(
            {"field": "source_materialization", "message": "single_object execution must not define source_materialization"}
        )
    if execution_shape == "join_pair" and source_materialization is None:
        violations.append(
            {"field": "source_materialization", "message": "join_pair execution requires source_materialization"}
        )

    return violations


def _normalized_engine_type(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _single_suite_selection_engine_type(version_row: GxRunPlanVersionEntity) -> str | None:
    suite_selection = build_gx_run_plan_suite_selection_entity(version_row.gxSuiteSelection)
    suite_id = str(version_row.suiteId or "").strip()
    suite_version = version_row.suiteVersion

    matching_suite_refs = [
        item
        for item in suite_selection.suiteRefs
        if str(item.suiteId or "").strip() == suite_id and item.suiteVersion == suite_version
    ]
    if len(matching_suite_refs) == 1:
        return _normalized_engine_type(matching_suite_refs[0].engineType)

    if len(suite_selection.suiteRefs) == 1:
        return _normalized_engine_type(suite_selection.suiteRefs[0].engineType)

    return None


def _resolved_single_suite_engine_type(
    *,
    version_row: GxRunPlanVersionEntity,
    snapshot: GxRunPlanSingleSuiteSnapshotEntity,
    execution_contract_snapshot: GxExecutionContractEntity | None,
) -> str | None:
    execution_contract = snapshot.executionContract
    if execution_contract is not None:
        engine_type = _normalized_engine_type(execution_contract.engineType)
        if engine_type:
            return engine_type

    if execution_contract_snapshot is not None:
        engine_type = _normalized_engine_type(execution_contract_snapshot.engineType)
        if engine_type:
            return engine_type

    return _single_suite_selection_engine_type(version_row)


def _with_single_suite_engine_type(
    snapshot: GxRunPlanSingleSuiteSnapshotEntity,
    engine_type: str | None,
) -> GxRunPlanSingleSuiteSnapshotEntity:
    if engine_type is None or snapshot.executionContract is None:
        return snapshot
    if _normalized_engine_type(snapshot.executionContract.engineType) is not None:
        return snapshot
    return snapshot.model_copy(
        update={
            "executionContract": snapshot.executionContract.model_copy(update={"engineType": engine_type})
        }
    )



def _single_suite_snapshot_structure_errors(snapshot: GxRunPlanSingleSuiteSnapshotEntity) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if not str(snapshot.suiteId or "").strip():
        errors.append({"field": "suite_id", "message": "suite_id is required"})
    if snapshot.suiteVersion is None or int(snapshot.suiteVersion) < 1:
        errors.append({"field": "suite_version", "message": "suite_version must be >= 1"})
    if not str(snapshot.artifactVersion or "").strip():
        errors.append({"field": "artifact_version", "message": "artifact_version is required"})

    assignment_scope = snapshot.assignmentScope or {}
    if not any(str(assignment_scope.get(key) or "").strip() for key in ("dataObjectId", "datasetId", "dataProductId")):
        errors.append(
            {
                "field": "assignment_scope",
                "message": "At least one assignment scope identifier is required: dataObjectId, datasetId, or dataProductId",
            }
        )

    resolved_scope = snapshot.resolvedExecutionScope or {}
    target_ids = [str(value or "").strip() for value in resolved_scope.get("dataObjectVersionIds", []) if str(value or "").strip()]
    if not target_ids:
        errors.append({"field": "resolved_execution_scope.data_object_version_ids", "message": "at least one target is required"})

    compiled_from = snapshot.compiledFrom or {}
    if not str(compiled_from.get("compilerVersion") or "").strip():
        errors.append({"field": "compiled_from.compiler_version", "message": "compiler_version is required"})
    if not str(compiled_from.get("generatedAt") or "").strip():
        errors.append({"field": "compiled_from.generated_at", "message": "generated_at is required"})

    execution_hints = snapshot.executionHints or {}
    if not str(execution_hints.get("recommendedEngine") or "").strip():
        errors.append({"field": "execution_hints.recommended_engine", "message": "recommended_engine is required"})

    return errors



def validate_gx_run_plan_version_snapshot(
    version_row: GxRunPlanVersionEntity,
) -> list[GxRunPlanValidationDiagnosticEntity]:
    diagnostics: list[GxRunPlanValidationDiagnosticEntity] = []
    validation_snapshot = build_gx_run_plan_version_validation_snapshot_entity(version_row)

    scheduled_at = str(validation_snapshot.scheduledAt or "").strip()
    if not scheduled_at:
        diagnostics.append(
            _diagnostic(
                code="missing_schedule_definition",
                message="GX run plan version is missing scheduled_at",
                scope="schedule_definition",
            )
        )

    selection_mode = str(validation_snapshot.selectionMode or "").strip()
    execution_contract_snapshot = validation_snapshot.executionContractSnapshot
    if execution_contract_snapshot is None:
        diagnostics.append(
            _diagnostic(
                code="missing_execution_contract_snapshot",
                message="GX run plan version is missing the execution contract snapshot required for validation",
                scope="execution_contract_snapshot",
            )
        )
    elif selection_mode != "grouped_scope":
        violations = _validate_execution_contract_snapshot(execution_contract_snapshot)
        if violations:
            diagnostics.append(
                _diagnostic(
                    code="invalid_execution_contract_snapshot",
                    message="GX run plan version contains an invalid execution contract snapshot required for validation",
                    scope="execution_contract_snapshot",
                    details=violations,
                )
            )

    if selection_mode == "grouped_scope":
        grouped_snapshot = validation_snapshot.suiteSnapshot
        if grouped_snapshot is None or not isinstance(grouped_snapshot, GxRunPlanGroupedSuiteSnapshotEntity):
            diagnostics.append(
                _diagnostic(
                    code="missing_grouped_suite_snapshot",
                    message="GX run plan version is missing the grouped suite snapshot required for validation",
                    scope="suite_snapshot",
                )
            )
            return diagnostics

        if validation_snapshot.groupedExecutionPlan is None:
            diagnostics.append(
                _diagnostic(
                    code="missing_grouped_execution_plan",
                    message="GX run plan version is missing the grouped execution plan required for validation",
                    scope="suite_snapshot",
                )
            )

        suite_envelopes = validation_snapshot.groupedSuiteEnvelopes
        if not suite_envelopes:
            diagnostics.append(
                _diagnostic(
                    code="missing_grouped_suite_envelopes",
                    message="GX run plan version is missing grouped suite envelopes required for validation",
                    scope="suite_snapshot",
                )
            )
            return diagnostics

        for index, suite in enumerate(suite_envelopes):
            structure_errors = _single_suite_snapshot_structure_errors(suite)
            if structure_errors:
                diagnostics.append(
                    _diagnostic(
                        code="invalid_grouped_suite_snapshot",
                        message=f"Grouped suite snapshot at index {index} is invalid",
                        scope="suite_snapshot",
                        details=structure_errors,
                    )
                )
                continue
            try:
                assert_gx_suite_runnable(suite)
            except GxSuiteValidationError as exc:
                diagnostics.append(
                    _diagnostic(
                        code=exc.reason or "invalid_grouped_suite_snapshot",
                        message=exc.message or f"Grouped suite snapshot at index {index} is invalid",
                        scope="suite_snapshot",
                        details={
                            "error": "gx_suite_not_runnable",
                            "reason": exc.reason,
                            "message": exc.message,
                            "suite_id": exc.suite_id,
                            "suite_version": exc.suite_version,
                        },
                    )
                )
        return diagnostics

    single_suite_snapshot = validation_snapshot.suiteSnapshot
    if single_suite_snapshot is None or not isinstance(single_suite_snapshot, GxRunPlanSingleSuiteSnapshotEntity):
        diagnostics.append(
            _diagnostic(
                code="missing_suite_snapshot",
                message="GX run plan version is missing the suite snapshot required for validation",
                scope="suite_snapshot",
            )
        )
        return diagnostics

    structure_errors = _single_suite_snapshot_structure_errors(single_suite_snapshot)
    if structure_errors:
        diagnostics.append(
            _diagnostic(
                code="invalid_suite_snapshot",
                message="GX run plan version contains an invalid suite snapshot required for validation",
                scope="suite_snapshot",
                details=structure_errors,
            )
        )
        return diagnostics

    try:
        assert_gx_suite_runnable(single_suite_snapshot)
    except GxSuiteValidationError as exc:
        diagnostics.append(
            _diagnostic(
                code=exc.reason or "invalid_suite_snapshot",
                message=exc.message or "GX run plan version contains an invalid suite snapshot required for validation",
                scope="suite_snapshot",
                details={
                    "error": "gx_suite_not_runnable",
                    "reason": exc.reason,
                    "message": exc.message,
                    "suite_id": exc.suite_id,
                    "suite_version": exc.suite_version,
                },
            )
        )

    return diagnostics


def resolve_single_suite_activation_snapshot(
    version_row: GxRunPlanVersionEntity,
) -> GxArtifactEnvelopeEntity:
    validation_snapshot = build_gx_run_plan_version_validation_snapshot_entity(version_row)
    single_suite_snapshot = validation_snapshot.suiteSnapshot
    if single_suite_snapshot is None or not isinstance(single_suite_snapshot, GxRunPlanSingleSuiteSnapshotEntity):
        raise GxRunPlanActivationSnapshotError(
            code="missing_suite_snapshot",
            message="GX run plan version is missing the suite snapshot required for activation",
        )

    structure_errors = _single_suite_snapshot_structure_errors(single_suite_snapshot)
    if structure_errors:
        raise GxRunPlanActivationSnapshotError(
            code="invalid_suite_snapshot",
            message="GX run plan version contains an invalid suite snapshot required for activation",
            details=structure_errors,
        )

    single_suite_snapshot = _with_single_suite_engine_type(
        single_suite_snapshot,
        _resolved_single_suite_engine_type(
            version_row=version_row,
            snapshot=single_suite_snapshot,
            execution_contract_snapshot=validation_snapshot.executionContractSnapshot,
        ),
    )

    try:
        assert_gx_suite_runnable(single_suite_snapshot)
    except GxSuiteValidationError as exc:
        raise GxRunPlanActivationSnapshotError(
            code=exc.reason or "invalid_suite_snapshot",
            message=exc.message or "GX run plan version contains an invalid suite snapshot required for activation",
            details={
                "error": "gx_suite_not_runnable",
                "reason": exc.reason,
                "message": exc.message,
                "suite_id": exc.suite_id,
                "suite_version": exc.suite_version,
            },
        ) from exc

    return build_gx_artifact_envelope_entity(single_suite_snapshot.model_dump(exclude_none=True))
