from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field

from app.domain.entities.base import EntityModel
from app.domain.entities.rule import RuleTaxonomyEntity


def _normalized_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalized_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalized_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


class RuleRegistryEntryEntity(EntityModel):
    id: str
    name: str
    description: str | None = None
    comments: str | None = None
    expression: str
    dimension: str
    active: bool = True
    lifecycle_status: str = "active"
    status: str = "active"
    workspace: str | None = None
    created_by: str | None = None
    data_steward: str | None = None
    domain_owner: str | None = None
    technical_owner: str | None = None
    generated: bool = False
    is_template: bool = False
    template_id: str | None = None
    suggestion_id: str | None = None
    check_type: str | None = None
    check_type_params: dict[str, Any] | None = None
    reusable_join_id: str | None = None
    reusable_filter_ids: list[str] = Field(default_factory=list)
    tag_ids: list[str] = Field(default_factory=list)
    join_conditions: list[dict[str, Any]] = Field(default_factory=list)
    alias_mappings: dict[str, Any] = Field(default_factory=dict)
    current_version_id: str | None = None
    total_versions: int | None = None
    versioning_enabled: bool | None = None
    version_created_at: str | None = None
    version_updated_at: str | None = None
    pending_deactivation_requested: bool = False
    taxonomy: RuleTaxonomyEntity = Field(default_factory=RuleTaxonomyEntity)


class RuleRegistryDiscoveryEntity(EntityModel):
    workspaces: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    lifecycle_statuses: list[str] = Field(default_factory=list)
    owners: list[str] = Field(default_factory=list)
    data_stewards: list[str] = Field(default_factory=list)
    domain_owners: list[str] = Field(default_factory=list)
    technical_owners: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    execution_targets: list[str] = Field(default_factory=list)
    rule_types: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)


def build_rule_registry_entry_entity(payload: Any) -> RuleRegistryEntryEntity | None:
    if not isinstance(payload, Mapping):
        return None

    rule_id = _normalized_text(payload.get("id"))
    if not rule_id:
        return None

    taxonomy_payload = payload.get("taxonomy") if isinstance(payload.get("taxonomy"), Mapping) else {}
    total_versions_raw = payload.get("total_versions")
    try:
        total_versions = int(total_versions_raw) if total_versions_raw not in (None, "") else None
    except (TypeError, ValueError):
        total_versions = None

    return RuleRegistryEntryEntity(
        id=rule_id,
        name=_normalized_text(payload.get("name")) or "",
        description=str(payload.get("description")) if payload.get("description") is not None else None,
        comments=str(payload.get("comments")) if payload.get("comments") is not None else None,
        expression=_normalized_text(payload.get("expression")) or "",
        dimension=_normalized_text(payload.get("dimension")) or "",
        active=bool(payload.get("active")),
        lifecycle_status=_normalized_text(payload.get("lifecycle_status")) or "active",
        status=_normalized_text(payload.get("status")) or "active",
        workspace=_normalized_text(payload.get("workspace")),
        created_by=_normalized_text(payload.get("created_by") or payload.get("createdBy")),
        data_steward=_normalized_text(
            payload.get("data_steward")
            or payload.get("dataSteward")
            or taxonomy_payload.get("data_steward")
            or taxonomy_payload.get("dataSteward")
        ),
        domain_owner=_normalized_text(
            payload.get("domain_owner")
            or payload.get("domainOwner")
            or taxonomy_payload.get("domain_owner")
            or taxonomy_payload.get("domainOwner")
        ),
        technical_owner=_normalized_text(
            payload.get("technical_owner")
            or payload.get("technicalOwner")
            or taxonomy_payload.get("technical_owner")
            or taxonomy_payload.get("technicalOwner")
        ),
        generated=bool(payload.get("generated")),
        is_template=bool(payload.get("is_template")),
        template_id=_normalized_text(payload.get("template_id") or payload.get("templateId")),
        suggestion_id=_normalized_text(payload.get("suggestion_id") or payload.get("suggestionId")),
        check_type=_normalized_text(payload.get("check_type") or payload.get("checkType")),
        check_type_params=dict(payload.get("check_type_params"))
        if isinstance(payload.get("check_type_params"), Mapping)
        else dict(payload.get("checkTypeParams"))
        if isinstance(payload.get("checkTypeParams"), Mapping)
        else None,
        reusable_join_id=_normalized_text(payload.get("reusable_join_id") or payload.get("reusableJoinId")),
        reusable_filter_ids=_normalized_list(payload.get("reusableFilterIds") or payload.get("reusable_filter_ids")),
        tag_ids=_normalized_list(payload.get("tagIds") or payload.get("tag_ids")),
        join_conditions=list(payload.get("joinConditions")) if isinstance(payload.get("joinConditions"), list) else list(payload.get("join_conditions")) if isinstance(payload.get("join_conditions"), list) else [],
        alias_mappings=_normalized_dict(payload.get("aliasMappings") or payload.get("alias_mappings")),
        current_version_id=_normalized_text(payload.get("current_version_id") or payload.get("currentVersionId")),
        total_versions=total_versions,
        versioning_enabled=(bool(payload.get("versioning_enabled")) if payload.get("versioning_enabled") is not None else bool(payload.get("versioningEnabled")) if payload.get("versioningEnabled") is not None else None),
        version_created_at=_normalized_text(payload.get("version_created_at") or payload.get("versionCreatedAt")),
        version_updated_at=_normalized_text(payload.get("version_updated_at") or payload.get("versionUpdatedAt")),
        pending_deactivation_requested=bool(
            payload.get("pending_deactivation_requested") or payload.get("pendingDeactivationRequested")
        ),
        taxonomy=RuleTaxonomyEntity.model_validate(taxonomy_payload),
    )


