from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import ConfigDict, Field, ValidationError

from app.domain.entities.base import EntityModel
from app.domain.entities.gx_execution_run import GxExecutionRunEntity
from app.domain.entities.gx_execution_run import build_gx_execution_result_item_entities
from app.domain.entities.gx_execution_run import build_gx_execution_result_summary_entity
from app.domain.entities.gx_suite import GxArtifactEnvelopeEntity
from app.domain.entities.rule import RuleEntity
from app.domain.entities.rule import RuleTaxonomyEntity
from app.schemas.pydantic_base import to_snake_alias


class DqResultScoreDimensionEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    name: str
    value: float | int | None = None
    maximum: float | int | None = None
    weight: float | int | None = None
    normalizedValue: float | int | None = Field(default=None, alias="normalized_value")
    threshold: float | int | None = None
    passed: bool | None = None
    reason: str | None = None


class DqResultDatasetEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    id: str
    name: str | None = None
    workspaceId: str | None = Field(default=None, alias="workspace_id")
    dataProductId: str | None = Field(default=None, alias="data_product_id")
    dataObjectId: str | None = Field(default=None, alias="data_object_id")
    dataObjectVersionId: str | None = Field(default=None, alias="data_object_version_id")


class DqResultDomainEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    id: str
    name: str | None = None


class DqResultRuleEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    id: str
    name: str | None = None
    workspaceId: str | None = Field(default=None, alias="workspace_id")
    versionId: str | None = Field(default=None, alias="version_id")
    versionNumber: int | None = Field(default=None, alias="version_number")
    taxonomy: RuleTaxonomyEntity = Field(default_factory=RuleTaxonomyEntity)


class DqResultRunOutcomeEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    status: str
    result: str | None = None
    passed: bool | None = None
    totalCount: int | None = Field(default=None, alias="total_count")
    validCount: int | None = Field(default=None, alias="valid_count")
    invalidCount: int | None = Field(default=None, alias="invalid_count")
    warningCount: int | None = Field(default=None, alias="warning_count")
    errorCount: int | None = Field(default=None, alias="error_count")
    score: float | int | None = None
    scoreLabel: str | None = Field(default=None, alias="score_label")
    observedAt: str | None = Field(default=None, alias="observed_at")
    durationMs: int | None = Field(default=None, alias="duration_ms")
    message: str | None = None


class DqResultCorrelationEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    correlationId: str = Field(alias="correlation_id")
    runId: str | None = Field(default=None, alias="run_id")
    requestId: str | None = Field(default=None, alias="request_id")
    queueMessageId: str | None = Field(default=None, alias="queue_message_id")
    traceId: str | None = Field(default=None, alias="trace_id")
    parentCorrelationId: str | None = Field(default=None, alias="parent_correlation_id")
    sourceSystem: str | None = Field(default=None, alias="source_system")


class DqResultEventEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    eventType: str = Field(default="dq_result_event", alias="event_type")
    eventVersion: str = Field(default="1", alias="event_version")
    emittedAt: str = Field(alias="emitted_at")
    severity: str
    dataset: DqResultDatasetEntity
    domain: DqResultDomainEntity | None = None
    rule: DqResultRuleEntity
    runOutcome: DqResultRunOutcomeEntity = Field(alias="run_outcome")
    scoreDimensions: list[DqResultScoreDimensionEntity] = Field(default_factory=list, alias="score_dimensions")
    correlation: DqResultCorrelationEntity


def build_dq_result_event_entity(payload: Any) -> DqResultEventEntity | None:
    if not isinstance(payload, Mapping):
        return None

    try:
        return DqResultEventEntity.model_validate(payload)
    except ValidationError:
        return None


