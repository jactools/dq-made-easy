from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.presenters.rules import build_rules_page_payload
from app.domain.entities import rule_policy
from app.domain.entities.rule_registry import build_rule_registry_entry_entity
from app.domain.interfaces import ApprovalsRepository
from app.domain.interfaces import RulesRepository


@dataclass(slots=True)
class GovernanceInboxQuery:
    workspace_id: str | None = None
    page: int = 1
    limit: int = 20


async def _list_all_rule_records(
    request: GovernanceInboxQuery,
    repository: RulesRepository,
) -> list[Any]:
    rows: list[Any] = []
    offset = 0
    page_size = 500
    while True:
        batch = await repository.list_rule_records(
            workspace=request.workspace_id,
            include_deleted=False,
            is_template=None,
            query=None,
            limit=page_size,
            offset=offset,
        )
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def _is_reassignment_candidate(entry: Any) -> bool:
    return not all(
        (
            str(getattr(entry, "data_steward", None) or "").strip(),
            str(getattr(entry, "domain_owner", None) or "").strip(),
            str(getattr(entry, "technical_owner", None) or "").strip(),
        )
    )


def _is_deprecation_review_candidate(entry: Any) -> bool:
    return str(getattr(entry, "lifecycle_status", None) or "").strip().lower() in {"deprecated", "superseded"}


async def list_governance_inboxes(
    request: GovernanceInboxQuery,
    repository: RulesRepository,
    approvals_repository: ApprovalsRepository,
) -> dict[str, Any]:
    pending_approvals = approvals_repository.list_approvals(
        workspace_id=request.workspace_id,
        status="pending",
    )
    approval_inbox = build_rules_page_payload(
        [approval.model_dump(mode="python", exclude_none=True) for approval in pending_approvals],
        request.page,
        request.limit,
    )

    rows = await _list_all_rule_records(request, repository)
    pending_rule_ids = rule_policy.build_pending_deactivation_rule_ids(
        [approval.model_dump() for approval in pending_approvals]
    )

    reassignment_candidates: list[Any] = []
    deprecation_review_candidates: list[Any] = []

    for row in rows:
        normalized = rule_policy.normalize_rule_row_contract(row.to_payload())
        normalized["status"] = rule_policy.derive_rule_status_from_row(normalized)
        rule_id = str(normalized.get("id") or "").strip()
        normalized["pending_deactivation_requested"] = bool(rule_id and rule_id in pending_rule_ids)
        registry_entry = build_rule_registry_entry_entity(normalized)
        if registry_entry is None:
            continue
        if _is_reassignment_candidate(registry_entry):
            reassignment_candidates.append(registry_entry)
        if _is_deprecation_review_candidate(registry_entry):
            deprecation_review_candidates.append(registry_entry)

    reassignment_inbox = build_rules_page_payload(
        [entry.model_dump(mode="python", exclude_none=True) for entry in reassignment_candidates],
        request.page,
        request.limit,
    )
    deprecation_review_inbox = build_rules_page_payload(
        [entry.model_dump(mode="python", exclude_none=True) for entry in deprecation_review_candidates],
        request.page,
        request.limit,
    )

    return {
        "approval_inbox": approval_inbox,
        "reassignment_inbox": reassignment_inbox,
        "deprecation_review_inbox": deprecation_review_inbox,
    }