def build_rule_registry_discovery_entity(entries: list[RuleRegistryEntryEntity]) -> RuleRegistryDiscoveryEntity:
    def _sorted_unique(values: list[str]) -> list[str]:
        return sorted({value for value in values if value})

    workspaces: list[str] = []
    statuses: list[str] = []
    lifecycle_statuses: list[str] = []
    owners: list[str] = []
    data_stewards: list[str] = []
    domain_owners: list[str] = []
    technical_owners: list[str] = []
    domains: list[str] = []
    execution_targets: list[str] = []
    rule_types: list[str] = []
    dimensions: list[str] = []

    for entry in entries:
        if entry.workspace:
            workspaces.append(entry.workspace)
        if entry.status:
            statuses.append(entry.status)
        if entry.lifecycle_status:
            lifecycle_statuses.append(entry.lifecycle_status)
        if entry.taxonomy.owner:
            owners.append(entry.taxonomy.owner)
        if entry.data_steward:
            data_stewards.append(entry.data_steward)
        if entry.domain_owner:
            domain_owners.append(entry.domain_owner)
        if entry.technical_owner:
            technical_owners.append(entry.technical_owner)
        if entry.taxonomy.domain:
            domains.append(entry.taxonomy.domain)
        if entry.taxonomy.execution_target:
            execution_targets.append(entry.taxonomy.execution_target)
        if entry.taxonomy.type:
            rule_types.append(entry.taxonomy.type)
        if entry.dimension:
            dimensions.append(entry.dimension)

    return RuleRegistryDiscoveryEntity(
        workspaces=_sorted_unique(workspaces),
        statuses=_sorted_unique(statuses),
        lifecycle_statuses=_sorted_unique(lifecycle_statuses),
        owners=_sorted_unique(owners),
        data_stewards=_sorted_unique(data_stewards),
        domain_owners=_sorted_unique(domain_owners),
        technical_owners=_sorted_unique(technical_owners),
        domains=_sorted_unique(domains),
        execution_targets=_sorted_unique(execution_targets),
        rule_types=_sorted_unique(rule_types),
        dimensions=_sorted_unique(dimensions),
    )