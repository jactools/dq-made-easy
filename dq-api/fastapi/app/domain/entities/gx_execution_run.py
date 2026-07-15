from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field

from app.domain.entities.base import EntityModel
from app.schemas.pydantic_base import to_snake_alias


class GxExecutionRunStatusHistoryEntity(EntityModel):
    id: str
    runId: str
    fromStatus: str | None = None
    toStatus: str
    changedBy: str | None = None
    changedAt: str
    reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class GxExecutionProgressEntity(EntityModel):
    percent: int
    label: str | None = None
    completedSteps: int | None = None
    totalSteps: int | None = None
    source: str | None = None
    updatedAt: str | None = None


class GxExecutionTraceabilityEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    ruleId: str | None = None
    ruleVersionId: str | None = None
    gxSuiteId: str | None = None
    gxSuiteVersion: int | None = None
    dataObjectVersionId: str | None = None
    sourceRuleExpression: str | None = None
    compiledExpression: str | None = None
    artifactKey: str | None = None


class GxExecutionIncrementalSelectionEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    selectionMode: str | None = None
    selectedDataObjectVersionIds: list[str] = Field(default_factory=list)


class GxExecutionSourceTargetEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    dataObjectId: str | None = None
    dataObjectVersionId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = None


class GxExecutionSourceMaterializationEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    landingZoneArtifactId: str | None = None
    landingZoneVersionId: str | None = None
    outputLocation: str | None = None
    joinType: str | None = None
    joinKeys: list[str] = Field(default_factory=list)
    joinKeyPairs: list[dict[str, Any]] = Field(default_factory=list)
    leftSource: GxExecutionSourceTargetEntity | None = None
    rightSource: GxExecutionSourceTargetEntity | None = None


class GxExecutionContractEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    engineType: str | None = None
    engineTarget: str | None = None
    executionShape: str | None = None
    traceability: GxExecutionTraceabilityEntity | None = None
    sourceMaterialization: GxExecutionSourceMaterializationEntity | None = None
    resolvedDataObjectVersionId: str | None = Field(default=None, alias="resolved_data_object_version_id")
    resolvedDataDeliveryId: str | None = Field(default=None, alias="resolved_data_delivery_id")
    resolvedDeliveryLocation: str | None = Field(default=None, alias="resolved_delivery_location")
    deliveryResolutionMode: str | None = Field(default=None, alias="delivery_resolution_mode")
    selectionMode: str | None = Field(default=None, alias="selection_mode")
    scopeSelector: dict[str, Any] = Field(default_factory=dict, alias="scope_selector")
    suiteRefs: list[dict[str, Any]] = Field(default_factory=list, alias="suite_refs")
    suiteCount: int | None = Field(default=None, alias="suite_count")
    batchCount: int | None = Field(default=None, alias="batch_count")


class GxGroupedExecutionPlanEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    suiteCount: int | None = None
    batchCount: int | None = None


class GxExecutionDiagnosticEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    dataObjectVersionId: str | None = None
    dataPrimaryKey: str | None = None
    rowIdentifier: str | None = None
    reason: str | None = None
    expectationType: str | None = None
    message: str | None = None
    detectedAt: str | None = None


class GxExecutionResultItemEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    dataObjectVersionId: str | None = None
    ok: bool | None = None
    recordsFailed: Any = None
    failedCount: Any = None
    violationCount: Any = None


class GxExecutionResultSummaryEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    results: list[Any] = Field(default_factory=list)
    recordsFailed: Any = None
    failedCount: Any = None
    violationCount: Any = None


class GxStructuredErrorDetailEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    reason: str | None = None
    error: str | None = None
    message: str | None = None
    correlationId: str | None = None
    queueMessageId: str | None = None


