from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import logging
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request
from opentelemetry import propagate
from pydantic import ValidationError

from app.application.services import gx_queue_service
from app.application.services.delivery_linked_execution_request_resolver import DeliveryLinkedExecutionRequestResolver
from app.application.use_cases.gx_dispatch_runtime import persist_grouped_dispatch_run as persist_grouped_dispatch_run_use_case
from app.core.config import get_settings
from app.core.request_context import get_user_id
from app.domain.entities import build_gx_artifact_envelope_from_validation_artifact
from app.domain.entities import build_validation_artifact_envelope_entity
from app.domain.entities import GxArtifactEnvelopeEntity
from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.domain.entities.gx_execution_run import GxDispatchPayloadEntity
from app.domain.entities.gx_execution_run import build_gx_dispatch_payload_entity
from app.domain.entities.gx_execution_run import build_gx_grouped_execution_plan_entity
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import ValidationArtifactRepository
from app.domain.interfaces import ValidationRunPlanRepository
from app.schemas.pydantic_base import to_snake_alias


_log = logging.getLogger(__name__)
aioredis = gx_queue_service.aioredis
redis_sync = gx_queue_service.redis_sync


class DeliveryLinkedExecutionOrchestrator:
    def __init__(
        self,
        *,
        catalog_repository: DataCatalogRepository,
        validation_artifact_repository: ValidationArtifactRepository,
        validation_run_plan_repository: ValidationRunPlanRepository,
        execution_run_repository: GxExecutionRunRepository,
        runtime_api: Any,
    ) -> None:
        self._catalog_repository = catalog_repository
        self._validation_artifact_repository = validation_artifact_repository
        self._validation_run_plan_repository = validation_run_plan_repository
        self._execution_run_repository = execution_run_repository
        self._runtime_api = runtime_api
        self._resolver = DeliveryLinkedExecutionRequestResolver(
            catalog_repository=catalog_repository,
            validation_artifact_repository=validation_artifact_repository,
            validation_run_plan_repository=validation_run_plan_repository,
        )

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _snakecase_payload(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                to_snake_alias(str(key)): DeliveryLinkedExecutionOrchestrator._snakecase_payload(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [DeliveryLinkedExecutionOrchestrator._snakecase_payload(item) for item in value]
        return value

    @staticmethod
    def _delivery_snapshot(receipt: Mapping[str, Any]) -> dict[str, Any]:
        data_delivery_id = str(receipt.get("data_delivery_id") or "").strip()
        resolved_data_object_version_id = str(receipt.get("resolved_data_object_version_id") or "").strip()
        resolved_delivery_location = str(receipt.get("resolved_delivery_location") or "").strip()
        delivery_note = receipt.get("delivery_note") if isinstance(receipt.get("delivery_note"), Mapping) else {}
        delivery_format = str(delivery_note.get("delivery_format") or "").strip()

        if not delivery_format:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "missing_delivery_format",
                    "message": "Data delivery is missing a delivery_format required for execution",
                    "data_delivery_id": data_delivery_id,
                },
            )

        if not resolved_data_object_version_id:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "missing_data_object_version_id",
                    "message": "Data delivery is missing resolved_data_object_version_id",
                    "data_delivery_id": data_delivery_id,
                },
            )

        if not resolved_delivery_location:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "missing_delivery_location",
                    "message": "Data delivery is missing resolved_delivery_location",
                    "data_delivery_id": data_delivery_id,
                },
            )

        return {
            "engineType": str(receipt.get("resolved_engine_type") or "").strip() or None,
            "resolvedDataObjectVersionId": resolved_data_object_version_id,
            "resolvedDataDeliveryId": data_delivery_id,
            "resolvedDeliveryLocation": resolved_delivery_location,
            "deliveryResolutionMode": "specific_delivery",
            "deliveryFormat": delivery_format,
        }

    @staticmethod
    def _source_overrides(receipt: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        resolved_data_object_version_id = str(receipt.get("resolved_data_object_version_id") or "").strip()
        delivery_note = receipt.get("delivery_note") if isinstance(receipt.get("delivery_note"), Mapping) else {}
        delivery_format = str(delivery_note.get("delivery_format") or "").strip()
        return {
            resolved_data_object_version_id: {
                "uri": str(receipt.get("resolved_delivery_location") or "").strip(),
                "format": delivery_format,
            }
        }

    @staticmethod
    def _applicable_run_plan(receipt: Mapping[str, Any], run_plan_id: str) -> dict[str, Any] | None:
        execution_resolution = receipt.get("execution_resolution") if isinstance(receipt.get("execution_resolution"), Mapping) else {}
        run_plans = execution_resolution.get("applicable_run_plans") if isinstance(execution_resolution.get("applicable_run_plans"), list) else []
        for candidate in run_plans:
            if not isinstance(candidate, Mapping):
                continue
            if str(candidate.get("run_plan_id") or "").strip() == run_plan_id:
                return dict(candidate)
        return None

    @staticmethod
    def _resolved_engine_type(receipt: Mapping[str, Any]) -> str | None:
        resolved_engine_type = str(receipt.get("resolved_engine_type") or "").strip().lower()
        if resolved_engine_type:
            return resolved_engine_type

        execution_resolution = receipt.get("execution_resolution") if isinstance(receipt.get("execution_resolution"), Mapping) else {}
        applicable_suites = execution_resolution.get("applicable_gx_suites") if isinstance(execution_resolution.get("applicable_gx_suites"), list) else []
        engine_types = {
            str(item.get("engine_type") or "").strip().lower()
            for item in applicable_suites
            if isinstance(item, Mapping) and str(item.get("engine_type") or "").strip()
        }
        if len(engine_types) == 1:
            return next(iter(engine_types))
        return None

    @staticmethod
    def _receipt_engine_types(receipt: Mapping[str, Any]) -> set[str]:
        engine_types: set[str] = set()

        resolved_engine_type = str(receipt.get("resolved_engine_type") or "").strip().lower()
        if resolved_engine_type:
            engine_types.add(resolved_engine_type)

        execution_resolution = receipt.get("execution_resolution") if isinstance(receipt.get("execution_resolution"), Mapping) else {}
        applicable_suites = execution_resolution.get("applicable_gx_suites") if isinstance(execution_resolution.get("applicable_gx_suites"), list) else []
        engine_types.update(
            str(item.get("engine_type") or "").strip().lower()
            for item in applicable_suites
            if isinstance(item, Mapping) and str(item.get("engine_type") or "").strip()
        )

        selected_run_plan_id = str(receipt.get("resolved_run_plan_id") or "").strip()
        if selected_run_plan_id:
            candidate = DeliveryLinkedExecutionOrchestrator._applicable_run_plan(receipt, selected_run_plan_id)
            active_version = candidate.get("active_version") if isinstance(candidate, Mapping) else {}
            if not isinstance(active_version, Mapping):
                active_version = {}
            selected_run_plan_engine_type = str(active_version.get("engine_type") or "").strip().lower()
            if selected_run_plan_engine_type:
                engine_types.add(selected_run_plan_engine_type)

        return engine_types

    @staticmethod
    def _assert_grouped_execution_engine_supported(
        receipt: Mapping[str, Any],
        *,
        data_delivery_id: str,
    ) -> None:
        engine_types = DeliveryLinkedExecutionOrchestrator._receipt_engine_types(receipt)
        if not engine_types:
            return

        if len(engine_types) > 1:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "mixed_engine_types",
                    "message": "GX grouped dispatch requires a single engine_type",
                    "data_delivery_id": data_delivery_id,
                    "engine_types": sorted(engine_types),
                },
            )

        engine_type = next(iter(engine_types))
        if engine_type != "gx":
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "unsupported_engine_type",
                    "message": f"Execution runtime does not support engine_type '{engine_type}'",
                    "data_delivery_id": data_delivery_id,
                    "engine_type": engine_type,
                },
            )

    @staticmethod
    def _choose_execution_mode(receipt: Mapping[str, Any]) -> str:
        selector = receipt.get("execution_selector") if isinstance(receipt.get("execution_selector"), Mapping) else {}
        selector_type = str(selector.get("selector_type") or "").strip()
        execution_resolution = receipt.get("execution_resolution") if isinstance(receipt.get("execution_resolution"), Mapping) else {}
        applicable_suites = execution_resolution.get("applicable_gx_suites") if isinstance(execution_resolution.get("applicable_gx_suites"), list) else []

        if selector_type == "gx_suite":
            return "single_suite"

        if selector_type == "run_plan":
            selected_run_plan_id = str(receipt.get("resolved_run_plan_id") or "").strip()
            candidate = DeliveryLinkedExecutionOrchestrator._applicable_run_plan(receipt, selected_run_plan_id)
            if candidate is not None and str(candidate.get("planning_mode") or "").strip() == "grouped_scope":
                return "grouped_scope"
            return "single_suite"

        if len(applicable_suites) <= 1:
            return "single_suite"
        return "grouped_scope"

    async def _load_suite(self, receipt: Mapping[str, Any]) -> GxArtifactEnvelopeEntity:
        suite_id = self._text(receipt.get("resolved_gx_suite_id"))
        suite_version_raw = receipt.get("resolved_gx_suite_version")
        suite_version = int(suite_version_raw) if suite_version_raw not in (None, "") else None
        if not suite_id or suite_version is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "missing_gx_suite_selection",
                    "message": "A GX suite must be selected before execution can start",
                    "data_delivery_id": receipt.get("data_delivery_id"),
                },
            )

        row = await self._validation_artifact_repository.get_artifact_by_id(
            artifact_id=suite_id,
            artifact_version=suite_version,
            status="active",
        )
        if row is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "gx_suite_not_found",
                    "message": f"GX suite '{suite_id}' not found",
                    "data_delivery_id": receipt.get("data_delivery_id"),
                },
            )

        try:
            if isinstance(row, ValidationArtifactEnvelopeEntity):
                artifact = row
            else:
                payload = row.model_dump(by_alias=False, exclude_none=False) if hasattr(row, "model_dump") else row
                artifact = build_validation_artifact_envelope_entity(payload)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "invalid_gx_suite_envelope",
                    "message": "GX suite envelope is invalid",
                    "data_delivery_id": receipt.get("data_delivery_id"),
                    "validation_errors": exc.errors(),
                },
            ) from exc

        engine_type = str(artifact.engineType or "").strip().lower()
        if engine_type != "gx":
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "unsupported_engine_type",
                    "message": f"Execution runtime does not support engine_type '{engine_type or 'unknown'}'",
                    "data_delivery_id": receipt.get("data_delivery_id"),
                    "engine_type": engine_type or None,
                },
            )

        return build_gx_artifact_envelope_from_validation_artifact(artifact)

    async def execute_submission(
        self,
        *,
        request: Request,
        data_delivery_id: str,
        execution_selector: Mapping[str, Any] | None = None,
        requested_by: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        receipt = await self._resolver.resolve_submission(
            data_delivery_id=data_delivery_id,
            execution_selector=execution_selector,
        )
        engine_type = self._resolved_engine_type(receipt)
        if engine_type not in {None, "gx"}:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "unsupported_engine_type",
                    "message": f"Execution runtime does not support engine_type '{engine_type}'",
                    "data_delivery_id": data_delivery_id,
                    "engine_type": engine_type,
                },
            )

        delivery_snapshot = self._delivery_snapshot({**dict(receipt), "resolved_engine_type": engine_type or receipt.get("resolved_engine_type")})
        source_overrides = self._source_overrides(receipt)
        requested_by_user = self._text(requested_by) or self._text(get_user_id()) or "system"
        request_correlation_id = self._text(correlation_id) or self._text(request.headers.get("X-Correlation-ID")) or f"corr-{uuid4().hex[:12]}"
        execution_mode = self._choose_execution_mode(receipt)

        if execution_mode == "grouped_scope":
            self._assert_grouped_execution_engine_supported(receipt, data_delivery_id=data_delivery_id)

        if execution_mode == "single_suite":
            suite = await self._load_suite(receipt)
            dispatch_payload = await self._runtime_api.enqueue_scheduled_suite_run(
                request=request,
                suite=suite,
                scheduled_at=datetime.now(UTC),
                execution_run_repository=self._execution_run_repository,
                requested_by=requested_by_user,
                status_source="data_catalog.delivery_linked_execution",
                status_reason="Delivery-linked GX execution accepted",
                run_plan_id=self._text(receipt.get("resolved_run_plan_id")) or None,
                run_plan_version_id=self._text(receipt.get("resolved_run_plan_version_id")) or None,
                source_overrides_by_data_object_version_id=source_overrides,
                delivery_snapshot=delivery_snapshot,
                correlation_id=request_correlation_id,
                queue_key=self._runtime_api.resolve_execution_queue_key(),
                join_pair_materialization_queue_key=self._runtime_api.resolve_join_pair_materialization_queue_key(),
                data_catalog_repository=self._catalog_repository,
                settings_provider=get_settings,
                dispatch_worker_heartbeat_key_builder=self._runtime_api.resolve_execution_worker_heartbeat_key,
                dispatch_worker_heartbeat_ttl_seconds=self._runtime_api.resolve_execution_worker_heartbeat_ttl_seconds(),
                join_pair_materialization_worker_heartbeat_key_builder=self._runtime_api.resolve_join_pair_materialization_worker_heartbeat_key,
                join_pair_materialization_worker_heartbeat_ttl_seconds=self._runtime_api.resolve_join_pair_materialization_worker_heartbeat_ttl_seconds(),
                inject_trace_carrier=propagate.inject,
                map_persistence_error=self._runtime_api.map_execution_run_persistence_error,
                async_redis_module=aioredis,
                sync_redis_module=redis_sync,
                logger=_log,
            )
        else:
            execution_resolution = receipt.get("execution_resolution") if isinstance(receipt.get("execution_resolution"), Mapping) else {}
            applicable_suites = execution_resolution.get("applicable_gx_suites") if isinstance(execution_resolution.get("applicable_gx_suites"), list) else []
            grouped_execution_plan = build_gx_grouped_execution_plan_entity(
                execution_resolution.get("grouped_execution_plan")
            )
            dispatch_payload = await self._runtime_api.enqueue_grouped_scope_run(
                request=request,
                grouped_execution_plan=(
                    grouped_execution_plan.model_dump(exclude_none=True)
                    if grouped_execution_plan is not None
                    else {}
                ),
                scope_selector={"dataObjectVersionId": receipt.get("resolved_data_object_version_id")},
                suite_refs=[dict(item) for item in applicable_suites if isinstance(item, Mapping)],
                scheduled_at=datetime.now(UTC),
                execution_run_repository=self._execution_run_repository,
                requested_by=requested_by_user,
                run_plan_id=self._text(receipt.get("resolved_run_plan_id")) or None,
                run_plan_version_id=self._text(receipt.get("resolved_run_plan_version_id")) or None,
                source_overrides_by_data_object_version_id=source_overrides,
                delivery_snapshot=delivery_snapshot,
                correlation_id=request_correlation_id,
                queue_key=self._runtime_api.resolve_execution_queue_key(),
                settings_provider=get_settings,
                dispatch_worker_heartbeat_key_builder=self._runtime_api.resolve_execution_worker_heartbeat_key,
                dispatch_worker_heartbeat_ttl_seconds=self._runtime_api.resolve_execution_worker_heartbeat_ttl_seconds(),
                build_grouped_scope_command=self._runtime_api.build_grouped_scope_command,
                persist_grouped_dispatch_run_use_case=persist_grouped_dispatch_run_use_case,
                inject_trace_carrier=propagate.inject,
                async_redis_module=aioredis,
                sync_redis_module=redis_sync,
                logger=_log,
            )

        if not str(engine_type or "").strip():
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "missing_engine_type",
                    "message": "Delivery-linked execution dispatch requires explicit engine_type",
                    "correlation_id": request_correlation_id,
                },
            )

        if isinstance(dispatch_payload, Mapping):
            dispatch_payload = {**dispatch_payload, "engine_type": str(engine_type).strip().lower()}

        typed_dispatch_payload = (
            dispatch_payload
            if isinstance(dispatch_payload, GxDispatchPayloadEntity)
            else build_gx_dispatch_payload_entity(dispatch_payload)
        )
        execution_run_id = str(
            (typed_dispatch_payload.queueMessageId if typed_dispatch_payload is not None else None)
            or (typed_dispatch_payload.runId if typed_dispatch_payload is not None else None)
            or ""
        ).strip()
        return {
            **dict(receipt),
            "execution_mode": execution_mode,
            "execution_run_id": execution_run_id or None,
            "resolved_engine_type": engine_type or receipt.get("resolved_engine_type"),
            "execution_dispatch": (
                typed_dispatch_payload.model_dump(by_alias=True, exclude_none=True)
                if typed_dispatch_payload is not None
                else self._snakecase_payload(dispatch_payload)
            ),
        }
