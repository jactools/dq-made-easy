from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Protocol

from fastapi import HTTPException
from pydantic import ValidationError

from app.application.services.grouped_execution_planner import GroupedExecutionPlanner
from app.application.services.gx_suite_validation import assert_gx_suite_runnable as assert_gx_suite_runnable_service
from app.application.services.gx_suite_validation import GxSuiteValidationError
from app.domain.entities import build_gx_grouped_execution_plan_entity
from app.domain.entities import build_gx_artifact_envelope_from_validation_artifact
from app.domain.entities import GxArtifactEnvelopeEntity
from app.domain.entities import GxSuiteRetrievalQueryEntity
from app.domain.entities.gx_run_plan import GxRunPlanSeedEntity
from app.domain.entities.gx_run_plan import GxRunPlanScopeSelectorEntity
from app.domain.entities.gx_run_plan import GxRunPlanAssignmentScopeEntity
from app.domain.entities.gx_run_plan import GxRunPlanSuiteSelectionEntity
from app.domain.entities.gx_run_plan import GxRunPlanSuiteRefEntity
from app.domain.entities.gx_run_plan import GxRunPlanSingleSuiteSnapshotEntity
from app.domain.entities.gx_run_plan import GxRunPlanGroupedSuiteSnapshotEntity
from app.domain.interfaces import ValidationArtifactRepository
from app.domain.interfaces import RulesRepository


@dataclass(slots=True)
class ResolveGxRunPlanSeedCommand:
    planning_mode: str = "single_suite"
    suite_id: str | None = None
    suite_version: int | None = None
    data_object_id: str | None = None
    data_object_version_id: str | None = None
    dataset_id: str | None = None
    data_product_id: str | None = None
    tag_ids: list[str] | None = None


class GxRunPlanSeedResolver(Protocol):
    async def resolve_seed(
        self,
        command: ResolveGxRunPlanSeedCommand,
    ) -> GxRunPlanSeedEntity:
        ...


def _artifact_identifier(payload: Any, *keys: str) -> Any:
    if isinstance(payload, dict):
        for key in keys:
            if payload.get(key) is not None:
                return payload.get(key)
    for key in keys:
        value = getattr(payload, key, None)
        if value is not None:
            return value
    return None


def _artifact_engine_type(payload: Any) -> str | None:
    engine_type = _artifact_identifier(payload, "engineType", "engine_type")
    normalized = str(engine_type or "").strip().lower()
    if normalized:
        return normalized

    execution_contract = _artifact_identifier(payload, "executionContract", "execution_contract")
    execution_engine_type = _artifact_identifier(execution_contract, "engineType", "engine_type")
    normalized = str(execution_engine_type or "").strip().lower()
    return normalized or None


def _coerce_suite_entity(payload: GxArtifactEnvelopeEntity | Any) -> GxArtifactEnvelopeEntity:
    if isinstance(payload, GxArtifactEnvelopeEntity):
        return payload
    if hasattr(payload, "model_dump"):
        payload = getattr(payload, "model_dump")(by_alias=False, exclude_none=False)
    if isinstance(payload, dict) and (
        payload.get("validationArtifactId") is not None or payload.get("validation_artifact_id") is not None
    ):
        try:
            return build_gx_artifact_envelope_from_validation_artifact(payload)
        except ValueError as exc:
            suite_id = str(
                _artifact_identifier(payload, "validationArtifactId", "validation_artifact_id", "suiteId", "suite_id") or ""
            ).strip()
            raw_version = _artifact_identifier(
                payload,
                "validationArtifactVersion",
                "validation_artifact_version",
                "suiteVersion",
                "suite_version",
            )
            try:
                suite_version = int(raw_version) if raw_version is not None else None
            except (TypeError, ValueError):
                suite_version = None

            message = str(exc)
            if "engine_type" in message:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "unsupported_engine_type",
                        "message": message,
                        "suite_id": suite_id or None,
                        "suite_version": suite_version,
                    },
                ) from exc
            raise _reject_non_runnable_suite(
                suite_id=suite_id,
                suite_version=suite_version,
                message="GX suite envelope is invalid",
                reason="invalid_envelope",
            ) from exc
    return GxArtifactEnvelopeEntity.model_validate(payload)

def _to_dict_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return getattr(value, "model_dump")()
    return dict(value)

def _reject_non_runnable_suite(
    *,
    suite_id: str,
    suite_version: int | None,
    message: str,
    reason: str,
) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "error": "gx_suite_not_runnable",
            "message": message,
            "reason": reason,
            "suite_id": suite_id,
            "suite_version": suite_version,
        },
    )


