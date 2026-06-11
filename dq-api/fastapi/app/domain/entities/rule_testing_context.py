from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException

from app.domain.entities import build_compiler_artifact_entity
from app.domain.entities import build_rule_version_entity
from app.domain.entities import rule_autopublish_policy
from app.domain.entities import rule_policy
from app.domain.entities.rule import RuleExecutionContextEntity
from app.domain.entities.rule import RuleVersionEntity


async def resolve_current_rule_version(repository: Any, rule_id: str) -> RuleVersionEntity | None:
    return await rule_autopublish_policy.resolve_current_rule_version(repository, rule_id)


def raise_compiler_artifact_required(rule_id: str, rule_version_id: str | None = None) -> None:
    raise HTTPException(
        status_code=409,
        detail={
            "error": "active_compiler_artifact_required",
            "message": (
                "An active compiler artifact with a compiled expression is required before testing this rule. "
                "Validate the current rule version and try again."
            ),
            "rule_id": rule_id,
            "rule_version_id": rule_version_id,
        },
    )


async def build_execution_context(repository: Any, rule_id: str) -> RuleExecutionContextEntity | None:
    version = await resolve_current_rule_version(repository, rule_id)
    if version is None:
        raise_compiler_artifact_required(rule_id)

    rule_version_id = str(version.id or "").strip()
    if not rule_version_id:
        raise_compiler_artifact_required(rule_id)

    version_detail = build_rule_version_entity(await repository.get_rule_version(rule_id, rule_version_id))
    source_rule_expression = str(version_detail.expression or "").strip() if version_detail is not None else ""

    active_artifact = build_compiler_artifact_entity(
        await repository.get_active_compiler_artifact(rule_version_id)
    )
    if active_artifact is None:
        raise_compiler_artifact_required(rule_id, rule_version_id)

    artifact_payload = active_artifact.artifactPayload
    execution_contract = artifact_payload.executionContract if artifact_payload is not None else None
    filter_payload = artifact_payload.filter if artifact_payload is not None else None
    compiled_expression = str(filter_payload.normalized or "").strip() if filter_payload is not None else ""
    if not compiled_expression:
        raise_compiler_artifact_required(rule_id, rule_version_id)

    executed_expression = compiled_expression or source_rule_expression

    return RuleExecutionContextEntity(
        ruleId=rule_id,
        ruleVersionId=rule_version_id,
        ruleVersionNumber=int(version.versionNumber or 0),
        sourceRuleExpression=source_rule_expression or None,
        artifactKey=active_artifact.artifactKey,
        compilerVersion=active_artifact.compilerVersion,
        compilerRevision=active_artifact.compilerRevision,
        compileStatus=active_artifact.compileStatus,
        schemaVersion=artifact_payload.schemaVersion if artifact_payload is not None else None,
        executionContract=execution_contract,
        compiledExpression=compiled_expression or None,
        executedExpression=executed_expression or None,
        handoffReady=bool(execution_contract and str(active_artifact.artifactKey or "").strip()),
    )


def derive_rule_status_from_row(row: Mapping[str, Any] | None) -> str:
    if row is None:
        return "draft"
    return rule_policy.derive_rule_status_from_row(row)


async def resolve_current_rule_status(repository: Any, rule_id: str) -> str | None:
    rows = await repository.list_rule_records(
        workspace=None,
        include_deleted=True,
        is_template=False,
        limit=500,
        offset=0,
    )
    current_row = next(
        (
            row for row in rows
            if str(rule_policy.read_row_field(row, "id") or "") == str(rule_id)
        ),
        None,
    )
    if current_row is None:
        return None
    return derive_rule_status_from_row(current_row)