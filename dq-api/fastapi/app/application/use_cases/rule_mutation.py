from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from app.application.services import compile_rule_to_intermediate_model
from app.application.services import build_sodacl_checks_from_rule_dsl_v2
from app.application.services import build_gx_expectations_from_rule_dsl_v2
from app.application.services import generate_expression_from_check_type
from app.application.services import rule_join_consistency_mapping
from app.application.services import SodaclExpectationBuildError
from app.application.services.rule_dsl_gx_lowerer import GxExpectationBuildError
from app.application.services import validate_filter_expression
from app.application.services.data_contract_resolver import JoinConsistencyContractResolver
from app.domain.entities.rule_dsl_ir import RuleDslIrDocument
from app.domain.entities.rule_dsl_ir import RuleDslIrMetricMeasure
from app.domain.entities.rule_dsl_ir import RuleDslIrRowPredicate
from app.domain.entities.rule_dsl_ir import RuleDslIrRowPredicateMeasure
from app.domain.entities.rule_dsl_ir import RuleDslIrThresholdExpectation
from app.domain.entities.rule_dsl_ir import build_rule_dsl_v2_semantic_ir
from app.domain.entities.rule_dsl_capability_registry import RULE_DSL_BACKEND_CAPABILITY_REGISTRY
from app.domain.entities.rule import build_rule_taxonomy_entity, RuleTaxonomyEntity
from app.domain.entities.rule_dsl_v2 import RuleDslV2Document
from app.domain.entities import rule_policy
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import RulesRepository


_RULE_DSL_V1_SCHEMA_VERSION = "1.0.0"
_RULE_DSL_V2_SCHEMA_VERSION = "2.0.0"
_RULE_DSL_V2_TARGET_ENGINES = ("gx", "sodacl")
_RULE_DSL_V2_OPT_IN_CONFIG_KEY = "feature_rule_dsl_v2"
_RULE_DSL_TOP_LEVEL_RUNTIME_FIELDS = {
    "aliasMappings",
    "alias_mappings",
    "checkType",
    "check_type",
    "checkTypeParams",
    "check_type_params",
    "expression",
    "filterExpression",
    "filter_expression",
    "joinConditions",
    "join_conditions",
    "manualExpressionOverride",
    "manual_expression_override",
    "reusableFilterIds",
    "reusable_filter_ids",
    "reusableJoinId",
    "reusable_join_id",
}


@dataclass(slots=True)
class RuleMutationCommand:
    name: str
    description: str | None = None
    comments: str | None = None
    dimension: str = ""
    active: bool = False
    workspace: str | None = None
    workspace_id: str | None = None
    generated: bool | None = None
    is_template: bool = False
    template_id: str | None = None
    suggestion_id: str | None = None
    ai_output: bool = False
    dsl: dict[str, Any] = field(default_factory=dict)
    taxonomy: dict[str, Any] = field(default_factory=dict)


def _require_mapping(value: Any, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail=f"{field_name} must be an object")
    return dict(value)


def _require_list_of_dicts(value: Any, *, field_name: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise HTTPException(status_code=400, detail=f"{field_name} must be an array of objects")
    return [dict(item) for item in value]


def _read_mapping_value(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _normalize_rule_taxonomy_payload(
    *,
    command: RuleMutationCommand,
    workspace_id: str,
    normalized_dsl: dict[str, Any],
    check_type: str | None,
    owner_fallback: str | None,
    existing_taxonomy: dict[str, Any] | None,
) -> dict[str, Any]:
    explicit_taxonomy = RuleTaxonomyEntity.model_validate(command.taxonomy or {})
    previous_taxonomy = RuleTaxonomyEntity.model_validate(existing_taxonomy or {})
    derived_taxonomy = build_rule_taxonomy_entity(
        workspace=workspace_id,
        created_by=owner_fallback,
        check_type=check_type,
        dsl=normalized_dsl,
    )
    normalized_taxonomy = RuleTaxonomyEntity(
        type=explicit_taxonomy.type or derived_taxonomy.type or previous_taxonomy.type,
        severity=explicit_taxonomy.severity or derived_taxonomy.severity or previous_taxonomy.severity,
        domain=explicit_taxonomy.domain or derived_taxonomy.domain or previous_taxonomy.domain,
        owner=
            explicit_taxonomy.owner
            or explicit_taxonomy.data_steward
            or explicit_taxonomy.domain_owner
            or explicit_taxonomy.technical_owner
            or previous_taxonomy.owner
            or derived_taxonomy.owner
            or owner_fallback,
        data_steward=
            explicit_taxonomy.data_steward
            or explicit_taxonomy.owner
            or previous_taxonomy.data_steward
            or derived_taxonomy.data_steward
            or owner_fallback,
        domain_owner=explicit_taxonomy.domain_owner or previous_taxonomy.domain_owner or derived_taxonomy.domain_owner,
        technical_owner=explicit_taxonomy.technical_owner or previous_taxonomy.technical_owner or derived_taxonomy.technical_owner,
        sla_scope=explicit_taxonomy.sla_scope or derived_taxonomy.sla_scope or previous_taxonomy.sla_scope,
        execution_target=(
            explicit_taxonomy.execution_target
            or derived_taxonomy.execution_target
            or previous_taxonomy.execution_target
        ),
    )
    return normalized_taxonomy.model_dump(mode="python", exclude_none=True)


def _validation_issues_from_pydantic(exc: ValidationError) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item in exc.errors():
        location = ".".join(str(part) for part in item.get("loc") or ()) or "dsl"
        issues.append(
            {
                "field": location,
                "message": str(item.get("msg") or "Invalid value"),
                "type": str(item.get("type") or "validation_error"),
            }
        )
    return issues


def _normalize_rule_dsl_v1_contract(contract: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    schema_version = str(_read_mapping_value(contract, "schemaVersion", "schema_version") or "").strip()
    if schema_version != _RULE_DSL_V1_SCHEMA_VERSION:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported DQ DSL schemaVersion '{schema_version}'. "
                f"Supported versions: {_RULE_DSL_V1_SCHEMA_VERSION}, {_RULE_DSL_V2_SCHEMA_VERSION}"
            ),
        )

    source = _require_mapping(_read_mapping_value(contract, "source"), field_name="dsl.source")
    kind = str(source.get("kind") or "").strip()
    if kind not in {"filter_expression", "check_type"}:
        raise HTTPException(status_code=400, detail="dsl.source.kind must be 'filter_expression' or 'check_type'")

    join_conditions = _require_list_of_dicts(
        _read_mapping_value(source, "joinConditions", "join_conditions"),
        field_name="dsl.source.joinConditions",
    )
    alias_mappings = _require_mapping(
        _read_mapping_value(source, "aliasMappings", "alias_mappings") or {},
        field_name="dsl.source.aliasMappings",
    )
    reusable_join_id = str(_read_mapping_value(source, "reusableJoinId", "reusable_join_id") or "").strip() or None
    reusable_filter_ids_value = _read_mapping_value(source, "reusableFilterIds", "reusable_filter_ids") or []
    if not isinstance(reusable_filter_ids_value, list) or any(not isinstance(item, str) for item in reusable_filter_ids_value):
        raise HTTPException(status_code=400, detail="dsl.source.reusableFilterIds must be an array of strings")
    reusable_filter_ids = [str(item).strip() for item in reusable_filter_ids_value if str(item).strip()]

    normalized_source: dict[str, Any] = {
        "kind": kind,
        "joinConditions": join_conditions,
        "aliasMappings": alias_mappings,
        "reusableJoinId": reusable_join_id,
        "reusableFilterIds": reusable_filter_ids,
    }
    source_details: dict[str, Any] = {
        "schema_version": schema_version,
        "kind": kind,
        "join_conditions": join_conditions,
        "alias_mappings": alias_mappings,
        "reusable_join_id": reusable_join_id,
        "reusable_filter_ids": reusable_filter_ids,
    }

    if kind == "filter_expression":
        expression = str(source.get("expression") or "").strip()
        if not expression:
            raise HTTPException(status_code=400, detail="dsl.source.expression is required for filter_expression DSL")
        normalized_source["expression"] = expression
        source_details["expression"] = expression
        return {"schemaVersion": schema_version, "source": normalized_source}, source_details

    check_type = str(_read_mapping_value(source, "checkType", "check_type") or "").strip().upper()
    if not check_type:
        raise HTTPException(status_code=400, detail="dsl.source.checkType is required for check_type DSL")
    check_type_params = _require_mapping(
        _read_mapping_value(source, "checkTypeParams", "check_type_params"),
        field_name="dsl.source.checkTypeParams",
    )
    normalized_source["checkType"] = check_type
    normalized_source["checkTypeParams"] = check_type_params
    source_details["check_type"] = check_type
    source_details["check_type_params"] = check_type_params

    manual_override_raw = _read_mapping_value(source, "manualExpressionOverride", "manual_expression_override")
    if manual_override_raw is not None:
        manual_override = _require_mapping(manual_override_raw, field_name="dsl.source.manualExpressionOverride")
        manual_expression = str(manual_override.get("expression") or "").strip()
        if not manual_expression:
            raise HTTPException(status_code=400, detail="dsl.source.manualExpressionOverride.expression is required")
        confirmed = bool(manual_override.get("confirmed"))
        normalized_source["manualExpressionOverride"] = {
            "expression": manual_expression,
            "confirmed": confirmed,
        }
        source_details["manual_expression_override"] = {
            "expression": manual_expression,
            "confirmed": confirmed,
        }

    return {"schemaVersion": schema_version, "source": normalized_source}, source_details


def _normalize_rule_dsl_v2_contract(contract: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    schema_version = str(_read_mapping_value(contract, "schema_version", "schemaVersion") or "").strip()
    if schema_version != _RULE_DSL_V2_SCHEMA_VERSION:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported DQ DSL schemaVersion '{schema_version}'. "
                f"Supported versions: {_RULE_DSL_V1_SCHEMA_VERSION}, {_RULE_DSL_V2_SCHEMA_VERSION}"
            ),
        )

    rule = _require_mapping(_read_mapping_value(contract, "rule"), field_name="dsl.rule")
    try:
        semantic_model = RuleDslV2Document.model_validate({
            "schema_version": schema_version,
            "rule": rule,
        })
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_rule_dsl",
                "message": "DQ DSL 2.0.0 contract is invalid",
                "validation_errors": _validation_issues_from_pydantic(exc),
            },
        ) from exc

    normalized_dsl = semantic_model.model_dump(mode="python", by_alias=True, exclude_none=True)
    semantic_ir = build_rule_dsl_v2_semantic_ir(semantic_model=semantic_model)
    return normalized_dsl, {
        "schema_version": schema_version,
        "semantic_model": semantic_model,
        "semantic_ir": semantic_ir,
        "reusable_join_id": semantic_model.rule.reusableJoinId,
        "reusable_filter_ids": list(semantic_model.rule.reusableFilterIds),
    }


def _normalize_rule_dsl_contract(dsl: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = _require_mapping(dsl, field_name="dsl")
    schema_version = str(_read_mapping_value(contract, "schemaVersion", "schema_version") or "").strip()
    _raise_if_rule_dsl_contract_shape_is_mixed(contract=contract, schema_version=schema_version)
    if schema_version == _RULE_DSL_V1_SCHEMA_VERSION:
        return _normalize_rule_dsl_v1_contract(contract)
    if schema_version == _RULE_DSL_V2_SCHEMA_VERSION:
        return _normalize_rule_dsl_v2_contract(contract)
    raise HTTPException(
        status_code=400,
        detail=(
            f"Unsupported DQ DSL schemaVersion '{schema_version}'. "
            f"Supported versions: {_RULE_DSL_V1_SCHEMA_VERSION}, {_RULE_DSL_V2_SCHEMA_VERSION}"
        ),
    )


def _read_rule_dsl_schema_version(dsl: dict[str, Any]) -> str:
    if not isinstance(dsl, dict):
        return ""
    return str(_read_mapping_value(dsl, "schemaVersion", "schema_version") or "").strip()


def _raise_if_rule_dsl_contract_shape_is_mixed(*, contract: dict[str, Any], schema_version: str) -> None:
    invalid_fields: list[str] = []
    if schema_version == _RULE_DSL_V1_SCHEMA_VERSION and "rule" in contract:
        invalid_fields.append("dsl.rule")
    if schema_version == _RULE_DSL_V2_SCHEMA_VERSION and "source" in contract:
        invalid_fields.append("dsl.source")
    invalid_fields.extend(
        f"dsl.{key}"
        for key in sorted(_RULE_DSL_TOP_LEVEL_RUNTIME_FIELDS)
        if key in contract
    )
    if not invalid_fields:
        return

    raise HTTPException(
        status_code=400,
        detail={
            "error": "mixed_rule_dsl_contract",
            "message": "DQ DSL payload must use exactly one schema-version contract without embedded compatibility fields.",
            "schema_version": schema_version or None,
            "fields": invalid_fields,
        },
    )


def _raise_if_rule_dsl_v2_not_enabled(*, config_repository: AppConfigRepository) -> None:
    try:
        app_config = config_repository.get_app_config()
    except AttributeError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "rule_dsl_v2_gate_unavailable",
                "message": "DQ DSL 2.0.0 ingestion requires the app-config repository.",
                "schema_version": _RULE_DSL_V2_SCHEMA_VERSION,
                "config_key": _RULE_DSL_V2_OPT_IN_CONFIG_KEY,
            },
        ) from exc

    if getattr(app_config, "featureRuleDslV2", None) is True:
        return

    raise HTTPException(
        status_code=403,
        detail={
            "error": "rule_dsl_v2_not_enabled",
            "message": "DQ DSL 2.0.0 payloads require explicit feature_rule_dsl_v2 opt-in.",
            "schema_version": _RULE_DSL_V2_SCHEMA_VERSION,
            "config_key": _RULE_DSL_V2_OPT_IN_CONFIG_KEY,
        },
    )


