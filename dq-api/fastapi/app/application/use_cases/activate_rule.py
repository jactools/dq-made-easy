from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from typing import Callable

from fastapi import HTTPException

from app.domain.entities.rule_autopublish_policy import persist_gx_suite_from_compiler
from app.domain.entities import rule_autopublish_policy
from app.domain.entities import rule_policy
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import GxSuiteRepository
from app.domain.interfaces import RulesRepository
from app.domain.interfaces import ValidationArtifactRepository


@dataclass(slots=True)
class ActivateRuleCommand:
    rule_id: str
    effective_at: str | None = None
    granted_scopes: list[str] | None = None
    auto_publish_request: Any = None
    saved_by: str | None = None


async def activate_rule(
    command: ActivateRuleCommand,
    repository: RulesRepository,
    validation_artifact_repository: ValidationArtifactRepository,
    gx_suite_repository: GxSuiteRepository,
    catalog_repository: DataCatalogRepository,
    *,
    span: Any = None,
    current_time: Callable[[], datetime] | None = None,
    parse_effective_at_param: Callable[[str | None], datetime | None] = rule_policy.parse_effective_at_param,
    read_row_field: Callable[[object, str], Any] = rule_policy.read_row_field,
    derive_rule_status_from_row: Callable[[object], str] = rule_policy.derive_rule_status_from_row,
    is_transition_allowed: Callable[..., bool],
    resolve_current_rule_version: Callable[..., Any],
    compile_rule_to_intermediate_model: Callable[..., dict[str, Any]],
    persist_compiler_artifact: Callable[..., Any],
    persist_validation_artifact_from_compiler: Callable[..., Any],
    set_span_attributes: Callable[[Any, Any], None],
    log_event: Callable[..., None],
    logger: logging.Logger,
) -> dict[str, Any]:
    now = current_time or (lambda: datetime.now(UTC))
    parsed_effective_at = parse_effective_at_param(command.effective_at)
    if parsed_effective_at is not None and parsed_effective_at > now():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "downstream_unavailable",
                "service": "lifecycle-scheduler",
                "message": "lifecycle-scheduler is unavailable",
            },
        )

    rows = await repository.list_rule_records(
        workspace=None,
        include_deleted=False,
        is_template=False,
        limit=500,
        offset=0,
    )
    current_row = next(
        (row for row in rows if str(read_row_field(row, "id") or "") == str(command.rule_id)),
        None,
    )
    if current_row is None:
        raise HTTPException(status_code=404, detail=f"Rule '{command.rule_id}' not found")

    current_status = derive_rule_status_from_row(current_row)
    granted_scopes = [str(scope).strip() for scope in command.granted_scopes or [] if str(scope).strip()]
    if not is_transition_allowed(
        entity="rule",
        from_status=current_status,
        to_status="activated",
        granted_scopes=granted_scopes,
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Transition '{current_status}' -> 'activated' is not allowed",
        )

    try:
        payload = await repository.activate_rule_record(command.rule_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if payload is None:
        set_span_attributes(span, rule_found=False)
        log_event(
            logger,
            "compiler.activate.not_found",
            level="warning",
            component="rule-compiler",
            ruleId=command.rule_id,
        )
        raise HTTPException(status_code=404, detail=f"Rule '{command.rule_id}' not found")

    log_event(
        logger,
        "compiler.activate.start",
        component="rule-compiler",
        ruleId=command.rule_id,
    )
    entity = await repository.get_rule_by_id(command.rule_id)
    set_span_attributes(span, rule_found=entity is not None)
    if entity is not None:
        version = await resolve_current_rule_version(repository, command.rule_id)
        rule_version_id = str(version.id or "latest") if version else "latest"
        set_span_attributes(span, rule_version_id=rule_version_id)
        autopublish_target_engine, _ = rule_autopublish_policy.resolve_rule_autopublish_target_engine(entity)
        set_span_attributes(span, autopublish_target_engine=autopublish_target_engine)
        expression = (entity.expression or "").strip()
        check_type = str(getattr(entity, "check_type", None) or getattr(entity, "checkType", None) or "").strip()
        if not expression and not check_type:
            intermediate_model = {
                "artifactKey": f"rule::{command.rule_id}::version::{rule_version_id}::custom-query",
                "compilerVersion": "unknown",
                "schemaVersion": "1.1.0",
                "target": "dsl",
                "rule": {
                    "id": command.rule_id,
                    "version_id": rule_version_id,
                },
                "filter": {
                    "source": "",
                    "normalized": "",
                    "predicates": [],
                    "logical_operators": [],
                    "alias_expectations": [],
                    "ast": None,
                },
                "join": None,
                "execution_contract": {
                    "engine_target": "dq-engine",
                    "input_format": "dq.intermediate-model.v1",
                    "compatibility_policy": {
                        "schema_versioning": "semver",
                        "compiler_versioning": "dq-semver",
                        "supported_schema_series": "1.x.x",
                        "minor_version_backward_compatible": True,
                    },
                    "traceability": {
                        "rule_id": command.rule_id,
                        "rule_version_id": rule_version_id,
                        "artifact_key": f"rule::{command.rule_id}::version::{rule_version_id}::custom-query",
                        "compiler_version": "unknown",
                        "schema_version": "1.1.0",
                    },
                    "required_execution_result_fields": ["artifactKey", "ruleId", "ruleVersionId", "executionId", "executedAt", "resultStatus"],
                },
                "diagnostics": [],
                "compilable": True,
                "summary": {"errors": 0, "warnings": 0},
            }
        else:
            intermediate_model = compile_rule_to_intermediate_model(
                rule_id=command.rule_id,
                rule_version_id=rule_version_id,
                filter_expression=expression,
            )
        log_event(
            logger,
            "compiler.compile.complete",
            component="rule-compiler",
            ruleId=command.rule_id,
            ruleVersionId=rule_version_id,
        )
        try:
            await persist_compiler_artifact(
                repository,
                rule_id=command.rule_id,
                filter_expression=expression,
                intermediate_model=intermediate_model,
            )
            log_event(
                logger,
                "compiler.artifact.persist",
                component="rule-compiler",
                ruleId=command.rule_id,
            )
        except LookupError:
            pass

        if command.auto_publish_request is not None:
            if autopublish_target_engine == "gx":
                log_event(
                    logger,
                    "compiler.gx.auto_publish.start",
                    component="rule-compiler",
                    ruleId=command.rule_id,
                    dataObjectId=command.auto_publish_request.dataObjectId,
                    datasetId=command.auto_publish_request.datasetId,
                    dataProductId=command.auto_publish_request.dataProductId,
                    sourcePipeline="rule-compiler",
                )
                await persist_gx_suite_from_compiler(
                    gx_suite_repository,
                    rule_id=command.rule_id,
                    rule_version_id=rule_version_id,
                    rule=entity,
                    catalog_repository=catalog_repository,
                    intermediate_model=intermediate_model,
                    publish_request=command.auto_publish_request,
                    saved_by=command.saved_by,
                )
                await persist_validation_artifact_from_compiler(
                    validation_artifact_repository,
                    rule_id=command.rule_id,
                    rule_version_id=rule_version_id,
                    rule=entity,
                    catalog_repository=catalog_repository,
                    intermediate_model=intermediate_model,
                    publish_request=command.auto_publish_request,
                    saved_by=command.saved_by,
                )
                log_event(
                    logger,
                    "compiler.gx.auto_publish.complete",
                    component="rule-compiler",
                    ruleId=command.rule_id,
                    sourcePipeline="rule-compiler",
                )
            elif autopublish_target_engine == "sodacl":
                log_event(
                    logger,
                    "compiler.sodacl.auto_publish.start",
                    component="rule-compiler",
                    ruleId=command.rule_id,
                    dataObjectId=command.auto_publish_request.dataObjectId,
                    datasetId=command.auto_publish_request.datasetId,
                    dataProductId=command.auto_publish_request.dataProductId,
                    sourcePipeline="rule-compiler",
                )
                await persist_validation_artifact_from_compiler(
                    validation_artifact_repository,
                    rule_id=command.rule_id,
                    rule_version_id=rule_version_id,
                    rule=entity,
                    catalog_repository=catalog_repository,
                    intermediate_model=intermediate_model,
                    publish_request=command.auto_publish_request,
                    saved_by=command.saved_by,
                )
                log_event(
                    logger,
                    "compiler.sodacl.auto_publish.complete",
                    component="rule-compiler",
                    ruleId=command.rule_id,
                    sourcePipeline="rule-compiler",
                )
            else:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "rule_dsl_lowering_unsupported",
                        "message": (
                            f"DQ DSL 2.0.0 auto-publish does not yet support target_engine '{autopublish_target_engine}'."
                        ),
                        "schema_version": "2.0.0",
                        "rule_kind": getattr(getattr(entity, "dsl", None), "get", lambda *_: None)("rule", {}).get("kind")
                        if isinstance(getattr(entity, "dsl", None), dict)
                        else None,
                    },
                )

    return payload.to_payload()