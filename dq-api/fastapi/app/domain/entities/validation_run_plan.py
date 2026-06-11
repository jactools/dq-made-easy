from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ConfigDict
from pydantic import Field

from app.domain.entities.base import EntityModel
from app.domain.entities.gx_execution_run import GxExecutionContractEntity
from app.domain.entities.gx_execution_run import GxGroupedExecutionPlanEntity
from app.domain.entities.gx_execution_run import build_gx_execution_contract_entity
from app.domain.entities.gx_execution_run import build_gx_grouped_execution_plan_entity
from app.domain.entities.gx_run_plan import GxRunPlanEntity
from app.domain.entities.gx_run_plan import build_gx_run_plan_entity
from app.domain.entities.validation_artifact import build_gx_artifact_envelope_from_validation_artifact
from app.domain.entities.validation_artifact import build_validation_artifact_envelope_entity
from app.domain.entities.validation_artifact import build_validation_artifact_envelope_from_gx_artifact
from app.domain.entities.validation_artifact import ValidationArtifactEnvelopeEntity


def _looks_like_gx_artifact_snapshot(payload: Mapping[str, Any]) -> bool:
    return any(key in payload for key in ("suiteId", "suiteVersion", "gxSuite", "artifactVersion"))


def _looks_like_validation_artifact_snapshot(payload: Mapping[str, Any]) -> bool:
    return any(key in payload for key in ("validationArtifactId", "validationArtifactVersion", "engineArtifact"))


class ValidationRunPlanScheduleDefinitionEntity(EntityModel):
    scheduledAt: str | None = None


class ValidationRunPlanAssignmentScopeEntity(EntityModel):
    model_config = ConfigDict(extra="allow")

    dataObjectId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = None
    tagIds: list[str] = Field(default_factory=list)


class ValidationRunPlanScopeSelectorEntity(EntityModel):
    model_config = ConfigDict(extra="allow")

    assignmentScope: ValidationRunPlanAssignmentScopeEntity | None = None
    dataObjectId: str | None = None
    dataObjectVersionId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = None
    tagIds: list[str] = Field(default_factory=list)
    workspaceId: str | None = None


class ValidationRunPlanArtifactRefEntity(EntityModel):
    artifactId: str | None = None
    artifactVersion: int | None = None
    engineType: str | None = None


class ValidationRunPlanArtifactSelectionEntity(EntityModel):
    selectionMode: str | None = None
    scopeSelector: ValidationRunPlanScopeSelectorEntity = Field(default_factory=ValidationRunPlanScopeSelectorEntity)
    artifactRefs: list[ValidationRunPlanArtifactRefEntity] = Field(default_factory=list)
    groupedExecutionPlan: GxGroupedExecutionPlanEntity | None = None


class ValidationRunPlanGroupedArtifactSnapshotEntity(EntityModel):
    groupedExecutionPlan: GxGroupedExecutionPlanEntity | None = None
    artifactEnvelopes: list[ValidationArtifactEnvelopeEntity] = Field(default_factory=list)


class ValidationRunPlanVersionEntity(EntityModel):
    runPlanVersionId: str
    runPlanId: str
    governanceState: str
    validationArtifactSelection: dict[str, Any] = Field(default_factory=dict)
    artifactId: str | None = None
    artifactVersion: int | None = None
    artifactSnapshot: dict[str, Any] | None = None
    scheduleDefinition: dict[str, Any] = Field(default_factory=dict)
    executionContractSnapshot: dict[str, Any] | None = None
    validationStatus: str | None = None
    reviewStatus: str | None = None
    effectiveFrom: str | None = None
    supersedesVersionId: str | None = None
    createdBy: str | None = None
    createdAt: str


class ValidationRunPlanTransitionEventEntity(EntityModel):
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


class ValidationRunPlanEntity(EntityModel):
    runPlanId: str
    businessKey: str | None = None
    workspaceId: str
    scopeSelector: ValidationRunPlanScopeSelectorEntity = Field(default_factory=ValidationRunPlanScopeSelectorEntity)
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
    versions: list[ValidationRunPlanVersionEntity] = Field(default_factory=list)
    transitionEvents: list[ValidationRunPlanTransitionEventEntity] = Field(default_factory=list)


def build_validation_run_plan_schedule_definition_entity(
    payload: Mapping[str, Any] | None,
) -> ValidationRunPlanScheduleDefinitionEntity:
    if not isinstance(payload, Mapping):
        return ValidationRunPlanScheduleDefinitionEntity()
    return ValidationRunPlanScheduleDefinitionEntity(
        scheduledAt=(str(payload.get("scheduledAt")) if payload.get("scheduledAt") is not None else None),
    )


