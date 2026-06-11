from datetime import UTC, datetime
import logging
from typing import Any
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from app.schemas.pydantic_base import SnakeModel

from app.application.services import apply_validation_policies
from app.application.services import compile_rule_to_intermediate_model
from app.application.services import detect_conflicts
from app.application.services import infer_alias_expectations
from app.application.services.data_contract_resolver import JoinConsistencyContractResolver
from app.api.v1.schemas import BatchValidationRequestView
from app.api.v1.schemas import BatchValidationResponseView
from app.api.v1.schemas import RuleView
from app.api.v1.schemas import RuleStatusHistoryView
from app.api.v1.schemas import RuleValidationResponseView
from app.application.resolvers import resolve_rule_view
from app.application.use_cases import activate_rule as activate_rule_use_case
from app.application.use_cases import ActivateRuleCommand
from app.application.use_cases import compare_rule_versions as compare_rule_versions_use_case
from app.application.use_cases import create_rule as create_rule_use_case
from app.application.use_cases import get_rule_rollback_history as get_rule_rollback_history_use_case
from app.application.use_cases import get_rule_status_history as get_rule_status_history_use_case
from app.application.use_cases import get_rule_version as get_rule_version_use_case
from app.application.use_cases import get_rule_version_active_compiler_artifact as get_rule_version_active_compiler_artifact_use_case
from app.application.use_cases import get_rule_version_statistics as get_rule_version_statistics_use_case
from app.application.use_cases import get_rule_versions as get_rule_versions_use_case
from app.application.use_cases import get_rule_details
from app.application.use_cases import ListRulesQuery
from app.application.use_cases import list_rule_compiler_versions as list_rule_compiler_versions_use_case
from app.application.use_cases import list_rule_version_compiler_artifacts as list_rule_version_compiler_artifacts_use_case
from app.application.use_cases import list_rules as list_rules_use_case
from app.application.use_cases import ListRuleTemplatesQuery
from app.application.use_cases import list_rule_template_packs as list_rule_template_packs_use_case
from app.application.use_cases import list_rule_templates as list_rule_templates_use_case
from app.application.use_cases import resolve_rule_template as resolve_rule_template_use_case
from app.application.use_cases import ResolveRuleTemplateCommand
from app.application.use_cases.rule_registry import RuleRegistryQuery
from app.application.use_cases.rule_registry import list_rule_registry as list_rule_registry_use_case
from app.application.use_cases import mark_rule_version_for_rollback as mark_rule_version_for_rollback_use_case
from app.application.use_cases import MarkRuleVersionForRollbackCommand
from app.application.use_cases import remove_rule as remove_rule_use_case
from app.application.use_cases import RemoveRuleCommand
from app.application.use_cases import rollback_rule as rollback_rule_use_case
from app.application.use_cases import RollbackRuleCommand
from app.application.use_cases import RuleMutationCommand
from app.application.use_cases import RuleCompilerVersionsQuery
from app.application.use_cases import TransitionRuleLifecycleCommand
from app.application.use_cases import RuleVersionComparison
from app.application.use_cases import RuleVersionLookup
from app.application.use_cases import RuleVersionsQuery
from app.application.use_cases import save_rule_as_template as save_rule_as_template_use_case
from app.application.use_cases import SaveRuleTemplateCommand
from app.application.use_cases import update_rule_version_tags as update_rule_version_tags_use_case
from app.application.use_cases import UpdateRuleVersionTagsCommand
from app.application.use_cases import transition_rule_lifecycle as transition_rule_lifecycle_use_case
from app.application.use_cases import update_rule as update_rule_use_case
from app.application.use_cases import validate_rule as validate_rule_use_case
from app.application.use_cases import validate_rule_enriched as validate_rule_enriched_use_case
from app.application.use_cases import ValidateRuleEnrichedCommand
from app.application.use_cases import ValidateRuleCommand
from app.application.use_cases import validate_rules_batch as validate_rules_batch_use_case
from app.application.use_cases import ValidateRulesBatchCommand
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_approvals_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_join_consistency_contract_resolver
from app.core.dependencies import get_gx_suite_repository
from app.core.dependencies import get_rules_repository
from app.core.dependencies import get_validation_artifact_repository
from app.core.dependencies import get_validation_run_repository
from app.core.request_context import get_scopes
from app.core.request_context import get_user_id
from app.core.log_event import log_event
from app.core.telemetry import set_span_attributes, traced_span
from app.domain.status_governance import is_transition_allowed
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import ApprovalsRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import GxSuiteRepository
from app.domain.interfaces import RulesRepository
from app.domain.interfaces import ValidationArtifactRepository
from app.domain.interfaces import ValidationRunRepository
from app.domain.entities import build_catalog_term_entities
from app.domain.entities import resolve_rule_aliases
from app.domain.entities import rule_autopublish_policy
from app.domain.entities import rule_policy
from app.domain.entities.rule_templates import RuleTemplateEntity
from app.domain.entities.rule_templates import RuleTemplatePackEntity
from app.domain.entities.rule_templates import RuleTemplateResolutionEntity
from app.domain.entities.rule_check_type import RuleCheckType
from app.domain.entities.rule_dsl_v2 import RuleDslV2Document

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/rules", tags=["rules"])


