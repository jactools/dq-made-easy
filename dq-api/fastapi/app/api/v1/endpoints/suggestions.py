from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from app.api.presenters.suggestions import build_data_sources_payload
from app.api.presenters.suggestions import build_not_authenticated_payload
from app.api.presenters.suggestions import build_natural_language_draft_request_not_found_payload
from app.api.presenters.suggestions import build_suggestion_not_found_payload
from app.api.presenters.suggestions import build_suggestions_payload
from app.api.presenters.suggestions import normalize_suggestion_apply_rule_id
from app.api.presenters.suggestions import serialize_suggestion_entity
from app.api.v1.schemas.natural_language_rule_drafting_view import NaturalLanguageRulePreviewCreateSuggestionRequestView
from app.api.v1.schemas.natural_language_rule_drafting_view import NaturalLanguageDraftRequestStatusResponseView
from app.api.v1.schemas.natural_language_rule_drafting_view import NaturalLanguageDraftRequestHistoryResponseView
from app.api.v1.schemas.natural_language_rule_drafting_view import NaturalLanguageDraftSuggestionResponseView
from app.api.v1.schemas.natural_language_rule_drafting_view import NaturalLanguageRulePreviewRequestView
from app.api.v1.schemas.natural_language_rule_drafting_view import NaturalLanguageRulePreviewResponseView
from app.application.services.natural_language_draft_enqueue_service import NaturalLanguageDraftEnqueueServiceError
from app.application.services.natural_language_draft_enqueue_service import enqueue_natural_language_draft_job
from app.application.services.natural_language_draft_enqueue_service import load_request_record_from_settings
from app.application.services.metadata_steward_service import MetadataStewardLookupError
from app.application.services.metadata_steward_service import build_metadata_steward_payload
from app.application.services.metadata_steward_service import normalize_metadata_steward_error
from app.application.services.natural_language_rule_drafting import NaturalLanguageDraftingProviderResponseError
from app.application.services.natural_language_rule_drafting import NaturalLanguageDraftingProviderUnavailableError
from app.application.services.natural_language_rule_drafting import build_natural_language_rule_draft_suggestion_payload
from app.application.services.natural_language_rule_drafting import build_natural_language_rule_preview_payload_for_provider
from app.application.services.tag_suggestion_service import TagSuggestionService
from app.core.config import get_settings
from app.core.dependencies import get_admin_repository
from app.core.dependencies import get_approvals_repository
from app.core.dependencies import get_data_asset_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_incident_repository
from app.core.dependencies import get_profiling_repository
from app.core.dependencies import get_registry_definition_resolver
from app.core.dependencies import get_rules_repository
from app.core.dependencies import get_suggestions_repository
from app.core.otel_metrics import increment_suggestions_preview_event
from app.core.request_context import get_scopes, get_user_id
from app.domain.interfaces import AdminRepository
from app.domain.interfaces import ApprovalsRepository
from app.domain.interfaces import DataAssetRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import IncidentRepository
from app.domain.interfaces import ProfilingRepository
from app.domain.interfaces import RulesRepository
from app.domain.interfaces import SuggestionsRepository
from app.domain.entities.rule_check_type import RuleCheckType
from app.domain.entities import NaturalLanguageDraftRequestEntity
from app.domain.entities.rule_dsl_capability_registry import rule_dsl_backend_capability_matrix
from app.domain.entities.rule_dsl_capability_registry import RuleDslCapabilityFamily
from app.domain.interfaces.v1.suggestions_repository import SuggestionNotFoundError
from app.schemas.pydantic_base import SnakeModel

router = APIRouter(tags=["suggestions"])


class NaturalLanguageRulePreviewTelemetryRequest(SnakeModel):
    action: Literal["attributes_selected", "preview_cancelled"]
    currentWorkspaceId: str = Field(min_length=1)
    selectedAttributeCount: int | None = Field(default=None, ge=0)


class SuggestionRuleActionRequestView(SnakeModel):
    ruleId: str | None = None
    workspaceId: str | None = None


def _append_suggestion_audit_event(
    *,
    approvals_repository: ApprovalsRepository,
    suggestion_id: str,
    action: str,
    user_id: str,
    workspace_id: str,
    rule_id: str | None = None,
) -> None:
    normalized_workspace_id = str(workspace_id or '').strip()
    if not normalized_workspace_id:
        raise HTTPException(status_code=400, detail='workspaceId is required for suggestion interactions')

    approvals_repository.append_audit_event(
        approval_id=f'suggestion:{suggestion_id}',
        action=f'suggestion.{action}',
        actor_id=user_id,
        details={
            'suggestion_id': suggestion_id,
            'workspace_id': normalized_workspace_id,
            'rule_id': rule_id,
        },
    )


