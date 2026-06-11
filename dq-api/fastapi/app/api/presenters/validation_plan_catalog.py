from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.api.presenters.validation_run_plans import build_validation_run_plan_view
from app.api.v1.schemas.validation_plan_catalog_view import ValidationPlanCatalogSuiteView
from app.api.v1.schemas.validation_plan_catalog_view import ValidationPlanCatalogView
from app.api.v1.schemas.validation_plan_catalog_view import ValidationPlanCatalogSummaryView
from app.api.v1.schemas.validation_run_plan_view import ValidationRunPlanScheduleDefinitionView


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return dict(model_dump(mode="python", by_alias=False, exclude_none=True))
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}


def _extract_tag_ids(scope_selector: Any) -> list[str]:
    scope_selector_payload = _coerce_mapping(scope_selector)
    tag_ids = scope_selector_payload.get("tagIds")
    if not isinstance(tag_ids, list):
        return []

    normalized: list[str] = []
    for tag_id in tag_ids:
        value = str(tag_id or "").strip()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _extract_engine_type(version: Any) -> str | None:
    artifact_snapshot = _coerce_mapping(getattr(version, "artifactSnapshot", None))
    engine_type = artifact_snapshot.get("engineType")
    if engine_type is not None:
        return str(engine_type)

    engine_artifact = _coerce_mapping(artifact_snapshot.get("engineArtifact"))
    engine_type = engine_artifact.get("engineType")
    if engine_type is not None:
        return str(engine_type)

    validation_artifact_selection = _coerce_mapping(getattr(version, "validationArtifactSelection", None))
    artifact_refs = validation_artifact_selection.get("artifactRefs")
    if isinstance(artifact_refs, list) and artifact_refs:
        first_ref = _coerce_mapping(artifact_refs[0])
        engine_type = first_ref.get("engineType")
        if engine_type is not None:
            return str(engine_type)

    if artifact_snapshot:
        if "gxSuite" in artifact_snapshot:
            return "gx"
        if "engineArtifact" in artifact_snapshot:
            return str(_coerce_mapping(artifact_snapshot.get("engineArtifact")).get("engineType") or "") or None

    return None


def _build_suite_view(plan: Any, version: Any) -> ValidationPlanCatalogSuiteView:
    artifact_snapshot = _coerce_mapping(getattr(version, "artifactSnapshot", None))
    schedule_definition = _coerce_mapping(getattr(version, "scheduleDefinition", None))
    validation_artifact_selection = _coerce_mapping(getattr(version, "validationArtifactSelection", None))
    gx_suite_selection = _coerce_mapping(getattr(version, "gxSuiteSelection", None))
    scope_selector = _coerce_mapping(validation_artifact_selection.get("scopeSelector"))
    if not scope_selector:
        scope_selector = _coerce_mapping(gx_suite_selection.get("scopeSelector"))
    if not scope_selector:
        scope_selector = _coerce_mapping(getattr(plan, "scopeSelector", None))
    return ValidationPlanCatalogSuiteView(
        runPlanId=str(getattr(plan, "runPlanId", "") or ""),
        runPlanVersionId=str(getattr(version, "runPlanVersionId", "") or ""),
        governanceState=str(getattr(version, "governanceState", "") or ""),
        artifactId=(str(getattr(version, "artifactId", None)) if getattr(version, "artifactId", None) is not None else None),
        artifactVersion=(int(getattr(version, "artifactVersion", None)) if getattr(version, "artifactVersion", None) is not None else None),
        engineType=_extract_engine_type(version),
        tagIds=_extract_tag_ids(scope_selector),
        scheduleDefinition=ValidationRunPlanScheduleDefinitionView.model_validate(schedule_definition),
        artifactSnapshot=artifact_snapshot or None,
        createdAt=str(getattr(version, "createdAt", "") or ""),
    )


def build_validation_plan_catalog_view(rows: Sequence[Any]) -> ValidationPlanCatalogView:
    plans = [build_validation_run_plan_view(row) for row in rows]
    suites = []
    engine_types: set[str] = set()
    for plan in rows:
        versions = getattr(plan, "versions", None)
        if not isinstance(versions, list):
            continue
        for version in versions:
            suite_view = _build_suite_view(plan, version)
            suites.append(suite_view)
            if suite_view.engineType:
                engine_types.add(suite_view.engineType)

    return ValidationPlanCatalogView(
        validationRunPlans=plans,
        validationSuites=suites,
        validationSummary=ValidationPlanCatalogSummaryView(
            runPlanCount=len(plans),
            suiteCount=len(suites),
            engineTypes=sorted(engine_types),
        ),
    )