def _raise_if_ai_output_mutation_requested(*, command: RuleMutationCommand) -> None:
    if not command.ai_output:
        return

    raise HTTPException(
        status_code=403,
        detail={
            "error": "ai_output_mutation_blocked",
            "message": "AI assistant output is read-only and cannot create, update, or persist rule contracts.",
            "field": "ai_output",
        },
    )


def _raise_if_dsl_not_compilable(*, expression: str, join_conditions: list[dict[str, Any]]) -> None:
    intermediate_model = compile_rule_to_intermediate_model(
        rule_id="pending-rule",
        rule_version_id="pending-version",
        filter_expression=expression,
        join_definition=join_conditions if join_conditions else None,
    )
    if bool(intermediate_model.get("compilable", True)):
        return

    diagnostics = [
        {
            "code": str(item.get("code") or "DQ7_DIAGNOSTIC"),
            "severity": str(item.get("severity") or "error"),
            "message": str(item.get("message") or "DQ DSL compilation failed"),
        }
        for item in (intermediate_model.get("diagnostics") or [])
        if isinstance(item, dict)
    ]
    raise HTTPException(
        status_code=400,
        detail={
            "error": "invalid_rule_dsl",
            "message": "DQ DSL contract is not compilable",
            "diagnostics": diagnostics,
        },
    )


def _raise_if_rule_dsl_v2_lowering_is_unsupported(
    *,
    semantic_ir: RuleDslIrDocument,
    message: str | None = None,
) -> None:
    raise HTTPException(
        status_code=422,
        detail={
            "error": "rule_dsl_lowering_unsupported",
            "message": message
            or (
                "DQ DSL 2.0.0 request validation and semantic normalization succeeded, "
                "but the current rule write pipeline does not yet implement runtime lowering "
                "from the semantic model to executable rule fields."
            ),
            "schema_version": _RULE_DSL_V2_SCHEMA_VERSION,
            "rule_kind": semantic_ir.rule.kind,
        },
    )


def _select_rule_dsl_v2_target_engine(*, semantic_ir: RuleDslIrDocument) -> str:
    preferred_engines = [
        str(value).strip().lower()
        for value in semantic_ir.rule.operations.preferred_engines
        if str(value).strip()
    ]
    if not preferred_engines:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message="DQ DSL 2.0.0 lowering requires at least one preferred engine.",
        )

    target_engine = preferred_engines[0]
    if target_engine not in _RULE_DSL_V2_TARGET_ENGINES:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                "DQ DSL 2.0.0 lowering currently supports only target_engine values "
                f"{', '.join(_RULE_DSL_V2_TARGET_ENGINES)}."
            ),
        )
    return target_engine


def _raise_if_rule_dsl_v2_target_cannot_preserve_semantics(*, semantic_ir: RuleDslIrDocument, target_engine: str) -> None:
    rule = semantic_ir.rule
    preferred_engines = {
        str(value).strip().lower()
        for value in rule.operations.preferred_engines
        if str(value).strip()
    }

    if target_engine not in preferred_engines:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                f"DQ DSL 2.0.0 lowering requires target_engine '{target_engine}', but "
                "dsl.rule.operations.preferred_engines does not include it."
            ),
        )

    capability_entry = RULE_DSL_BACKEND_CAPABILITY_REGISTRY.get_entry(rule.kind, target_engine)
    if capability_entry.support == "no":
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                f"DQ DSL 2.0.0 lowering cannot preserve rule.kind = '{rule.kind}' on "
                f"target_engine '{target_engine}'."
            ),
        )

    if rule.operations.fail_if_not_native and capability_entry.support != "native":
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                f"DQ DSL 2.0.0 lowering requires native support on target_engine '{target_engine}' "
                "because dsl.rule.operations.fail_if_not_native is true."
            ),
        )


def _validate_rule_dsl_v2_predicate(
    *,
    predicate: RuleDslIrRowPredicate,
    semantic_ir: RuleDslIrDocument,
    field_name: str,
) -> str:
    if predicate.language != "dq_predicate":
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                f"DQ DSL 2.0.0 lowering currently supports only {field_name}.language = "
                "'dq_predicate'."
            ),
        )

    expression = str(predicate.expression or "").strip()
    validation_error = validate_filter_expression(expression)
    if validation_error:
        raise HTTPException(status_code=400, detail=validation_error)
    return expression


def _rule_dsl_v2_scope_filter_expression(
    *,
    semantic_ir: RuleDslIrDocument,
    allow_row_filter: bool,
) -> str | None:
    scope = semantic_ir.rule.scope
    unsupported_scope_features: list[str] = []
    if scope.join is not None:
        unsupported_scope_features.append("scope.join")
    if scope.grouping is not None:
        unsupported_scope_features.append("scope.grouping")
    if scope.time_window is not None:
        unsupported_scope_features.append("scope.time_window")
    if scope.comparison is not None:
        unsupported_scope_features.append("scope.comparison")
    if unsupported_scope_features:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                "DQ DSL 2.0.0 lowering does not yet support "
                + ", ".join(unsupported_scope_features)
                + "."
            ),
        )

    if scope.row_filter is None:
        return None
    if not allow_row_filter:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message="DQ DSL 2.0.0 lowering does not yet support scope.row_filter for this rule kind.",
        )
    return _validate_rule_dsl_v2_predicate(
        predicate=scope.row_filter,
        semantic_ir=semantic_ir,
        field_name="dsl.rule.scope.row_filter",
    )


def _wrap_rule_dsl_v2_scope_filter(*, scope_filter_expression: str | None, base_expression: str) -> str:
    if not scope_filter_expression:
        return base_expression
    return f"NOT ({scope_filter_expression}) OR ({base_expression})"