class Dq7DslAssistantSupportView(SnakeModel):
    engine: str
    support: Literal["native", "partial", "sql", "custom", "no"]
    supportedSubsets: list[str] = Field(default_factory=list)
    compilerBehavior: str
    notes: str


class Dq7DslAssistantPreviewResponseView(SnakeModel):
    success: bool = True
    checkType: RuleCheckType
    constructFamily: RuleDslCapabilityFamily
    capabilitySummary: str
    compilerHint: str
    support: list[Dq7DslAssistantSupportView]


class TagSuggestionView(SnakeModel):
    id: str
    name: str
    usageCount: int
    sourceCount: int


class TagSuggestionsResponseView(SnakeModel):
    success: bool = True
    query: str | None = None
    count: int = 0
    tags: list[TagSuggestionView] = Field(default_factory=list)


def _build_preview_error_payload(*, error: str, message: str, status: int) -> dict:
    return {
        "error": error,
        "message": message,
        "status": status,
    }


def _build_metadata_steward_error_payload(*, error: str, message: str, status: int) -> dict:
    return {
        "error": error,
        "message": message,
        "status": status,
    }


def _build_natural_language_request_record(
    *,
    request_id: str,
    job_id: str,
    user_id: str,
    payload: NaturalLanguageRulePreviewRequestView,
    analysis_type: str,
    accessible_workspace_ids: list[str] | None = None,
    result: dict | None = None,
    status: str = "started",
    error_message: str | None = None,
) -> NaturalLanguageDraftRequestEntity:
    now = datetime.now(UTC).isoformat()
    completed_at = now if status in {"completed", "failed"} else None
    return NaturalLanguageDraftRequestEntity(
        request_id=request_id,
        job_id=job_id,
        requested_by_user_id=user_id,
        current_workspace_id=payload.currentWorkspaceId,
        search_scope=payload.searchScope,
        analysis_provider=payload.analysisProvider,
        analysis_type=analysis_type,
        prompt=payload.prompt,
        selected_attribute_ids=[],
        accessible_workspace_ids=list(accessible_workspace_ids or []),
        requested_at=now,
        started_at=now,
        completed_at=completed_at,
        status=status,
        error_message=error_message,
        suggestion_id=None,
        result=result,
        correlation_id=request_id,
    )


_D7_ASSISTANT_FAMILY_BY_CHECK_TYPE: dict[str, RuleDslCapabilityFamily] = {
    "ROW_COUNT": "metric_threshold",
    "THRESHOLD": "metric_threshold",
    "PRESENT": "row_assertion",
    "REGEX": "row_assertion",
    "RANGE": "row_assertion",
    "ALLOWLIST": "row_assertion",
    "BLOCKLIST": "row_assertion",
    "UNIQUENESS": "row_assertion",
    "REFERENTIAL_INTEGRITY": "reference_assertion",
    "FRESHNESS": "freshness_assertion",
    "LAG": "freshness_assertion",
    "FUTURE_DATE": "freshness_assertion",
    "CORRECT": "reconciliation_assertion",
    "RECONCILE": "reconciliation_assertion",
    "PLAUSIBLE": "row_assertion",
    "TRANSFER_MATCH": "reconciliation_assertion",
    "JOIN_CONSISTENCY": "reconciliation_assertion",
}

_D7_ASSISTANT_SUMMARIES: dict[RuleDslCapabilityFamily, str] = {
    "row_assertion": "Row-level predicate checks over one or more selected attributes.",
    "metric_threshold": "Dataset-level threshold checks over deterministic metrics such as row count or completeness.",
    "reference_assertion": "Existence checks against another source or dataset.",
    "freshness_assertion": "Timeliness checks anchored to a time window or recency rule.",
    "reconciliation_assertion": "Cross-source comparisons and reconciliation rules.",
}

_D7_ASSISTANT_COMPILER_HINTS: dict[RuleDslCapabilityFamily, str] = {
    "row_assertion": "Current implemented runtime: GX predicate lowering with fail-fast validation.",
    "metric_threshold": "Current implemented runtime: GX metric expectation lowering for supported metric subsets.",
    "reference_assertion": "Current implemented runtime: GX-supported reference lowering; unsupported shapes fail fast.",
    "freshness_assertion": "Current implemented runtime: GX-supported freshness lowering after duration normalization.",
    "reconciliation_assertion": "Current implemented runtime: GX-supported reconciliation subsets; unsupported shapes fail fast.",
}

_D7_ASSISTANT_IMPLEMENTED_TARGETS = {"gx"}

_D7_ASSISTANT_IMPLEMENTED_NOTES: dict[RuleDslCapabilityFamily, str] = {
    "row_assertion": "Implemented through the GX lowerer for supported row predicates and evidence policy.",
    "metric_threshold": "Implemented through the GX lowerer for supported metric thresholds and bounded aggregate semantics.",
    "reference_assertion": "Implemented through the GX lowerer only where reference semantics can be preserved.",
    "freshness_assertion": "Implemented through the GX lowerer for supported freshness checks.",
    "reconciliation_assertion": "Implemented through the GX lowerer only for currently supported reconciliation subsets.",
}


