from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException, Request
from pydantic import ValidationError

from app.api.v1.schemas import GxArtifactEnvelopeView
from app.api.v1.schemas import GxSuiteRunHandoffView
from app.application.services.data_delivery_resolver import DataDeliveryResolutionError
from app.application.services.data_delivery_resolver import DataDeliveryResolver
from app.application.services.gx_suite_validation import assert_gx_suite_runnable as assert_gx_suite_runnable_service
from app.application.services.gx_suite_validation import GxSuiteValidationError
from app.application.use_cases.gx_dispatch_runtime import build_execution_run_create_entity_for_suite_dispatch
from app.domain.entities.gx_execution_run import build_gx_execution_contract_entity
from app.domain.entities.gx_execution_run import build_gx_execution_delivery_snapshot_entity
from app.domain.entities.gx_execution_run import build_gx_dispatch_payload_entity
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import GxSuiteRepository
from app.schemas.pydantic_base import to_snake_alias


@dataclass(slots=True)
class StartSuiteRunResult:
    handoff_view: GxSuiteRunHandoffView
    run_id: str
    correlation_id: str
    engine_target: str
    execution_shape: str


class GxStartSuiteRunPersistenceError(HTTPException):
    def __init__(
        self,
        *,
        suite_id: str,
        run_id: str,
        correlation_id: str,
        engine_target: str,
        execution_shape: str,
        exc: Exception,
    ) -> None:
        super().__init__(
            status_code=503,
            detail={
                "error": "execution_run_persistence_failed",
                "message": "Unable to persist GX execution run",
                "suite_id": suite_id,
                "run_id": run_id,
                "correlation_id": correlation_id,
                "exception": exc.__class__.__name__,
            },
        )
        self.engine_target = engine_target
        self.execution_shape = execution_shape


def request_correlation_id(request: Request | None) -> str:
    return (request.headers.get("X-Correlation-ID") if request is not None else None) or f"corr-{uuid4().hex[:12]}"


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


def _snakecase_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {to_snake_alias(str(key)): _snakecase_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_snakecase_payload(item) for item in value]
    return value


def _resolve_primary_data_object_version_id(suite: GxArtifactEnvelopeView) -> str | None:
    execution_contract = build_gx_execution_contract_entity(
        suite.executionContract.model_dump() if suite.executionContract is not None else None
    )
    if execution_contract is not None:
        traceability = execution_contract.traceability
        primary_version_id = str(traceability.dataObjectVersionId or "").strip() if traceability is not None else ""
        if primary_version_id:
            return primary_version_id

    resolved_scope = suite.resolvedExecutionScope
    if resolved_scope is None:
        return None

    target_ids = [str(value or "").strip() for value in resolved_scope.dataObjectVersionIds if str(value or "").strip()]
    if len(target_ids) == 1:
        return target_ids[0]
    return None


def _resolve_execution_delivery_snapshot(
    *,
    suite: GxArtifactEnvelopeView,
    data_catalog_repository: DataCatalogRepository,
):
    data_object_version_id = _resolve_primary_data_object_version_id(suite)
    if not data_object_version_id:
        return None

    resolver = DataDeliveryResolver(catalog_repository=data_catalog_repository)
    try:
        return build_gx_execution_delivery_snapshot_entity(
            resolver.resolve_delivery(data_object_version_id=data_object_version_id)
        )
    except DataDeliveryResolutionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "error": exc.reason,
                "message": str(exc),
                "data_object_version_id": data_object_version_id,
            },
        ) from exc


def _merge_execution_contract_delivery_snapshot(
    execution_contract_payload: dict[str, Any],
    delivery_snapshot_payload: Any,
) -> dict[str, Any]:
    merged_payload = dict(execution_contract_payload)
    delivery_snapshot = build_gx_execution_delivery_snapshot_entity(delivery_snapshot_payload)
    if delivery_snapshot is not None:
        merged_payload.update(delivery_snapshot.model_dump(by_alias=True, exclude_none=True))
    return merged_payload


def _assert_suite_runnable(suite: GxArtifactEnvelopeView) -> None:
    try:
        assert_gx_suite_runnable_service(suite)
    except GxSuiteValidationError as exc:
        raise _reject_non_runnable_suite(
            suite_id=exc.suite_id,
            suite_version=exc.suite_version,
            message=exc.message,
            reason=exc.reason,
        ) from exc


