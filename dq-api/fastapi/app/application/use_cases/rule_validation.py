from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Callable

from fastapi import HTTPException

from app.domain.entities import rule_policy
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import RulesRepository


@dataclass(slots=True)
class RuleValidationEvaluation:
    rule_id: str
    rule_name: str | None
    rule_version_id: str
    rule_version_number: int | None
    valid: bool
    compiled_expression: str
    inferred_aliases: list[dict[str, Any]]
    artifact_key: str | None
    compiler_version: str | None
    target: str | None
    intermediate_model: dict[str, Any]
    diagnostics: list[dict[str, Any]]
    errors: int
    warnings: int
    workspace: str | None


def load_validation_policies(config_repository: AppConfigRepository) -> list[dict[str, Any]] | None:
    app_config = config_repository.get_app_config()
    if app_config is None:
        return None

    validation_policies = getattr(app_config, "validationPolicies", None)
    if not validation_policies:
        return None

    return [
        policy.model_dump() if hasattr(policy, "model_dump") else dict(policy)
        for policy in validation_policies
    ]


async def evaluate_rule_validation(
    *,
    rule_id: str,
    repository: RulesRepository,
    data_catalog_repository: DataCatalogRepository,
    raw_policies: list[dict[str, Any]] | None,
    apply_validation_policies: Callable[[list[dict[str, Any]], list[dict[str, Any]] | None, str | None], list[dict[str, Any]]],
    compile_rule_to_intermediate_model: Callable[..., dict[str, Any]],
    infer_alias_expectations: Callable[[str], list[dict[str, Any]]],
    persist_compiler_artifact: Callable[..., Any],
    resolve_current_rule_version: Callable[..., Any],
    has_upstream_validation_issue: Callable[[list[dict[str, Any]]], bool],
    workspace_override: str | None = None,
    validated_by: str | None = None,
    persist_validation_state: bool = False,
) -> RuleValidationEvaluation:
    entity = await repository.get_rule_by_id(rule_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")

    rule_dsl = getattr(entity, "dsl", None)
    rule_kind = ""
    if isinstance(rule_dsl, dict):
        rule_kind = str(((rule_dsl.get("rule") or {}).get("kind") or "")).strip()

    rule_attributes = [
        str(item.attributeId or '').strip()
        for item in data_catalog_repository.list_rule_attributes()
        if str(item.ruleId or '').strip() == rule_id and str(item.attributeId or '').strip()
    ]
    catalog_attribute_ids = {
        str(item.id or '').strip()
        for item in data_catalog_repository.list_attributes_catalog()
        if str(item.id or '').strip()
    }
    resolvable_attribute_ids = [attribute_id for attribute_id in rule_attributes if attribute_id in catalog_attribute_ids]
    unresolved_attribute_ids = [attribute_id for attribute_id in rule_attributes if attribute_id not in catalog_attribute_ids]

    if rule_kind != "custom_query_assertion" and (not rule_attributes or not resolvable_attribute_ids):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unresolved_rule_attributes",
                "message": "Rule has no resolvable assigned attributes.",
                "rule_id": rule_id,
                "assigned_attribute_ids": rule_attributes,
                "unresolved_attribute_ids": unresolved_attribute_ids,
            },
        )

    expression = str(rule_policy.read_row_field(entity, "expression") or "").strip()
    workspace = rule_policy.read_row_field(entity, "workspace") or workspace_override
    rule_name_value = rule_policy.read_row_field(entity, "name")
    rule_name = str(rule_name_value).strip() if rule_name_value is not None else None

    version = await resolve_current_rule_version(repository, rule_id)
    rule_version_id = str(version.id or "latest") if version else "latest"
    rule_version_number = int(version.versionNumber or 0) if version and getattr(version, "versionNumber", None) is not None else None

    intermediate_model = compile_rule_to_intermediate_model(
        rule_id=rule_id,
        rule_version_id=rule_version_id,
        filter_expression=expression,
    )

    try:
        await persist_compiler_artifact(
            repository,
            rule_id=rule_id,
            filter_expression=expression,
            intermediate_model=intermediate_model,
        )
    except LookupError:
        pass

    raw_diagnostics = [
        {
            "scope": "rule",
            "severity": str(item.get("severity") or "warning"),
            "message": str(item.get("message") or ""),
            "code": str(item.get("code") or "DQ7_DIAGNOSTIC"),
        }
        for item in intermediate_model.get("diagnostics") or []
    ]
    diagnostics = apply_validation_policies(raw_diagnostics, raw_policies, workspace)

    errors = len([item for item in diagnostics if item["severity"] == "error"])
    warnings = len([item for item in diagnostics if item["severity"] == "warning"])
    valid = bool(intermediate_model.get("compilable", errors == 0))
    compiled_expression = str(intermediate_model.get("filter", {}).get("normalized") or "")
    inferred_aliases = intermediate_model.get("filter", {}).get("aliasExpectations") or infer_alias_expectations(
        compiled_expression
    )

    if persist_validation_state:
        validation_state = "valid" if valid else (
            "upstream-error" if has_upstream_validation_issue(diagnostics) else "invalid"
        )
        try:
            await repository.set_current_rule_version_validation(
                rule_id=rule_id,
                validation_status=validation_state,
                validated_by=validated_by,
            )
        except LookupError:
            pass

    return RuleValidationEvaluation(
        rule_id=rule_id,
        rule_name=rule_name,
        rule_version_id=rule_version_id,
        rule_version_number=rule_version_number,
        valid=valid,
        compiled_expression=compiled_expression,
        inferred_aliases=inferred_aliases,
        artifact_key=intermediate_model.get("artifactKey"),
        compiler_version=intermediate_model.get("compilerVersion"),
        target=intermediate_model.get("target"),
        intermediate_model=intermediate_model,
        diagnostics=diagnostics,
        errors=errors,
        warnings=warnings,
        workspace=workspace,
    )