def _validate_rule_dsl_v2_reference_scope(*, semantic_ir: RuleDslIrDocument) -> tuple[str, str, str | None, str]:
    scope = semantic_ir.rule.scope
    unsupported_scope_features: list[str] = []
    if scope.dataset is not None:
        unsupported_scope_features.append("scope.dataset")
    if scope.row_filter is not None:
        unsupported_scope_features.append("scope.row_filter")
    if scope.join is not None:
        unsupported_scope_features.append("scope.join")
    if scope.grouping is not None:
        unsupported_scope_features.append("scope.grouping")
    if scope.time_window is not None:
        unsupported_scope_features.append("scope.time_window")
    if unsupported_scope_features:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                "DQ DSL 2.0.0 reference_assertion lowering does not yet support "
                + ", ".join(unsupported_scope_features)
                + "."
            ),
        )

    comparison = scope.comparison
    if comparison is None:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message="DQ DSL 2.0.0 reference_assertion lowering requires scope.comparison.",
        )
    if len(comparison.join_keys) != 1:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                "DQ DSL 2.0.0 reference_assertion lowering currently supports exactly one "
                "scope.comparison.join_key."
            ),
        )

    join_key = comparison.join_keys[0]
    ref_version_id = str(comparison.right.data_object_version_id or "").strip()
    if not ref_version_id:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                "DQ DSL 2.0.0 reference_assertion lowering requires "
                "scope.comparison.right.data_object_version_id."
            ),
        )

    return (
        join_key.left_column,
        join_key.right_column,
        str(comparison.right.data_object_id or "").strip() or None,
        ref_version_id,
    )


def _rule_dsl_v2_subject_columns(
    *,
    semantic_ir: RuleDslIrDocument,
    field_name: str,
) -> list[str]:
    subject = semantic_ir.rule.measure.subject if isinstance(semantic_ir.rule.measure, RuleDslIrMetricMeasure) else None
    if subject is None:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=f"DQ DSL 2.0.0 lowering requires {field_name}.",
        )

    columns: list[str] = []
    if subject.column:
        column = str(subject.column).strip()
        if column:
            columns.append(column)
    if subject.columns:
        columns.extend(str(value).strip() for value in subject.columns if str(value).strip())
    if not columns:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=f"DQ DSL 2.0.0 lowering requires {field_name}.",
        )
    return columns


def _rule_dsl_v2_threshold_percentage(
    *,
    semantic_ir: RuleDslIrDocument,
    expectation: RuleDslIrThresholdExpectation,
    field_name: str,
) -> float:
    if expectation.operator == "between":
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                "DQ DSL 2.0.0 lowering does not yet support threshold operator 'between' "
                f"for {field_name}."
            ),
        )

    try:
        value = float(expectation.value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name}.value must be numeric") from exc

    if value < 0.0 or value > 100.0:
        raise HTTPException(status_code=400, detail=f"{field_name}.value must be between 0 and 100")
    return value


def _rule_dsl_v2_threshold_count(
    *,
    semantic_ir: RuleDslIrDocument,
    expectation: RuleDslIrThresholdExpectation,
    field_name: str,
) -> float:
    if expectation.unit not in {None, "count"}:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                "DQ DSL 2.0.0 lowering for count-based metrics currently supports only "
                f"{field_name}.unit = 'count'."
            ),
        )

    try:
        value = float(expectation.value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name}.value must be numeric") from exc

    if value < 0.0:
        raise HTTPException(status_code=400, detail=f"{field_name}.value must be greater than or equal to 0")
    return value


_AGGREGATE_NUMERIC_METRICS = {
    "min",
    "max",
    "avg",
    "sum",
    "stddev",
}

_AGGREGATE_COUNT_METRICS = {"distinct_count"}


def _rule_dsl_v2_numeric_threshold_value(
    *,
    semantic_ir: RuleDslIrDocument,
    raw_value: Any,
    field_name: str,
) -> int | float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be numeric") from exc
    if value.is_integer():
        return int(value)
    return value


def _rule_dsl_v2_non_negative_count_value(
    *,
    semantic_ir: RuleDslIrDocument,
    raw_value: Any,
    field_name: str,
) -> int:
    value = _rule_dsl_v2_numeric_threshold_value(
        semantic_ir=semantic_ir,
        raw_value=raw_value,
        field_name=field_name,
    )
    if isinstance(value, float) and not value.is_integer():
        raise HTTPException(status_code=400, detail=f"{field_name} must be a non-negative whole number")
    return int(value)


def _lower_rule_dsl_v2_aggregate_metric_threshold(
    *,
    semantic_ir: RuleDslIrDocument,
    metric: str,
    expectation: RuleDslIrThresholdExpectation,
) -> dict[str, Any]:
    if metric in _AGGREGATE_NUMERIC_METRICS:
        allowed_units = {None, "raw"}
    elif metric in _AGGREGATE_COUNT_METRICS:
        allowed_units = {None, "count"}
    else:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                f"DQ DSL 2.0.0 metric_threshold lowering does not yet support measure.metric = '{metric}'."
            ),
        )

    if expectation.unit not in allowed_units:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                f"DQ DSL 2.0.0 metric_threshold lowering for measure.metric = '{metric}' supports only expectation.unit values in {sorted(value for value in allowed_units if value is not None) or ['None']}."
            ),
        )

    if expectation.operator == "between":
        min_value = expectation.min_value
        max_value = expectation.max_value
        if metric in _AGGREGATE_COUNT_METRICS:
            min_number = _rule_dsl_v2_non_negative_count_value(
                semantic_ir=semantic_ir,
                raw_value=min_value,
                field_name="dsl.rule.expectation.min_value",
            )
            max_number = _rule_dsl_v2_non_negative_count_value(
                semantic_ir=semantic_ir,
                raw_value=max_value,
                field_name="dsl.rule.expectation.max_value",
            )
        else:
            min_number = _rule_dsl_v2_numeric_threshold_value(
                semantic_ir=semantic_ir,
                raw_value=min_value,
                field_name="dsl.rule.expectation.min_value",
            )
            max_number = _rule_dsl_v2_numeric_threshold_value(
                semantic_ir=semantic_ir,
                raw_value=max_value,
                field_name="dsl.rule.expectation.max_value",
            )
        if max_number < min_number:
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    f"DQ DSL 2.0.0 metric_threshold lowering for measure.metric = '{metric}' requires expectation.max_value >= expectation.min_value."
                ),
            )
        return {}

    if expectation.operator not in {"gt", "gte", "lt", "lte"}:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                f"DQ DSL 2.0.0 metric_threshold lowering for measure.metric = '{metric}' currently supports only operators gt, gte, lt, lte, and between."
            ),
        )

    threshold_value = expectation.value
    if metric in _AGGREGATE_COUNT_METRICS:
        _rule_dsl_v2_non_negative_count_value(
            semantic_ir=semantic_ir,
            raw_value=threshold_value,
            field_name="dsl.rule.expectation.value",
        )
    else:
        _rule_dsl_v2_numeric_threshold_value(
            semantic_ir=semantic_ir,
            raw_value=threshold_value,
            field_name="dsl.rule.expectation.value",
        )
    return {}


