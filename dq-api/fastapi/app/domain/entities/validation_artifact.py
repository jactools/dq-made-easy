from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ConfigDict
from pydantic import Field

from app.domain.entities.base import EntityModel
from app.domain.entities.gx_suite import GxArtifactEnvelopeEntity
from app.domain.entities.gx_suite import build_gx_artifact_envelope_entity
from app.domain.entities.gx_execution_run import GxExecutionContractEntity
from app.domain.entities.gx_execution_run import GxExecutionIncrementalSelectionEntity
from app.domain.entities.gx_execution_run import GxExecutionSourceMaterializationEntity
from app.domain.entities.gx_execution_run import GxExecutionSourceTargetEntity
from app.domain.entities.gx_execution_run import GxExecutionTraceabilityEntity
from app.domain.entities.gx_execution_run import build_gx_execution_incremental_selection_entity
from app.schemas.pydantic_base import to_snake_alias


class ValidationArtifactAssignmentScopeEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    dataObjectId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = None


class ValidationArtifactResolvedExecutionScopeEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    dataObjectVersionIds: list[str] = Field(default_factory=list)


class ValidationArtifactCompiledFromEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    ruleIds: list[str] = Field(default_factory=list)
    compilerVersion: str = "unknown"
    generatedAt: str = ""


class ValidationArtifactFailedRowsPolicyEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    mode: str | None = None
    limit: int | None = None
    includeRowIdentifier: bool | None = None
    includePrimaryKey: bool | None = None


class ValidationArtifactEvidencePolicyEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    failedRows: ValidationArtifactFailedRowsPolicyEntity | None = None
    emitCompiledArtifact: bool | None = None
    emitGeneratedSql: bool | None = None


class ValidationArtifactExecutionHintsEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    recommendedEngineTarget: str | None = None
    primaryKeyFields: list[str] = Field(default_factory=list)
    businessKeyFields: list[str] = Field(default_factory=list)
    supportedExecutionShapes: list[str] = Field(default_factory=list)
    evidence: ValidationArtifactEvidencePolicyEntity | None = None
    incrementalSelection: GxExecutionIncrementalSelectionEntity | None = None


class ValidationArtifactRunPlanningTraceabilityEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    ruleId: str | None = None
    ruleVersionId: str | None = None
    validationArtifactId: str | None = None
    validationArtifactVersion: int | None = None
    dataObjectVersionId: str | None = None


class ValidationArtifactSourceTargetEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    dataObjectId: str | None = None
    dataObjectVersionId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = None


class ValidationArtifactSourceMaterializationEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    landingZoneArtifactId: str | None = None
    landingZoneVersionId: str | None = None
    outputLocation: str | None = None
    joinType: str | None = None
    joinKeys: list[str] = Field(default_factory=list)
    leftSource: ValidationArtifactSourceTargetEntity | None = None
    rightSource: ValidationArtifactSourceTargetEntity | None = None


class ValidationArtifactRunPlanningEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    engineTarget: str | None = None
    executionShape: str | None = None
    groupingKey: str | None = None
    groupingValues: list[str] = Field(default_factory=list)
    traceability: ValidationArtifactRunPlanningTraceabilityEntity | None = None
    sourceMaterialization: ValidationArtifactSourceMaterializationEntity | None = None


class ValidationArtifactEngineArtifactEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    engineType: str
    artifactKind: str
    artifactSchemaVersion: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ValidationArtifactStatusHistoryEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    validationArtifactId: str
    validationArtifactVersion: int
    fromStatus: str | None = None
    toStatus: str
    changedBy: str | None = None
    changedAt: str
    reason: str | None = None


class ValidationArtifactEnvelopeEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    validationArtifactId: str
    validationArtifactVersion: int = Field(ge=1)
    artifactContractVersion: str = "v1"
    engineType: str
    assignmentScope: ValidationArtifactAssignmentScopeEntity = Field(default_factory=ValidationArtifactAssignmentScopeEntity)
    resolvedExecutionScope: ValidationArtifactResolvedExecutionScopeEntity = Field(default_factory=ValidationArtifactResolvedExecutionScopeEntity)
    compiledFrom: ValidationArtifactCompiledFromEntity = Field(default_factory=ValidationArtifactCompiledFromEntity)
    executionHints: ValidationArtifactExecutionHintsEntity = Field(default_factory=ValidationArtifactExecutionHintsEntity)
    runPlanning: ValidationArtifactRunPlanningEntity = Field(default_factory=ValidationArtifactRunPlanningEntity)
    engineArtifact: ValidationArtifactEngineArtifactEntity
    savedBy: str | None = None
    sourcePipeline: str | None = None
    status: str | None = None
    artifactHash: str | None = None


