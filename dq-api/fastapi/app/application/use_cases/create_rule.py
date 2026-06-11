from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from app.application.services.data_contract_resolver import JoinConsistencyContractResolver
from app.application.use_cases.rule_mutation import resolve_rule_mutation_payload
from app.application.use_cases.rule_mutation import RuleMutationCommand
from app.domain.entities import rule_policy
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import RulesRepository

logger = logging.getLogger(__name__)


async def create_rule(
    command: RuleMutationCommand,
    repository: RulesRepository,
    config_repository: AppConfigRepository,
    catalog_repository: DataCatalogRepository,
    contract_resolver: JoinConsistencyContractResolver,
    actor_id: str,
) -> dict[str, Any]:
    workspace_id = rule_policy.require_workspace(command.workspace_id, command.workspace)
    common_kwargs = await resolve_rule_mutation_payload(
        command=command,
        repository=repository,
        config_repository=config_repository,
        catalog_repository=catalog_repository,
        contract_resolver=contract_resolver,
        actor_id=actor_id,
        workspace_id=workspace_id,
        owner_fallback=actor_id,
    )
    create_kwargs = {
        **common_kwargs,
        "workspace": workspace_id,
        "created_by": actor_id,
        "generated": command.generated,
        "is_template": command.is_template,
        "template_id": command.template_id,
        "suggestion_id": command.suggestion_id,
    }
    try:
        payload = await repository.create_rule_record(**create_kwargs)
        return payload.to_payload()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Failed to create rule '%s' in workspace '%s'",
            command.name,
            workspace_id,
        )
        raise HTTPException(status_code=500, detail=f"Failed to create rule: {exc}") from exc