def build_dq_result_event_from_gx_execution_run(
    run: GxExecutionRunEntity,
    *,
    suite: GxArtifactEnvelopeEntity | Mapping[str, Any] | None = None,
    rule: RuleEntity | None = None,
    report_body: Mapping[str, Any] | None = None,
) -> DqResultEventEntity:
    suite_payload = _normalize_payload(suite)
    body_payload = _normalize_payload(report_body)
    details = _normalize_payload(_lookup_mapping(body_payload, "details"))
    execution_contract = run.executionContract
    traceability = execution_contract.traceability if execution_contract is not None else None
    source_materialization = execution_contract.sourceMaterialization if execution_contract is not None else None
    left_source = source_materialization.leftSource if source_materialization is not None else None
    right_source = source_materialization.rightSource if source_materialization is not None else None

    emitted_at = _first_text(
        _lookup_text(body_payload, "completed_at", "completedAt"),
        run.completedAt,
        run.updatedAt,
        run.startedAt,
    ) or datetime.now(tz=UTC).isoformat()
    status = _first_text(_lookup_text(body_payload, "new_status", "newStatus"), run.status) or "unknown"
    message = _first_text(
        _lookup_text(body_payload, "failure_message", "failureMessage"),
        _lookup_text(body_payload, "reason"),
        run.failureMessage,
        run.comments,
    )

    result_summary = build_gx_execution_result_summary_entity(run.resultSummary)
    result_items = build_gx_execution_result_item_entities(result_summary)
    valid_count = sum(1 for item in result_items if item.ok is True) if result_items else None
    invalid_count = sum(1 for item in result_items if item.ok is False) if result_items else None
    total_count = len(result_items) if result_items else None
    if total_count and total_count > 0:
        score = round((valid_count or 0) / total_count * 100, 2)
    else:
        score = 100 if status == "succeeded" else 0 if status in {"failed", "cancelled"} else None

    dataset = _build_dataset_entity(
        run=run,
        suite_payload=suite_payload,
        left_source=left_source,
        right_source=right_source,
        rule=rule,
    )
    domain = _build_domain_entity(suite_payload=suite_payload, details=details)
    rule_entity = _build_rule_entity(run=run, suite_payload=suite_payload, traceability=traceability, rule=rule)
    correlation = _build_correlation_entity(run=run, body_payload=body_payload, details=details)

    return DqResultEventEntity(
        emittedAt=emitted_at,
        severity=_severity_for_status(status),
        dataset=dataset,
        domain=domain,
        rule=rule_entity,
        runOutcome=DqResultRunOutcomeEntity(
            status=status,
            result=status,
            passed=status == "succeeded",
            totalCount=total_count,
            validCount=valid_count,
            invalidCount=invalid_count,
            warningCount=None,
            errorCount=invalid_count,
            score=score,
            scoreLabel="quality_score",
            observedAt=emitted_at,
            durationMs=_duration_ms(run.startedAt, emitted_at),
            message=message,
        ),
        scoreDimensions=[
            DqResultScoreDimensionEntity(
                name="quality_score",
                value=score,
                maximum=100,
                normalizedValue=(score / 100) if score is not None else None,
                threshold=None,
                passed=status == "succeeded",
                reason=message,
            )
        ],
        correlation=correlation,
    )


