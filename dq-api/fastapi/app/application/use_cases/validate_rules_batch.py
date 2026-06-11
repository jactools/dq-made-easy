from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from typing import Callable
from uuid import uuid4

from fastapi import HTTPException

from app.application.use_cases.rule_validation import evaluate_rule_validation
from app.application.use_cases.rule_validation import load_validation_policies
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import RulesRepository
from app.domain.interfaces import ValidationRunRepository


@dataclass(slots=True)
class ValidateRulesBatchCommand:
    rule_ids: list[str]
    workspace: str | None = None
    triggered_by: str | None = None


async def validate_rules_batch(
    command: ValidateRulesBatchCommand,
    repository: RulesRepository,
    data_catalog_repository: DataCatalogRepository,
    config_repository: AppConfigRepository,
    run_repository: ValidationRunRepository,
    *,
    apply_validation_policies: Callable[..., list[dict[str, Any]]],
    compile_rule_to_intermediate_model: Callable[..., dict[str, Any]],
    infer_alias_expectations: Callable[[str], list[dict[str, Any]]],
    persist_compiler_artifact: Callable[..., Any],
    resolve_current_rule_version: Callable[..., Any],
    has_upstream_validation_issue: Callable[[list[dict[str, Any]]], bool],
    detect_conflicts: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    logger: Any,
    uuid_factory: Callable[[], Any] = uuid4,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    if not command.rule_ids:
        raise HTTPException(status_code=422, detail="ruleIds must not be empty")
    if len(command.rule_ids) > 100:
        raise HTTPException(status_code=422, detail="Batch size cannot exceed 100 rules")

    raw_policies = load_validation_policies(config_repository)

    results: list[dict[str, Any]] = []
    for rule_id in command.rule_ids:
        try:
            evaluation = await evaluate_rule_validation(
                rule_id=rule_id,
                repository=repository,
                data_catalog_repository=data_catalog_repository,
                raw_policies=raw_policies,
                apply_validation_policies=apply_validation_policies,
                compile_rule_to_intermediate_model=compile_rule_to_intermediate_model,
                infer_alias_expectations=infer_alias_expectations,
                persist_compiler_artifact=persist_compiler_artifact,
                resolve_current_rule_version=resolve_current_rule_version,
                has_upstream_validation_issue=has_upstream_validation_issue,
                workspace_override=command.workspace,
            )
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            results.append(
                {
                    "ruleId": rule_id,
                    "ruleName": None,
                    "valid": False,
                    "compiledExpression": "",
                    "artifactKey": None,
                    "compilerVersion": None,
                    "errors": 1,
                    "warnings": 0,
                    "diagnostics": [
                        {
                            "code": "DQ1_RULE_NOT_FOUND",
                            "severity": "error",
                            "message": f"Rule '{rule_id}' was not found",
                            "scope": "rule",
                        }
                    ],
                }
            )
            continue

        results.append(
            {
                "ruleId": evaluation.rule_id,
                "ruleName": evaluation.rule_name,
                "ruleVersionNumber": evaluation.rule_version_number,
                "valid": evaluation.valid,
                "compiledExpression": evaluation.compiled_expression,
                "artifactKey": evaluation.artifact_key,
                "compilerVersion": evaluation.compiler_version,
                "errors": evaluation.errors,
                "warnings": evaluation.warnings,
                "diagnostics": evaluation.diagnostics,
            }
        )

    conflicts = detect_conflicts(
        [
            {
                "ruleId": result["ruleId"],
                "ruleName": result.get("ruleName"),
                "compiledExpression": result.get("compiledExpression") or "",
            }
            for result in results
            if result.get("compiledExpression")
        ]
    )

    total = len(results)
    valid_count = sum(1 for result in results if result.get("valid"))
    invalid_count = total - valid_count
    total_errors = sum(result.get("errors", 0) for result in results)
    total_warnings = sum(result.get("warnings", 0) for result in results)

    run_id = str(uuid_factory())
    run_at = now().isoformat()
    items_for_run = [
        {
            "ruleId": result["ruleId"],
            "ruleName": result.get("ruleName"),
            "ruleVersionNumber": result.get("ruleVersionNumber"),
            "valid": result.get("valid", False),
            "errors": result.get("errors", 0),
            "warnings": result.get("warnings", 0),
            "diagnostics": result.get("diagnostics", []),
            "conflicts": [
                conflict
                for conflict in conflicts
                if conflict["ruleId"] == result["ruleId"] or conflict["conflictsWith"] == result["ruleId"]
            ],
        }
        for result in results
    ]
    try:
        await run_repository.save_run(
            run_id=run_id,
            workspace=command.workspace,
            triggered_by=command.triggered_by,
            run_at=run_at,
            total=total,
            valid_count=valid_count,
            invalid_count=invalid_count,
            status="complete",
            items=items_for_run,
        )
    except Exception as exc:
        logger.warning("Failed to persist validation run '%s': %s", run_id, exc)

    return {
        "runId": run_id,
        "results": results,
        "conflicts": conflicts,
        "summary": {
            "total": total,
            "valid": valid_count,
            "invalid": invalid_count,
            "errors": total_errors,
            "warnings": total_warnings,
        },
    }