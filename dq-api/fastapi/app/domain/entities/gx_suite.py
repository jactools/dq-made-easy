from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator

from app.domain.entities.base import EntityModel
from app.domain.entities.gx_execution_run import GxExecutionContractEntity
from app.domain.entities.gx_execution_run import GxExecutionIncrementalSelectionEntity
from app.domain.entities.gx_execution_run import build_gx_execution_contract_entity
from app.domain.entities.gx_execution_run import build_gx_execution_incremental_selection_entity
from app.schemas.pydantic_base import to_snake_alias


class GxSuiteExpectationEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    expectationType: str | None = None
    kwargs: dict[str, Any] | None = None


class GxSuiteEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    expectations: list[GxSuiteExpectationEntity] = Field(default_factory=list)


class GxArtifactAssignmentScopeEntity(EntityModel):
    dataObjectId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = None
    tagIds: list[str] = Field(default_factory=list)


class GxArtifactResolvedExecutionScopeEntity(EntityModel):
    dataObjectVersionIds: list[str] = Field(default_factory=list)


class GxArtifactCompiledFromEntity(EntityModel):
    ruleIds: list[str] = Field(default_factory=list)
    compilerVersion: str = "unknown"
    generatedAt: str = ""


class GxArtifactFailedRowsPolicyEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    mode: str | None = None
    limit: int | None = None
    includeRowIdentifier: bool | None = None
    includePrimaryKey: bool | None = None


class GxArtifactEvidencePolicyEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    failedRows: GxArtifactFailedRowsPolicyEntity | None = None
    emitCompiledArtifact: bool | None = None
    emitGeneratedSql: bool | None = None


class GxArtifactExecutionHintsEntity(EntityModel):
    recommendedEngine: str | None = None
    primaryKeyFields: list[str] = Field(default_factory=list)
    businessKeyFields: list[str] = Field(default_factory=list)
    evidence: GxArtifactEvidencePolicyEntity | None = None
    incrementalSelection: GxExecutionIncrementalSelectionEntity | None = None


class GxArtifactEnvelopeEntity(EntityModel):
    suiteId: str
    suiteVersion: int = Field(ge=1)
    artifactVersion: str
    assignmentScope: GxArtifactAssignmentScopeEntity = Field(default_factory=GxArtifactAssignmentScopeEntity)
    resolvedExecutionScope: GxArtifactResolvedExecutionScopeEntity = Field(default_factory=GxArtifactResolvedExecutionScopeEntity)
    gxSuite: dict[str, Any] = Field(default_factory=dict)
    compiledFrom: GxArtifactCompiledFromEntity = Field(default_factory=GxArtifactCompiledFromEntity)
    executionHints: GxArtifactExecutionHintsEntity = Field(default_factory=GxArtifactExecutionHintsEntity)
    executionContract: GxExecutionContractEntity | None = None
    savedBy: str | None = None
    sourcePipeline: str | None = None
    status: str | None = None
    artifactHash: str | None = None


class GxSuiteRetrievalQueryEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)

    dataObjectId: str | None = None
    dataObjectVersionId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = Field(default=None, pattern=r"^(odcs\..+|prod-.+)$")
    tagIds: list[str] = Field(default_factory=list)
    status: str = "active"
    latestOnly: bool = True

    @model_validator(mode="after")
    def validate_primary_scope(self) -> "GxSuiteRetrievalQueryEntity":
        primary_scope_count = sum(
            bool(value)
            for value in (
                self.dataObjectId,
                self.dataObjectVersionId,
                self.datasetId,
                self.dataProductId,
            )
        )
        if primary_scope_count == 1 or (primary_scope_count == 0 and self.tagIds):
            return self
        raise ValueError(
            "Exactly one primary scope filter is required: dataObjectId, "
            "dataObjectVersionId, datasetId, dataProductId, or tagIds"
        )


class GxSuiteStatusHistoryEntity(EntityModel):
    suiteId: str
    suiteVersion: int
    fromStatus: str | None = None
    toStatus: str
    changedBy: str | None = None
    changedAt: str
    reason: str | None = None


def build_gx_suite_expectation_entity(payload: Any) -> GxSuiteExpectationEntity | None:
    if isinstance(payload, GxSuiteExpectationEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None
    return GxSuiteExpectationEntity.model_validate(payload)


def build_gx_suite_entity(payload: Any) -> GxSuiteEntity | None:
    if isinstance(payload, GxSuiteEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    normalized_payload = dict(payload)
    normalized_payload["expectations"] = [
        expectation
        for expectation in (
            build_gx_suite_expectation_entity(item)
            for item in normalized_payload.get("expectations", [])
        )
        if expectation is not None
    ]
    return GxSuiteEntity.model_validate(normalized_payload)


def build_gx_artifact_assignment_scope_entity(
    payload: Mapping[str, Any] | GxArtifactAssignmentScopeEntity | None,
) -> GxArtifactAssignmentScopeEntity:
    if isinstance(payload, GxArtifactAssignmentScopeEntity):
        return payload
    if not isinstance(payload, Mapping):
        return GxArtifactAssignmentScopeEntity()
    return GxArtifactAssignmentScopeEntity(
        dataObjectId=(
            str(payload.get("dataObjectId"))
            if payload.get("dataObjectId") is not None
            else str(payload.get("data_object_id"))
            if payload.get("data_object_id") is not None
            else None
        ),
        datasetId=(
            str(payload.get("datasetId"))
            if payload.get("datasetId") is not None
            else str(payload.get("dataset_id"))
            if payload.get("dataset_id") is not None
            else None
        ),
        dataProductId=(
            str(payload.get("dataProductId"))
            if payload.get("dataProductId") is not None
            else str(payload.get("data_product_id"))
            if payload.get("data_product_id") is not None
            else None
        ),
    )


def build_gx_artifact_resolved_execution_scope_entity(
    payload: Mapping[str, Any] | GxArtifactResolvedExecutionScopeEntity | None,
) -> GxArtifactResolvedExecutionScopeEntity:
    if isinstance(payload, GxArtifactResolvedExecutionScopeEntity):
        return payload
    if not isinstance(payload, Mapping):
        return GxArtifactResolvedExecutionScopeEntity()
    raw_target_ids = payload.get("dataObjectVersionIds") or payload.get("data_object_version_ids") or []
    return GxArtifactResolvedExecutionScopeEntity(
        dataObjectVersionIds=[
            str(value).strip()
            for value in raw_target_ids
            if str(value).strip()
        ]
    )


def build_gx_artifact_compiled_from_entity(
    payload: Mapping[str, Any] | GxArtifactCompiledFromEntity | None,
) -> GxArtifactCompiledFromEntity:
    if isinstance(payload, GxArtifactCompiledFromEntity):
        return payload
    if not isinstance(payload, Mapping):
        return GxArtifactCompiledFromEntity()
    return GxArtifactCompiledFromEntity(
        ruleIds=[
            str(value).strip()
            for value in (payload.get("ruleIds") or payload.get("rule_ids") or [])
            if str(value).strip()
        ],
        compilerVersion=str(payload.get("compilerVersion") or payload.get("compiler_version") or "unknown"),
        generatedAt=str(payload.get("generatedAt") or payload.get("generated_at") or ""),
    )


def build_gx_artifact_execution_hints_entity(
    payload: Mapping[str, Any] | GxArtifactExecutionHintsEntity | None,
) -> GxArtifactExecutionHintsEntity:
    if isinstance(payload, GxArtifactExecutionHintsEntity):
        return payload
    if not isinstance(payload, Mapping):
        return GxArtifactExecutionHintsEntity()
    normalized_payload = dict(payload)
    evidence = normalized_payload.get("evidence")
    if hasattr(evidence, "model_dump"):
        normalized_payload["evidence"] = evidence.model_dump(mode="python", by_alias=True, exclude_none=True)
    incremental_selection = normalized_payload.get("incrementalSelection")
    if incremental_selection is None:
        incremental_selection = normalized_payload.get("incremental_selection")
    if hasattr(incremental_selection, "model_dump"):
        normalized_payload["incrementalSelection"] = incremental_selection.model_dump(
            mode="python",
            by_alias=True,
            exclude_none=True,
        )
    return GxArtifactExecutionHintsEntity(
        recommendedEngine=(
            str(normalized_payload.get("recommendedEngine"))
            if normalized_payload.get("recommendedEngine") is not None
            else None
        ),
        primaryKeyFields=[
            str(value).strip() for value in (normalized_payload.get("primaryKeyFields") or []) if str(value).strip()
        ],
        businessKeyFields=[
            str(value).strip() for value in (normalized_payload.get("businessKeyFields") or []) if str(value).strip()
        ],
        evidence=normalized_payload.get("evidence"),
        incrementalSelection=build_gx_execution_incremental_selection_entity(normalized_payload.get("incrementalSelection")),
    )


def build_gx_artifact_envelope_entity(
    payload: Mapping[str, Any] | GxArtifactEnvelopeEntity,
) -> GxArtifactEnvelopeEntity:
    if isinstance(payload, GxArtifactEnvelopeEntity):
        return payload
    execution_contract_payload = payload.get("executionContract")
    if execution_contract_payload is None:
        execution_contract_payload = payload.get("execution_contract")
    return GxArtifactEnvelopeEntity(
        suiteId=str(payload.get("suiteId") or ""),
        suiteVersion=int(payload.get("suiteVersion") or 0),
        artifactVersion=str(payload.get("artifactVersion") or "v1"),
        assignmentScope=build_gx_artifact_assignment_scope_entity(payload.get("assignmentScope")),
        resolvedExecutionScope=build_gx_artifact_resolved_execution_scope_entity(payload.get("resolvedExecutionScope")),
        gxSuite=dict(payload.get("gxSuite") or {}),
        compiledFrom=build_gx_artifact_compiled_from_entity(payload.get("compiledFrom")),
        executionHints=build_gx_artifact_execution_hints_entity(payload.get("executionHints")),
        executionContract=build_gx_execution_contract_entity(execution_contract_payload),
        savedBy=(str(payload.get("savedBy")) if payload.get("savedBy") is not None else None),
        sourcePipeline=(str(payload.get("sourcePipeline")) if payload.get("sourcePipeline") is not None else None),
        status=(str(payload.get("status")) if payload.get("status") is not None else None),
        artifactHash=(str(payload.get("artifactHash")) if payload.get("artifactHash") is not None else None),
    )


def build_gx_suite_retrieval_query_entity(
    payload: Mapping[str, Any] | GxSuiteRetrievalQueryEntity,
) -> GxSuiteRetrievalQueryEntity:
    if isinstance(payload, GxSuiteRetrievalQueryEntity):
        return payload
    return GxSuiteRetrievalQueryEntity.model_validate(payload)


def build_gx_suite_status_history_entity(
    payload: Mapping[str, Any] | GxSuiteStatusHistoryEntity,
) -> GxSuiteStatusHistoryEntity:
    if isinstance(payload, GxSuiteStatusHistoryEntity):
        return payload
    return GxSuiteStatusHistoryEntity(
        suiteId=str(payload.get("suiteId") or ""),
        suiteVersion=int(payload.get("suiteVersion") or 0),
        fromStatus=(str(payload.get("fromStatus")) if payload.get("fromStatus") is not None else None),
        toStatus=str(payload.get("toStatus") or ""),
        changedBy=(str(payload.get("changedBy")) if payload.get("changedBy") is not None else None),
        changedAt=str(payload.get("changedAt") or ""),
        reason=(str(payload.get("reason")) if payload.get("reason") is not None else None),
    )


def build_gx_suite_status_history_entities(
    payloads: list[Mapping[str, Any] | GxSuiteStatusHistoryEntity] | None,
) -> list[GxSuiteStatusHistoryEntity]:
    return [build_gx_suite_status_history_entity(payload) for payload in payloads or []]