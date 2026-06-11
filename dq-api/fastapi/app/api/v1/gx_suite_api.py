from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.schemas import GxArtifactEnvelopeView
from app.api.v1.schemas import GxSuiteDirectFetchQueryView
from app.api.v1.schemas import GxSuiteRetrievalQueryView
from app.api.v1.schemas import GxSuiteStatusHistoryView
from app.core.request_context import get_user_id
from app.domain.entities import build_gx_artifact_envelope_from_validation_artifact
from app.domain.entities import build_validation_artifact_envelope_entity
from app.domain.entities import build_validation_artifact_envelope_from_gx_artifact
from app.domain.interfaces import ValidationArtifactRepository
from dq_domain_validation import GxArtifactStatus


@dataclass(slots=True, frozen=True)
class SaveGxSuiteResult:
    saved_view: GxArtifactEnvelopeView
    artifact_hash: str | None


@dataclass(slots=True, frozen=True)
class ListGxSuitesResult:
    query: GxSuiteRetrievalQueryView
    suites: list[GxArtifactEnvelopeView]


@dataclass(slots=True, frozen=True)
class GetGxSuiteResult:
    query: GxSuiteDirectFetchQueryView
    suite: GxArtifactEnvelopeView


def _as_http_400(exc: ValidationError) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "message": "Invalid GX retrieval query",
            "errors": json.loads(exc.json()),
        },
    )


def _payload_extra_value(payload: Any, *keys: str) -> Any:
    if isinstance(payload, Mapping):
        for key in keys:
            if key in payload and payload[key] is not None:
                return payload[key]
    for key in keys:
        attribute_value = getattr(payload, key, None)
        if attribute_value is not None:
            return attribute_value
    extra = getattr(payload, "model_extra", None) or {}
    for key in keys:
        if key in extra and extra[key] is not None:
            return extra[key]
    return None


def _gx_view_from_validation_artifact(payload: Any) -> GxArtifactEnvelopeView:
    validation_artifact = build_validation_artifact_envelope_entity(payload)
    gx_artifact = build_gx_artifact_envelope_from_validation_artifact(validation_artifact)
    return GxArtifactEnvelopeView.model_validate(
        gx_artifact.model_dump(mode="python", by_alias=False, exclude_none=True)
    )


def _is_gx_validation_artifact(payload: Any) -> bool:
    validation_artifact = build_validation_artifact_envelope_entity(payload)
    return (
        str(validation_artifact.engineType or "").strip().lower() == "gx"
        and str(validation_artifact.engineArtifact.engineType or "").strip().lower() == "gx"
    )


def _gx_history_view_from_validation_entry(payload: Any) -> GxSuiteStatusHistoryView:
    suite_id = _payload_extra_value(payload, "suiteId", "suite_id", "validationArtifactId", "validation_artifact_id")
    suite_version = _payload_extra_value(
        payload,
        "suiteVersion",
        "suite_version",
        "validationArtifactVersion",
        "validation_artifact_version",
    )
    return GxSuiteStatusHistoryView.model_validate(
        {
            "suiteId": suite_id,
            "suiteVersion": suite_version,
            "fromStatus": _payload_extra_value(payload, "fromStatus", "from_status"),
            "toStatus": _payload_extra_value(payload, "toStatus", "to_status"),
            "changedBy": _payload_extra_value(payload, "changedBy", "changed_by"),
            "changedAt": _payload_extra_value(payload, "changedAt", "changed_at"),
            "reason": _payload_extra_value(payload, "reason"),
        }
    )


