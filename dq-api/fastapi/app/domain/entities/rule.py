from collections.abc import Mapping
import json
from typing import Any

from pydantic import ConfigDict, Field, model_validator

from app.domain.entities.base import EntityModel


def _normalized_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _mapping_value(mapping: Mapping[str, Any] | None, *keys: str) -> Any:
    if mapping is None:
        return None
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _mapping_or_none(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    return None


def _json_mapping_or_none(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str):
        return None
    payload = value.strip()
    if not payload:
        return None
    try:
        parsed = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if isinstance(parsed, Mapping):
        return parsed
    return None


def _derive_rule_scope_taxonomy(dsl: Mapping[str, Any] | None) -> str | None:
    rule_payload = _mapping_or_none(_mapping_value(dsl, "rule"))
    scope_payload = _mapping_or_none(_mapping_value(rule_payload, "scope"))
    if scope_payload is None:
        return None
    if _mapping_or_none(_mapping_value(scope_payload, "comparison")) is not None:
        return "comparison"
    if _mapping_or_none(_mapping_value(scope_payload, "join")) is not None:
        return "join"
    if _mapping_or_none(_mapping_value(scope_payload, "grouping")) is not None:
        return "grouping"
    if _mapping_or_none(_mapping_value(scope_payload, "time_window", "timeWindow")) is not None:
        return "time_window"
    if _mapping_or_none(_mapping_value(scope_payload, "dataset")) is not None:
        return "dataset"
    return None


def _derive_rule_domain(
    *,
    workspace: str | None,
    dsl: Mapping[str, Any] | None,
) -> str | None:
    rule_payload = _mapping_or_none(_mapping_value(dsl, "rule"))
    scope_payload = _mapping_or_none(_mapping_value(rule_payload, "scope"))
    dataset_payload = _mapping_or_none(_mapping_value(scope_payload, "dataset"))
    comparison_payload = _mapping_or_none(_mapping_value(scope_payload, "comparison"))
    for payload in (
        dataset_payload,
        _mapping_or_none(_mapping_value(comparison_payload, "left")),
        _mapping_or_none(_mapping_value(comparison_payload, "right")),
    ):
        candidate = _normalized_text(_mapping_value(payload, "data_product_id", "dataProductId"))
        if candidate:
            return candidate
    return _normalized_text(workspace)


def _derive_rule_type(
    *,
    check_type: str | None,
    dsl: Mapping[str, Any] | None,
) -> str | None:
    normalized_check_type = _normalized_text(check_type)
    if normalized_check_type:
        return normalized_check_type.upper()

    rule_payload = _mapping_or_none(_mapping_value(dsl, "rule"))
    rule_kind = _normalized_text(_mapping_value(rule_payload, "kind"))
    if rule_kind:
        return rule_kind

    source_payload = _mapping_or_none(_mapping_value(dsl, "source"))
    source_kind = _normalized_text(_mapping_value(source_payload, "kind"))
    if source_kind == "check_type":
        source_check_type = _normalized_text(_mapping_value(source_payload, "check_type", "checkType"))
        if source_check_type:
            return source_check_type.upper()
    return source_kind


def _derive_rule_severity(dsl: Mapping[str, Any] | None) -> str | None:
    rule_payload = _mapping_or_none(_mapping_value(dsl, "rule"))
    operations_payload = _mapping_or_none(_mapping_value(rule_payload, "operations"))
    return _normalized_text(_mapping_value(operations_payload, "severity"))


def _derive_rule_execution_target(dsl: Mapping[str, Any] | None) -> str | None:
    rule_payload = _mapping_or_none(_mapping_value(dsl, "rule"))
    operations_payload = _mapping_or_none(_mapping_value(rule_payload, "operations"))
    preferred_engines = _mapping_value(operations_payload, "preferred_engines", "preferredEngines")
    if isinstance(preferred_engines, list):
        for item in preferred_engines:
            normalized = _normalized_text(item)
            if normalized:
                return normalized
    return None


class RuleTaxonomyEntity(EntityModel):
    type: str | None = None
    severity: str | None = None
    domain: str | None = None
    owner: str | None = None
    data_steward: str | None = None
    domain_owner: str | None = None
    technical_owner: str | None = None
    sla_scope: str | None = None
    execution_target: str | None = None


def build_rule_taxonomy_entity(
    *,
    workspace: str | None = None,
    created_by: str | None = None,
    created_by_user_id: str | None = None,
    check_type: str | None = None,
    dsl: Mapping[str, Any] | None = None,
    existing: RuleTaxonomyEntity | Mapping[str, Any] | None = None,
) -> RuleTaxonomyEntity:
    explicit = (
        existing
        if isinstance(existing, RuleTaxonomyEntity)
        else RuleTaxonomyEntity.model_validate(existing or {})
    )
    derived = RuleTaxonomyEntity(
        type=_derive_rule_type(check_type=check_type, dsl=dsl),
        severity=_derive_rule_severity(dsl),
        domain=_derive_rule_domain(workspace=workspace, dsl=dsl),
        owner=_normalized_text(created_by) or _normalized_text(created_by_user_id),
        data_steward=_normalized_text(created_by) or _normalized_text(created_by_user_id),
        sla_scope=_derive_rule_scope_taxonomy(dsl),
        execution_target=_derive_rule_execution_target(dsl),
    )
    return RuleTaxonomyEntity(
        type=explicit.type or derived.type,
        severity=explicit.severity or derived.severity,
        domain=explicit.domain or derived.domain,
        owner=explicit.owner or derived.owner,
        data_steward=explicit.data_steward or explicit.owner or derived.data_steward,
        domain_owner=explicit.domain_owner or derived.domain_owner,
        technical_owner=explicit.technical_owner or derived.technical_owner,
        sla_scope=explicit.sla_scope or derived.sla_scope,
        execution_target=explicit.execution_target or derived.execution_target,
    )


class RuleTagEntity(EntityModel):
    id: str
    name: str


class RuleCreatorEntity(EntityModel):
    id: str
    username: str
    display_name: str


class RuleEntity(EntityModel):
    id: str
    name: str
    description: str | None = None
    comments: str | None = None
    expression: str
    dimension: str
    active: bool = True
    lifecycle_status: str = "active"
    workspace: str | None = None
    created_by_user_id: str = Field(alias="createdByUserId")
    tag_ids: list[str] = Field(default_factory=list, alias="tagIds")
    manual_override_by: str | None = None
    manual_override_at: str | None = None
    check_type: str | None = Field(default=None, alias="checkType")
    check_type_params: dict | None = Field(default=None, alias="checkTypeParams")
    reusable_join_id: str | None = Field(default=None, alias="reusableJoinId")
    reusable_filter_ids: list[str] = Field(default_factory=list, alias="reusableFilterIds")
    dsl: dict[str, Any] | None = None
    taxonomy: RuleTaxonomyEntity = Field(default_factory=RuleTaxonomyEntity)

    @model_validator(mode="after")
    def _populate_taxonomy(self) -> "RuleEntity":
        self.taxonomy = build_rule_taxonomy_entity(
            workspace=self.workspace,
            created_by_user_id=self.created_by_user_id,
            check_type=self.check_type,
            dsl=self.dsl,
            existing=self.taxonomy,
        )
        return self


class RuleRecordEntity(EntityModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: str | None = None
    comments: str | None = None
    expression: str
    dimension: str
    active: bool = True
    lifecycle_status: str = "active"
    generated: bool = False
    is_template: bool = False
    template_id: str | None = None
    workspace: str | None = None
    created_by: str | None = None
    last_approval_by: str | None = None
    last_approval_status: str | None = None
    last_approval_at: str | None = None
    removed: bool = False
    removed_at: str | None = None
    removed_by: str | None = None
    deleted_on: str | None = None
    deleted_by: str | None = None
    suggestion_id: str | None = None
    join_conditions: Any = None
    alias_mappings: Any = None
    reusable_join_id: str | None = None
    manual_override_by: str | None = None
    manual_override_at: str | None = None
    check_type: str | None = None
    check_type_params: Any = None
    dsl: dict[str, Any] | None = None
    validation_status: str | None = None
    validated_at: str | None = None
    current_version_id: str | None = None
    total_versions: int | None = None
    versioning_enabled: bool | None = None
    version_created_at: str | None = None
    version_updated_at: str | None = None
    tagIds: list[str] = Field(default_factory=list)
    reusableFilterIds: list[str] = Field(default_factory=list)
    reusableFilters: list[Any] = Field(default_factory=list)
    joinConditions: list[dict[str, Any]] | None = None
    aliasMappings: dict[str, Any] | None = None
    taxonomy: RuleTaxonomyEntity = Field(default_factory=RuleTaxonomyEntity)

    @model_validator(mode="after")
    def _populate_taxonomy(self) -> "RuleRecordEntity":
        self.taxonomy = build_rule_taxonomy_entity(
            workspace=self.workspace,
            created_by=self.created_by,
            check_type=self.check_type,
            dsl=self.dsl,
            existing=self.taxonomy,
        )
        return self

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python")


class RuleVersionEntity(EntityModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    versionNumber: int | None = None
    isCurrentVersion: bool = False
    expression: str | None = None


class RuleVersionListEntity(EntityModel):
    model_config = ConfigDict(populate_by_name=True)

    versions: list[RuleVersionEntity] = Field(default_factory=list)


class CompilerArtifactFilterEntity(EntityModel):
    model_config = ConfigDict(populate_by_name=True)

    normalized: str | None = None
    source: str | None = None


class CompilerArtifactPayloadEntity(EntityModel):
    model_config = ConfigDict(populate_by_name=True)

    schemaVersion: str | None = None
    filter: CompilerArtifactFilterEntity | None = None
    executionContract: dict[str, Any] | None = None


class CompilerArtifactEntity(EntityModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    isActive: bool = False
    createdAt: str | None = None
    artifactKey: str | None = None
    compilerVersion: str | None = None
    compilerRevision: int | None = None
    compileStatus: str | None = None
    diagnosticsPayload: list[dict[str, Any]] = Field(default_factory=list)
    artifactPayload: CompilerArtifactPayloadEntity | None = None


class RuleExecutionContextEntity(EntityModel):
    model_config = ConfigDict(populate_by_name=True)

    ruleId: str
    ruleVersionId: str
    ruleVersionNumber: int
    sourceRuleExpression: str | None = None
    artifactKey: str | None = None
    compilerVersion: str | None = None
    compilerRevision: int | None = None
    compileStatus: str | None = None
    schemaVersion: str | None = None
    executionContract: dict[str, Any] | None = None
    compiledExpression: str | None = None
    executedExpression: str | None = None
    handoffReady: bool = False


def build_rule_version_entity(payload: Any) -> RuleVersionEntity | None:
    if not isinstance(payload, Mapping):
        return None

    version_id = str(payload.get("id") or "").strip()
    if not version_id:
        return None

    version_number_raw = payload.get("versionNumber")
    try:
        version_number = int(version_number_raw) if version_number_raw not in (None, "") else None
    except (TypeError, ValueError):
        version_number = None

    expression = str(payload.get("expression") or "").strip() or None
    return RuleVersionEntity(
        id=version_id,
        versionNumber=version_number,
        isCurrentVersion=bool(payload.get("isCurrentVersion")),
        expression=expression,
    )


def build_rule_record_entity(payload: Any) -> RuleRecordEntity | None:
    if not isinstance(payload, Mapping):
        return None

    rule_id = str(payload.get("id") or "").strip()
    if not rule_id:
        return None

    total_versions_raw = payload.get("total_versions")
    try:
        total_versions = int(total_versions_raw) if total_versions_raw not in (None, "") else None
    except (TypeError, ValueError):
        total_versions = None

    raw_join_conditions = payload.get("joinConditions")
    join_conditions = raw_join_conditions if isinstance(raw_join_conditions, list) else None

    raw_alias_mappings = payload.get("aliasMappings")
    alias_mappings = dict(raw_alias_mappings) if isinstance(raw_alias_mappings, Mapping) else None
    taxonomy = _json_mapping_or_none(payload.get("taxonomy"))

    return RuleRecordEntity(
        id=rule_id,
        name=str(payload.get("name") or "").strip(),
        description=str(payload.get("description")) if payload.get("description") is not None else None,
        comments=str(payload.get("comments")) if payload.get("comments") is not None else None,
        expression=str(payload.get("expression") or "").strip(),
        dimension=str(payload.get("dimension") or "").strip(),
        active=bool(payload.get("active")),
        lifecycle_status=str(payload.get("lifecycle_status") or "").strip() or "active",
        generated=bool(payload.get("generated")),
        is_template=bool(payload.get("is_template")),
        template_id=str(payload.get("template_id") or "").strip() or None,
        workspace=str(payload.get("workspace") or "").strip() or None,
        created_by=str(payload.get("created_by") or "").strip() or None,
        last_approval_by=str(payload.get("last_approval_by") or "").strip() or None,
        last_approval_status=str(payload.get("last_approval_status") or "").strip() or None,
        last_approval_at=str(payload.get("last_approval_at") or "").strip() or None,
        removed=bool(payload.get("removed")),
        removed_at=str(payload.get("removed_at") or "").strip() or None,
        removed_by=str(payload.get("removed_by") or "").strip() or None,
        deleted_on=str(payload.get("deleted_on") or "").strip() or None,
        deleted_by=str(payload.get("deleted_by") or "").strip() or None,
        suggestion_id=str(payload.get("suggestion_id") or "").strip() or None,
        join_conditions=payload.get("join_conditions"),
        alias_mappings=payload.get("alias_mappings"),
        reusable_join_id=str(payload.get("reusable_join_id") or "").strip() or None,
        manual_override_by=str(payload.get("manual_override_by") or "").strip() or None,
        manual_override_at=str(payload.get("manual_override_at") or "").strip() or None,
        check_type=str(payload.get("check_type") or "").strip() or None,
        check_type_params=payload.get("check_type_params"),
        dsl=dict(payload.get("dsl")) if isinstance(payload.get("dsl"), Mapping) else None,
        validation_status=str(payload.get("validation_status") or "").strip() or None,
        validated_at=str(payload.get("validated_at") or "").strip() or None,
        current_version_id=str(payload.get("current_version_id") or "").strip() or None,
        total_versions=total_versions,
        versioning_enabled=(bool(payload.get("versioning_enabled")) if payload.get("versioning_enabled") is not None else None),
        version_created_at=str(payload.get("version_created_at") or "").strip() or None,
        version_updated_at=str(payload.get("version_updated_at") or "").strip() or None,
        tagIds=[str(item) for item in (payload.get("tagIds") if isinstance(payload.get("tagIds"), list) else [])],
        reusableFilterIds=[
            str(item)
            for item in (payload.get("reusableFilterIds") if isinstance(payload.get("reusableFilterIds"), list) else [])
        ],
        reusableFilters=list(payload.get("reusableFilters") if isinstance(payload.get("reusableFilters"), list) else []),
        joinConditions=join_conditions,
        aliasMappings=alias_mappings,
        taxonomy=taxonomy or {},
    )


def build_rule_version_list_entity(payload: Any) -> RuleVersionListEntity | None:
    if not isinstance(payload, Mapping):
        return None

    raw_versions = payload.get("versions") if isinstance(payload.get("versions"), list) else []
    versions = [
        entity
        for entity in (build_rule_version_entity(item) for item in raw_versions)
        if entity is not None
    ]
    return RuleVersionListEntity(versions=versions)


def build_compiler_artifact_entity(payload: Any) -> CompilerArtifactEntity | None:
    if not isinstance(payload, Mapping):
        return None

    artifact_payload = payload.get("artifactPayload") if isinstance(payload.get("artifactPayload"), Mapping) else None
    filter_payload = artifact_payload.get("filter") if isinstance(artifact_payload, Mapping) and isinstance(artifact_payload.get("filter"), Mapping) else None
    execution_contract = (
        dict(artifact_payload.get("executionContract") or {})
        if isinstance(artifact_payload, Mapping) and isinstance(artifact_payload.get("executionContract"), Mapping)
        else None
    )

    compiler_revision_raw = payload.get("compilerRevision")
    try:
        compiler_revision = int(compiler_revision_raw) if compiler_revision_raw not in (None, "") else None
    except (TypeError, ValueError):
        compiler_revision = None

    diagnostics_payload = payload.get("diagnosticsPayload")
    diagnostics = [
        dict(item)
        for item in (diagnostics_payload if isinstance(diagnostics_payload, list) else [])
        if isinstance(item, Mapping)
    ]

    return CompilerArtifactEntity(
        id=str(payload.get("id") or "").strip() or None,
        isActive=bool(payload.get("isActive", payload.get("is_active", False))),
        createdAt=str(payload.get("createdAt") or payload.get("created_at") or "").strip() or None,
        artifactKey=str(payload.get("artifactKey") or "").strip() or None,
        compilerVersion=str(payload.get("compilerVersion") or "").strip() or None,
        compilerRevision=compiler_revision,
        compileStatus=str(payload.get("compileStatus") or "").strip() or None,
        diagnosticsPayload=diagnostics,
        artifactPayload=(
            CompilerArtifactPayloadEntity(
                schemaVersion=str(artifact_payload.get("schemaVersion") or "").strip() or None,
                filter=(
                    CompilerArtifactFilterEntity(
                        normalized=str(filter_payload.get("normalized") or "").strip() or None,
                        source=str(filter_payload.get("source") or "").strip() or None,
                    )
                    if filter_payload is not None
                    else None
                ),
                executionContract=execution_contract,
            )
            if artifact_payload is not None
            else None
        ),
    )