def _resolve_accessible_workspace_ids(
    *,
    request: Request,
    admin_repository: AdminRepository,
    user_id: str,
) -> set[str]:
    auth_claims = getattr(request.state, "auth_claims", None)
    current_user = admin_repository.get_current_user(user_id, auth_claims)
    if current_user is None:
        return set()

    workspace_ids = {
        str(item.workspace_id or "").strip()
        for item in list(current_user.workspace_roles or [])
        if str(item.workspace_id or "").strip()
    }
    if workspace_ids:
        return workspace_ids
    return {
        str(item or "").strip()
        for item in list(current_user.workspaces or [])
        if str(item or "").strip()
    }


def _normalize_preview_error_code(message: str) -> str:
    normalized_message = str(message or "").strip().lower()
    if "preview prompt cannot be blank" in normalized_message:
        return "blank_prompt"
    if "supports uniqueness, present, regex, range, allowlist, and freshness" in normalized_message:
        return "unsupported_check_type"
    if "mention the attribute, column, or field" in normalized_message:
        return "missing_target_attribute"
    if "unsupported search scope" in normalized_message:
        return "unsupported_search_scope"
    if "current workspace is required" in normalized_message:
        return "missing_workspace"
    if "preview metadata dependencies are unavailable" in normalized_message:
        return "missing_metadata_dependencies"
    if "cross-workspace attribute search is not available" in normalized_message:
        return "cross_workspace_access_denied"
    if "same data object version" in normalized_message:
        return "ambiguous_multi_object_selection"
    if "select at least one candidate attribute" in normalized_message:
        return "missing_selected_attributes"
    if "selected attributes are no longer valid" in normalized_message:
        return "stale_selected_attributes"
    return "invalid_preview_request"


def _record_preview_event(
    *,
    repository: SuggestionsRepository,
    user_id: str,
    workspace_id: str,
    action: str,
    result: str = "success",
    error_code: str | None = None,
    details: dict | None = None,
) -> None:
    repository.record_preview_event(
        user_id=user_id,
        workspace_id=workspace_id,
        action=action,
        result=result,
        error_code=error_code,
        details=details,
    )
    increment_suggestions_preview_event(action=action, result=result, error_code=error_code)


def _label_dq7_engine(target: str) -> str:
    return {
        "gx": "GX",
        "sodacl": "SodaCL",
        "sql": "SQL",
        "pyspark_native": "PySpark native",
        "custom_worker": "Custom worker",
    }.get(target, target)


def _build_dq7_dsl_assistant_payload(*, check_type: RuleCheckType) -> Dq7DslAssistantPreviewResponseView:
    family = _D7_ASSISTANT_FAMILY_BY_CHECK_TYPE.get(check_type.value)
    if family is None:
        raise ValueError(f"Unsupported DQ7 assistant check type '{check_type}'.")

    capability_matrix = rule_dsl_backend_capability_matrix()
    family_rows = capability_matrix.get(family)
    if family_rows is None:
        raise ValueError(f"No DQ7 capability matrix entry registered for '{family}'.")

    implemented_family_rows = {
        target: entry
        for target, entry in family_rows.items()
        if str(target) in _D7_ASSISTANT_IMPLEMENTED_TARGETS
    }
    if not implemented_family_rows:
        raise RuntimeError(f"No implemented DQ7 assistant runtime capability entry registered for '{family}'.")

    engine_sort_order = {"gx": 0}

    support_rows = [
        Dq7DslAssistantSupportView(
            engine=_label_dq7_engine(str(entry["target"])),
            support=entry["support"],
            supportedSubsets=list(entry.get("supported_subsets") or []),
            compilerBehavior=str(entry.get("compiler_behavior") or ""),
            notes=_D7_ASSISTANT_IMPLEMENTED_NOTES[family],
        )
        for _, entry in sorted(
            implemented_family_rows.items(),
            key=lambda item: engine_sort_order.get(str(item[0]), len(engine_sort_order)),
        )
    ]

    return Dq7DslAssistantPreviewResponseView(
        checkType=check_type,
        constructFamily=family,
        capabilitySummary=_D7_ASSISTANT_SUMMARIES[family],
        compilerHint=_D7_ASSISTANT_COMPILER_HINTS[family],
        support=support_rows,
    )


