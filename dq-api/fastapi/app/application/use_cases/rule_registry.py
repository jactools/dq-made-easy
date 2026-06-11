from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.application.presenters import build_rules_page_payload
from app.domain.entities import rule_policy
from app.domain.entities.rule_registry import build_rule_registry_discovery_entity
from app.domain.entities.rule_registry import build_rule_registry_entry_entity
from app.domain.interfaces import ApprovalsRepository
from app.domain.interfaces import RulesRepository


@dataclass(slots=True)
class RuleRegistryQuery:
    page: int = 1
    limit: int = 20
    include_deleted: bool = False
    workspace: str | None = None
    is_template: bool | None = None
    query: str | None = None
    status: str | None = None
    lifecycle_status: str | None = None
    owner: str | None = None
    domain: str | None = None
    severity: str | None = None
    execution_target: str | None = None
    rule_type: str | None = None
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


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _matches_registry_filters(row: dict, request: RuleRegistryQuery) -> bool:
    status = _normalize_text(request.status)
    if status and _normalize_text(row.get("status")) != status:
        return False

    lifecycle_status = _normalize_text(request.lifecycle_status)
    if lifecycle_status and _normalize_text(row.get("lifecycle_status")) != lifecycle_status:
        return False

    taxonomy = row.get("taxonomy") if isinstance(row.get("taxonomy"), dict) else {}

    owner = _normalize_text(request.owner)
    if owner and owner != _normalize_text(taxonomy.get("owner")):
        return False

    domain = _normalize_text(request.domain)
    if domain and domain != _normalize_text(taxonomy.get("domain")):
        return False

    severity = _normalize_text(request.severity)
    if severity and severity != _normalize_text(taxonomy.get("severity")):
        return False

    execution_target = _normalize_text(request.execution_target)
    if execution_target and execution_target != _normalize_text(taxonomy.get("execution_target")):
        return False

    rule_type = _normalize_text(request.rule_type)
    if rule_type and rule_type != _normalize_text(taxonomy.get("type")):
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


async def _list_all_rule_records(
    request: RuleRegistryQuery,
    repository: RulesRepository,
) -> list[Any]:
    rows: list[Any] = []
    offset = 0
    page_size = 500
    while True:
        batch = await repository.list_rule_records(
            workspace=request.workspace,
            include_deleted=request.include_deleted,
            is_template=request.is_template,
            query=request.query,
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


async def list_rule_registry(
    request: RuleRegistryQuery,
    repository: RulesRepository,
    approvals_repository: ApprovalsRepository,
) -> dict[str, Any]:
    rows = await _list_all_rule_records(request, repository)
    pending_rule_ids = rule_policy.build_pending_deactivation_rule_ids(
        [approval.model_dump() for approval in approvals_repository.list_approvals(None)]
    )

    registry_entries = []
    for row in rows:
        normalized = rule_policy.normalize_rule_row_contract(row.to_payload())
        normalized["status"] = rule_policy.derive_rule_status_from_row(normalized)
        rule_id = str(normalized.get("id") or "").strip()
        normalized["pending_deactivation_requested"] = bool(rule_id and rule_id in pending_rule_ids)
        if not _matches_registry_filters(normalized, request):
            continue
        registry_entry = build_rule_registry_entry_entity(normalized)
        if registry_entry is not None:
            registry_entries.append(registry_entry)

    discovery = build_rule_registry_discovery_entity(registry_entries)
    page_payload = build_rules_page_payload(
        [entry.model_dump(mode="python", exclude_none=True) for entry in registry_entries],
        request.page,
        request.limit,
    )
    return {
        "data": page_payload["data"],
        "pagination": page_payload["pagination"],
        "discovery": discovery.model_dump(mode="python", exclude_none=True),
    }