def _rule_dsl_v2_failure_percent_to_success_threshold(*, operator: str, failure_percent: float) -> tuple[str, float]:
    success_threshold = 100.0 - failure_percent
    operator_map = {
        "lt": "gt",
        "lte": "gte",
        "gt": "lt",
        "gte": "lte",
    }
    return operator_map[operator], success_threshold


def _rule_dsl_v2_day_duration(
    *,
    semantic_ir: RuleDslIrDocument,
    expectation: RuleDslIrThresholdExpectation,
    field_name: str,
) -> int:
    if expectation.operator != "lte":
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                "DQ DSL 2.0.0 freshness_assertion lowering currently supports only "
                f"{field_name}.operator = 'lte'."
            ),
        )
    if expectation.unit != "duration":
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                "DQ DSL 2.0.0 freshness_assertion lowering currently supports only "
                f"{field_name}.unit = 'duration'."
            ),
        )

    raw_value = str(expectation.value or "").strip().upper()
    match = re.fullmatch(r"P(\d+)D", raw_value)
    if match is None:
        _raise_if_rule_dsl_v2_lowering_is_unsupported(
            semantic_ir=semantic_ir,
            message=(
                "DQ DSL 2.0.0 freshness_assertion lowering currently supports only ISO-8601 "
                f"day durations like 'P3D' for {field_name}.value."
            ),
        )

    return int(match.group(1))


def _rule_dsl_v2_count_value(
    *,
    raw_value: Any,
    field_name: str,
) -> int:
    try:
        number = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be numeric") from exc
    if number < 0.0 or not number.is_integer():
        raise HTTPException(status_code=400, detail=f"{field_name} must be a non-negative whole number")
    return int(number)