class GxSuiteAutoPublishRequest(SnakeModel):
    """Optional body for activate_rule to auto-publish a GX suite stub."""

    dataObjectId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = Field(default=None, pattern=r"^odcs\..+$")
    dataObjectVersionIds: list[str] = Field(default_factory=list)
    primaryKeyFields: list[str] = Field(default_factory=list)
    businessKeyFields: list[str] = Field(default_factory=list)
    suiteVersion: int = Field(default=1, ge=1)




class RollbackRequest(SnakeModel):
    toVersionId: str
    reason: str
    skipApproval: bool = False
    tags: list[str] | None = None


class VersionTagsUpdateRequest(SnakeModel):
    tags: list[str]


class MarkForRollbackRequest(SnakeModel):
    marked: bool


class ManualExpressionOverrideRequest(SnakeModel):
    expression: str
    confirmed: bool = False


class BaseRuleDslSourceRequest(SnakeModel):
    joinConditions: list[dict] = Field(default_factory=list)
    aliasMappings: dict = Field(default_factory=dict)
    reusableJoinId: str | None = None
    reusableFilterIds: list[str] = Field(default_factory=list)


class FilterExpressionRuleDslSourceRequest(BaseRuleDslSourceRequest):
    kind: Literal["filter_expression"]
    expression: str


class CheckTypeRuleDslSourceRequest(BaseRuleDslSourceRequest):
    kind: Literal["check_type"]
    checkType: str
    checkTypeParams: dict
    manualExpressionOverride: ManualExpressionOverrideRequest | None = None


RuleDslSourceRequest = Annotated[
    FilterExpressionRuleDslSourceRequest | CheckTypeRuleDslSourceRequest,
    Field(discriminator="kind"),
]


class RuleDslV1Request(SnakeModel):
    schemaVersion: Literal["1.0.0"] = "1.0.0"
    source: RuleDslSourceRequest


RuleDslRequest = Annotated[
    RuleDslV1Request | RuleDslV2Document,
    Field(discriminator="schemaVersion"),
]


class RuleTaxonomyRequest(SnakeModel):
    type: str | None = None
    severity: str | None = None
    domain: str | None = None
    owner: str | None = None
    dataSteward: str | None = None
    domainOwner: str | None = None
    technicalOwner: str | None = None
    slaScope: str | None = None
    executionTarget: str | None = None