def build_suite_run_handoff_payload(
    *,
    suite: GxArtifactEnvelopeView,
    correlation_id: str,
    requested_by: str | None,
    data_catalog_repository: DataCatalogRepository,
) -> dict[str, Any]:
    _assert_suite_runnable(suite)
    execution_contract = suite.executionContract
    if execution_contract is None:
        raise _reject_non_runnable_suite(
            suite_id=suite.suiteId,
            suite_version=suite.suiteVersion,
            message=f"GX suite '{suite.suiteId}' is missing an execution_contract",
            reason="missing_execution_contract",
        )

    resolved_delivery_snapshot = _resolve_execution_delivery_snapshot(
        suite=suite,
        data_catalog_repository=data_catalog_repository,
    )
    execution_contract_payload = _merge_execution_contract_delivery_snapshot(
        _snakecase_payload(execution_contract.model_dump()),
        resolved_delivery_snapshot,
    )
    dispatch_engine_type = str(execution_contract_payload.get("engine_type") or "").strip().lower()
    if not dispatch_engine_type:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_engine_type",
                "message": f"GX suite '{suite.suiteId}' requires explicit execution_contract.engine_type",
                "suite_id": suite.suiteId,
                "suite_version": suite.suiteVersion,
                "correlation_id": correlation_id,
            },
        )
    if resolved_delivery_snapshot is not None and str(resolved_delivery_snapshot.engineType or "").strip().lower() not in {"", dispatch_engine_type}:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "engine_type_mismatch",
                "message": "GX suite run handoff requires matching engine_type across execution_contract and delivery_snapshot",
                "suite_id": suite.suiteId,
                "suite_version": suite.suiteVersion,
                "engine_type": dispatch_engine_type,
                "delivery_snapshot_engine_type": str(resolved_delivery_snapshot.engineType or "").strip().lower(),
                "correlation_id": correlation_id,
            },
        )

    return {
        "run_id": f"run-{uuid4().hex[:12]}",
        "suite_id": suite.suiteId,
        "suite_version": suite.suiteVersion,
        "correlation_id": correlation_id,
        "requested_by": requested_by,
        "engine_type": dispatch_engine_type,
        "engine_target": execution_contract.engineTarget,
        "execution_shape": execution_contract.executionShape,
        "handoff_status": "accepted",
        "handoff_ready": True,
        "submitted_at": datetime.now(UTC).isoformat(),
        "execution_contract": execution_contract_payload,
    }


async def start_suite_run(
    *,
    request: Request,
    suite_id: str,
    suite_version: int | None,
    status: str,
    repository: GxSuiteRepository,
    execution_run_repository: GxExecutionRunRepository,
    data_catalog_repository: DataCatalogRepository,
    requested_by: str | None,
) -> StartSuiteRunResult:
    row = await repository.get_suite_by_id(
        suite_id=suite_id,
        suite_version=suite_version,
        status=status,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"GX suite '{suite_id}' not found")

    try:
        suite = GxArtifactEnvelopeView.model_validate(row)
    except ValidationError as exc:
        raise _reject_non_runnable_suite(
            suite_id=suite_id,
            suite_version=suite_version,
            message="GX suite envelope is invalid",
            reason="invalid_envelope",
        ) from exc

    correlation_id = request_correlation_id(request)
    handoff_payload = build_suite_run_handoff_payload(
        suite=suite,
        correlation_id=correlation_id,
        requested_by=requested_by,
        data_catalog_repository=data_catalog_repository,
    )
    typed_handoff_payload = build_gx_dispatch_payload_entity(handoff_payload)

    try:
        await execution_run_repository.create_run(
            build_execution_run_create_entity_for_suite_dispatch(
                suite=suite,
                handoff_payload=typed_handoff_payload,
                requested_by=requested_by,
                status_source="gx.suite.run.start",
                status_reason="GX suite run accepted",
            )
        )
    except Exception as exc:
        raise GxStartSuiteRunPersistenceError(
            suite_id=suite_id,
            run_id=str(handoff_payload["run_id"]),
            correlation_id=correlation_id,
            engine_target=str(handoff_payload["engine_target"]),
            execution_shape=str(handoff_payload["execution_shape"]),
            exc=exc,
        ) from exc

    handoff_view = GxSuiteRunHandoffView.model_validate(handoff_payload)
    return StartSuiteRunResult(
        handoff_view=handoff_view,
        run_id=handoff_view.runId,
        correlation_id=handoff_view.correlationId,
        engine_target=handoff_view.engineTarget,
        execution_shape=handoff_view.executionShape,
    )