def build_validation_artifact_assignment_scope_entity(
    payload: Mapping[str, Any] | ValidationArtifactAssignmentScopeEntity | None,
) -> ValidationArtifactAssignmentScopeEntity:
    if isinstance(payload, ValidationArtifactAssignmentScopeEntity):
        return payload
    if not isinstance(payload, Mapping):
        return ValidationArtifactAssignmentScopeEntity()
    return ValidationArtifactAssignmentScopeEntity.model_validate(payload)


def build_validation_artifact_resolved_execution_scope_entity(
    payload: Mapping[str, Any] | ValidationArtifactResolvedExecutionScopeEntity | None,
) -> ValidationArtifactResolvedExecutionScopeEntity:
    if isinstance(payload, ValidationArtifactResolvedExecutionScopeEntity):
        return payload
    if not isinstance(payload, Mapping):
        return ValidationArtifactResolvedExecutionScopeEntity()
    return ValidationArtifactResolvedExecutionScopeEntity.model_validate(payload)


def build_validation_artifact_compiled_from_entity(
    payload: Mapping[str, Any] | ValidationArtifactCompiledFromEntity | None,
) -> ValidationArtifactCompiledFromEntity:
    if isinstance(payload, ValidationArtifactCompiledFromEntity):
        return payload
    if not isinstance(payload, Mapping):
        return ValidationArtifactCompiledFromEntity()
    return ValidationArtifactCompiledFromEntity.model_validate(payload)


def build_validation_artifact_execution_hints_entity(
    payload: Mapping[str, Any] | ValidationArtifactExecutionHintsEntity | None,
) -> ValidationArtifactExecutionHintsEntity:
    if isinstance(payload, ValidationArtifactExecutionHintsEntity):
        return payload
    if not isinstance(payload, Mapping):
        return ValidationArtifactExecutionHintsEntity()
    normalized_payload = dict(payload)
    incremental_selection = normalized_payload.get("incrementalSelection")
    if incremental_selection is None:
        incremental_selection = normalized_payload.get("incremental_selection")
    if hasattr(incremental_selection, "model_dump"):
        normalized_payload["incrementalSelection"] = incremental_selection.model_dump(
            mode="python",
            by_alias=True,
            exclude_none=True,
        )
    return ValidationArtifactExecutionHintsEntity.model_validate(normalized_payload)


