from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ConfigDict, Field

from app.domain.entities.base import EntityModel
from app.domain.entities.gx_execution_run import GxExecutionContractEntity
from app.domain.entities.gx_execution_run import GxGroupedExecutionPlanEntity
from app.domain.entities.gx_execution_run import build_gx_execution_contract_entity
from app.domain.entities.gx_execution_run import build_gx_grouped_execution_plan_entity


class GxRunPlanScheduleDefinitionEntity(EntityModel):
    scheduledAt: str | None = None


class GxRunPlanAssignmentScopeEntity(EntityModel):
    model_config = ConfigDict(extra="allow")

    dataObjectId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = None
    tagIds: list[str] = Field(default_factory=list)


class GxRunPlanScopeSelectorEntity(EntityModel):
    model_config = ConfigDict(extra="allow")

    assignmentScope: GxRunPlanAssignmentScopeEntity | None = None
    dataObjectId: str | None = None
    dataObjectVersionId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = None
    tagIds: list[str] = Field(default_factory=list)
    workspaceId: str | None = None


class GxRunPlanSuiteRefEntity(EntityModel):
    suiteId: str | None = None
    suiteVersion: int | None = None
    engineType: str | None = None


class GxRunPlanSuiteSelectionEntity(EntityModel):
    selectionMode: str | None = None
    scopeSelector: GxRunPlanScopeSelectorEntity = Field(default_factory=GxRunPlanScopeSelectorEntity)
    suiteRefs: list[GxRunPlanSuiteRefEntity] = Field(default_factory=list)
    groupedExecutionPlan: GxGroupedExecutionPlanEntity | None = None


class GxRunPlanSingleSuiteSnapshotEntity(EntityModel):
    suiteId: str | None = None
    suiteVersion: int | None = None
    artifactVersion: str | None = None
    assignmentScope: dict[str, Any] = Field(default_factory=dict)
    resolvedExecutionScope: dict[str, Any] = Field(default_factory=dict)
    gxSuite: dict[str, Any] = Field(default_factory=dict)
    compiledFrom: dict[str, Any] = Field(default_factory=dict)
    executionHints: dict[str, Any] = Field(default_factory=dict)
    executionContract: GxExecutionContractEntity | None = None
    savedBy: str | None = None
    sourcePipeline: str | None = None


class GxRunPlanGroupedSuiteSnapshotEntity(EntityModel):
    groupedExecutionPlan: GxGroupedExecutionPlanEntity | None = None
    suiteEnvelopes: list[GxRunPlanSingleSuiteSnapshotEntity] = Field(default_factory=list)


class GxRunPlanValidationDiagnosticEntity(EntityModel):
    scope: str
    severity: str = "error"
    code: str
    message: str
    details: Any | None = None


class GxRunPlanSeedEntity(EntityModel):
    scopeSelector: GxRunPlanScopeSelectorEntity = Field(default_factory=GxRunPlanScopeSelectorEntity)
    gxSuiteSelection: GxRunPlanSuiteSelectionEntity = Field(default_factory=GxRunPlanSuiteSelectionEntity)
    suiteId: str | None = None
    suiteVersion: int | None = None
    suiteSnapshot: GxRunPlanSingleSuiteSnapshotEntity | GxRunPlanGroupedSuiteSnapshotEntity | None = None
    executionContractSnapshot: GxExecutionContractEntity | None = None


class GxRunPlanVersionValidationSnapshotEntity(EntityModel):
    scheduledAt: str | None = None
    selectionMode: str | None = None
    executionContractSnapshot: GxExecutionContractEntity | None = None
    suiteSnapshot: GxRunPlanSingleSuiteSnapshotEntity | GxRunPlanGroupedSuiteSnapshotEntity | None = None
    groupedExecutionPlan: GxGroupedExecutionPlanEntity | None = None
    groupedSuiteEnvelopes: list[GxRunPlanSingleSuiteSnapshotEntity] = Field(default_factory=list)