@router.get("/suggestions/dq7-dsl-assistant", response_model=Dq7DslAssistantPreviewResponseView)
async def get_dq7_dsl_assistant_preview(
    check_type: RuleCheckType = Query(alias="check_type"),
    current_workspace_id: str = Query(min_length=1, alias="current_workspace_id"),
    repository: SuggestionsRepository = Depends(get_suggestions_repository),
) -> JSONResponse:
    user_id = get_user_id()
    if not user_id:
        return JSONResponse(status_code=401, content=build_not_authenticated_payload())

    try:
        preview_payload = _build_dq7_dsl_assistant_payload(check_type=check_type)
        repository.record_preview_event(
            user_id=user_id,
            workspace_id=current_workspace_id,
            action="dq7_dsl_assistant_preview",
            details={
                "check_type": check_type.value,
                "construct_family": str(preview_payload.constructFamily),
            },
        )
        increment_suggestions_preview_event(
            action="dq7_dsl_assistant_preview",
            result="success",
        )
    except ValueError as exc:
        repository.record_preview_event(
            user_id=user_id,
            workspace_id=current_workspace_id,
            action="dq7_dsl_assistant_preview",
            result="failure",
            error_code="invalid_dq7_assistant_request",
            details={"check_type": check_type.value},
        )
        increment_suggestions_preview_event(
            action="dq7_dsl_assistant_preview",
            result="failure",
            error_code="invalid_dq7_assistant_request",
        )
        return JSONResponse(
            status_code=400,
            content=_build_preview_error_payload(
                error="invalid_dq7_assistant_request",
                message=str(exc),
                status=400,
            ),
        )

    return JSONResponse(status_code=200, content=preview_payload.model_dump(by_alias=True, mode="json"))
@router.get("/suggestions/data-sources")
async def get_data_sources(
    repository: SuggestionsRepository = Depends(get_suggestions_repository),
) -> dict:
    data_sources = repository.list_data_sources()
    return build_data_sources_payload(data_sources=data_sources, granted_scopes=list(get_scopes()))