def _assert_gx_suite_runnable(suite: GxArtifactEnvelopeEntity) -> None:
    try:
        assert_gx_suite_runnable_service(suite)
    except GxSuiteValidationError as exc:
        raise _reject_non_runnable_suite(
            suite_id=exc.suite_id,
            suite_version=exc.suite_version,
            message=exc.message,
            reason=exc.reason,
        ) from exc


def _as_http_400(exc: ValidationError) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "message": "Invalid GX retrieval query",
            "errors": exc.errors(),
        },
    )


@dataclass(slots=True)
class GxRunPlanSeedResolutionService:
    artifact_repository: ValidationArtifactRepository
    grouped_execution_planner: GroupedExecutionPlanner
    rules_repository: RulesRepository

    async def _rule_ids_for_tags(self, tag_ids: list[str] | None) -> set[str]:
        normalized_tag_ids = {str(tag_id or "").strip() for tag_id in (tag_ids or []) if str(tag_id or "").strip()}
        if not normalized_tag_ids:
            return set()

        rule_ids: set[str] = set()
        for record in await self.rules_repository.list_rule_records():
            record_tag_ids = {str(tag_id or "").strip() for tag_id in (record.tag_ids or []) if str(tag_id or "").strip()}
            if record_tag_ids.intersection(normalized_tag_ids):
                rule_ids.add(str(record.id or "").strip())
        return {rule_id for rule_id in rule_ids if rule_id}

    async def resolve_seed(
        self,
        command: ResolveGxRunPlanSeedCommand,
    ) -> GxRunPlanSeedEntity:
        if command.planning_mode == "grouped_scope":
            return await self._resolve_grouped_scope_seed(command)
        return await self._resolve_single_suite_seed(
            suite_id=command.suite_id,
            suite_version=command.suite_version,
            tag_ids=command.tag_ids,
        )

    async def _resolve_single_suite_seed(
        self,
        *,
        suite_id: str | None,
        suite_version: int | None,
        tag_ids: list[str] | None,
    ) -> GxRunPlanSeedEntity:
        normalized_suite_id = str(suite_id or "").strip()
        if not normalized_suite_id:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "missing_suite_selector",
                    "message": "suite_id is required for single_suite run plans",
                },
            )

        suite_row = await self.artifact_repository.get_artifact_by_id(
            artifact_id=normalized_suite_id,
            artifact_version=suite_version,
            status="active",
        )
        if suite_row is None:
            raise HTTPException(status_code=404, detail=f"GX suite '{normalized_suite_id}' not found")

        try:
            suite = _coerce_suite_entity(suite_row)
        except ValidationError as exc:
            raise _reject_non_runnable_suite(
                suite_id=normalized_suite_id,
                suite_version=suite_version,
                message="GX suite envelope is invalid",
                reason="invalid_envelope",
            ) from exc

        _assert_gx_suite_runnable(suite)
        matching_rule_ids = await self._rule_ids_for_tags(tag_ids)
        if matching_rule_ids:
            suite_rule_ids = {str(rule_id or "").strip() for rule_id in (suite.compiledFrom.ruleIds if suite.compiledFrom else []) if str(rule_id or "").strip()}
            if not suite_rule_ids.intersection(matching_rule_ids):
                raise HTTPException(status_code=404, detail=f"GX suite '{normalized_suite_id}' not found")
        suite_engine_type = _artifact_engine_type(suite_row) or _artifact_engine_type(suite) or "gx"
        return GxRunPlanSeedEntity(
            scopeSelector=GxRunPlanScopeSelectorEntity(
                assignmentScope=(
                    GxRunPlanAssignmentScopeEntity(**suite.assignmentScope.model_dump())
                    if suite.assignmentScope
                    else None
                ),
                tagIds=list(tag_ids or []),
            ),
            gxSuiteSelection=GxRunPlanSuiteSelectionEntity(
                selectionMode="single_suite",
                scopeSelector=GxRunPlanScopeSelectorEntity(
                    assignmentScope=(
                        GxRunPlanAssignmentScopeEntity(**suite.assignmentScope.model_dump())
                        if suite.assignmentScope
                        else None
                    ),
                    tagIds=list(tag_ids or []),
                ),
                suiteRefs=[
                    GxRunPlanSuiteRefEntity(
                        suiteId=suite.suiteId,
                        suiteVersion=suite.suiteVersion,
                        engineType=suite_engine_type,
                    )
                ],
            ),
            suiteId=suite.suiteId,
            suiteVersion=suite.suiteVersion,
            suiteSnapshot=GxRunPlanSingleSuiteSnapshotEntity(
                suiteId=suite.suiteId,
                suiteVersion=suite.suiteVersion,
                artifactVersion=suite.artifactVersion,
                assignmentScope=suite.assignmentScope.model_dump() if suite.assignmentScope else {},
                resolvedExecutionScope=suite.resolvedExecutionScope.model_dump() if suite.resolvedExecutionScope else {},
                gxSuite=_to_dict_payload(suite.gxSuite),
                compiledFrom=_to_dict_payload(suite.compiledFrom),
                executionHints=_to_dict_payload(suite.executionHints),
                executionContract=suite.executionContract,
            ),
            executionContractSnapshot=suite.executionContract,
        )

    async def _resolve_grouped_scope_seed(
        self,
        command: ResolveGxRunPlanSeedCommand,
    ) -> GxRunPlanSeedEntity:
        try:
            scope_query = GxSuiteRetrievalQueryEntity(
                dataObjectId=command.data_object_id,
                dataObjectVersionId=command.data_object_version_id,
                datasetId=command.dataset_id,
                dataProductId=command.data_product_id,
                tagIds=list(command.tag_ids or []),
                status="active",
                latestOnly=True,
            )
        except ValidationError as exc:
            raise _as_http_400(exc) from exc

        rows = await self.artifact_repository.list_artifacts(
            data_object_id=scope_query.dataObjectId,
            data_object_version_id=scope_query.dataObjectVersionId,
            dataset_id=scope_query.datasetId,
            data_product_id=scope_query.dataProductId,
            status=scope_query.status,
            latest_only=scope_query.latestOnly,
        )
        matching_rule_ids = await self._rule_ids_for_tags(command.tag_ids)
        suites: list[GxArtifactEnvelopeEntity] = []
        suite_refs: list[GxRunPlanSuiteRefEntity] = []
        filtered_rows: list[Any] = []
        for row in rows:
            suite = _coerce_suite_entity(row)
            if matching_rule_ids:
                suite_rule_ids = {str(rule_id or "").strip() for rule_id in (suite.compiledFrom.ruleIds if suite.compiledFrom else []) if str(rule_id or "").strip()}
                if not suite_rule_ids.intersection(matching_rule_ids):
                    continue
            _assert_gx_suite_runnable(suite)
            suites.append(suite)
            filtered_rows.append(row)
            suite_refs.append(
                GxRunPlanSuiteRefEntity(
                    suiteId=suite.suiteId,
                    suiteVersion=suite.suiteVersion,
                    engineType=_artifact_engine_type(row) or _artifact_engine_type(suite) or "gx",
                )
            )

        if not suites:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "gx_suites_not_found",
                    "message": "No active GX suites found for the requested grouped scope",
                },
            )

        grouped_plan = await self.grouped_execution_planner.build_plan(filtered_rows)
        scope_selector_dict = scope_query.model_dump(exclude={"status", "latestOnly"}, exclude_none=True)
        scope_selector_dict["tagIds"] = list(command.tag_ids or [])
        grouped_plan_payload = build_gx_grouped_execution_plan_entity(grouped_plan)
        
        return GxRunPlanSeedEntity(
            scopeSelector=GxRunPlanScopeSelectorEntity(**scope_selector_dict),
            gxSuiteSelection=GxRunPlanSuiteSelectionEntity(
                selectionMode="grouped_scope",
                scopeSelector=GxRunPlanScopeSelectorEntity(**scope_selector_dict),
                suiteRefs=suite_refs,
                groupedExecutionPlan=grouped_plan_payload,
            ),
            suiteId=None,
            suiteVersion=None,
            suiteSnapshot=GxRunPlanGroupedSuiteSnapshotEntity(
                groupedExecutionPlan=grouped_plan_payload,
                suiteEnvelopes=[
                    GxRunPlanSingleSuiteSnapshotEntity(
                        suiteId=suite.suiteId,
                        suiteVersion=suite.suiteVersion,
                        artifactVersion=suite.artifactVersion,
                        assignmentScope=suite.assignmentScope.model_dump() if suite.assignmentScope else {},
                        resolvedExecutionScope=suite.resolvedExecutionScope.model_dump() if suite.resolvedExecutionScope else {},
                        gxSuite=_to_dict_payload(suite.gxSuite),
                        compiledFrom=_to_dict_payload(suite.compiledFrom),
                        executionHints=_to_dict_payload(suite.executionHints),
                        executionContract=suite.executionContract,
                    )
                    for suite in suites
                ],
            ),
            executionContractSnapshot=None,  # For grouped scope, we don't have a single contract
        )