def _lower_rule_dsl_v2_to_runtime(*, semantic_ir: RuleDslIrDocument) -> dict[str, Any]:
    rule = semantic_ir.rule

    if rule.kind == "metric_threshold":
        if not isinstance(rule.measure, RuleDslIrMetricMeasure):
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message="DQ DSL 2.0.0 metric_threshold lowering requires measure.type = 'metric'.",
            )
        if not isinstance(rule.expectation, RuleDslIrThresholdExpectation):
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message="DQ DSL 2.0.0 metric_threshold lowering requires expectation.type = 'threshold'.",
            )

        if rule.measure.metric == "row_count":
            scope_filter_expression = _rule_dsl_v2_scope_filter_expression(semantic_ir=semantic_ir, allow_row_filter=True)
            if rule.measure.subject is not None:
                _raise_if_rule_dsl_v2_lowering_is_unsupported(
                    semantic_ir=semantic_ir,
                    message=(
                        "DQ DSL 2.0.0 metric_threshold lowering for measure.metric = 'row_count' does not accept measure.subject."
                    ),
                )
            if rule.expectation.unit not in {None, "count"}:
                _raise_if_rule_dsl_v2_lowering_is_unsupported(
                    semantic_ir=semantic_ir,
                    message=(
                        "DQ DSL 2.0.0 metric_threshold lowering for measure.metric = 'row_count' supports only expectation.unit = 'count'."
                    ),
                )
            if rule.expectation.operator == "between":
                min_value = _rule_dsl_v2_count_value(
                    raw_value=rule.expectation.min_value,
                    field_name="dsl.rule.expectation.min_value",
                )
                max_value = _rule_dsl_v2_count_value(
                    raw_value=rule.expectation.max_value,
                    field_name="dsl.rule.expectation.max_value",
                )
                if max_value < min_value:
                    _raise_if_rule_dsl_v2_lowering_is_unsupported(
                        semantic_ir=semantic_ir,
                        message=(
                            "DQ DSL 2.0.0 metric_threshold lowering for measure.metric = 'row_count' requires expectation.maxValue >= expectation.minValue."
                        ),
                    )
                return {
                    "expression": scope_filter_expression or "1 = 1",
                    "join_conditions": [],
                    "alias_mappings": {},
                    "reusable_join_id": None,
                    "reusable_filter_ids": [],
                    "check_type": "ROW_COUNT",
                    "check_type_params": {
                        "checkType": "ROW_COUNT",
                        "operator": "between",
                        "minValue": min_value,
                        "maxValue": max_value,
                    },
                }

            if rule.expectation.operator not in {"gt", "gte", "lt", "lte"}:
                _raise_if_rule_dsl_v2_lowering_is_unsupported(
                    semantic_ir=semantic_ir,
                    message=(
                        "DQ DSL 2.0.0 metric_threshold lowering for measure.metric = 'row_count' currently supports only operators gt, gte, lt, lte, and between."
                    ),
                )

            threshold = _rule_dsl_v2_count_value(
                raw_value=rule.expectation.value,
                field_name="dsl.rule.expectation.value",
            )
            if rule.expectation.operator == "lt" and threshold == 0:
                _raise_if_rule_dsl_v2_lowering_is_unsupported(
                    semantic_ir=semantic_ir,
                    message=(
                        "DQ DSL 2.0.0 metric_threshold lowering for measure.metric = 'row_count' cannot express operator 'lt' with threshold 0."
                    ),
                )
            return {
                "expression": scope_filter_expression or "1 = 1",
                "join_conditions": [],
                "alias_mappings": {},
                "reusable_join_id": None,
                "reusable_filter_ids": [],
                "check_type": "ROW_COUNT",
                "check_type_params": {
                    "checkType": "ROW_COUNT",
                    "operator": rule.expectation.operator,
                    "threshold": threshold,
                },
            }

        if rule.measure.metric == "duplicate_count":
            _rule_dsl_v2_scope_filter_expression(semantic_ir=semantic_ir, allow_row_filter=False)
            columns = _rule_dsl_v2_subject_columns(
                semantic_ir=semantic_ir,
                field_name="measure.subject.column or measure.subject.columns",
            )
            threshold = _rule_dsl_v2_threshold_count(
                semantic_ir=semantic_ir,
                expectation=rule.expectation,
                field_name="dsl.rule.expectation",
            )
            if rule.expectation.operator != "lte" or threshold != 0.0:
                _raise_if_rule_dsl_v2_lowering_is_unsupported(
                    semantic_ir=semantic_ir,
                    message=(
                        "DQ DSL 2.0.0 metric_threshold lowering for measure.metric = 'duplicate_count' "
                        "currently requires expectation.type = 'threshold' with operator 'lte' and value 0."
                    ),
                )
            return {
                "expression": "",
                "join_conditions": [],
                "alias_mappings": {},
                "reusable_join_id": None,
                "reusable_filter_ids": [],
                "check_type": "UNIQUENESS",
                "check_type_params": {
                    "checkType": "UNIQUENESS",
                    "attributes": columns,
                },
            }

        if rule.measure.metric == "duplicate_percent":
            _rule_dsl_v2_scope_filter_expression(semantic_ir=semantic_ir, allow_row_filter=False)
            columns = _rule_dsl_v2_subject_columns(
                semantic_ir=semantic_ir,
                field_name="measure.subject.column or measure.subject.columns",
            )
            if rule.expectation.unit not in {None, "percent"}:
                _raise_if_rule_dsl_v2_lowering_is_unsupported(
                    semantic_ir=semantic_ir,
                    message=(
                        "DQ DSL 2.0.0 metric_threshold lowering for measure.metric = 'duplicate_percent' "
                        "supports only expectation.unit = 'percent'."
                    ),
                )
            threshold = _rule_dsl_v2_threshold_percentage(
                semantic_ir=semantic_ir,
                expectation=rule.expectation,
                field_name="dsl.rule.expectation",
            )
            if rule.expectation.operator != "lte" or threshold != 0.0:
                _raise_if_rule_dsl_v2_lowering_is_unsupported(
                    semantic_ir=semantic_ir,
                    message=(
                        "DQ DSL 2.0.0 metric_threshold lowering for measure.metric = 'duplicate_percent' "
                        "currently requires expectation.type = 'threshold' with operator 'lte' and value 0."
                    ),
                )
            return {
                "expression": "",
                "join_conditions": [],
                "alias_mappings": {},
                "reusable_join_id": None,
                "reusable_filter_ids": [],
                "check_type": "UNIQUENESS",
                "check_type_params": {
                    "checkType": "UNIQUENESS",
                    "attributes": columns,
                },
            }

        if rule.measure.metric in _AGGREGATE_NUMERIC_METRICS or rule.measure.metric in _AGGREGATE_COUNT_METRICS:
            _rule_dsl_v2_scope_filter_expression(semantic_ir=semantic_ir, allow_row_filter=False)
            subject = rule.measure.subject
            column = str(subject.column if subject is not None else "" or "").strip()
            if not column:
                _raise_if_rule_dsl_v2_lowering_is_unsupported(
                    semantic_ir=semantic_ir,
                    message=(
                        f"DQ DSL 2.0.0 metric_threshold lowering requires measure.subject.column for measure.metric = '{rule.measure.metric}'."
                    ),
                )
            if subject is not None and subject.columns:
                _raise_if_rule_dsl_v2_lowering_is_unsupported(
                    semantic_ir=semantic_ir,
                    message=(
                        f"DQ DSL 2.0.0 metric_threshold lowering does not yet support measure.subject.columns for measure.metric = '{rule.measure.metric}'."
                    ),
                )
            _lower_rule_dsl_v2_aggregate_metric_threshold(
                semantic_ir=semantic_ir,
                metric=rule.measure.metric,
                expectation=rule.expectation,
            )
            return {
                "expression": "",
                "join_conditions": [],
                "alias_mappings": {},
                "reusable_join_id": None,
                "reusable_filter_ids": [],
                "check_type": None,
                "check_type_params": None,
            }

        if rule.measure.metric == "missing_count":
            _rule_dsl_v2_scope_filter_expression(semantic_ir=semantic_ir, allow_row_filter=False)
            subject = rule.measure.subject
            column = str(subject.column if subject is not None else "" or "").strip()
            if not column:
                _raise_if_rule_dsl_v2_lowering_is_unsupported(
                    semantic_ir=semantic_ir,
                    message=(
                        "DQ DSL 2.0.0 metric_threshold lowering requires "
                        "measure.subject.column for measure.metric = 'missing_count'."
                    ),
                )
            if subject is not None and subject.columns:
                _raise_if_rule_dsl_v2_lowering_is_unsupported(
                    semantic_ir=semantic_ir,
                    message=(
                        "DQ DSL 2.0.0 metric_threshold lowering does not yet support "
                        "measure.subject.columns for measure.metric = 'missing_count'."
                    ),
                )
            threshold = _rule_dsl_v2_threshold_count(
                semantic_ir=semantic_ir,
                expectation=rule.expectation,
                field_name="dsl.rule.expectation",
            )
            if rule.expectation.operator != "lte" or threshold != 0.0:
                _raise_if_rule_dsl_v2_lowering_is_unsupported(
                    semantic_ir=semantic_ir,
                    message=(
                        "DQ DSL 2.0.0 metric_threshold lowering for measure.metric = 'missing_count' "
                        "currently requires expectation.type = 'threshold' with operator 'lte' and value 0."
                    ),
                )
            return {
                "expression": "",
                "join_conditions": [],
                "alias_mappings": {},
                "reusable_join_id": None,
                "reusable_filter_ids": [],
                "check_type": "THRESHOLD",
                "check_type_params": {
                    "checkType": "THRESHOLD",
                    "attribute": column,
                    "metric": "null_pct",
                    "operator": "gte",
                    "threshold": 100.0,
                },
            }

        if rule.measure.metric != "missing_percent":
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 metric_threshold lowering currently supports only "
                    "measure.metric = 'row_count', 'missing_percent', 'missing_count', 'duplicate_percent', 'duplicate_count', 'distinct_count', 'min', 'max', 'avg', 'sum', or 'stddev'."
                ),
            )

        _rule_dsl_v2_scope_filter_expression(semantic_ir=semantic_ir, allow_row_filter=False)

        subject = rule.measure.subject
        column = str(subject.column if subject is not None else "" or "").strip()
        if not column:
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 metric_threshold lowering requires "
                    "measure.subject.column for measure.metric = 'missing_percent'."
                ),
            )
        if subject is not None and subject.columns:
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 metric_threshold lowering does not yet support "
                    "measure.subject.columns."
                ),
            )
        if rule.expectation.unit not in {None, "percent"}:
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 metric_threshold lowering for measure.metric = 'missing_percent' "
                    "supports only expectation.unit = 'percent'."
                ),
            )

        threshold = _rule_dsl_v2_threshold_percentage(
            semantic_ir=semantic_ir,
            expectation=rule.expectation,
            field_name="dsl.rule.expectation",
        )
        legacy_operator, legacy_threshold = _rule_dsl_v2_failure_percent_to_success_threshold(
            operator=rule.expectation.operator,
            failure_percent=threshold,
        )
        return {
            "expression": "",
            "join_conditions": [],
            "alias_mappings": {},
            "reusable_join_id": None,
            "reusable_filter_ids": [],
            "check_type": "THRESHOLD",
            "check_type_params": {
                "checkType": "THRESHOLD",
                "attribute": column,
                "metric": "null_pct",
                "operator": legacy_operator,
                "threshold": legacy_threshold,
            },
        }

    if rule.kind == "row_assertion":
        if not isinstance(rule.measure, RuleDslIrRowPredicateMeasure):
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message="DQ DSL 2.0.0 row_assertion lowering requires measure.type = 'row_predicate'.",
            )
        if not isinstance(rule.expectation, RuleDslIrThresholdExpectation):
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 row_assertion lowering currently requires expectation.type = "
                    "'threshold' with operator 'gte' and value 100."
                ),
            )
        if rule.expectation.unit not in {None, "percent"}:
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 row_assertion lowering supports only expectation.unit = 'percent'."
                ),
            )

        threshold = _rule_dsl_v2_threshold_percentage(
            semantic_ir=semantic_ir,
            expectation=rule.expectation,
            field_name="dsl.rule.expectation",
        )
        if rule.expectation.operator != "gte" or threshold != 100.0:
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 row_assertion lowering currently requires expectation.type = "
                    "'threshold' with operator 'gte' and value 100."
                ),
            )

        scope_filter_expression = _rule_dsl_v2_scope_filter_expression(
            semantic_ir=semantic_ir,
            allow_row_filter=True,
        )
        base_expression = _validate_rule_dsl_v2_predicate(
            predicate=rule.measure.predicate,
            semantic_ir=semantic_ir,
            field_name="dsl.rule.measure.predicate",
        )
        return {
            "expression": _wrap_rule_dsl_v2_scope_filter(
                scope_filter_expression=scope_filter_expression,
                base_expression=base_expression,
            ),
            "join_conditions": [],
            "alias_mappings": {},
            "reusable_join_id": None,
            "reusable_filter_ids": [],
            "check_type": None,
            "check_type_params": None,
        }

    if rule.kind == "freshness_assertion":
        if not isinstance(rule.measure, RuleDslIrMetricMeasure):
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message="DQ DSL 2.0.0 freshness_assertion lowering requires measure.type = 'metric'.",
            )
        if not isinstance(rule.expectation, RuleDslIrThresholdExpectation):
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message="DQ DSL 2.0.0 freshness_assertion lowering requires expectation.type = 'threshold'.",
            )

        _rule_dsl_v2_scope_filter_expression(semantic_ir=semantic_ir, allow_row_filter=False)

        if rule.measure.metric != "freshness_age":
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 freshness_assertion lowering currently supports only "
                    "measure.metric = 'freshness_age'."
                ),
            )

        subject = rule.measure.subject
        column = str(subject.column if subject is not None else "" or "").strip()
        if not column:
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 freshness_assertion lowering requires "
                    "measure.subject.column for measure.metric = 'freshness_age'."
                ),
            )
        if subject is not None and subject.columns:
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 freshness_assertion lowering does not yet support "
                    "measure.subject.columns."
                ),
            )

        max_days_old = _rule_dsl_v2_day_duration(
            semantic_ir=semantic_ir,
            expectation=rule.expectation,
            field_name="dsl.rule.expectation",
        )
        return {
            "expression": "",
            "join_conditions": [],
            "alias_mappings": {},
            "reusable_join_id": None,
            "reusable_filter_ids": [],
            "check_type": "FRESHNESS",
            "check_type_params": {
                "checkType": "FRESHNESS",
                "attribute": column,
                "maxDaysOld": max_days_old,
                "anchor": "now",
            },
        }

    if rule.kind == "custom_query_assertion":
        try:
            build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)
        except GxExpectationBuildError as exc:
            _raise_if_rule_dsl_v2_lowering_is_unsupported(semantic_ir=semantic_ir, message=str(exc))
        return {
            "expression": "",
            "join_conditions": [],
            "alias_mappings": {},
            "reusable_join_id": None,
            "reusable_filter_ids": [],
            "check_type": None,
            "check_type_params": None,
        }

    if rule.kind == "reference_assertion":
        if not isinstance(rule.measure, RuleDslIrMetricMeasure):
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message="DQ DSL 2.0.0 reference_assertion lowering requires measure.type = 'metric'.",
            )
        if not isinstance(rule.expectation, RuleDslIrThresholdExpectation):
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message="DQ DSL 2.0.0 reference_assertion lowering requires expectation.type = 'threshold'.",
            )
        if rule.measure.metric != "match_percent":
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 reference_assertion lowering currently supports only "
                    "measure.metric = 'match_percent'."
                ),
            )

        subject = rule.measure.subject
        subject_column = str(subject.column if subject is not None else "" or "").strip()
        if not subject_column:
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 reference_assertion lowering requires "
                    "measure.subject.column."
                ),
            )
        if subject is not None and subject.columns:
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 reference_assertion lowering does not yet support "
                    "measure.subject.columns."
                ),
            )
        if rule.expectation.unit not in {None, "percent"}:
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 reference_assertion lowering currently supports only "
                    "expectation.unit = 'percent'."
                ),
            )

        threshold = _rule_dsl_v2_threshold_percentage(
            semantic_ir=semantic_ir,
            expectation=rule.expectation,
            field_name="dsl.rule.expectation",
        )
        if rule.expectation.operator != "gte" or threshold != 100.0:
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 reference_assertion lowering currently requires "
                    "expectation.type = 'threshold' with operator 'gte' and value 100."
                ),
            )

        left_column, right_column, ref_object_id, ref_version_id = _validate_rule_dsl_v2_reference_scope(
            semantic_ir=semantic_ir,
        )
        if subject_column != left_column:
            _raise_if_rule_dsl_v2_lowering_is_unsupported(
                semantic_ir=semantic_ir,
                message=(
                    "DQ DSL 2.0.0 reference_assertion lowering requires measure.subject.column "
                    "to match scope.comparison.join_keys[0].left_column."
                ),
            )

        check_type_params: dict[str, Any] = {
            "checkType": "REFERENTIAL_INTEGRITY",
            "attribute": subject_column,
            "refDataObjectVersionId": ref_version_id,
            "refAttribute": right_column,
        }
        if ref_object_id is not None:
            check_type_params["refDataObjectId"] = ref_object_id
        return {
            "expression": "",
            "join_conditions": [],
            "alias_mappings": {},
            "reusable_join_id": None,
            "reusable_filter_ids": [],
            "check_type": "REFERENTIAL_INTEGRITY",
            "check_type_params": check_type_params,
        }

    _raise_if_rule_dsl_v2_lowering_is_unsupported(
        semantic_ir=semantic_ir,
        message=f"DQ DSL 2.0.0 lowering does not yet support rule.kind = '{rule.kind}'.",
    )