def build_validation_artifact_run_planning_traceability_entity(
    payload: Mapping[str, Any] | ValidationArtifactRunPlanningTraceabilityEntity | None,
) -> ValidationArtifactRunPlanningTraceabilityEntity | None:
    if isinstance(payload, ValidationArtifactRunPlanningTraceabilityEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None
    return ValidationArtifactRunPlanningTraceabilityEntity.model_validate(payload)


def build_validation_artifact_source_target_entity(
    payload: Mapping[str, Any] | ValidationArtifactSourceTargetEntity | None,
) -> ValidationArtifactSourceTargetEntity | None:
    if isinstance(payload, ValidationArtifactSourceTargetEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None
    return ValidationArtifactSourceTargetEntity.model_validate(payload)


def build_validation_artifact_source_materialization_entity(
    payload: Mapping[str, Any] | ValidationArtifactSourceMaterializationEntity | None,
) -> ValidationArtifactSourceMaterializationEntity | None:
    if isinstance(payload, ValidationArtifactSourceMaterializationEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None
    return ValidationArtifactSourceMaterializationEntity.model_validate(payload)


def build_validation_artifact_run_planning_entity(
    payload: Mapping[str, Any] | ValidationArtifactRunPlanningEntity | None,
) -> ValidationArtifactRunPlanningEntity:
    if isinstance(payload, ValidationArtifactRunPlanningEntity):
        return payload
    if not isinstance(payload, Mapping):
        return ValidationArtifactRunPlanningEntity()
    return ValidationArtifactRunPlanningEntity.model_validate(payload)


def build_validation_artifact_engine_artifact_entity(
    payload: Mapping[str, Any] | ValidationArtifactEngineArtifactEntity,
) -> ValidationArtifactEngineArtifactEntity:
    if isinstance(payload, ValidationArtifactEngineArtifactEntity):
        return payload
    return ValidationArtifactEngineArtifactEntity.model_validate(payload)


def build_validation_artifact_status_history_entity(
    payload: Mapping[str, Any] | ValidationArtifactStatusHistoryEntity,
) -> ValidationArtifactStatusHistoryEntity:
    if isinstance(payload, ValidationArtifactStatusHistoryEntity):
        return payload
    return ValidationArtifactStatusHistoryEntity.model_validate(payload)


def build_validation_artifact_status_history_entities(
    payloads: list[Mapping[str, Any] | ValidationArtifactStatusHistoryEntity] | None,
) -> list[ValidationArtifactStatusHistoryEntity]:
    return [build_validation_artifact_status_history_entity(payload) for payload in payloads or []]


def build_validation_artifact_envelope_entity(
    payload: Mapping[str, Any] | ValidationArtifactEnvelopeEntity,
) -> ValidationArtifactEnvelopeEntity:
    if isinstance(payload, ValidationArtifactEnvelopeEntity):
        return payload
    return ValidationArtifactEnvelopeEntity.model_validate(payload)


def build_validation_artifact_envelope_from_gx_artifact(
    payload: Mapping[str, Any] | GxArtifactEnvelopeEntity,
) -> ValidationArtifactEnvelopeEntity:
    gx_envelope = build_gx_artifact_envelope_entity(payload) if not isinstance(payload, GxArtifactEnvelopeEntity) else payload
    execution_contract = gx_envelope.executionContract
    traceability = execution_contract.traceability if execution_contract is not None else None
    source_materialization = execution_contract.sourceMaterialization if execution_contract is not None else None

    return ValidationArtifactEnvelopeEntity(
        validationArtifactId=gx_envelope.suiteId,
        validationArtifactVersion=gx_envelope.suiteVersion,
        artifactContractVersion="v1",
        engineType="gx",
        assignmentScope=ValidationArtifactAssignmentScopeEntity(
            dataObjectId=gx_envelope.assignmentScope.dataObjectId,
            datasetId=gx_envelope.assignmentScope.datasetId,
            dataProductId=gx_envelope.assignmentScope.dataProductId,
        ),
        resolvedExecutionScope=ValidationArtifactResolvedExecutionScopeEntity(
            dataObjectVersionIds=list(gx_envelope.resolvedExecutionScope.dataObjectVersionIds)
        ),
        compiledFrom=ValidationArtifactCompiledFromEntity(
            ruleIds=list(gx_envelope.compiledFrom.ruleIds),
            compilerVersion=gx_envelope.compiledFrom.compilerVersion,
            generatedAt=gx_envelope.compiledFrom.generatedAt,
        ),
        executionHints=ValidationArtifactExecutionHintsEntity(
            recommendedEngineTarget=gx_envelope.executionHints.recommendedEngine,
            primaryKeyFields=list(gx_envelope.executionHints.primaryKeyFields),
            businessKeyFields=list(gx_envelope.executionHints.businessKeyFields),
            supportedExecutionShapes=(
                [execution_contract.executionShape]
                if execution_contract is not None and execution_contract.executionShape
                else []
            ),
            evidence=(
                ValidationArtifactEvidencePolicyEntity.model_validate(
                    gx_envelope.executionHints.evidence.model_dump(mode="python", by_alias=True, exclude_none=True)
                )
                if gx_envelope.executionHints.evidence is not None
                else None
            ),
            incrementalSelection=(
                build_gx_execution_incremental_selection_entity(gx_envelope.executionHints.incrementalSelection)
            ),
        ),
        runPlanning=ValidationArtifactRunPlanningEntity(
            engineTarget=(execution_contract.engineTarget if execution_contract is not None else gx_envelope.executionHints.recommendedEngine),
            executionShape=(execution_contract.executionShape if execution_contract is not None else None),
            groupingKey=("data_object_version_id" if gx_envelope.resolvedExecutionScope.dataObjectVersionIds else None),
            groupingValues=list(gx_envelope.resolvedExecutionScope.dataObjectVersionIds),
            traceability=(
                ValidationArtifactRunPlanningTraceabilityEntity(
                    ruleId=traceability.ruleId,
                    ruleVersionId=traceability.ruleVersionId,
                    validationArtifactId=gx_envelope.suiteId,
                    validationArtifactVersion=gx_envelope.suiteVersion,
                    dataObjectVersionId=traceability.dataObjectVersionId,
                )
                if traceability is not None
                else None
            ),
            sourceMaterialization=(
                ValidationArtifactSourceMaterializationEntity(
                    landingZoneArtifactId=source_materialization.landingZoneArtifactId,
                    landingZoneVersionId=source_materialization.landingZoneVersionId,
                    outputLocation=source_materialization.outputLocation,
                    joinType=source_materialization.joinType,
                    joinKeys=list(source_materialization.joinKeys),
                    leftSource=(
                        ValidationArtifactSourceTargetEntity.model_validate(
                            source_materialization.leftSource.model_dump(by_alias=True, exclude_none=True)
                        )
                        if source_materialization.leftSource is not None
                        else None
                    ),
                    rightSource=(
                        ValidationArtifactSourceTargetEntity.model_validate(
                            source_materialization.rightSource.model_dump(by_alias=True, exclude_none=True)
                        )
                        if source_materialization.rightSource is not None
                        else None
                    ),
                )
                if source_materialization is not None
                else None
            ),
        ),
        engineArtifact=ValidationArtifactEngineArtifactEntity(
            engineType="gx",
            artifactKind="gx_expectation_suite",
            artifactSchemaVersion=f"gx-artifact-envelope/{gx_envelope.artifactVersion}",
            payload=gx_envelope.model_dump(mode="python", by_alias=True, exclude_none=True),
        ),
        savedBy=gx_envelope.savedBy,
        sourcePipeline=gx_envelope.sourcePipeline,
        status=gx_envelope.status,
        artifactHash=gx_envelope.artifactHash,
    )


def build_gx_artifact_envelope_from_validation_artifact(
    payload: Mapping[str, Any] | ValidationArtifactEnvelopeEntity,
) -> GxArtifactEnvelopeEntity:
    validation_artifact = build_validation_artifact_envelope_entity(payload)
    engine_type = str(validation_artifact.engineType or "").strip().lower()
    engine_artifact_type = str(validation_artifact.engineArtifact.engineType or "").strip().lower()

    nested_payload = validation_artifact.engineArtifact.payload
    if not isinstance(nested_payload, Mapping) or not nested_payload:
        raise ValueError("Validation artifact cannot be projected to GX: missing engine_artifact.payload")

    if engine_type == "gx" and engine_artifact_type == "gx":
        gx_payload = dict(nested_payload)
        gx_payload.setdefault("suiteId", validation_artifact.validationArtifactId)
        gx_payload.setdefault("suiteVersion", validation_artifact.validationArtifactVersion)
        gx_payload.setdefault("artifactVersion", validation_artifact.engineArtifact.artifactSchemaVersion.rsplit("/", 1)[-1])
        if validation_artifact.savedBy is not None:
            gx_payload["savedBy"] = validation_artifact.savedBy
        if validation_artifact.sourcePipeline is not None:
            gx_payload["sourcePipeline"] = validation_artifact.sourcePipeline
        if validation_artifact.status is not None:
            gx_payload["status"] = validation_artifact.status
        if validation_artifact.artifactHash is not None:
            gx_payload["artifactHash"] = validation_artifact.artifactHash
        return build_gx_artifact_envelope_entity(gx_payload)

    if engine_type != "pyspark_native" or engine_artifact_type != "pyspark_native":
        raise ValueError(
            "Validation artifact cannot be projected to GX: engine_type must be 'gx' or 'pyspark_native'"
        )

    pyspark_plan = nested_payload.get("pyspark_plan")
    if not isinstance(pyspark_plan, Mapping) or not pyspark_plan:
        raise ValueError("Validation artifact cannot be projected to GX: missing pyspark_plan payload")

    execution_shape = str(
        pyspark_plan.get("execution_shape") or validation_artifact.runPlanning.executionShape or ""
    ).strip()
    if execution_shape not in {"single_object", "join_pair", "streaming", "micro_batch"}:
        raise ValueError("Validation artifact cannot be projected to GX: unsupported pyspark execution shape")

    engine_target = str(
        nested_payload.get("engine_target")
        or validation_artifact.runPlanning.engineTarget
        or validation_artifact.executionHints.recommendedEngineTarget
        or ""
    ).strip()
    if engine_target.lower() != "pyspark":
        raise ValueError("Validation artifact cannot be projected to GX: engine_target must be 'pyspark'")

    traceability_payload = validation_artifact.runPlanning.traceability
    if traceability_payload is None:
        raise ValueError("Validation artifact cannot be projected to GX: missing run planning traceability")

    evidence_payload = (
        validation_artifact.executionHints.evidence.model_dump(mode="python", by_alias=True, exclude_none=True)
        if validation_artifact.executionHints.evidence is not None
        else None
    )

    gx_payload = {
        "suiteId": str(nested_payload.get("artifact_id") or validation_artifact.validationArtifactId),
        "suiteVersion": int(nested_payload.get("artifact_revision") or validation_artifact.validationArtifactVersion),
        "artifactVersion": str(nested_payload.get("artifact_version") or "v1"),
        "assignmentScope": validation_artifact.assignmentScope.model_dump(mode="python", by_alias=True, exclude_none=True),
        "resolvedExecutionScope": validation_artifact.resolvedExecutionScope.model_dump(mode="python", by_alias=True, exclude_none=True),
        "gxSuite": {"pysparkPlan": dict(pyspark_plan)},
        "compiledFrom": validation_artifact.compiledFrom.model_dump(mode="python", by_alias=True, exclude_none=True),
        "executionHints": {
            "recommendedEngine": engine_target,
            "primaryKeyFields": list(validation_artifact.executionHints.primaryKeyFields or []),
            "businessKeyFields": list(validation_artifact.executionHints.businessKeyFields or []),
            "evidence": evidence_payload,
            "incrementalSelection": (
                validation_artifact.executionHints.incrementalSelection.model_dump(
                    mode="python",
                    by_alias=False,
                    exclude_none=True,
                )
                if validation_artifact.executionHints.incrementalSelection is not None
                else None
            ),
        },
        "executionContract": GxExecutionContractEntity(
            engineType=engine_type,
            engineTarget=engine_target,
            executionShape=execution_shape,
            traceability=GxExecutionTraceabilityEntity(
                ruleId=traceability_payload.ruleId,
                ruleVersionId=traceability_payload.ruleVersionId,
                gxSuiteId=validation_artifact.validationArtifactId,
                gxSuiteVersion=validation_artifact.validationArtifactVersion,
                dataObjectVersionId=traceability_payload.dataObjectVersionId,
            ),
            sourceMaterialization=(
                GxExecutionSourceMaterializationEntity(
                    landingZoneArtifactId=validation_artifact.runPlanning.sourceMaterialization.landingZoneArtifactId,
                    landingZoneVersionId=validation_artifact.runPlanning.sourceMaterialization.landingZoneVersionId,
                    outputLocation=validation_artifact.runPlanning.sourceMaterialization.outputLocation,
                    joinType=validation_artifact.runPlanning.sourceMaterialization.joinType,
                    joinKeys=list(validation_artifact.runPlanning.sourceMaterialization.joinKeys),
                    leftSource=(
                        GxExecutionSourceTargetEntity.model_validate(
                            validation_artifact.runPlanning.sourceMaterialization.leftSource.model_dump(
                                mode="python", by_alias=True, exclude_none=True
                            )
                        )
                        if validation_artifact.runPlanning.sourceMaterialization.leftSource is not None
                        else None
                    ),
                    rightSource=(
                        GxExecutionSourceTargetEntity.model_validate(
                            validation_artifact.runPlanning.sourceMaterialization.rightSource.model_dump(
                                mode="python", by_alias=True, exclude_none=True
                            )
                        )
                        if validation_artifact.runPlanning.sourceMaterialization.rightSource is not None
                        else None
                    ),
                )
                if validation_artifact.runPlanning.sourceMaterialization is not None
                else None
            ),
        ).model_dump(mode="python", by_alias=True, exclude_none=True),
        "savedBy": validation_artifact.savedBy,
        "sourcePipeline": validation_artifact.sourcePipeline,
        "status": validation_artifact.status,
        "artifactHash": validation_artifact.artifactHash,
    }
    return build_gx_artifact_envelope_entity(gx_payload)