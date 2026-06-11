from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.application.presenters import build_rules_page_payload
from app.domain.entities import build_compiler_artifact_entity
from app.domain.entities import build_rule_version_entity
from app.domain.entities import rule_policy
from app.domain.interfaces import RulesRepository


@dataclass(slots=True)
class RuleCompilerVersionsQuery:
    page: int = 1
    limit: int = 20
    workspace: str | None = None


@dataclass(slots=True)
class RuleVersionsQuery:
    rule_id: str
    limit: int = 20
    offset: int = 0


@dataclass(slots=True)
class RuleVersionLookup:
    rule_id: str
    version_id: str


@dataclass(slots=True)
class RuleVersionComparison:
    rule_id: str
    version_1: str
    version_2: str


async def list_rule_compiler_versions(
    request: RuleCompilerVersionsQuery,
    repository: RulesRepository,
    *,
    resolve_current_rule_version,
) -> dict[str, Any]:
    rows = await repository.list_rule_records(
        workspace=request.workspace,
        include_deleted=False,
        is_template=False,
        limit=500,
        offset=0,
    )

    view_rows: list[dict[str, Any]] = []
    for row in rows:
        rule_id = str(rule_policy.read_row_field(row, "id") or "")
        if not rule_id:
            continue

        version = await resolve_current_rule_version(repository, rule_id)
        rule_version_id = str(version.id or "") if version else ""
        active_artifact = (
            build_compiler_artifact_entity(await repository.get_active_compiler_artifact(rule_version_id))
            if rule_version_id
            else None
        )
        artifact_payload = active_artifact.artifactPayload if active_artifact is not None else None
        filter_payload = artifact_payload.filter if artifact_payload is not None else None
        compiled_expression = str(filter_payload.normalized or "").strip() if filter_payload is not None else ""

        view_rows.append(
            {
                "ruleId": rule_id,
                "ruleName": str(rule_policy.read_row_field(row, "name") or rule_id),
                "ruleVersionId": rule_version_id or None,
                "ruleVersionNumber": int(version.versionNumber or 0) if version else None,
                "compilerVersion": active_artifact.compilerVersion if active_artifact else None,
                "compilerRevision": active_artifact.compilerRevision if active_artifact else None,
                "compileStatus": active_artifact.compileStatus if active_artifact else None,
                "artifactKey": active_artifact.artifactKey if active_artifact else None,
                "compiledAt": active_artifact.createdAt if active_artifact else None,
                "compiledExpression": compiled_expression or None,
            }
        )

    return build_rules_page_payload(view_rows, request.page, request.limit)


async def get_rule_versions(request: RuleVersionsQuery, repository: RulesRepository) -> dict[str, Any]:
    payload = await repository.list_rule_versions(request.rule_id, limit=request.limit, offset=request.offset)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Rule '{request.rule_id}' not found")
    return payload


async def get_rule_rollback_history(request: RuleVersionsQuery, repository: RulesRepository) -> dict[str, Any]:
    payload = await repository.get_rule_rollback_history(request.rule_id, limit=request.limit, offset=request.offset)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Rule '{request.rule_id}' not found")
    return payload


async def get_rule_status_history(request: RuleVersionsQuery, repository: RulesRepository) -> list[dict[str, Any]]:
    payload = await repository.list_rule_status_history(request.rule_id, limit=request.limit, offset=request.offset)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Rule '{request.rule_id}' not found")
    return list(payload)


async def get_rule_version_statistics(rule_id: str, repository: RulesRepository) -> dict[str, Any]:
    payload = await repository.get_rule_version_statistics(rule_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    return payload


async def compare_rule_versions(request: RuleVersionComparison, repository: RulesRepository) -> dict[str, Any]:
    payload = await repository.compare_rule_versions(request.rule_id, request.version_1, request.version_2)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"One or both versions not found for rule '{request.rule_id}'",
        )
    return payload


async def get_rule_version(request: RuleVersionLookup, repository: RulesRepository) -> dict[str, Any]:
    payload = await repository.get_rule_version(request.rule_id, request.version_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version '{request.version_id}' not found for rule '{request.rule_id}'",
        )
    return payload


async def list_rule_version_compiler_artifacts(request: RuleVersionLookup, repository: RulesRepository) -> dict[str, Any]:
    version_payload = build_rule_version_entity(await repository.get_rule_version(request.rule_id, request.version_id))
    if version_payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version '{request.version_id}' not found for rule '{request.rule_id}'",
        )

    artifacts = await repository.list_compiler_artifacts(request.version_id)
    active = build_compiler_artifact_entity(await repository.get_active_compiler_artifact(request.version_id))
    active_id = str(active.id or "").strip() or None if active is not None else None

    return {
        "ruleId": request.rule_id,
        "ruleVersionId": request.version_id,
        "ruleVersionNumber": int(version_payload.versionNumber or 0),
        "activeArtifactId": active_id,
        "items": artifacts,
    }


async def get_rule_version_active_compiler_artifact(request: RuleVersionLookup, repository: RulesRepository) -> dict[str, Any]:
    version_payload = build_rule_version_entity(await repository.get_rule_version(request.rule_id, request.version_id))
    if version_payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version '{request.version_id}' not found for rule '{request.rule_id}'",
        )

    active = build_compiler_artifact_entity(await repository.get_active_compiler_artifact(request.version_id))
    if active is None:
        raise HTTPException(
            status_code=404,
            detail=f"No compiler artifact found for version '{request.version_id}'",
        )
    return active.model_dump(by_alias=True, exclude_none=True)