async def resolve_rule_mutation_payload(
    *,
    command: RuleMutationCommand,
    repository: RulesRepository,
    config_repository: AppConfigRepository,
    catalog_repository: DataCatalogRepository,
    contract_resolver: JoinConsistencyContractResolver,
    actor_id: str,
    workspace_id: str,
    exclude_rule_id: str | None = None,
    existing_taxonomy: dict[str, Any] | None = None,
    owner_fallback: str | None = None,
) -> dict[str, Any]:
    _raise_if_ai_output_mutation_requested(command=command)

    contract = _require_mapping(command.dsl, field_name="dsl")
    dsl_schema_version = _read_rule_dsl_schema_version(contract)
    _raise_if_rule_dsl_contract_shape_is_mixed(contract=contract, schema_version=dsl_schema_version)

    if dsl_schema_version == _RULE_DSL_V2_SCHEMA_VERSION:
        _raise_if_rule_dsl_v2_not_enabled(config_repository=config_repository)

    await rule_policy.ensure_unique_rule_name(
        repository=repository,
        name=command.name,
        workspace=workspace_id,
        exclude_rule_id=exclude_rule_id,
    )

    normalized_dsl, source_details = _normalize_rule_dsl_contract(command.dsl)
    dsl_schema_version = str(source_details.get("schema_version") or "").strip()

    if dsl_schema_version == _RULE_DSL_V2_SCHEMA_VERSION:
        semantic_ir = source_details.get("semantic_ir")
        if not isinstance(semantic_ir, RuleDslIrDocument):
            raise HTTPException(status_code=500, detail="DQ DSL 2.0.0 normalization produced no semantic IR")
        target_engine = _select_rule_dsl_v2_target_engine(semantic_ir=semantic_ir)
        _raise_if_rule_dsl_v2_target_cannot_preserve_semantics(semantic_ir=semantic_ir, target_engine=target_engine)
        if target_engine == "sodacl":
            try:
                build_sodacl_checks_from_rule_dsl_v2(semantic_ir=semantic_ir)
            except SodaclExpectationBuildError as exc:
                _raise_if_rule_dsl_v2_lowering_is_unsupported(semantic_ir=semantic_ir, message=str(exc))
        reusable_join_id = source_details.get("reusable_join_id")
        reusable_filter_ids = source_details.get("reusable_filter_ids")
        source_details.update(_lower_rule_dsl_v2_to_runtime(semantic_ir=semantic_ir))
        source_details["reusable_join_id"] = reusable_join_id
        source_details["reusable_filter_ids"] = reusable_filter_ids

    expression = str(source_details.get("expression") or "").strip()
    join_conditions = source_details["join_conditions"]
    alias_mappings = source_details["alias_mappings"]
    reusable_join_id = source_details["reusable_join_id"]
    reusable_filter_ids = source_details["reusable_filter_ids"]
    check_type = str(source_details.get("check_type") or "").strip() or None
    effective_check_type_params = source_details.get("check_type_params")

    if check_type and effective_check_type_params:
        effective_check_type_params = rule_policy.apply_threshold_default_from_config(
            check_type=check_type,
            check_type_params=effective_check_type_params,
            config_repository=config_repository,
        )
        effective_check_type_params = rule_policy.apply_referential_integrity_version_mapping(
            check_type=check_type,
            check_type_params=effective_check_type_params,
            catalog_repository=catalog_repository,
        )
        contract_cache_ttl_seconds = 0
        if check_type.upper() == "JOIN_CONSISTENCY":
            contract_cache_ttl_seconds = rule_policy.resolve_openmetadata_contract_cache_ttl_seconds(config_repository)
        effective_check_type_params = await rule_join_consistency_mapping.apply_join_consistency_contract_mapping(
            check_type=check_type,
            check_type_params=effective_check_type_params,
            catalog_repository=catalog_repository,
            contract_resolver=contract_resolver,
            contract_cache_ttl_seconds=contract_cache_ttl_seconds,
        )
        effective_check_type_params = rule_policy.validate_rule_check_type_params(
            check_type=check_type,
            check_type_params=effective_check_type_params,
        )

    manual_override = source_details.get("manual_expression_override")
    manual_override_requested = bool(manual_override)
    if manual_override_requested and not bool(manual_override.get("confirmed")):
        raise HTTPException(status_code=400, detail="Manual expression override requires explicit confirmation")

    if check_type and effective_check_type_params and not manual_override_requested:
        preserved_expression = expression
        try:
            generated_expression = generate_expression_from_check_type(check_type, effective_check_type_params)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if check_type == "ROW_COUNT" and preserved_expression and preserved_expression != "1 = 1":
            expression = preserved_expression
        else:
            expression = generated_expression
        if dsl_schema_version == _RULE_DSL_V1_SCHEMA_VERSION:
            normalized_dsl["source"]["checkType"] = check_type
            normalized_dsl["source"]["checkTypeParams"] = effective_check_type_params
    else:
        if manual_override_requested:
            expression = str(manual_override.get("expression") or "").strip()
        validation_error = None
        if not (dsl_schema_version == _RULE_DSL_V2_SCHEMA_VERSION and check_type is None and not expression):
            validation_error = validate_filter_expression(expression)
        if validation_error:
            raise HTTPException(status_code=400, detail=validation_error)

    if not (dsl_schema_version == _RULE_DSL_V2_SCHEMA_VERSION and check_type is None and not expression):
        _raise_if_dsl_not_compilable(expression=expression, join_conditions=join_conditions)

    manual_override_by = actor_id if manual_override_requested else None
    manual_override_at = datetime.now(timezone.utc) if manual_override_requested else None

    if manual_override_requested:
        normalized_dsl["source"]["manualExpressionOverride"] = {
            "expression": expression,
            "confirmed": True,
        }

    normalized_taxonomy = _normalize_rule_taxonomy_payload(
        command=command,
        workspace_id=workspace_id,
        normalized_dsl=normalized_dsl,
        check_type=check_type,
        owner_fallback=owner_fallback or actor_id,
        existing_taxonomy=existing_taxonomy,
    )

    return {
        "name": command.name,
        "description": command.description,
        "comments": command.comments,
        "expression": expression,
        "dimension": command.dimension,
        "active": command.active,
        "dsl": normalized_dsl,
        "join_conditions": join_conditions,
        "alias_mappings": alias_mappings,
        "reusable_join_id": reusable_join_id,
        "reusable_filter_ids": reusable_filter_ids,
        "manual_override_by": manual_override_by,
        "manual_override_at": manual_override_at,
        "check_type": check_type,
        "check_type_params": effective_check_type_params,
        "taxonomy": normalized_taxonomy,
    }