def _normalize_payload(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        dumped = payload.model_dump(mode="python", by_alias=True, exclude_none=True)
        return dict(dumped) if isinstance(dumped, Mapping) else {}
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _lookup_text(payload: Any, *keys: str) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    for key in keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _lookup_mapping(payload: Any, *keys: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    for key in keys:
        value = payload.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _read_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_ms(started_at: Any, completed_at: Any) -> int | None:
    start = _parse_datetime(started_at)
    end = _parse_datetime(completed_at)
    if start is None or end is None:
        return None
    return max(int((end - start).total_seconds() * 1000), 0)


def _severity_for_status(status: str) -> str:
    if status == "succeeded":
        return "info"
    if status == "cancelled":
        return "warning"
    return "critical"


def _build_dataset_entity(
    *,
    run: GxExecutionRunEntity,
    suite_payload: Mapping[str, Any],
    left_source: Mapping[str, Any],
    right_source: Mapping[str, Any],
    rule: RuleEntity | None,
) -> DqResultDatasetEntity:
    assignment_scope = _lookup_mapping(suite_payload, "assignment_scope", "assignmentScope")
    resolved_scope = _lookup_mapping(suite_payload, "resolved_execution_scope", "resolvedExecutionScope")
    source_candidate = assignment_scope or resolved_scope
    if not source_candidate:
        source_candidate = _lookup_mapping(
            _normalize_payload(run.executionContract.sourceMaterialization if run.executionContract else None),
            "left_source",
            "leftSource",
        )

    dataset_id = _lookup_text(source_candidate, "dataset_id", "datasetId")
    data_product_id = _lookup_text(source_candidate, "data_product_id", "dataProductId")
    data_object_id = _lookup_text(source_candidate, "data_object_id", "dataObjectId")
    data_object_version_id = _lookup_text(source_candidate, "data_object_version_id", "dataObjectVersionId")

    if dataset_id is None:
        dataset_id = _lookup_text(left_source, "dataset_id", "datasetId") or _lookup_text(right_source, "dataset_id", "datasetId")
    if data_product_id is None:
        data_product_id = _lookup_text(left_source, "data_product_id", "dataProductId") or _lookup_text(right_source, "data_product_id", "dataProductId")
    if data_object_id is None:
        data_object_id = _lookup_text(left_source, "data_object_id", "dataObjectId") or _lookup_text(right_source, "data_object_id", "dataObjectId")
    if data_object_version_id is None:
        data_object_version_id = (
            _lookup_text(left_source, "data_object_version_id", "dataObjectVersionId")
            or _lookup_text(right_source, "data_object_version_id", "dataObjectVersionId")
            or _lookup_text(_normalize_payload(run.executionContract.traceability if run.executionContract else None), "data_object_version_id", "dataObjectVersionId")
            or _lookup_text(_normalize_payload(run.executionContract if run.executionContract else None), "resolved_data_object_version_id", "resolvedDataObjectVersionId")
        )

    if dataset_id is None:
        dataset_id = _first_text(run.suiteId, run.id) or "unknown"

    return DqResultDatasetEntity(
        id=dataset_id,
        name=_lookup_text(source_candidate, "dataset_name", "datasetName"),
        workspaceId=_lookup_text(source_candidate, "workspace_id", "workspaceId") or _normalized_text(rule.workspace if rule is not None else None),
        dataProductId=data_product_id,
        dataObjectId=data_object_id,
        dataObjectVersionId=data_object_version_id,
    )


def _build_domain_entity(suite_payload: Mapping[str, Any], details: Mapping[str, Any]) -> DqResultDomainEntity | None:
    gx_suite = _lookup_mapping(suite_payload, "gx_suite", "gxSuite")
    domain_id = _lookup_text(
        details,
        "domain_id",
        "domainId",
        "domain",
    ) or _lookup_text(
        gx_suite,
        "primary_domain",
        "primaryDomain",
        "domain_id",
        "domainId",
        "domain",
    )
    if domain_id is None:
        return None
    return DqResultDomainEntity(
        id=domain_id,
        name=_lookup_text(gx_suite, "domain_name", "domainName", "primary_domain_name", "primaryDomainName") or domain_id,
    )


def _build_rule_entity(
    *,
    run: GxExecutionRunEntity,
    suite_payload: Mapping[str, Any],
    traceability: Any,
    rule: RuleEntity | None,
) -> DqResultRuleEntity:
    gx_suite = _lookup_mapping(suite_payload, "gx_suite", "gxSuite")
    rule_id = _first_text(
        run.ruleId,
        rule.id if rule is not None else None,
        _lookup_text(gx_suite, "rule_id", "ruleId"),
        _lookup_text(_normalize_payload(traceability), "rule_id", "ruleId"),
    ) or run.id
    rule_name = _first_text(
        rule.name if rule is not None else None,
        _lookup_text(gx_suite, "rule_name", "ruleName", "name", "expectation_suite_name", "expectationSuiteName"),
        _lookup_text(_normalize_payload(traceability), "source_rule_expression", "sourceRuleExpression"),
    )
    version_id = _first_text(run.ruleVersionId, _lookup_text(_normalize_payload(traceability), "rule_version_id", "ruleVersionId"))
    version_number = _read_int(run.suiteVersion) or _read_int(_lookup_text(suite_payload, "suite_version", "suiteVersion"))
    return DqResultRuleEntity(
        id=rule_id,
        name=rule_name,
        workspaceId=_normalized_text(rule.workspace if rule is not None else None),
        versionId=version_id,
        versionNumber=version_number,
        taxonomy=rule.taxonomy if rule is not None else RuleTaxonomyEntity(),
    )


def _normalized_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _build_correlation_entity(
    *,
    run: GxExecutionRunEntity,
    body_payload: Mapping[str, Any],
    details: Mapping[str, Any],
) -> DqResultCorrelationEntity:
    handoff_payload = _normalize_payload(run.handoffPayload)
    headers = _normalize_payload(handoff_payload.get("headers"))
    return DqResultCorrelationEntity(
        correlationId=run.correlationId,
        runId=run.id,
        requestId=_first_text(_lookup_text(details, "request_id", "requestId"), run.id),
        queueMessageId=_first_text(
            _lookup_text(details, "queue_message_id", "queueMessageId"),
            _lookup_text(handoff_payload, "queue_message_id", "queueMessageId"),
        ),
        traceId=_first_text(
            _lookup_text(details, "trace_id", "traceId"),
            _lookup_text(headers, "trace_id", "traceId", "traceparent"),
        ),
        parentCorrelationId=_lookup_text(details, "parent_correlation_id", "parentCorrelationId"),
        sourceSystem=_first_text(
            _lookup_text(details, "source_system", "sourceSystem"),
            "gx_report_api",
        ),
    )