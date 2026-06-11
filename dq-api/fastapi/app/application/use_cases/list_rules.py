from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.application.presenters import build_rules_page_payload
from app.domain.entities import rule_policy
from app.domain.interfaces import ApprovalsRepository
from app.domain.interfaces import RulesRepository


@dataclass(slots=True)
class ListRulesQuery:
    page: int = 1
    limit: int = 20
    include_deleted: bool = False
    workspace: str | None = None
    is_template: bool | None = None
    query: str | None = None
    status: str | None = None
    lifecycle_status: str | None = None
    owner: str | None = None
    updated_since: datetime | None = None
    updated_before: datetime | None = None


def _row_updated_at(row: dict) -> datetime | None:
    raw_value = row.get("version_updated_at") or row.get("version_created_at") or row.get("updated_at") or row.get("created_at")
    if not raw_value:
        return None
    value = str(raw_value).strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _matches_list_filters(row: dict, request: ListRulesQuery) -> bool:
    status = str(request.status or "").strip().lower()
    if status and str(row.get("status") or "").strip().lower() != status:
        return False

    lifecycle_status = str(request.lifecycle_status or "").strip().lower()
    if lifecycle_status and str(row.get("lifecycle_status") or "").strip().lower() != lifecycle_status:
        return False

    owner = str(request.owner or "").strip().lower()
    if owner:
        taxonomy = row.get("taxonomy") if isinstance(row.get("taxonomy"), dict) else {}
        taxonomy_owner = str(taxonomy.get("owner") or "").strip().lower()
        if owner != taxonomy_owner:
            return False

    if request.updated_since or request.updated_before:
        updated_at = _row_updated_at(row)
        if updated_at is None:
            return False
        if request.updated_since and updated_at < request.updated_since:
            return False
        if request.updated_before and updated_at > request.updated_before:
            return False

    return True


async def list_rules(
    request: ListRulesQuery,
    repository: RulesRepository,
    approvals_repository: ApprovalsRepository,
) -> dict:
    has_use_case_filters = any([request.status, request.lifecycle_status, request.owner, request.updated_since, request.updated_before])
    repository_limit = 1000 if has_use_case_filters else request.limit
    repository_offset = 0 if has_use_case_filters else (request.page - 1) * request.limit
    rows = await repository.list_rule_records(
        workspace=request.workspace,
        include_deleted=request.include_deleted,
        is_template=request.is_template,
        query=request.query,
        limit=repository_limit,
        offset=repository_offset,
    )
    pending_rule_ids = rule_policy.build_pending_deactivation_rule_ids([
        approval.model_dump() for approval in approvals_repository.list_approvals(None)
    ])
    normalized_rows = []
    for row in rows:
        normalized = rule_policy.normalize_rule_row_contract(row.to_payload())
        normalized["status"] = rule_policy.derive_rule_status_from_row(normalized)
        rule_id = str(normalized.get("id") or "").strip()
        normalized["pending_deactivation_requested"] = bool(rule_id and rule_id in pending_rule_ids)
        if _matches_list_filters(normalized, request):
            normalized_rows.append(normalized)
    return build_rules_page_payload(normalized_rows, request.page, request.limit)