class RuleMutationRequest(SnakeModel):
    name: str
    description: str | None = None
    comments: str | None = None
    dimension: str = ""
    active: bool = False
    workspace: str | None = None
    workspaceId: str | None = None
    generated: bool | None = None
    isTemplate: bool = False
    templateId: str | None = None
    suggestionId: str | None = None
    aiOutput: bool = False
    dsl: RuleDslRequest
    taxonomy: RuleTaxonomyRequest | None = None


class RuleLifecycleTransitionRequest(SnakeModel):
    lifecycle_status: str
    reason: str | None = None


def _to_rule_mutation_command(body: RuleMutationRequest) -> RuleMutationCommand:
    return RuleMutationCommand(
        name=body.name,
        description=body.description,
        comments=body.comments,
        dimension=body.dimension,
        active=body.active,
        workspace=body.workspace,
        workspace_id=body.workspaceId,
        generated=body.generated,
        is_template=body.isTemplate,
        template_id=body.templateId,
        suggestion_id=body.suggestionId,
        ai_output=body.aiOutput,
        dsl=body.dsl.model_dump(mode="python", by_alias=True, exclude_none=True),
        taxonomy=(body.taxonomy.model_dump(mode="python", by_alias=True, exclude_none=True) if body.taxonomy else {}),
    )


class RuleTemplateRequest(SnakeModel):
    templateName: str
    templateDescription: str | None = None


class RuleTemplateResolveRequest(SnakeModel):
    overrides: dict[str, Any] = Field(default_factory=dict)


class EnrichedValidationRequest(SnakeModel):
    ruleVersionId: str
    expression: str
    detectedAliases: list[str] = Field(default_factory=list)
    unresolvedAliases: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    manualAliasMappings: dict[str, str] = Field(default_factory=dict)


class RuleCheckTypeValidationRequest(SnakeModel):
    checkType: RuleCheckType
    checkTypeParams: dict[str, Any] = Field(default_factory=dict)


class RuleCheckTypeValidationResponseView(SnakeModel):
    valid: bool
    message: str | None = None
    fieldErrors: dict[str, str] = Field(default_factory=dict)
    normalizedCheckTypeParams: dict[str, Any] | None = None


class AliasResolveRequest(SnakeModel):
    aliases: list[str] = Field(default_factory=list)
    manualMappings: dict[str, str] = Field(default_factory=dict)