@router.get("/suggestions/tags", response_model=TagSuggestionsResponseView)
async def get_tag_suggestions(
    query: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    data_asset_repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> TagSuggestionsResponseView:
    service = TagSuggestionService(
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        data_asset_repository=data_asset_repository,
    )
    tags = await service.list_tag_suggestions(query=query, limit=limit)
    return TagSuggestionsResponseView(
        query=query,
        count=len(tags),
        tags=[TagSuggestionView.model_validate(tag.model_dump(mode="python")) for tag in tags],
    )


@router.get("/suggestions")
async def get_suggestions(
    data_source_id: str | None = Query(default=None),
    status: str = Query(default="pending"),
    repository: SuggestionsRepository = Depends(get_suggestions_repository),
) -> dict:
    suggestions = repository.list_suggestions(
        user_id=get_user_id(),
        data_source_id=data_source_id,
        status=status,
    )
    return build_suggestions_payload(suggestions)


@router.post("/suggestions/natural-language-rule-previews", response_model=NaturalLanguageRulePreviewResponseView)
async def create_natural_language_rule_preview(
    payload: NaturalLanguageRulePreviewRequestView,
    request: Request,
    suggestions_repository: SuggestionsRepository = Depends(get_suggestions_repository),
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    registry_definition_resolver = Depends(get_registry_definition_resolver),
    admin_repository: AdminRepository = Depends(get_admin_repository),
    profiling_repository: ProfilingRepository = Depends(get_profiling_repository),
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> NaturalLanguageRulePreviewResponseView | JSONResponse:
    user_id = get_user_id()
    if not user_id:
        return JSONResponse(status_code=401, content=build_not_authenticated_payload())

    try:
        assistant_mode = str(payload.assistantMode or "preview").strip().lower() or "preview"
        if assistant_mode not in {"preview", "steward"}:
            raise ValueError(f"Unsupported assistant mode '{assistant_mode}'")

        accessible_workspace_ids = _resolve_accessible_workspace_ids(
            request=request,
            admin_repository=admin_repository,
            user_id=user_id,
        )

        if assistant_mode == "steward":
            request_id = str(uuid4())
            job_id = request_id
            request_record = _build_natural_language_request_record(
                request_id=request_id,
                job_id=job_id,
                user_id=user_id,
                payload=payload,
                analysis_type="steward",
                accessible_workspace_ids=sorted(accessible_workspace_ids),
            )
            suggestions_repository.record_natural_language_request(request=request_record)
            try:
                steward_payload = await build_metadata_steward_payload(
                    prompt=payload.prompt,
                    current_workspace_id=payload.currentWorkspaceId,
                    target_type=str(payload.targetType or "").strip(),
                    target_id=str(payload.targetId or "").strip(),
                    catalog_repository=catalog_repository,
                    registry_definition_resolver=registry_definition_resolver,
                )
            except MetadataStewardLookupError as exc:
                steward_error = exc
            except Exception as exc:
                steward_error = normalize_metadata_steward_error(exc)
            else:
                steward_error = None

            if steward_error is not None:
                suggestions_repository.update_natural_language_request(
                    request_id=request_id,
                    status="failed",
                    completed_at=datetime.now(UTC).isoformat(),
                    error_message=str(steward_error),
                )
                _record_preview_event(
                    repository=suggestions_repository,
                    user_id=user_id,
                    workspace_id=payload.currentWorkspaceId,
                    action="steward_error",
                    result="failure",
                    error_code="metadata_steward_request_failed",
                    details={
                        "assistant_mode": assistant_mode,
                        "target_type": str(payload.targetType or "").strip(),
                        "target_id": str(payload.targetId or "").strip(),
                    },
                )
                return JSONResponse(
                    status_code=steward_error.status_code,
                    content=_build_metadata_steward_error_payload(
                        error="metadata_steward_request_failed",
                        message=str(steward_error),
                        status=steward_error.status_code,
                    ),
                )

            response_payload = NaturalLanguageRulePreviewResponseView.model_validate(
                {
                    "success": True,
                    "queued": False,
                    "requestId": request_id,
                    "message": "Metadata steward analysis completed and persisted in Postgres.",
                    "assistantMode": "steward",
                    "targetType": steward_payload["target_type"],
                    "targetId": steward_payload["target_id"],
                    "targetLabel": steward_payload["target_label"],
                    "metadataSummary": steward_payload["metadata_summary"],
                    "explanation": steward_payload["explanation"],
                    "suggestedFixes": steward_payload["suggested_fixes"],
                    "metadataFacts": steward_payload["metadata_facts"],
                    "searchScope": payload.searchScope,
                    "candidateAttributes": [],
                    "targetTerms": [],
                    "requiresStewardConfirmation": False,
                    "draftRulePreview": None,
                    "parsedCondition": None,
                }
            )
            suggestions_repository.update_natural_language_request(
                request_id=request_id,
                status="completed",
                completed_at=datetime.now(UTC).isoformat(),
                result=response_payload.model_dump(by_alias=True, mode="json"),
            )
            _record_preview_event(
                repository=suggestions_repository,
                user_id=user_id,
                workspace_id=payload.currentWorkspaceId,
                action="steward_completed",
                details={
                    "assistant_mode": assistant_mode,
                    "target_type": str(payload.targetType or "").strip(),
                    "target_id": str(payload.targetId or "").strip(),
                    "request_id": request_id,
                },
            )
            return JSONResponse(status_code=200, content=response_payload.model_dump(by_alias=True, mode="json"))
        _record_preview_event(
            repository=suggestions_repository,
            user_id=user_id,
            workspace_id=payload.currentWorkspaceId,
            action="preview_clicked",
            details={"search_scope": payload.searchScope, "analysis_provider": payload.analysisProvider},
        )
        if payload.analysisProvider == "llm":
            try:
                queue_result = await enqueue_natural_language_draft_job(
                    request_body=payload,
                    settings=get_settings(),
                    suggestions_repository=suggestions_repository,
                    correlation_id=getattr(request.state, "correlation_id", None) or user_id,
                    requested_by_user_id=user_id,
                    accessible_workspace_ids=accessible_workspace_ids,
                    selected_attribute_ids=[],
                )
            except NaturalLanguageDraftEnqueueServiceError as exc:
                _record_preview_event(
                    repository=suggestions_repository,
                    user_id=user_id,
                    workspace_id=payload.currentWorkspaceId,
                    action="preview_queue_error",
                    result="failure",
                    error_code="natural_language_preview_queue_error",
                    details={"search_scope": payload.searchScope, "analysis_provider": payload.analysisProvider},
                )
                return JSONResponse(status_code=exc.status_code, content={
                    "error": "natural_language_preview_enqueue_failed",
                    "message": exc.public_detail,
                    "status": exc.status_code,
                })

            _record_preview_event(
                repository=suggestions_repository,
                user_id=user_id,
                workspace_id=payload.currentWorkspaceId,
                action="preview_queued",
                details={
                    "search_scope": payload.searchScope,
                    "analysis_provider": payload.analysisProvider,
                    "request_id": queue_result.request_id,
                },
            )
            return JSONResponse(status_code=200, content=NaturalLanguageRulePreviewResponseView.model_validate({
                "success": True,
                "queued": True,
                "requestId": queue_result.request_id,
                "message": "LLM preview request started. Check Recent LLM Analysis Requests for progress.",
                "searchScope": payload.searchScope,
            }).model_dump(by_alias=True, mode="json"))

        preview_payload = await build_natural_language_rule_preview_payload_for_provider(
            prompt=payload.prompt,
            search_scope=payload.searchScope,
            current_workspace_id=payload.currentWorkspaceId,
            accessible_workspace_ids=accessible_workspace_ids,
            catalog_repository=catalog_repository,
            analysis_provider=payload.analysisProvider,
            llm_service_url=get_settings().llm_service_url,
            current_user_id=user_id,
            registry_definition_resolver=registry_definition_resolver,
            profiling_repository=profiling_repository,
            incident_repository=incident_repository,
        )
    except NaturalLanguageDraftingProviderUnavailableError as exc:
        _record_preview_event(
            repository=suggestions_repository,
            user_id=user_id,
            workspace_id=payload.currentWorkspaceId,
            action="preview_error",
            result="failure",
            error_code="llm_service_unavailable",
            details={"search_scope": payload.searchScope, "analysis_provider": payload.analysisProvider},
        )
        return JSONResponse(status_code=503, content=_build_preview_error_payload(error="llm_service_unavailable", message=str(exc), status=503))
    except NaturalLanguageDraftingProviderResponseError as exc:
        _record_preview_event(
            repository=suggestions_repository,
            user_id=user_id,
            workspace_id=payload.currentWorkspaceId,
            action="preview_error",
            result="failure",
            error_code="llm_service_invalid_response",
            details={"search_scope": payload.searchScope, "analysis_provider": payload.analysisProvider},
        )
        return JSONResponse(status_code=502, content=_build_preview_error_payload(error="llm_service_invalid_response", message=str(exc), status=502))
    except PermissionError as exc:
        _record_preview_event(
            repository=suggestions_repository,
            user_id=user_id,
            workspace_id=payload.currentWorkspaceId,
            action="preview_error",
            result="failure",
            error_code=_normalize_preview_error_code(str(exc)),
            details={"search_scope": payload.searchScope, "analysis_provider": payload.analysisProvider},
        )
        return JSONResponse(status_code=403, content=_build_preview_error_payload(error="unauthorized_search_scope", message=str(exc), status=403))
    except ValueError as exc:
        error_code = _normalize_preview_error_code(str(exc))
        _record_preview_event(
            repository=suggestions_repository,
            user_id=user_id,
            workspace_id=payload.currentWorkspaceId,
            action="preview_error",
            result="failure",
            error_code=error_code,
            details={"search_scope": payload.searchScope, "analysis_provider": payload.analysisProvider},
        )
        return JSONResponse(
            status_code=400,
            content=_build_preview_error_payload(
                error=error_code if error_code != "invalid_preview_request" else "invalid_natural_language_preview",
                message=str(exc),
                status=400,
            ),
        )

    return NaturalLanguageRulePreviewResponseView.model_validate(preview_payload)


@router.post("/suggestions/natural-language-rule-previews/create-suggestion", response_model=NaturalLanguageDraftSuggestionResponseView)
async def create_natural_language_rule_draft_suggestion(
    payload: NaturalLanguageRulePreviewCreateSuggestionRequestView,
    request: Request,
    suggestions_repository: SuggestionsRepository = Depends(get_suggestions_repository),
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
    profiling_repository: ProfilingRepository = Depends(get_profiling_repository),
    incident_repository: IncidentRepository = Depends(get_incident_repository),
    registry_definition_resolver = Depends(get_registry_definition_resolver),
) -> JSONResponse:
    user_id = get_user_id()
    if not user_id:
        return JSONResponse(status_code=401, content=build_not_authenticated_payload())

    try:
        accessible_workspace_ids = _resolve_accessible_workspace_ids(
            request=request,
            admin_repository=admin_repository,
            user_id=user_id,
        )
        selected_ids = [str(value or "").strip() for value in payload.selectedAttributeIds if str(value or "").strip()]
        if not selected_ids:
            raise ValueError("Select at least one candidate attribute before creating a draft suggestion.")

        if payload.analysisProvider == "llm":
            try:
                queue_result = await enqueue_natural_language_draft_job(
                    request_body=payload,
                    settings=get_settings(),
                    suggestions_repository=suggestions_repository,
                    correlation_id=getattr(request.state, "correlation_id", None) or user_id,
                    requested_by_user_id=user_id,
                    accessible_workspace_ids=accessible_workspace_ids,
                )
            except NaturalLanguageDraftEnqueueServiceError as exc:
                _record_preview_event(
                    repository=suggestions_repository,
                    user_id=user_id,
                    workspace_id=payload.currentWorkspaceId,
                    action="draft_queue_error",
                    result="failure",
                    error_code="natural_language_draft_queue_error",
                    details={
                        "attribute_count": len(selected_ids),
                        "search_scope": payload.searchScope,
                        "analysis_provider": payload.analysisProvider,
                    },
                )
                return JSONResponse(status_code=exc.status_code, content={
                    "error": "natural_language_draft_enqueue_failed",
                    "message": exc.public_detail,
                    "status": exc.status_code,
                })

            _record_preview_event(
                repository=suggestions_repository,
                user_id=user_id,
                workspace_id=payload.currentWorkspaceId,
                action="draft_queued",
                details={
                    "attribute_count": len(selected_ids),
                    "search_scope": payload.searchScope,
                    "analysis_provider": payload.analysisProvider,
                    "request_id": queue_result.request_id,
                },
            )
            return NaturalLanguageDraftSuggestionResponseView(
                success=True,
                queued=True,
                message="Draft suggestion request started. Check Notifications for progress.",
                requestId=queue_result.request_id,
            ).model_dump(by_alias=True, mode="json")

        preview_payload = await build_natural_language_rule_preview_payload_for_provider(
            prompt=payload.prompt,
            search_scope=payload.searchScope,
            current_workspace_id=payload.currentWorkspaceId,
            accessible_workspace_ids=accessible_workspace_ids,
            catalog_repository=catalog_repository,
            analysis_provider=payload.analysisProvider,
            llm_service_url=get_settings().llm_service_url,
            current_user_id=user_id,
            registry_definition_resolver=registry_definition_resolver,
            profiling_repository=profiling_repository,
            incident_repository=incident_repository,
        )
        candidate_ids = {
            str(candidate.get("attribute_id") or "")
            for candidate in list(preview_payload.get("candidate_attributes") or [])
        }
        if any(selected_id not in candidate_ids for selected_id in selected_ids):
            raise ValueError("One or more selected attributes are no longer valid for this preview scope.")

        draft_payload = build_natural_language_rule_draft_suggestion_payload(
            prompt=payload.prompt,
            search_scope=payload.searchScope,
            current_workspace_id=payload.currentWorkspaceId,
            selected_attribute_ids=selected_ids,
            preview_payload=preview_payload,
        )
        created = suggestions_repository.create_suggestion(
            user_id=user_id,
            data_source_id=draft_payload["data_source_id"],
            suggested_rule=draft_payload["suggested_rule"],
            confidence_score=draft_payload["confidence_score"],
            reason=draft_payload["reason"],
            rule_type=draft_payload["rule_type"],
        )
        _record_preview_event(
            repository=suggestions_repository,
            user_id=user_id,
            workspace_id=payload.currentWorkspaceId,
            action="draft_created",
            details={
                "attribute_count": len(selected_ids),
                "check_type": draft_payload["rule_type"],
                "search_scope": payload.searchScope,
                "analysis_provider": payload.analysisProvider,
                "suggestion_id": created.id,
            },
        )
        return NaturalLanguageDraftSuggestionResponseView(
            success=True,
            queued=False,
            message="Draft suggestion created.",
            suggestion=serialize_suggestion_entity(created),
        ).model_dump(by_alias=True, mode="json")
    except NaturalLanguageDraftingProviderUnavailableError as exc:
        return JSONResponse(status_code=503, content=_build_preview_error_payload(error="llm_service_unavailable", message=str(exc), status=503))
    except NaturalLanguageDraftingProviderResponseError as exc:
        return JSONResponse(status_code=502, content=_build_preview_error_payload(error="llm_service_invalid_response", message=str(exc), status=502))
    except PermissionError as exc:
        return JSONResponse(status_code=403, content=_build_preview_error_payload(error="unauthorized_search_scope", message=str(exc), status=403))
    except ValueError as exc:
        return JSONResponse(status_code=400, content=_build_preview_error_payload(error="invalid_natural_language_draft", message=str(exc), status=400))


@router.get("/suggestions/natural-language-rule-previews/requests/{request_id}/status", response_model=NaturalLanguageDraftRequestStatusResponseView)
async def get_natural_language_rule_draft_request_status(
    request_id: str,
) -> JSONResponse:
    try:
        record = load_request_record_from_settings(get_settings(), request_id)
    except NaturalLanguageDraftEnqueueServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={
            "error": "natural_language_draft_request_store_unavailable",
            "message": exc.public_detail,
            "status": exc.status_code,
        })

    if record is None:
        return JSONResponse(status_code=404, content=build_natural_language_draft_request_not_found_payload())

    return JSONResponse(
        status_code=200,
        content=NaturalLanguageDraftRequestStatusResponseView.model_validate({
            "success": True,
            "request": record,
        }).model_dump(by_alias=True, mode="json"),
    )


@router.get("/suggestions/natural-language-rule-previews/requests", response_model=NaturalLanguageDraftRequestHistoryResponseView)
async def list_natural_language_rule_draft_requests(
    workspace_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    repository: SuggestionsRepository = Depends(get_suggestions_repository),
) -> JSONResponse:
    user_id = get_user_id()
    if not user_id:
        return JSONResponse(status_code=401, content=build_not_authenticated_payload())

    requests = repository.list_natural_language_requests(
        user_id=user_id,
        workspace_id=workspace_id,
        limit=limit,
    )
    payload = NaturalLanguageDraftRequestHistoryResponseView.model_validate({
        "success": True,
        "requests": [request.model_dump(mode="json") for request in requests],
        "count": len(requests),
    })
    return JSONResponse(status_code=200, content=payload.model_dump(by_alias=True, mode="json"))


@router.post("/suggestions/natural-language-rule-previews/telemetry")
async def record_natural_language_rule_preview_telemetry(
    payload: NaturalLanguageRulePreviewTelemetryRequest,
    repository: SuggestionsRepository = Depends(get_suggestions_repository),
) -> JSONResponse:
    user_id = get_user_id()
    if not user_id:
        return JSONResponse(status_code=401, content=build_not_authenticated_payload())

    _record_preview_event(
        repository=repository,
        user_id=user_id,
        workspace_id=payload.currentWorkspaceId,
        action=payload.action,
        details={"selected_attribute_count": payload.selectedAttributeCount},
    )
    return JSONResponse(status_code=200, content={"success": True})


@router.post("/suggestions/{suggestion_id}/accept")
async def accept_suggestion(
    suggestion_id: str,
    body: SuggestionRuleActionRequestView | None = Body(default=None),
    repository: SuggestionsRepository = Depends(get_suggestions_repository),
    approvals_repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> JSONResponse:
    user_id = get_user_id()
    if not user_id:
        return JSONResponse(status_code=401, content=build_not_authenticated_payload())

    rule_id = normalize_suggestion_apply_rule_id(body.model_dump(mode="python", by_alias=True) if body is not None else None)
    workspace_id = str(getattr(body, 'workspaceId', None) or '').strip()
    if not workspace_id:
        raise HTTPException(status_code=400, detail='workspaceId is required for suggestion interactions')

    try:
        result = repository.update_suggestion_status(
            user_id=user_id,
            suggestion_id=suggestion_id,
            action="accept",
            rule_id=rule_id,
        )
    except SuggestionNotFoundError:
        return JSONResponse(status_code=404, content=build_suggestion_not_found_payload())

    _append_suggestion_audit_event(
        approvals_repository=approvals_repository,
        suggestion_id=suggestion_id,
        action='accepted',
        user_id=user_id,
        workspace_id=workspace_id,
        rule_id=rule_id,
    )
    return JSONResponse(status_code=200, content=serialize_suggestion_entity(result))


@router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(
    suggestion_id: str,
    body: SuggestionRuleActionRequestView | None = Body(default=None),
    repository: SuggestionsRepository = Depends(get_suggestions_repository),
    approvals_repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> JSONResponse:
    user_id = get_user_id()
    if not user_id:
        return JSONResponse(status_code=401, content=build_not_authenticated_payload())

    workspace_id = str(getattr(body, 'workspaceId', None) or '').strip()
    if not workspace_id:
        raise HTTPException(status_code=400, detail='workspaceId is required for suggestion interactions')

    try:
        result = repository.update_suggestion_status(
            user_id=user_id,
            suggestion_id=suggestion_id,
            action="dismiss",
        )
    except SuggestionNotFoundError:
        return JSONResponse(status_code=404, content=build_suggestion_not_found_payload())

    _append_suggestion_audit_event(
        approvals_repository=approvals_repository,
        suggestion_id=suggestion_id,
        action='dismissed',
        user_id=user_id,
        workspace_id=str(getattr(body, 'workspaceId', None) or '').strip(),
    )
    return JSONResponse(status_code=200, content=serialize_suggestion_entity(result))


@router.post("/suggestions/{suggestion_id}/apply")
async def apply_suggestion(
    suggestion_id: str,
    body: SuggestionRuleActionRequestView | None = Body(default=None),
    repository: SuggestionsRepository = Depends(get_suggestions_repository),
    approvals_repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> JSONResponse:
    user_id = get_user_id()
    if not user_id:
        return JSONResponse(status_code=401, content=build_not_authenticated_payload())

    rule_id = normalize_suggestion_apply_rule_id(body.model_dump(mode="python", by_alias=True) if body is not None else None)
    workspace_id = str(getattr(body, 'workspaceId', None) or '').strip()
    if not workspace_id:
        raise HTTPException(status_code=400, detail='workspaceId is required for suggestion interactions')

    try:
        result = repository.update_suggestion_status(
            user_id=user_id,
            suggestion_id=suggestion_id,
            action="apply",
            rule_id=rule_id,
        )
    except SuggestionNotFoundError:
        return JSONResponse(status_code=404, content=build_suggestion_not_found_payload())

    _append_suggestion_audit_event(
        approvals_repository=approvals_repository,
        suggestion_id=suggestion_id,
        action='applied',
        user_id=user_id,
        workspace_id=workspace_id,
        rule_id=rule_id,
    )
    return JSONResponse(status_code=200, content=serialize_suggestion_entity(result))


@router.post("/suggestions/metrics/clear")
async def clear_suggestions_metrics(
    repository: SuggestionsRepository = Depends(get_suggestions_repository),
) -> dict:
    return serialize_suggestion_entity(repository.clear_metrics())