async def save_suite(
    *,
    body: GxArtifactEnvelopeView,
    status: GxArtifactStatus,
    expected_existing_hash: str | None,
    source_pipeline: str | None,
    repository: ValidationArtifactRepository,
) -> SaveGxSuiteResult:
    try:
        saved = await repository.save_artifact(
            envelope=build_validation_artifact_envelope_from_gx_artifact(
                body.model_dump(mode="python", by_alias=False, exclude_none=True)
            ),
            status=status,
            expected_existing_hash=expected_existing_hash,
            saved_by=get_user_id(),
            source_pipeline=source_pipeline,
        )
    except ValidationError as exc:
        raise _as_http_400(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    artifact_hash = str(_payload_extra_value(saved, "artifactHash", "artifact_hash") or "").strip() or None
    return SaveGxSuiteResult(
        saved_view=_gx_view_from_validation_artifact(saved),
        artifact_hash=artifact_hash,
    )


async def patch_suite_status(
    *,
    suite_id: str,
    status: GxArtifactStatus,
    suite_version: int | None,
    reason: str | None,
    repository: ValidationArtifactRepository,
) -> GxArtifactEnvelopeView:
    updated = await repository.patch_artifact_status(
        artifact_id=suite_id,
        new_status=status,
        artifact_version=suite_version,
        changed_by=get_user_id(),
        reason=reason,
    )
    if updated is None or not _is_gx_validation_artifact(updated):
        raise HTTPException(status_code=404, detail=f"GX suite '{suite_id}' not found")
    return _gx_view_from_validation_artifact(updated)


async def list_suites(
    *,
    data_object_id: str | None,
    data_object_version_id: str | None,
    dataset_id: str | None,
    data_product_id: str | None,
    status: GxArtifactStatus,
    latest_only: bool,
    repository: ValidationArtifactRepository,
) -> ListGxSuitesResult:
    try:
        query = GxSuiteRetrievalQueryView(
            dataObjectId=data_object_id,
            dataObjectVersionId=data_object_version_id,
            datasetId=dataset_id,
            dataProductId=data_product_id,
            status=status,
            latestOnly=latest_only,
        )
    except ValidationError as exc:
        raise _as_http_400(exc) from exc

    rows = await repository.list_artifacts(
        data_object_id=query.dataObjectId,
        data_object_version_id=query.dataObjectVersionId,
        dataset_id=query.datasetId,
        data_product_id=query.dataProductId,
        status=query.status,
        latest_only=query.latestOnly,
    )
    gx_rows = [row for row in rows if _is_gx_validation_artifact(row)]
    return ListGxSuitesResult(
        query=query,
        suites=[_gx_view_from_validation_artifact(row) for row in gx_rows],
    )


async def list_suites_for_rule(
    *,
    rule_id: str,
    status: GxArtifactStatus,
    latest_only: bool,
    repository: ValidationArtifactRepository,
) -> list[GxArtifactEnvelopeView]:
    normalized_rule_id = str(rule_id or "").strip()
    if not normalized_rule_id:
        raise HTTPException(status_code=422, detail="rule_id is required")

    rows = await repository.list_artifacts_for_rule(
        rule_id=normalized_rule_id,
        status=status,
        latest_only=latest_only,
    )
    return [_gx_view_from_validation_artifact(row) for row in rows if _is_gx_validation_artifact(row)]


async def get_suite(
    *,
    suite_id: str,
    suite_version: int | None,
    status: GxArtifactStatus,
    repository: ValidationArtifactRepository,
) -> GetGxSuiteResult:
    try:
        query = GxSuiteDirectFetchQueryView(suiteVersion=suite_version)
    except ValidationError as exc:
        raise _as_http_400(exc) from exc

    row = await repository.get_artifact_by_id(
        artifact_id=suite_id,
        artifact_version=query.suiteVersion,
        status=status,
    )
    if row is None or not _is_gx_validation_artifact(row):
        raise HTTPException(status_code=404, detail=f"GX suite '{suite_id}' not found")

    return GetGxSuiteResult(
        query=query,
        suite=_gx_view_from_validation_artifact(row),
    )


async def list_suite_status_history(
    *,
    suite_id: str,
    suite_version: int | None,
    repository: ValidationArtifactRepository,
) -> list[GxSuiteStatusHistoryView]:
    history = await repository.list_artifact_status_history(
        artifact_id=suite_id,
        artifact_version=suite_version,
    )
    return [_gx_history_view_from_validation_entry(entry) for entry in history]