class GxExecutionDeliverySnapshotEntity(EntityModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    engineType: str | None = Field(default=None, alias="engine_type")
    resolvedDataObjectVersionId: str | None = Field(default=None, alias="resolved_data_object_version_id")
    resolvedDataDeliveryId: str | None = Field(default=None, alias="resolved_data_delivery_id")
    resolvedDeliveryLocation: str | None = Field(default=None, alias="resolved_delivery_location")
    deliveryResolutionMode: str | None = Field(default=None, alias="delivery_resolution_mode")


class GxDispatchSourceOverrideEntity(EntityModel):
    model_config = ConfigDict(extra="allow")

    uri: str | None = None
    format: str | None = None


class GxDispatchPayloadEntity(EntityModel):
    model_config = ConfigDict(extra="allow")

    runId: str | None = Field(default=None, alias="run_id")
    queueMessageId: str | None = Field(default=None, alias="queue_message_id")
    suiteId: str | None = Field(default=None, alias="suite_id")
    suiteVersion: int | None = Field(default=None, alias="suite_version")
    correlationId: str | None = Field(default=None, alias="correlation_id")
    requestedBy: str | None = Field(default=None, alias="requested_by")
    engineType: str | None = Field(default=None, alias="engine_type")
    engineTarget: str | None = Field(default=None, alias="engine_target")
    executionShape: str | None = Field(default=None, alias="execution_shape")
    dispatchMode: str | None = Field(default=None, alias="dispatch_mode")
    executorTarget: str | None = Field(default=None, alias="executor_target")
    queueKey: str | None = Field(default=None, alias="queue_key")
    handoffStatus: str | None = Field(default=None, alias="handoff_status")
    handoffReady: bool | None = Field(default=None, alias="handoff_ready")
    submittedAt: str | None = Field(default=None, alias="submitted_at")
    scheduledAt: str | None = Field(default=None, alias="scheduled_at")
    selectionMode: str | None = Field(default=None, alias="selection_mode")
    executionScopeOverride: list[str] = Field(default_factory=list, alias="execution_scope_override")
    executionContract: GxExecutionContractEntity | None = Field(default=None, alias="execution_contract")
    groupedExecutionPlan: GxGroupedExecutionPlanEntity | None = Field(default=None, alias="grouped_execution_plan")
    scopeSelector: dict[str, Any] = Field(default_factory=dict, alias="scope_selector")
    suiteRefs: list[dict[str, Any]] = Field(default_factory=list, alias="suite_refs")
    headers: dict[str, Any] = Field(default_factory=dict)
    materializationJobType: str | None = Field(default=None, alias="materialization_job_type")
    nextDispatchPayload: GxDispatchPayloadEntity | None = Field(default=None, alias="next_dispatch_payload")
    sourceOverridesByDataObjectVersionId: dict[str, GxDispatchSourceOverrideEntity] = Field(
        default_factory=dict,
        alias="source_overrides_by_data_object_version_id",
    )
    deliverySnapshot: GxExecutionDeliverySnapshotEntity | None = Field(default=None, alias="delivery_snapshot")


def build_gx_execution_incremental_selection_entity(
    payload: Mapping[str, Any] | GxExecutionIncrementalSelectionEntity | None,
) -> GxExecutionIncrementalSelectionEntity | None:
    if isinstance(payload, GxExecutionIncrementalSelectionEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    selected_data_object_version_ids = payload.get("selectedDataObjectVersionIds")
    if selected_data_object_version_ids is None:
        selected_data_object_version_ids = payload.get("selected_data_object_version_ids")

    return GxExecutionIncrementalSelectionEntity(
        selectionMode=(
            str(payload.get("selectionMode") or payload.get("selection_mode"))
            if (payload.get("selectionMode") is not None or payload.get("selection_mode") is not None)
            else None
        ),
        selectedDataObjectVersionIds=[
            str(value).strip() for value in (selected_data_object_version_ids or []) if str(value).strip()
        ],
    )


class GxExecutionRunCreateEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    runId: str
    suiteId: str | None = None
    suiteVersion: int | None = None
    ruleId: str | None = None
    ruleVersionId: str | None = None
    correlationId: str
    requestedBy: str | None = None
    engineType: str | None = None
    engineTarget: str
    executionShape: str
    status: str
    submittedAt: str
    executionContract: GxExecutionContractEntity = Field(default_factory=GxExecutionContractEntity)
    handoffPayload: GxDispatchPayloadEntity | None = None
    executionProgress: dict[str, Any] | None = None
    startedAt: str | None = None
    completedAt: str | None = None
    resultSummary: GxExecutionResultSummaryEntity | None = None
    metrics: dict[str, Any] | None = None
    performanceSummary: dict[str, Any] | None = None
    diagnostics: list[GxExecutionDiagnosticEntity] = Field(default_factory=list)
    failureCode: str | None = None
    failureMessage: str | None = None
    comments: str | None = None
    statusReason: str | None = None
    statusDetails: dict[str, Any] = Field(default_factory=dict)


class GxExecutionRunStatusTransitionEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    runId: str
    newStatus: str
    changedBy: str | None = None
    reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    executionProgress: dict[str, Any] | None = None
    startedAt: str | None = None
    completedAt: str | None = None
    resultSummary: GxExecutionResultSummaryEntity | None = None
    metrics: dict[str, Any] | None = None
    performanceSummary: dict[str, Any] | None = None
    diagnostics: list[GxExecutionDiagnosticEntity] | None = None
    failureCode: str | None = None
    failureMessage: str | None = None


class GxExecutionRunListQueryEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    submittedAfter: datetime | None = None
    submittedBefore: datetime | None = None
    suiteId: str | None = None
    ruleId: str | None = None
    status: str | None = None
    dataProductId: str | None = None
    datasetId: str | None = None
    dataObjectId: str | None = None
    dataObjectVersionId: str | None = None
    deliveryId: str | None = None


class GxExecutionRunEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    suiteId: str | None = None
    suiteVersion: int | None = None
    ruleId: str | None = None
    ruleVersionId: str | None = None
    correlationId: str
    requestedBy: str | None = None
    engineType: str | None = None
    engineTarget: str
    executionShape: str
    status: str
    submittedAt: str
    startedAt: str | None = None
    completedAt: str | None = None
    createdAt: str
    updatedAt: str
    executionContract: GxExecutionContractEntity | None = None
    handoffPayload: GxDispatchPayloadEntity | None = None
    executionProgress: GxExecutionProgressEntity | None = None
    resultSummary: GxExecutionResultSummaryEntity | None = None
    metrics: dict[str, Any] | None = None
    performanceSummary: dict[str, Any] | None = None
    diagnostics: list[GxExecutionDiagnosticEntity] = Field(default_factory=list)
    failureCode: str | None = None
    failureMessage: str | None = None
    comments: str | None = None
    statusHistory: list[GxExecutionRunStatusHistoryEntity] = Field(default_factory=list)


class GxExecutionRunSummaryEntity(EntityModel):
    id: str
    suiteId: str | None = None
    suiteVersion: int | None = None
    ruleId: str | None = None
    ruleName: str | None = None
    owner: str | None = None
    domain: str | None = None
    severity: str | None = None
    runPlanId: str | None = None
    dataObjectVersionId: str | None = None
    dataObjectNames: list[str] = Field(default_factory=list)
    resolvedDataDeliveryId: str | None = None
    correlationId: str
    requestedBy: str | None = None
    engineType: str | None = None
    engineTarget: str
    executionShape: str
    status: str
    failedRecordCount: int = 0
    submittedAt: str
    startedAt: str | None = None
    completedAt: str | None = None
    createdAt: str
    updatedAt: str


class GxExecutionRunCountEntity(EntityModel):
    name: str
    count: int


class GxExecutionRunStatisticsEntity(EntityModel):
    lookbackAmount: int
    lookbackUnit: str
    recentLimit: int
    totalRuns: int
    pendingRuns: int
    runningRuns: int
    succeededRuns: int
    failedRuns: int
    cancelledRuns: int
    statusBreakdown: list[GxExecutionRunCountEntity] = Field(default_factory=list)
    engineTargetBreakdown: list[GxExecutionRunCountEntity] = Field(default_factory=list)
    executionShapeBreakdown: list[GxExecutionRunCountEntity] = Field(default_factory=list)
    recentRuns: list[GxExecutionRunSummaryEntity] = Field(default_factory=list)


def _mapping_value(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def _run_suite_id(payload: Mapping[str, Any]) -> Any:
    return _mapping_value(
        payload,
        "suiteId",
        "suite_id",
        "artifactId",
        "artifact_id",
        "validationArtifactId",
        "validation_artifact_id",
    )


def _run_suite_version(payload: Mapping[str, Any]) -> Any:
    return _mapping_value(
        payload,
        "suiteVersion",
        "suite_version",
        "artifactVersion",
        "artifact_version",
        "validationArtifactVersion",
        "validation_artifact_version",
    )


def _normalized_engine_type(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _require_explicit_engine_type(payload: Mapping[str, Any], *, context: str) -> str:
    engine_type = _normalized_engine_type(_mapping_value(payload, "engineType", "engine_type"))
    if engine_type is None:
        raise ValueError(f"{context} requires explicit engine_type")
    return engine_type


def _assert_matching_engine_type(
    *,
    context: str,
    expected_engine_type: str,
    actual_engine_type: str | None,
) -> None:
    normalized_actual = _normalized_engine_type(actual_engine_type)
    if normalized_actual is None:
        raise ValueError(f"{context} requires explicit engine_type")
    if normalized_actual != expected_engine_type:
        raise ValueError(
            f"{context} engine_type '{normalized_actual}' does not match top-level engine_type '{expected_engine_type}'"
        )


def _run_engine_type(payload: Mapping[str, Any]) -> str:
    run_id = str(payload.get("id") or _mapping_value(payload, "runId", "run_id") or "").strip()
    context = f"GX execution run '{run_id}'" if run_id else "GX execution run"
    return _require_explicit_engine_type(payload, context=context)


def build_gx_execution_run_status_history_entity(
    payload: Mapping[str, Any],
) -> GxExecutionRunStatusHistoryEntity:
    return GxExecutionRunStatusHistoryEntity(
        id=str(payload.get("id") or ""),
        runId=str(_mapping_value(payload, "runId", "run_id") or ""),
        fromStatus=(
            str(_mapping_value(payload, "fromStatus", "from_status"))
            if _mapping_value(payload, "fromStatus", "from_status") is not None
            else None
        ),
        toStatus=str(_mapping_value(payload, "toStatus", "to_status") or ""),
        changedBy=(
            str(_mapping_value(payload, "changedBy", "changed_by"))
            if _mapping_value(payload, "changedBy", "changed_by") is not None
            else None
        ),
        changedAt=str(_mapping_value(payload, "changedAt", "changed_at") or ""),
        reason=(str(payload.get("reason")) if payload.get("reason") is not None else None),
        details=dict(payload.get("details") or {}),
    )


def build_gx_execution_progress_entity(payload: Mapping[str, Any]) -> GxExecutionProgressEntity:
    return GxExecutionProgressEntity(
        percent=int(payload.get("percent") or 0),
        label=(str(payload.get("label")) if payload.get("label") is not None else None),
        completedSteps=(
            int(_mapping_value(payload, "completedSteps", "completed_steps"))
            if _mapping_value(payload, "completedSteps", "completed_steps") is not None
            else None
        ),
        totalSteps=(
            int(_mapping_value(payload, "totalSteps", "total_steps"))
            if _mapping_value(payload, "totalSteps", "total_steps") is not None
            else None
        ),
        source=(str(payload.get("source")) if payload.get("source") is not None else None),
        updatedAt=(
            str(_mapping_value(payload, "updatedAt", "updated_at"))
            if _mapping_value(payload, "updatedAt", "updated_at") is not None
            else None
        ),
    )


def build_gx_execution_traceability_entity(payload: Any) -> GxExecutionTraceabilityEntity | None:
    if isinstance(payload, GxExecutionTraceabilityEntity):
        return payload
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(payload, Mapping):
        return None
    return GxExecutionTraceabilityEntity.model_validate(payload)


def build_gx_execution_source_target_entity(payload: Any) -> GxExecutionSourceTargetEntity | None:
    if isinstance(payload, GxExecutionSourceTargetEntity):
        return payload
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(payload, Mapping):
        return None
    return GxExecutionSourceTargetEntity.model_validate(payload)


def build_gx_execution_source_materialization_entity(payload: Any) -> GxExecutionSourceMaterializationEntity | None:
    if isinstance(payload, GxExecutionSourceMaterializationEntity):
        return payload
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(payload, Mapping):
        return None
    normalized_payload = dict(payload)
    if normalized_payload.get("left_source") is not None:
        normalized_payload["left_source"] = build_gx_execution_source_target_entity(normalized_payload.get("left_source"))
    if normalized_payload.get("right_source") is not None:
        normalized_payload["right_source"] = build_gx_execution_source_target_entity(normalized_payload.get("right_source"))
    return GxExecutionSourceMaterializationEntity.model_validate(normalized_payload)


def build_gx_execution_contract_entity(payload: Any) -> GxExecutionContractEntity | None:
    if isinstance(payload, GxExecutionContractEntity):
        return payload
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(payload, Mapping):
        return None

    normalized_payload = dict(payload)
    normalized_payload["traceability"] = build_gx_execution_traceability_entity(normalized_payload.get("traceability"))
    if normalized_payload.get("source_materialization") is not None:
        normalized_payload["source_materialization"] = build_gx_execution_source_materialization_entity(
            normalized_payload.get("source_materialization")
        )
    return GxExecutionContractEntity.model_validate(normalized_payload)


def build_gx_grouped_execution_plan_entity(payload: Any) -> GxGroupedExecutionPlanEntity | None:
    if isinstance(payload, GxGroupedExecutionPlanEntity):
        return payload
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(payload, Mapping):
        return None
    return GxGroupedExecutionPlanEntity.model_validate(payload)


def build_gx_execution_diagnostic_entity(payload: Any) -> GxExecutionDiagnosticEntity | None:
    if isinstance(payload, GxExecutionDiagnosticEntity):
        return payload
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(payload, Mapping):
        return None
    return GxExecutionDiagnosticEntity.model_validate(payload)


def build_gx_execution_diagnostic_entities(payloads: list[Any] | None) -> list[GxExecutionDiagnosticEntity]:
    return [
        diagnostic
        for diagnostic in (build_gx_execution_diagnostic_entity(item) for item in (payloads or []))
        if diagnostic is not None
    ]


def build_gx_execution_result_item_entity(payload: Any) -> GxExecutionResultItemEntity | None:
    if isinstance(payload, GxExecutionResultItemEntity):
        return payload
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(payload, Mapping):
        return None
    return GxExecutionResultItemEntity.model_validate(payload)


def build_gx_execution_result_summary_entity(payload: Any) -> GxExecutionResultSummaryEntity | None:
    if isinstance(payload, GxExecutionResultSummaryEntity):
        return payload
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(payload, Mapping):
        return None
    return GxExecutionResultSummaryEntity.model_validate(payload)


def build_gx_execution_result_item_entities(
    payload: GxExecutionResultSummaryEntity | None,
) -> list[GxExecutionResultItemEntity]:
    if payload is None:
        return []
    return [
        item
        for item in (build_gx_execution_result_item_entity(candidate) for candidate in payload.results)
        if item is not None
    ]


def build_gx_structured_error_detail_entity(payload: Any) -> GxStructuredErrorDetailEntity | None:
    if isinstance(payload, GxStructuredErrorDetailEntity):
        return payload
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(payload, Mapping):
        return None
    return GxStructuredErrorDetailEntity.model_validate(payload)


def build_gx_execution_delivery_snapshot_entity(payload: Any) -> GxExecutionDeliverySnapshotEntity | None:
    if isinstance(payload, GxExecutionDeliverySnapshotEntity):
        return payload
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(payload, Mapping):
        return None
    return GxExecutionDeliverySnapshotEntity.model_validate(payload)


def build_gx_dispatch_source_override_entity(payload: Any) -> GxDispatchSourceOverrideEntity | None:
    if isinstance(payload, GxDispatchSourceOverrideEntity):
        return payload
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(payload, Mapping):
        return None
    return GxDispatchSourceOverrideEntity.model_validate(payload)


def build_gx_dispatch_payload_entity(payload: Any) -> GxDispatchPayloadEntity | None:
    if isinstance(payload, GxDispatchPayloadEntity):
        return payload
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(payload, Mapping):
        return None

    normalized_payload = dict(payload)
    if normalized_payload.get("execution_contract") is not None:
        normalized_payload["execution_contract"] = build_gx_execution_contract_entity(normalized_payload.get("execution_contract"))
    if normalized_payload.get("delivery_snapshot") is not None:
        normalized_payload["delivery_snapshot"] = build_gx_execution_delivery_snapshot_entity(normalized_payload.get("delivery_snapshot"))
    if normalized_payload.get("grouped_execution_plan") is not None:
        normalized_payload["grouped_execution_plan"] = build_gx_grouped_execution_plan_entity(normalized_payload.get("grouped_execution_plan"))
    if normalized_payload.get("next_dispatch_payload") is not None:
        normalized_payload["next_dispatch_payload"] = build_gx_dispatch_payload_entity(normalized_payload.get("next_dispatch_payload"))
    raw_overrides = normalized_payload.get("source_overrides_by_data_object_version_id")

    normalized_overrides: dict[str, GxDispatchSourceOverrideEntity] = {}
    if isinstance(raw_overrides, Mapping):
        for key, value in raw_overrides.items():
            target_id = str(key or "").strip()
            override_entity = build_gx_dispatch_source_override_entity(value)
            if not target_id or override_entity is None:
                continue
            normalized_overrides[target_id] = override_entity

    normalized_payload["source_overrides_by_data_object_version_id"] = normalized_overrides
    dispatch_engine_type = _require_explicit_engine_type(normalized_payload, context="GX dispatch payload")
    normalized_payload["engine_type"] = dispatch_engine_type
    execution_contract = normalized_payload.get("execution_contract")
    if execution_contract is not None:
        _assert_matching_engine_type(
            context="GX dispatch execution_contract",
            expected_engine_type=dispatch_engine_type,
            actual_engine_type=execution_contract.engineType,
        )
    delivery_snapshot = normalized_payload.get("delivery_snapshot")
    if delivery_snapshot is not None and _normalized_engine_type(delivery_snapshot.engineType) is not None:
        _assert_matching_engine_type(
            context="GX dispatch delivery_snapshot",
            expected_engine_type=dispatch_engine_type,
            actual_engine_type=delivery_snapshot.engineType,
        )
    return GxDispatchPayloadEntity.model_validate(normalized_payload)


def build_gx_execution_run_create_entity(payload: Any) -> GxExecutionRunCreateEntity:
    if isinstance(payload, GxExecutionRunCreateEntity):
        return payload
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(by_alias=True, exclude_none=False)
    if not isinstance(payload, Mapping):
        raise TypeError("GX execution run create payload must be a mapping")
    normalized_payload = dict(payload)
    execution_contract_payload = normalized_payload.pop("executionContract", normalized_payload.get("execution_contract"))
    handoff_payload = normalized_payload.pop("handoffPayload", normalized_payload.get("handoff_payload"))
    result_summary_payload = normalized_payload.pop("resultSummary", normalized_payload.get("result_summary"))
    performance_summary_payload = normalized_payload.pop("performanceSummary", normalized_payload.get("performance_summary"))
    diagnostics_payload = normalized_payload.get("diagnostics")
    normalized_payload["execution_contract"] = build_gx_execution_contract_entity(execution_contract_payload)
    normalized_payload["handoff_payload"] = build_gx_dispatch_payload_entity(handoff_payload)
    normalized_payload["result_summary"] = build_gx_execution_result_summary_entity(result_summary_payload)
    normalized_payload["performance_summary"] = (
        dict(performance_summary_payload) if isinstance(performance_summary_payload, Mapping) else performance_summary_payload
    )
    normalized_payload["diagnostics"] = build_gx_execution_diagnostic_entities(diagnostics_payload)
    run_engine_type = _require_explicit_engine_type(normalized_payload, context="GX execution run create payload")
    normalized_payload["engine_type"] = run_engine_type
    execution_contract = normalized_payload.get("execution_contract")
    if execution_contract is not None:
        _assert_matching_engine_type(
            context="GX execution run create execution_contract",
            expected_engine_type=run_engine_type,
            actual_engine_type=execution_contract.engineType,
        )
    handoff_entity = normalized_payload.get("handoff_payload")
    if handoff_entity is not None:
        _assert_matching_engine_type(
            context="GX execution run create handoff_payload",
            expected_engine_type=run_engine_type,
            actual_engine_type=handoff_entity.engineType,
        )
    return GxExecutionRunCreateEntity.model_validate(normalized_payload)


def build_gx_execution_run_status_transition_entity(payload: Any) -> GxExecutionRunStatusTransitionEntity:
    if isinstance(payload, GxExecutionRunStatusTransitionEntity):
        return payload
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(by_alias=True, exclude_none=False)
    if not isinstance(payload, Mapping):
        raise TypeError("GX execution run status transition payload must be a mapping")
    normalized_payload = dict(payload)
    if normalized_payload.get("details") is None:
        normalized_payload["details"] = {}
    result_summary_payload = normalized_payload.pop("resultSummary", normalized_payload.get("result_summary"))
    metrics_payload = normalized_payload.pop("metrics", normalized_payload.get("metrics"))
    performance_summary_payload = normalized_payload.pop("performanceSummary", normalized_payload.get("performance_summary"))
    normalized_payload["result_summary"] = build_gx_execution_result_summary_entity(result_summary_payload)
    normalized_payload["metrics"] = (
        dict(metrics_payload)
        if isinstance(metrics_payload, Mapping)
        else (dict(performance_summary_payload) if isinstance(performance_summary_payload, Mapping) else None)
    )
    normalized_payload["performance_summary"] = (
        dict(performance_summary_payload) if isinstance(performance_summary_payload, Mapping) else performance_summary_payload
    )
    diagnostics_payload = normalized_payload.get("diagnostics")
    if diagnostics_payload is not None:
        normalized_payload["diagnostics"] = build_gx_execution_diagnostic_entities(diagnostics_payload)
    return GxExecutionRunStatusTransitionEntity.model_validate(normalized_payload)


def build_gx_execution_run_list_query_entity(payload: Any) -> GxExecutionRunListQueryEntity:
    if isinstance(payload, GxExecutionRunListQueryEntity):
        return payload
    if not isinstance(payload, Mapping):
        raise TypeError("GX execution run list query payload must be a mapping")
    normalized_payload = dict(payload)
    suite_id = _run_suite_id(normalized_payload)
    if suite_id is not None:
        normalized_payload["suite_id"] = str(suite_id)
    for key in (
        "artifactId",
        "artifact_id",
        "validationArtifactId",
        "validation_artifact_id",
    ):
        normalized_payload.pop(key, None)
    return GxExecutionRunListQueryEntity.model_validate(normalized_payload)


def build_gx_execution_run_entity(payload: Mapping[str, Any]) -> GxExecutionRunEntity:
    progress_payload = _mapping_value(payload, "executionProgress", "execution_progress")
    raw_history_payloads = _mapping_value(payload, "statusHistory", "status_history")
    history_payloads = raw_history_payloads if isinstance(raw_history_payloads, list) else []
    diagnostics_payload = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), list) else []
    execution_contract_payload = _mapping_value(payload, "executionContract", "execution_contract")
    handoff_payload = _mapping_value(payload, "handoffPayload", "handoff_payload")
    result_summary_payload = _mapping_value(payload, "resultSummary", "result_summary")
    metrics_payload = _mapping_value(payload, "metrics", "metrics_json")
    performance_summary_payload = _mapping_value(payload, "performanceSummary", "performance_summary")
    if metrics_payload is None and isinstance(performance_summary_payload, Mapping):
        metrics_payload = performance_summary_payload
    suite_id = _run_suite_id(payload)
    suite_version = _run_suite_version(payload)

    return GxExecutionRunEntity(
        id=str(payload.get("id") or ""),
        suiteId=(str(suite_id) if suite_id is not None else None),
        suiteVersion=(int(suite_version) if suite_version is not None else None),
        ruleId=(
            str(_mapping_value(payload, "ruleId", "rule_id"))
            if _mapping_value(payload, "ruleId", "rule_id") is not None
            else None
        ),
        ruleVersionId=(
            str(_mapping_value(payload, "ruleVersionId", "rule_version_id"))
            if _mapping_value(payload, "ruleVersionId", "rule_version_id") is not None
            else None
        ),
        correlationId=str(_mapping_value(payload, "correlationId", "correlation_id") or ""),
        requestedBy=(
            str(_mapping_value(payload, "requestedBy", "requested_by"))
            if _mapping_value(payload, "requestedBy", "requested_by") is not None
            else None
        ),
        engineType=_run_engine_type(payload),
        engineTarget=str(_mapping_value(payload, "engineTarget", "engine_target") or ""),
        executionShape=str(_mapping_value(payload, "executionShape", "execution_shape") or ""),
        status=str(payload.get("status") or ""),
        submittedAt=str(_mapping_value(payload, "submittedAt", "submitted_at") or ""),
        startedAt=(
            str(_mapping_value(payload, "startedAt", "started_at"))
            if _mapping_value(payload, "startedAt", "started_at") is not None
            else None
        ),
        completedAt=(
            str(_mapping_value(payload, "completedAt", "completed_at"))
            if _mapping_value(payload, "completedAt", "completed_at") is not None
            else None
        ),
        createdAt=str(_mapping_value(payload, "createdAt", "created_at") or ""),
        updatedAt=str(_mapping_value(payload, "updatedAt", "updated_at") or ""),
        executionContract=build_gx_execution_contract_entity(execution_contract_payload),
        handoffPayload=build_gx_dispatch_payload_entity(handoff_payload),
        executionProgress=(
            build_gx_execution_progress_entity(progress_payload)
            if isinstance(progress_payload, Mapping)
            else None
        ),
        resultSummary=build_gx_execution_result_summary_entity(result_summary_payload),
        metrics=(dict(metrics_payload) if isinstance(metrics_payload, Mapping) else None),
        performanceSummary=(dict(performance_summary_payload) if isinstance(performance_summary_payload, Mapping) else None),
        diagnostics=build_gx_execution_diagnostic_entities(diagnostics_payload),
        failureCode=(
            str(_mapping_value(payload, "failureCode", "failure_code"))
            if _mapping_value(payload, "failureCode", "failure_code") is not None
            else None
        ),
        failureMessage=(
            str(_mapping_value(payload, "failureMessage", "failure_message"))
            if _mapping_value(payload, "failureMessage", "failure_message") is not None
            else None
        ),
        comments=(
            str(_mapping_value(payload, "comments", "comment"))
            if _mapping_value(payload, "comments", "comment") is not None
            else None
        ),
        statusHistory=[
            build_gx_execution_run_status_history_entity(item)
            for item in history_payloads
            if isinstance(item, Mapping)
        ],
    )


def build_gx_execution_run_summary_entity(payload: Mapping[str, Any]) -> GxExecutionRunSummaryEntity:
    suite_id = _run_suite_id(payload)
    suite_version = _run_suite_version(payload)
    return GxExecutionRunSummaryEntity(
        id=str(payload.get("id") or ""),
        suiteId=(str(suite_id) if suite_id is not None else None),
        suiteVersion=(int(suite_version) if suite_version is not None else None),
        ruleId=(
            str(_mapping_value(payload, "ruleId", "rule_id"))
            if _mapping_value(payload, "ruleId", "rule_id") is not None
            else None
        ),
        ruleName=(
            str(_mapping_value(payload, "ruleName", "rule_name"))
            if _mapping_value(payload, "ruleName", "rule_name") is not None
            else None
        ),
        owner=(
            str(_mapping_value(payload, "owner", "rule_owner"))
            if _mapping_value(payload, "owner", "rule_owner") is not None
            else None
        ),
        domain=(
            str(_mapping_value(payload, "domain", "rule_domain"))
            if _mapping_value(payload, "domain", "rule_domain") is not None
            else None
        ),
        severity=(
            str(_mapping_value(payload, "severity", "rule_severity"))
            if _mapping_value(payload, "severity", "rule_severity") is not None
            else None
        ),
        runPlanId=(
            str(_mapping_value(payload, "runPlanId", "run_plan_id"))
            if _mapping_value(payload, "runPlanId", "run_plan_id") is not None
            else None
        ),
        dataObjectVersionId=(
            str(_mapping_value(payload, "dataObjectVersionId", "data_object_version_id"))
            if _mapping_value(payload, "dataObjectVersionId", "data_object_version_id") is not None
            else None
        ),
        dataObjectNames=[
            str(value)
            for value in list(_mapping_value(payload, "dataObjectNames", "data_object_names") or [])
            if str(value).strip()
        ],
        resolvedDataDeliveryId=(
            str(_mapping_value(payload, "resolvedDataDeliveryId", "resolved_data_delivery_id"))
            if _mapping_value(payload, "resolvedDataDeliveryId", "resolved_data_delivery_id") is not None
            else None
        ),
        correlationId=str(_mapping_value(payload, "correlationId", "correlation_id") or ""),
        requestedBy=(
            str(_mapping_value(payload, "requestedBy", "requested_by"))
            if _mapping_value(payload, "requestedBy", "requested_by") is not None
            else None
        ),
        engineType=_run_engine_type(payload),
        engineTarget=str(_mapping_value(payload, "engineTarget", "engine_target") or ""),
        executionShape=str(_mapping_value(payload, "executionShape", "execution_shape") or ""),
        status=str(payload.get("status") or ""),
        failedRecordCount=int(_mapping_value(payload, "failedRecordCount", "failed_record_count") or 0),
        submittedAt=str(_mapping_value(payload, "submittedAt", "submitted_at") or ""),
        startedAt=(
            str(_mapping_value(payload, "startedAt", "started_at"))
            if _mapping_value(payload, "startedAt", "started_at") is not None
            else None
        ),
        completedAt=(
            str(_mapping_value(payload, "completedAt", "completed_at"))
            if _mapping_value(payload, "completedAt", "completed_at") is not None
            else None
        ),
        createdAt=str(_mapping_value(payload, "createdAt", "created_at") or ""),
        updatedAt=str(_mapping_value(payload, "updatedAt", "updated_at") or ""),
    )