class GxRunPlanVersionEntity(EntityModel):
    runPlanVersionId: str
    runPlanId: str
    governanceState: str
    gxSuiteSelection: dict[str, Any] = Field(default_factory=dict)
    suiteId: str | None = None
    suiteVersion: int | None = None
    suiteSnapshot: dict[str, Any] | None = None
    scheduleDefinition: dict[str, Any] = Field(default_factory=dict)
    executionContractSnapshot: dict[str, Any] | None = None
    validationStatus: str | None = None
    reviewStatus: str | None = None
    effectiveFrom: str | None = None
    supersedesVersionId: str | None = None
    createdBy: str | None = None
    createdAt: str


class GxRunPlanTransitionEventEntity(EntityModel):
    id: str
    runPlanId: str
    runPlanVersionId: str | None = None
    action: str
    fromState: str | None = None
    toState: str | None = None
    actorId: str | None = None
    correlationId: str | None = None
    effectiveFrom: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    occurredAt: str


class GxRunPlanEntity(EntityModel):
    runPlanId: str
    businessKey: str | None = None
    workspaceId: str
    scopeSelector: GxRunPlanScopeSelectorEntity = Field(default_factory=GxRunPlanScopeSelectorEntity)
    planningMode: str
    currentActiveVersionId: str | None = None
    status: str
    pendingVersionId: str | None = None
    pendingVersionGovernanceState: str | None = None
    createdBy: str | None = None
    createdAt: str
    updatedAt: str
    activatedBy: str | None = None
    activatedAt: str | None = None
    lastDispatchedRunId: str | None = None
    versions: list[GxRunPlanVersionEntity] = Field(default_factory=list)
    transitionEvents: list[GxRunPlanTransitionEventEntity] = Field(default_factory=list)


def build_gx_run_plan_schedule_definition_entity(
    payload: Mapping[str, Any] | None,
) -> GxRunPlanScheduleDefinitionEntity:
    if not isinstance(payload, Mapping):
        return GxRunPlanScheduleDefinitionEntity()
    return GxRunPlanScheduleDefinitionEntity(
        scheduledAt=(str(payload.get("scheduledAt")) if payload.get("scheduledAt") is not None else None),
    )