def build_validation_run_plan_assignment_scope_entity(
    payload: Mapping[str, Any] | ValidationRunPlanAssignmentScopeEntity | None,
) -> ValidationRunPlanAssignmentScopeEntity | None:
    if isinstance(payload, ValidationRunPlanAssignmentScopeEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None
    return ValidationRunPlanAssignmentScopeEntity.model_validate(dict(payload))


def build_validation_run_plan_scope_selector_entity(
    payload: Mapping[str, Any] | ValidationRunPlanScopeSelectorEntity | None,
) -> ValidationRunPlanScopeSelectorEntity:
    if isinstance(payload, ValidationRunPlanScopeSelectorEntity):
        return payload
    if not isinstance(payload, Mapping):
        return ValidationRunPlanScopeSelectorEntity()

    normalized_payload = dict(payload)
    normalized_payload["assignmentScope"] = build_validation_run_plan_assignment_scope_entity(
        normalized_payload.get("assignmentScope")
    )
    if normalized_payload.get("workspaceId") is None and normalized_payload.get("workspace_id") is not None:
        normalized_payload["workspaceId"] = normalized_payload.get("workspace_id")
    return ValidationRunPlanScopeSelectorEntity.model_validate(normalized_payload)


def build_validation_run_plan_artifact_ref_entity(
    payload: Mapping[str, Any] | ValidationRunPlanArtifactRefEntity | None,
) -> ValidationRunPlanArtifactRefEntity | None:
    if isinstance(payload, ValidationRunPlanArtifactRefEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    artifact_id = payload.get("artifactId")
    if artifact_id is None:
        artifact_id = payload.get("artifact_id")

    artifact_version = payload.get("artifactVersion")
    if artifact_version is None:
        artifact_version = payload.get("artifact_version")

    return ValidationRunPlanArtifactRefEntity(
        artifactId=(str(artifact_id) if artifact_id is not None else None),
        artifactVersion=(int(artifact_version) if artifact_version is not None else None),
        engineType=(
            str(payload.get("engineType") or payload.get("engine_type"))
            if (payload.get("engineType") is not None or payload.get("engine_type") is not None)
            else None
        ),
    )


def build_validation_run_plan_artifact_ref_entities(
    payloads: list[Mapping[str, Any] | ValidationRunPlanArtifactRefEntity] | None,
) -> list[ValidationRunPlanArtifactRefEntity]:
    refs: list[ValidationRunPlanArtifactRefEntity] = []
    for payload in payloads or []:
        ref = build_validation_run_plan_artifact_ref_entity(payload)
        if ref is not None:
            refs.append(ref)
    return refs


def build_validation_run_plan_artifact_selection_entity(
    payload: Mapping[str, Any] | ValidationRunPlanArtifactSelectionEntity | None,
) -> ValidationRunPlanArtifactSelectionEntity:
    if isinstance(payload, ValidationRunPlanArtifactSelectionEntity):
        return payload
    if not isinstance(payload, Mapping):
        return ValidationRunPlanArtifactSelectionEntity()

    refs = payload.get("artifactRefs") if isinstance(payload.get("artifactRefs"), list) else []
    return ValidationRunPlanArtifactSelectionEntity(
        selectionMode=(str(payload.get("selectionMode")) if payload.get("selectionMode") is not None else None),
        scopeSelector=build_validation_run_plan_scope_selector_entity(payload.get("scopeSelector")),
        artifactRefs=build_validation_run_plan_artifact_ref_entities(refs),
        groupedExecutionPlan=build_gx_grouped_execution_plan_entity(payload.get("groupedExecutionPlan")),
    )


def build_validation_run_plan_grouped_artifact_snapshot_entity(
    payload: Mapping[str, Any] | ValidationRunPlanGroupedArtifactSnapshotEntity | None,
) -> ValidationRunPlanGroupedArtifactSnapshotEntity | None:
    if isinstance(payload, ValidationRunPlanGroupedArtifactSnapshotEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    artifact_envelopes = payload.get("artifactEnvelopes") if isinstance(payload.get("artifactEnvelopes"), list) else []
    return ValidationRunPlanGroupedArtifactSnapshotEntity(
        groupedExecutionPlan=build_gx_grouped_execution_plan_entity(payload.get("groupedExecutionPlan")),
        artifactEnvelopes=[
            build_validation_artifact_envelope_entity(item)
            for item in artifact_envelopes
            if isinstance(item, Mapping)
        ],
    )


def build_validation_artifact_selection_payload_from_gx_suite_selection(
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}

    normalized_payload = dict(payload)
    suite_refs = normalized_payload.pop("suiteRefs", []) if isinstance(normalized_payload.get("suiteRefs"), list) else []
    normalized_payload["artifactRefs"] = [
        {
            "artifactId": item.get("suiteId"),
            "artifactVersion": item.get("suiteVersion"),
            "engineType": item.get("engineType") if item.get("engineType") is not None else item.get("engine_type"),
        }
        for item in suite_refs
        if isinstance(item, Mapping)
    ]
    return normalized_payload


def build_gx_suite_selection_payload_from_validation_artifact_selection(
    payload: Mapping[str, Any] | ValidationRunPlanArtifactSelectionEntity | None,
) -> dict[str, Any]:
    if isinstance(payload, ValidationRunPlanArtifactSelectionEntity):
        normalized_payload = payload.model_dump(mode="python", by_alias=False, exclude_none=True)
    elif isinstance(payload, Mapping):
        normalized_payload = dict(payload)
    else:
        return {}

    artifact_refs = normalized_payload.pop("artifactRefs", []) if isinstance(normalized_payload.get("artifactRefs"), list) else []
    normalized_payload["suiteRefs"] = [
        {
            "suiteId": item.get("artifactId"),
            "suiteVersion": item.get("artifactVersion"),
            "engineType": item.get("engineType") if item.get("engineType") is not None else item.get("engine_type"),
        }
        for item in artifact_refs
        if isinstance(item, Mapping)
    ]
    return normalized_payload


def build_validation_artifact_snapshot_payload_from_gx_snapshot(
    payload: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None

    if isinstance(payload.get("suiteEnvelopes"), list):
        return {
            **{key: value for key, value in payload.items() if key != "suiteEnvelopes"},
            "artifactEnvelopes": [
                build_validation_artifact_envelope_from_gx_artifact(item).model_dump(mode="python", by_alias=False, exclude_none=True)
                if isinstance(item, Mapping) and _looks_like_gx_artifact_snapshot(item)
                else dict(item)
                for item in payload.get("suiteEnvelopes", [])
                if isinstance(item, Mapping)
            ],
        }

    if _looks_like_gx_artifact_snapshot(payload):
        return build_validation_artifact_envelope_from_gx_artifact(payload).model_dump(
            mode="python", by_alias=False, exclude_none=True
        )

    return dict(payload)


def build_gx_artifact_snapshot_payload_from_validation_snapshot(
    payload: Mapping[str, Any] | ValidationArtifactEnvelopeEntity | ValidationRunPlanGroupedArtifactSnapshotEntity | None,
) -> dict[str, Any] | None:
    if isinstance(payload, ValidationArtifactEnvelopeEntity):
        return build_gx_artifact_envelope_from_validation_artifact(payload).model_dump(
            mode="python", by_alias=False, exclude_none=True
        )
    if isinstance(payload, ValidationRunPlanGroupedArtifactSnapshotEntity):
        normalized_payload = payload.model_dump(mode="python", by_alias=False, exclude_none=True)
    elif isinstance(payload, Mapping):
        normalized_payload = dict(payload)
    else:
        return None

    if isinstance(normalized_payload.get("artifactEnvelopes"), list):
        return {
            **{key: value for key, value in normalized_payload.items() if key != "artifactEnvelopes"},
            "suiteEnvelopes": [
                build_gx_artifact_envelope_from_validation_artifact(item).model_dump(mode="python", by_alias=False, exclude_none=True)
                if isinstance(item, Mapping) and _looks_like_validation_artifact_snapshot(item)
                else dict(item)
                for item in normalized_payload.get("artifactEnvelopes", [])
                if isinstance(item, Mapping)
            ],
        }

    if _looks_like_validation_artifact_snapshot(normalized_payload):
        return build_gx_artifact_envelope_from_validation_artifact(normalized_payload).model_dump(
            mode="python", by_alias=False, exclude_none=True
        )

    return normalized_payload


def build_validation_run_plan_version_entity(
    payload: Mapping[str, Any] | ValidationRunPlanVersionEntity,
) -> ValidationRunPlanVersionEntity:
    if isinstance(payload, ValidationRunPlanVersionEntity):
        return payload
    return ValidationRunPlanVersionEntity(
        runPlanVersionId=str(payload.get("runPlanVersionId") or ""),
        runPlanId=str(payload.get("runPlanId") or ""),
        governanceState=str(payload.get("governanceState") or ""),
        validationArtifactSelection=dict(payload.get("validationArtifactSelection") or {}),
        artifactId=(str(payload.get("artifactId")) if payload.get("artifactId") is not None else None),
        artifactVersion=(int(payload.get("artifactVersion")) if payload.get("artifactVersion") is not None else None),
        artifactSnapshot=(dict(payload.get("artifactSnapshot") or {}) if payload.get("artifactSnapshot") is not None else None),
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


def build_validation_run_plan_transition_event_entity(
    payload: Mapping[str, Any] | ValidationRunPlanTransitionEventEntity,
) -> ValidationRunPlanTransitionEventEntity:
    if isinstance(payload, ValidationRunPlanTransitionEventEntity):
        return payload
    return ValidationRunPlanTransitionEventEntity(
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


def build_validation_run_plan_entity(
    payload: Mapping[str, Any] | ValidationRunPlanEntity,
) -> ValidationRunPlanEntity:
    if isinstance(payload, ValidationRunPlanEntity):
        return payload

    version_payloads = payload.get("versions") if isinstance(payload.get("versions"), list) else []
    transition_payloads = payload.get("transitionEvents") if isinstance(payload.get("transitionEvents"), list) else []
    return ValidationRunPlanEntity(
        runPlanId=str(payload.get("runPlanId") or ""),
        businessKey=(str(payload.get("businessKey")) if payload.get("businessKey") is not None else None),
        workspaceId=str(payload.get("workspaceId") or ""),
        scopeSelector=build_validation_run_plan_scope_selector_entity(payload.get("scopeSelector")),
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
        versions=[build_validation_run_plan_version_entity(item) for item in version_payloads if isinstance(item, Mapping)],
        transitionEvents=[
            build_validation_run_plan_transition_event_entity(item)
            for item in transition_payloads
            if isinstance(item, Mapping)
        ],
    )


def build_validation_run_plan_entity_from_gx_run_plan(
    payload: Mapping[str, Any] | GxRunPlanEntity,
) -> ValidationRunPlanEntity:
    gx_payload = payload.model_dump(mode="python", by_alias=False, exclude_none=True) if isinstance(payload, GxRunPlanEntity) else dict(payload)

    versions = gx_payload.get("versions") if isinstance(gx_payload.get("versions"), list) else []
    normalized_versions = []
    for version in versions:
        if not isinstance(version, Mapping):
            continue
        normalized_versions.append(
            {
                **{key: value for key, value in version.items() if key not in {"gxSuiteSelection", "suiteId", "suiteVersion", "suiteSnapshot"}},
                "validationArtifactSelection": build_validation_artifact_selection_payload_from_gx_suite_selection(
                    version.get("gxSuiteSelection") if isinstance(version.get("gxSuiteSelection"), Mapping) else None
                ),
                "artifactId": version.get("suiteId"),
                "artifactVersion": version.get("suiteVersion"),
                "artifactSnapshot": build_validation_artifact_snapshot_payload_from_gx_snapshot(
                    version.get("suiteSnapshot") if isinstance(version.get("suiteSnapshot"), Mapping) else None
                ),
            }
        )

    normalized_payload = {
        **gx_payload,
        "versions": normalized_versions,
    }
    return build_validation_run_plan_entity(normalized_payload)


def build_gx_run_plan_entity_from_validation_run_plan(
    payload: Mapping[str, Any] | ValidationRunPlanEntity,
) -> GxRunPlanEntity:
    validation_payload = payload.model_dump(mode="python", by_alias=False, exclude_none=True) if isinstance(payload, ValidationRunPlanEntity) else dict(payload)

    versions = validation_payload.get("versions") if isinstance(validation_payload.get("versions"), list) else []
    normalized_versions = []
    for version in versions:
        if not isinstance(version, Mapping):
            continue
        normalized_versions.append(
            {
                **{key: value for key, value in version.items() if key not in {"validationArtifactSelection", "artifactId", "artifactVersion", "artifactSnapshot"}},
                "gxSuiteSelection": build_gx_suite_selection_payload_from_validation_artifact_selection(
                    version.get("validationArtifactSelection") if isinstance(version.get("validationArtifactSelection"), Mapping) else None
                ),
                "suiteId": version.get("artifactId"),
                "suiteVersion": version.get("artifactVersion"),
                "suiteSnapshot": build_gx_artifact_snapshot_payload_from_validation_snapshot(
                    version.get("artifactSnapshot") if isinstance(version.get("artifactSnapshot"), Mapping) else None
                ),
            }
        )

    normalized_payload = {
        **validation_payload,
        "versions": normalized_versions,
    }
    return build_gx_run_plan_entity(normalized_payload)