@router.get("")
async def list_rules(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    workspace: str | None = Query(default=None),
    is_template: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    lifecycle_status: str | None = Query(default=None),
    owner: str | None = Query(default=None),
    updated_since: datetime | None = Query(default=None),
    updated_before: datetime | None = Query(default=None),
    repository: RulesRepository = Depends(get_rules_repository),
    approvals_repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> dict:
    log_event(
        _log,
        "rules.list.start",
        component="rules-api",
        page=page,
        limit=limit,
        includeDeleted=include_deleted,
        workspace=workspace,
        isTemplate=is_template,
        query=q,
        status=status,
        lifecycleStatus=lifecycle_status,
        owner=owner,
        updatedSince=updated_since.isoformat() if updated_since else None,
        updatedBefore=updated_before.isoformat() if updated_before else None,
    )
    payload = await list_rules_use_case(
        request=ListRulesQuery(
            page=page,
            limit=limit,
            include_deleted=include_deleted,
            workspace=workspace,
            is_template=is_template,
            query=q,
            status=status,
            lifecycle_status=lifecycle_status,
            owner=owner,
            updated_since=updated_since,
            updated_before=updated_before,
        ),
        repository=repository,
        approvals_repository=approvals_repository,
    )
    log_event(
        _log,
        "rules.list.complete",
        component="rules-api",
        resultCount=len(payload.get("data") or []),
        total=(payload.get("pagination") or {}).get("total"),
    )
    return payload


@router.get("/registry")
async def list_rule_registry(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    workspace: str | None = Query(default=None),
    is_template: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    lifecycle_status: str | None = Query(default=None),
    owner: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    execution_target: str | None = Query(default=None),
    rule_type: str | None = Query(default=None),
    updated_since: datetime | None = Query(default=None),
    updated_before: datetime | None = Query(default=None),
    repository: RulesRepository = Depends(get_rules_repository),
    approvals_repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> dict:
    log_event(
        _log,
        "rules.registry.start",
        component="rules-api",
        page=page,
        limit=limit,
        includeDeleted=include_deleted,
        workspace=workspace,
        isTemplate=is_template,
        query=q,
        status=status,
        lifecycleStatus=lifecycle_status,
        owner=owner,
        domain=domain,
        severity=severity,
        executionTarget=execution_target,
        ruleType=rule_type,
        updatedSince=updated_since.isoformat() if updated_since else None,
        updatedBefore=updated_before.isoformat() if updated_before else None,
    )
    payload = await list_rule_registry_use_case(
        request=RuleRegistryQuery(
            page=page,
            limit=limit,
            include_deleted=include_deleted,
            workspace=workspace,
            is_template=is_template,
            query=q,
            status=status,
            lifecycle_status=lifecycle_status,
            owner=owner,
            domain=domain,
            severity=severity,
            execution_target=execution_target,
            rule_type=rule_type,
            updated_since=updated_since,
            updated_before=updated_before,
        ),
        repository=repository,
        approvals_repository=approvals_repository,
    )
    log_event(
        _log,
        "rules.registry.complete",
        component="rules-api",
        resultCount=len(payload.get("data") or []),
        total=(payload.get("pagination") or {}).get("total"),
    )
    return payload


@router.get("/compiler-versions")
async def list_rule_compiler_versions(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    workspace: str | None = Query(default=None),
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    return await list_rule_compiler_versions_use_case(
        request=RuleCompilerVersionsQuery(page=page, limit=limit, workspace=workspace),
        repository=repository,
        resolve_current_rule_version=rule_autopublish_policy.resolve_current_rule_version,
    )


@router.get("/template-packs", response_model=list[RuleTemplatePackEntity])
async def list_rule_template_packs() -> list[RuleTemplatePackEntity]:
    return await list_rule_template_packs_use_case()


@router.get("/templates", response_model=list[RuleTemplateEntity])
async def list_rule_templates(
    pack_id: str | None = Query(default=None),
    dimension: str | None = Query(default=None),
) -> list[RuleTemplateEntity]:
    return await list_rule_templates_use_case(
        ListRuleTemplatesQuery(pack_id=pack_id, dimension=dimension),
    )


@router.post("/templates/{template_id}/resolve", response_model=RuleTemplateResolutionEntity)
async def resolve_rule_template(
    template_id: str,
    body: RuleTemplateResolveRequest,
) -> RuleTemplateResolutionEntity:
    return await resolve_rule_template_use_case(
        ResolveRuleTemplateCommand(template_id=template_id, overrides=body.overrides),
    )


@router.get("/{rule_id}", response_model=RuleView)
async def get_rule(
    rule_id: str,
    repository: RulesRepository = Depends(get_rules_repository),
    approvals_repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> RuleView:
    entity = await get_rule_details(rule_id, repository)
    rule_view = await resolve_rule_view(entity, repository)
    pending_rule_ids = rule_policy.build_pending_deactivation_rule_ids([
        approval.model_dump() for approval in approvals_repository.list_approvals(None)
    ])
    return rule_view.model_copy(update={"pendingDeactivationRequested": rule_id in pending_rule_ids})


@router.post("")
async def create_rule(
    body: RuleMutationRequest,
    repository: RulesRepository = Depends(get_rules_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    contract_resolver: JoinConsistencyContractResolver = Depends(get_join_consistency_contract_resolver),
) -> dict:
    actor_id = get_user_id() or "user-admin"
    return await create_rule_use_case(
        command=_to_rule_mutation_command(body),
        repository=repository,
        config_repository=config_repository,
        catalog_repository=catalog_repository,
        contract_resolver=contract_resolver,
        actor_id=actor_id,
    )


@router.put("/{rule_id}")
async def update_rule(
    rule_id: str,
    body: RuleMutationRequest,
    repository: RulesRepository = Depends(get_rules_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    contract_resolver: JoinConsistencyContractResolver = Depends(get_join_consistency_contract_resolver),
) -> dict:
    actor_id = get_user_id() or "user-admin"
    return await update_rule_use_case(
        rule_id=rule_id,
        command=_to_rule_mutation_command(body),
        repository=repository,
        config_repository=config_repository,
        catalog_repository=catalog_repository,
        contract_resolver=contract_resolver,
        actor_id=actor_id,
    )


@router.post("/{rule_id}/validate", response_model=RuleValidationResponseView)
async def validate_rule_composition(
    rule_id: str,
    repository: RulesRepository = Depends(get_rules_repository),
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> RuleValidationResponseView:
    response_payload = await validate_rule_use_case(
        command=ValidateRuleCommand(rule_id=rule_id, validated_by=get_user_id()),
        repository=repository,
        data_catalog_repository=catalog_repository,
        config_repository=config_repository,
        apply_validation_policies=apply_validation_policies,
        compile_rule_to_intermediate_model=compile_rule_to_intermediate_model,
        infer_alias_expectations=infer_alias_expectations,
        persist_compiler_artifact=rule_autopublish_policy.persist_compiler_artifact,
        resolve_current_rule_version=rule_autopublish_policy.resolve_current_rule_version,
        has_upstream_validation_issue=rule_policy.has_upstream_validation_issue,
    )
    return RuleValidationResponseView.model_validate(response_payload)


@router.post("/validate/check-type", response_model=RuleCheckTypeValidationResponseView)
async def validate_check_type_draft(
    body: RuleCheckTypeValidationRequest,
    user_id: str = Depends(get_user_id),
) -> RuleCheckTypeValidationResponseView:
    _ = user_id
    result = rule_policy.validate_rule_check_type_params_detailed(
        check_type=body.checkType,
        check_type_params=body.checkTypeParams,
    )
    return RuleCheckTypeValidationResponseView.model_validate(
        {
            "valid": result.valid,
            "message": result.message,
            "fieldErrors": result.field_errors or {},
            "normalizedCheckTypeParams": result.normalized_params,
        }
    )


@router.post("/{rule_id}/validate/enriched")
async def validate_rule_composition_enriched(
    rule_id: str,
    body: EnrichedValidationRequest,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    return await validate_rule_enriched_use_case(
        command=ValidateRuleEnrichedCommand(
            rule_id=rule_id,
            rule_version_id=body.ruleVersionId,
            expression=body.expression,
            detected_aliases=body.detectedAliases,
            unresolved_aliases=body.unresolvedAliases,
            issues=body.issues,
            manual_alias_mappings=body.manualAliasMappings,
        ),
        repository=repository,
    )


@router.post("/{rule_id}/activate")
async def activate_rule(
    rule_id: str,
    effective_at: str | None = Query(default=None),
    body: GxSuiteAutoPublishRequest | None = None,
    repository: RulesRepository = Depends(get_rules_repository),
    validation_artifact_repository: ValidationArtifactRepository = Depends(get_validation_artifact_repository),
    gx_suite_repository: GxSuiteRepository = Depends(get_gx_suite_repository),
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> dict:
    with traced_span(
        "rules.activate",
        endpoint_group="rules",
        operation="activate_rule",
        rule_id=rule_id,
        auto_publish_requested=body is not None,
        effective_at_requested=bool(str(effective_at or "").strip()),
    ) as span:
        return await activate_rule_use_case(
            command=ActivateRuleCommand(
                rule_id=rule_id,
                effective_at=effective_at,
                granted_scopes=get_scopes(),
                auto_publish_request=body,
                saved_by=get_user_id(),
            ),
            repository=repository,
            validation_artifact_repository=validation_artifact_repository,
            gx_suite_repository=gx_suite_repository,
            catalog_repository=catalog_repository,
            span=span,
            current_time=lambda: datetime.now(UTC),
            is_transition_allowed=is_transition_allowed,
            resolve_current_rule_version=rule_autopublish_policy.resolve_current_rule_version,
            compile_rule_to_intermediate_model=compile_rule_to_intermediate_model,
            persist_compiler_artifact=rule_autopublish_policy.persist_compiler_artifact,
            persist_validation_artifact_from_compiler=rule_autopublish_policy.persist_validation_artifact_from_compiler,
            set_span_attributes=set_span_attributes,
            log_event=log_event,
            logger=_log,
        )


@router.patch("/{rule_id}/lifecycle")
async def transition_rule_lifecycle(
    rule_id: str,
    body: RuleLifecycleTransitionRequest,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    return await transition_rule_lifecycle_use_case(
        command=TransitionRuleLifecycleCommand(
            rule_id=rule_id,
            lifecycle_status=body.lifecycle_status,
            granted_scopes=get_scopes(),
            changed_by=get_user_id() or "user-admin",
            reason=body.reason,
        ),
        repository=repository,
        is_transition_allowed=is_transition_allowed,
    )


@router.delete("/{rule_id}")
async def remove_rule(
    rule_id: str,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    return await remove_rule_use_case(
        command=RemoveRuleCommand(
            rule_id=rule_id,
            granted_scopes=get_scopes(),
            removed_by=get_user_id() or "user-admin",
        ),
        repository=repository,
        is_transition_allowed=is_transition_allowed,
    )


@router.post("/{rule_id}/template")
async def save_rule_as_template(
    rule_id: str,
    body: RuleTemplateRequest,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    return await save_rule_as_template_use_case(
        SaveRuleTemplateCommand(
            rule_id=rule_id,
            template_name=body.templateName,
            template_description=body.templateDescription,
            created_by=get_user_id() or "user-admin",
        ),
        repository=repository,
    )


@router.post("/aliases/resolve")
async def resolve_aliases(
    body: AliasResolveRequest,
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> dict:
    if not body.aliases:
        raise HTTPException(status_code=400, detail="aliases array required")

    catalog_terms = build_catalog_term_entities(catalog_repository.list_attributes_catalog(None))
    return {"resolutions": resolve_rule_aliases(body.aliases, body.manualMappings, catalog_terms)}


@router.get("/{rule_id}/versions")
async def get_rule_versions(
    rule_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    return await get_rule_versions_use_case(
        RuleVersionsQuery(rule_id=rule_id, limit=limit, offset=offset),
        repository=repository,
    )


@router.get("/{rule_id}/versions/rollback-history")
async def get_rule_rollback_history(
    rule_id: str,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    return await get_rule_rollback_history_use_case(
        RuleVersionsQuery(rule_id=rule_id, limit=limit, offset=offset),
        repository=repository,
    )


@router.get("/{rule_id}/status-history", response_model=list[RuleStatusHistoryView])
async def get_rule_status_history(
    rule_id: str,
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    repository: RulesRepository = Depends(get_rules_repository),
) -> list[RuleStatusHistoryView]:
    payload = await get_rule_status_history_use_case(
        RuleVersionsQuery(rule_id=rule_id, limit=limit, offset=offset),
        repository=repository,
    )
    return [RuleStatusHistoryView.model_validate(row) for row in payload]


@router.get("/{rule_id}/versions/stats")
async def get_rule_version_statistics(
    rule_id: str,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    return await get_rule_version_statistics_use_case(rule_id, repository=repository)


@router.get("/{rule_id}/versions/{version_1}/compare/{version_2}")
async def compare_rule_versions(
    rule_id: str,
    version_1: str,
    version_2: str,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    return await compare_rule_versions_use_case(
        RuleVersionComparison(rule_id=rule_id, version_1=version_1, version_2=version_2),
        repository=repository,
    )


@router.get("/{rule_id}/versions/{version_id}")
async def get_rule_version(
    rule_id: str,
    version_id: str,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    return await get_rule_version_use_case(
        RuleVersionLookup(rule_id=rule_id, version_id=version_id),
        repository=repository,
    )


@router.get("/{rule_id}/versions/{version_id}/compiler-artifacts")
async def list_rule_version_compiler_artifacts(
    rule_id: str,
    version_id: str,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    return await list_rule_version_compiler_artifacts_use_case(
        RuleVersionLookup(rule_id=rule_id, version_id=version_id),
        repository=repository,
    )


@router.get("/{rule_id}/versions/{version_id}/compiler-artifacts/active")
async def get_rule_version_active_compiler_artifact(
    rule_id: str,
    version_id: str,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    return await get_rule_version_active_compiler_artifact_use_case(
        RuleVersionLookup(rule_id=rule_id, version_id=version_id),
        repository=repository,
    )


@router.post("/{rule_id}/rollback", status_code=202)
async def rollback_rule(
    rule_id: str,
    body: RollbackRequest,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    return await rollback_rule_use_case(
        RollbackRuleCommand(
            rule_id=rule_id,
            to_version_id=body.toVersionId,
            reason=body.reason,
            requested_by_user_id=get_user_id() or "user-admin",
            skip_approval=body.skipApproval,
            tags=body.tags,
        ),
        repository=repository,
    )


@router.patch("/{rule_id}/versions/{version_id}/tags")
async def update_rule_version_tags(
    rule_id: str,
    version_id: str,
    body: VersionTagsUpdateRequest,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    return await update_rule_version_tags_use_case(
        UpdateRuleVersionTagsCommand(
            rule_id=rule_id,
            version_id=version_id,
            tags=body.tags,
            updated_by_user_id=get_user_id() or "user-admin",
        ),
        repository=repository,
    )


@router.patch("/{rule_id}/versions/{version_id}/mark-for-rollback")
async def mark_rule_version_for_rollback(
    rule_id: str,
    version_id: str,
    body: MarkForRollbackRequest,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    return await mark_rule_version_for_rollback_use_case(
        MarkRuleVersionForRollbackCommand(rule_id=rule_id, version_id=version_id, marked=body.marked),
        repository=repository,
    )


# ---------------------------------------------------------------------------
# DQ-1.2 + DQ-1.3: Batch validation with conflict detection
# ---------------------------------------------------------------------------

@router.post("/validate/batch", response_model=BatchValidationResponseView)
async def validate_rules_batch(
    body: BatchValidationRequestView,
    repository: RulesRepository = Depends(get_rules_repository),
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
    run_repository: ValidationRunRepository = Depends(get_validation_run_repository),
    user_id: str = Depends(get_user_id),
) -> BatchValidationResponseView:
    payload = await validate_rules_batch_use_case(
        command=ValidateRulesBatchCommand(
            rule_ids=body.ruleIds,
            workspace=body.workspace,
            triggered_by=user_id,
        ),
        repository=repository,
        data_catalog_repository=catalog_repository,
        config_repository=config_repository,
        run_repository=run_repository,
        apply_validation_policies=apply_validation_policies,
        compile_rule_to_intermediate_model=compile_rule_to_intermediate_model,
        infer_alias_expectations=infer_alias_expectations,
        persist_compiler_artifact=rule_autopublish_policy.persist_compiler_artifact,
        resolve_current_rule_version=rule_autopublish_policy.resolve_current_rule_version,
        has_upstream_validation_issue=rule_policy.has_upstream_validation_issue,
        detect_conflicts=detect_conflicts,
        logger=_log,
    )
    return BatchValidationResponseView.model_validate(payload)