def build_gx_run_plan_assignment_scope_entity(
    payload: Mapping[str, Any] | GxRunPlanAssignmentScopeEntity | None,
) -> GxRunPlanAssignmentScopeEntity | None:
    if isinstance(payload, GxRunPlanAssignmentScopeEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    normalized_payload = dict(payload)
    return GxRunPlanAssignmentScopeEntity.model_validate(
        {
            **normalized_payload,
            "dataObjectId": normalized_payload.get("dataObjectId"),
            "datasetId": normalized_payload.get("datasetId"),
            "dataProductId": normalized_payload.get("dataProductId"),
            "tagIds": normalized_payload.get("tagIds") if isinstance(normalized_payload.get("tagIds"), list) else [],
        }
    )


def build_gx_run_plan_scope_selector_entity(
    payload: Mapping[str, Any] | GxRunPlanScopeSelectorEntity | None,
) -> GxRunPlanScopeSelectorEntity:
    if isinstance(payload, GxRunPlanScopeSelectorEntity):
        return payload
    if not isinstance(payload, Mapping):
        return GxRunPlanScopeSelectorEntity()

    normalized_payload = dict(payload)
    assignment_scope = build_gx_run_plan_assignment_scope_entity(normalized_payload.get("assignmentScope"))
    workspace_id = normalized_payload.get("workspaceId")
    if workspace_id is None:
        workspace_id = normalized_payload.get("workspace_id")

    return GxRunPlanScopeSelectorEntity.model_validate(
        {
            **normalized_payload,
            "assignmentScope": assignment_scope,
            "dataObjectId": normalized_payload.get("dataObjectId"),
            "dataObjectVersionId": normalized_payload.get("dataObjectVersionId"),
            "datasetId": normalized_payload.get("datasetId"),
            "dataProductId": normalized_payload.get("dataProductId"),
            "tagIds": normalized_payload.get("tagIds") if isinstance(normalized_payload.get("tagIds"), list) else [],
            "workspaceId": workspace_id,
        }
    )


def build_gx_run_plan_suite_ref_entity(
    payload: Mapping[str, Any] | GxRunPlanSuiteRefEntity | None,
) -> GxRunPlanSuiteRefEntity | None:
    if isinstance(payload, GxRunPlanSuiteRefEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None
    suite_id = payload.get("suiteId")
    if suite_id is None:
        suite_id = payload.get("suite_id")
    if suite_id is None:
        suite_id = payload.get("artifactId")
    if suite_id is None:
        suite_id = payload.get("artifact_id")
    if suite_id is None:
        suite_id = payload.get("validationArtifactId")
    if suite_id is None:
        suite_id = payload.get("validation_artifact_id")

    suite_version = payload.get("suiteVersion")
    if suite_version is None:
        suite_version = payload.get("suite_version")
    if suite_version is None:
        suite_version = payload.get("artifactVersion")
    if suite_version is None:
        suite_version = payload.get("artifact_version")
    if suite_version is None:
        suite_version = payload.get("validationArtifactVersion")
    if suite_version is None:
        suite_version = payload.get("validation_artifact_version")

    return GxRunPlanSuiteRefEntity(
        suiteId=(str(suite_id) if suite_id is not None else None),
        suiteVersion=(int(suite_version) if suite_version is not None else None),
        engineType=(
            str(payload.get("engineType") or payload.get("engine_type"))
            if (payload.get("engineType") is not None or payload.get("engine_type") is not None)
            else None
        ),
    )


def build_gx_run_plan_suite_ref_entities(
    payloads: list[Mapping[str, Any] | GxRunPlanSuiteRefEntity] | None,
) -> list[GxRunPlanSuiteRefEntity]:
    suite_refs: list[GxRunPlanSuiteRefEntity] = []
    for payload in payloads or []:
        suite_ref = build_gx_run_plan_suite_ref_entity(payload)
        if suite_ref is not None:
            suite_refs.append(suite_ref)
    return suite_refs


def build_gx_run_plan_suite_selection_entity(
    payload: Mapping[str, Any] | None,
) -> GxRunPlanSuiteSelectionEntity:
    if not isinstance(payload, Mapping):
        return GxRunPlanSuiteSelectionEntity()

    suite_refs = payload.get("suiteRefs") if isinstance(payload.get("suiteRefs"), list) else []
    return GxRunPlanSuiteSelectionEntity(
        selectionMode=(str(payload.get("selectionMode")) if payload.get("selectionMode") is not None else None),
        scopeSelector=build_gx_run_plan_scope_selector_entity(payload.get("scopeSelector")),
        suiteRefs=build_gx_run_plan_suite_ref_entities(suite_refs),
        groupedExecutionPlan=build_gx_grouped_execution_plan_entity(payload.get("groupedExecutionPlan")),
    )


def build_gx_run_plan_single_suite_snapshot_entity(
    payload: Mapping[str, Any] | GxRunPlanSingleSuiteSnapshotEntity | None,
) -> GxRunPlanSingleSuiteSnapshotEntity | None:
    if isinstance(payload, GxRunPlanSingleSuiteSnapshotEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    return GxRunPlanSingleSuiteSnapshotEntity(
        suiteId=(str(payload.get("suiteId")) if payload.get("suiteId") is not None else None),
        suiteVersion=(int(payload.get("suiteVersion")) if payload.get("suiteVersion") is not None else None),
        artifactVersion=(str(payload.get("artifactVersion")) if payload.get("artifactVersion") is not None else None),
        assignmentScope=dict(payload.get("assignmentScope") or {}),
        resolvedExecutionScope=dict(payload.get("resolvedExecutionScope") or {}),
        gxSuite=dict(payload.get("gxSuite") or {}),
        compiledFrom=dict(payload.get("compiledFrom") or {}),
        executionHints=dict(payload.get("executionHints") or {}),
        executionContract=build_gx_execution_contract_entity(payload.get("executionContract")),
        savedBy=(str(payload.get("savedBy")) if payload.get("savedBy") is not None else None),
        sourcePipeline=(str(payload.get("sourcePipeline")) if payload.get("sourcePipeline") is not None else None),
    )


def build_gx_run_plan_single_suite_snapshot_entities(
    payloads: list[Mapping[str, Any] | GxRunPlanSingleSuiteSnapshotEntity] | None,
) -> list[GxRunPlanSingleSuiteSnapshotEntity]:
    snapshots: list[GxRunPlanSingleSuiteSnapshotEntity] = []
    for payload in payloads or []:
        snapshot = build_gx_run_plan_single_suite_snapshot_entity(payload)
        if snapshot is not None:
            snapshots.append(snapshot)
    return snapshots


def build_gx_run_plan_grouped_suite_snapshot_entity(
    payload: Mapping[str, Any] | None,
) -> GxRunPlanGroupedSuiteSnapshotEntity:
    if not isinstance(payload, Mapping):
        return GxRunPlanGroupedSuiteSnapshotEntity()

    suite_envelopes = payload.get("suiteEnvelopes") if isinstance(payload.get("suiteEnvelopes"), list) else []
    return GxRunPlanGroupedSuiteSnapshotEntity(
        groupedExecutionPlan=build_gx_grouped_execution_plan_entity(payload.get("groupedExecutionPlan")),
        suiteEnvelopes=build_gx_run_plan_single_suite_snapshot_entities(suite_envelopes),
    )


def build_gx_run_plan_validation_diagnostic_entity(
    payload: Mapping[str, Any] | GxRunPlanValidationDiagnosticEntity | None,
) -> GxRunPlanValidationDiagnosticEntity | None:
    if isinstance(payload, GxRunPlanValidationDiagnosticEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None
    code = str(payload.get("code") or "").strip()
    message = str(payload.get("message") or "").strip()
    if not code or not message:
        return None
    return GxRunPlanValidationDiagnosticEntity(
        scope=str(payload.get("scope") or "").strip() or "run_plan_validation",
        severity=str(payload.get("severity") or "error").strip() or "error",
        code=code,
        message=message,
        details=payload.get("details"),
    )


def build_gx_run_plan_validation_diagnostic_entities(
    payloads: list[Mapping[str, Any] | GxRunPlanValidationDiagnosticEntity] | None,
) -> list[GxRunPlanValidationDiagnosticEntity]:
    diagnostics: list[GxRunPlanValidationDiagnosticEntity] = []
    for payload in payloads or []:
        diagnostic = build_gx_run_plan_validation_diagnostic_entity(payload)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    return diagnostics


def build_gx_run_plan_version_validation_snapshot_entity(
    version_row: GxRunPlanVersionEntity,
) -> GxRunPlanVersionValidationSnapshotEntity:
    schedule_definition = build_gx_run_plan_schedule_definition_entity(version_row.scheduleDefinition)
    suite_selection = build_gx_run_plan_suite_selection_entity(version_row.gxSuiteSelection)
    grouped_suite_snapshot = build_gx_run_plan_grouped_suite_snapshot_entity(version_row.suiteSnapshot)
    execution_contract_snapshot = build_gx_execution_contract_entity(version_row.executionContractSnapshot)

    suite_snapshot: GxRunPlanSingleSuiteSnapshotEntity | GxRunPlanGroupedSuiteSnapshotEntity | None
    if str(suite_selection.selectionMode or "").strip() == "grouped_scope":
        suite_snapshot = grouped_suite_snapshot if isinstance(version_row.suiteSnapshot, Mapping) else None
    else:
        suite_snapshot = build_gx_run_plan_single_suite_snapshot_entity(version_row.suiteSnapshot)

    return GxRunPlanVersionValidationSnapshotEntity(
        scheduledAt=schedule_definition.scheduledAt,
        selectionMode=suite_selection.selectionMode,
        executionContractSnapshot=execution_contract_snapshot,
        suiteSnapshot=suite_snapshot,
        groupedExecutionPlan=grouped_suite_snapshot.groupedExecutionPlan,
        groupedSuiteEnvelopes=list(grouped_suite_snapshot.suiteEnvelopes),
    )


def build_gx_run_plan_version_entity(payload: Mapping[str, Any]) -> GxRunPlanVersionEntity:
    return GxRunPlanVersionEntity(
        runPlanVersionId=str(payload.get("runPlanVersionId") or ""),
        runPlanId=str(payload.get("runPlanId") or ""),
        governanceState=str(payload.get("governanceState") or ""),
        gxSuiteSelection=dict(payload.get("gxSuiteSelection") or {}),
        suiteId=(str(payload.get("suiteId")) if payload.get("suiteId") is not None else None),
        suiteVersion=(int(payload.get("suiteVersion")) if payload.get("suiteVersion") is not None else None),
        suiteSnapshot=(dict(payload.get("suiteSnapshot") or {}) if payload.get("suiteSnapshot") is not None else None),
        scheduleDefinition=dict(payload.get("scheduleDefinition") or {}),
        executionContractSnapshot=(
            dict(payload.get("executionContractSnapshot") or {})
            if payload.get("executionContractSnapshot") is not None
            else None
        ),
        validationStatus=(str(payload.get("validationStatus")) if payload.get("validationStatus") is not None else None),
        reviewStatus=(str(payload.get("reviewStatus")) if payload.get("reviewStatus") is not None else None),
        effectiveFrom=(str(payload.get("effectiveFrom")) if payload.get("effectiveFrom") is not None else None),
        supersedesVersionId=(
            str(payload.get("supersedesVersionId")) if payload.get("supersedesVersionId") is not None else None
        ),
        createdBy=(str(payload.get("createdBy")) if payload.get("createdBy") is not None else None),
        createdAt=str(payload.get("createdAt") or ""),
    )


def build_gx_run_plan_transition_event_entity(payload: Mapping[str, Any]) -> GxRunPlanTransitionEventEntity:
    return GxRunPlanTransitionEventEntity(
        id=str(payload.get("id") or ""),
        runPlanId=str(payload.get("runPlanId") or ""),
        runPlanVersionId=(str(payload.get("runPlanVersionId")) if payload.get("runPlanVersionId") is not None else None),
        action=str(payload.get("action") or ""),
        fromState=(str(payload.get("fromState")) if payload.get("fromState") is not None else None),
        toState=(str(payload.get("toState")) if payload.get("toState") is not None else None),
        actorId=(str(payload.get("actorId")) if payload.get("actorId") is not None else None),
        correlationId=(str(payload.get("correlationId")) if payload.get("correlationId") is not None else None),
        effectiveFrom=(str(payload.get("effectiveFrom")) if payload.get("effectiveFrom") is not None else None),
        details=dict(payload.get("details") or {}),
        occurredAt=str(payload.get("occurredAt") or ""),
    )


def build_gx_run_plan_entity(payload: Mapping[str, Any]) -> GxRunPlanEntity:
    transition_payloads = payload.get("transitionEvents") if isinstance(payload.get("transitionEvents"), list) else []
    version_payloads = payload.get("versions") if isinstance(payload.get("versions"), list) else []

    return GxRunPlanEntity(
        runPlanId=str(payload.get("runPlanId") or ""),
        businessKey=(str(payload.get("businessKey")) if payload.get("businessKey") is not None else None),
        workspaceId=str(payload.get("workspaceId") or ""),
        scopeSelector=build_gx_run_plan_scope_selector_entity(payload.get("scopeSelector")),
        planningMode=str(payload.get("planningMode") or ""),
        currentActiveVersionId=(
            str(payload.get("currentActiveVersionId"))
            if payload.get("currentActiveVersionId") is not None
            else None
        ),
        status=str(payload.get("status") or ""),
        pendingVersionId=(str(payload.get("pendingVersionId")) if payload.get("pendingVersionId") is not None else None),
        pendingVersionGovernanceState=(
            str(payload.get("pendingVersionGovernanceState"))
            if payload.get("pendingVersionGovernanceState") is not None
            else None
        ),
        createdBy=(str(payload.get("createdBy")) if payload.get("createdBy") is not None else None),
        createdAt=str(payload.get("createdAt") or ""),
        updatedAt=str(payload.get("updatedAt") or ""),
        activatedBy=(str(payload.get("activatedBy")) if payload.get("activatedBy") is not None else None),
        activatedAt=(str(payload.get("activatedAt")) if payload.get("activatedAt") is not None else None),
        lastDispatchedRunId=(
            str(payload.get("lastDispatchedRunId")) if payload.get("lastDispatchedRunId") is not None else None
        ),
        versions=[build_gx_run_plan_version_entity(item) for item in version_payloads if isinstance(item, Mapping)],
        transitionEvents=[
            build_gx_run_plan_transition_event_entity(item)
            for item in transition_payloads
            if isinstance(item, Mapping)
        ],
    )