from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Callable

from app.application.use_cases.rule_validation import evaluate_rule_validation
from app.application.use_cases.rule_validation import load_validation_policies
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import RulesRepository


@dataclass(slots=True)
class ValidateRuleCommand:
    rule_id: str
    validated_by: str | None = None


async def validate_rule(
    command: ValidateRuleCommand,
    repository: RulesRepository,
    data_catalog_repository: DataCatalogRepository,
    config_repository: AppConfigRepository,
    *,
    apply_validation_policies: Callable[..., list[dict[str, Any]]],
    compile_rule_to_intermediate_model: Callable[..., dict[str, Any]],
    infer_alias_expectations: Callable[[str], list[dict[str, Any]]],
    persist_compiler_artifact: Callable[..., Any],
    resolve_current_rule_version: Callable[..., Any],
    has_upstream_validation_issue: Callable[[list[dict[str, Any]]], bool],
) -> dict[str, Any]:
    evaluation = await evaluate_rule_validation(
        rule_id=command.rule_id,
        repository=repository,
        data_catalog_repository=data_catalog_repository,
        raw_policies=load_validation_policies(config_repository),
        apply_validation_policies=apply_validation_policies,
        compile_rule_to_intermediate_model=compile_rule_to_intermediate_model,
        infer_alias_expectations=infer_alias_expectations,
        persist_compiler_artifact=persist_compiler_artifact,
        resolve_current_rule_version=resolve_current_rule_version,
        has_upstream_validation_issue=has_upstream_validation_issue,
        validated_by=command.validated_by,
        persist_validation_state=True,
    )
    return {
        "valid": evaluation.valid,
        "compiledExpression": evaluation.compiled_expression,
        "inferredAliases": evaluation.inferred_aliases,
        "artifactKey": evaluation.artifact_key,
        "compilerVersion": evaluation.compiler_version,
        "target": evaluation.target,
        "intermediateModel": evaluation.intermediate_model,
        "summary": {
            "errors": evaluation.errors,
            "warnings": evaluation.warnings,
        },
        "diagnostics": evaluation.diagnostics,
    }