from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.application.services.data_contract_resolver import JoinConsistencyContractResolver
from app.application.use_cases.rule_mutation import resolve_rule_mutation_payload
from app.application.use_cases.rule_mutation import RuleMutationCommand
from app.domain.entities import rule_policy
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import RulesRepository


async def update_rule(
    rule_id: str,
    command: RuleMutationCommand,
    repository: RulesRepository,
    config_repository: AppConfigRepository,
    catalog_repository: DataCatalogRepository,
    contract_resolver: JoinConsistencyContractResolver,
    actor_id: str,
) -> dict[str, Any]:
    rows = await repository.list_rule_records(
        workspace=None,
        include_deleted=False,
        is_template=None,
        limit=500,
        offset=0,
    )
    existing_rule = next(
        (row for row in rows if str(rule_policy.read_row_field(row, "id") or "") == str(rule_id)),
        None,
    )
    if existing_rule is None:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")

    existing_approval_status = getattr(existing_rule, "last_approval_status", None)
    existing_active = getattr(existing_rule, "active", None)

    if str(existing_approval_status or "").strip().lower() == "approved" or bool(existing_active):
        raise HTTPException(
            status_code=409,
            detail="This rule version is approved and can no longer be changed.",
        )

    workspace_id = rule_policy.require_workspace(
        command.workspace_id,
        command.workspace,
        rule_policy.read_row_field(existing_rule, "workspaceId"),
        rule_policy.read_row_field(existing_rule, "workspace"),
    )
    existing_taxonomy = rule_policy.read_row_field(existing_rule, "taxonomy")
    if hasattr(existing_taxonomy, "model_dump"):
        existing_taxonomy = existing_taxonomy.model_dump(mode="python", exclude_none=True)
    common_kwargs = await resolve_rule_mutation_payload(
        command=command,
        repository=repository,
        config_repository=config_repository,
        catalog_repository=catalog_repository,
        contract_resolver=contract_resolver,
        actor_id=actor_id,
        workspace_id=workspace_id,
        exclude_rule_id=rule_id,
        existing_taxonomy=existing_taxonomy if isinstance(existing_taxonomy, dict) else None,
        owner_fallback=str(rule_policy.read_row_field(existing_rule, "created_by") or "").strip() or actor_id,
    )

    try:
        payload = await repository.update_rule_record(rule_id=rule_id, **common_kwargs)
        if payload is None:
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
        return payload.to_payload()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc