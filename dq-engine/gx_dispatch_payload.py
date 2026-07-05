"""GX dispatch payload parsing — source overrides, suite envelope resolution, primary key extraction.

Resolves source locations from dispatch payloads, extracts source overrides, and
validates suite envelopes for runnability.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from dq_plan_execution import coerce_int
from dq_plan_execution import coerce_str
from dq_plan_execution import parse_dispatch_payload

from gx_dispatch_api import (
    _api_get_data_object_version,
    _api_get_suite_envelope,
)
from gx_dispatch_expectations import _column_is_available
from gx_dispatch_expectations import _build_spark_row_condition_expression
from gx_dispatch_runtime import (
    _coerce_source_location,
    _infer_materialized_source_location,
)
from dq_plan_execution_types import GxWorkerConfig
from dq_plan_execution_types import GxWorkerExecutionError

from dq_utils.auth_utils import TokenProvider


# ---------------------------------------------------------------------------
# Source location dataclass
# ---------------------------------------------------------------------------


@dataclass
class SourceLocation:
    uri: str
    format: str  # "parquet" | "delta"
    options: dict[str, Any] = ()


# ---------------------------------------------------------------------------
# Payload parsing helpers
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Suite envelope helpers
# ---------------------------------------------------------------------------


def _extract_primary_key_fields(envelope: dict[str, Any]) -> list[str]:
    execution_hints = envelope.get("executionHints") if isinstance(envelope.get("executionHints"), dict) else None
    if execution_hints is None and isinstance(envelope.get("execution_hints"), dict):
        execution_hints = envelope.get("execution_hints")
    if not isinstance(execution_hints, dict):
        return []

    raw_fields = execution_hints.get("primaryKeyFields")
    if raw_fields is None:
        raw_fields = execution_hints.get("primary_key_fields")
    if not isinstance(raw_fields, list):
        return []
    return [str(value).strip() for value in raw_fields if str(value).strip()]


def _assert_runnable_suite(envelope: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    gx_suite = envelope.get("gx_suite") if isinstance(envelope.get("gx_suite"), dict) else None
    if not isinstance(gx_suite, dict):
        raise GxWorkerExecutionError("GX suite envelope is missing gx_suite", failure_code="GX_SUITE_NOT_RUNNABLE")

    expectations = gx_suite.get("expectations")
    if not isinstance(expectations, list) or not expectations:
        raise GxWorkerExecutionError("GX suite has no executable expectations", failure_code="GX_SUITE_NOT_RUNNABLE")
    for idx, exp in enumerate(expectations):
        if not isinstance(exp, dict):
            raise GxWorkerExecutionError(
                f"GX suite expectation at index {idx} is invalid",
                failure_code="GX_SUITE_NOT_RUNNABLE",
            )
        if not str(exp.get("expectation_type") or "").strip():
            raise GxWorkerExecutionError(
                f"GX suite expectation at index {idx} missing expectation_type",
                failure_code="GX_SUITE_NOT_RUNNABLE",
            )
        kwargs = exp.get("kwargs")
        if not isinstance(kwargs, dict) or not kwargs:
            raise GxWorkerExecutionError(
                f"GX suite expectation at index {idx} missing kwargs",
                failure_code="GX_SUITE_NOT_RUNNABLE",
            )

    resolved_scope = envelope.get("resolved_execution_scope") if isinstance(envelope.get("resolved_execution_scope"), dict) else None
    target_ids: list[str] = []
    if isinstance(resolved_scope, dict):
        raw_ids = resolved_scope.get("data_object_version_ids") or []
        target_ids = [str(v).strip() for v in raw_ids if str(v).strip()]
    if not target_ids:
        raise GxWorkerExecutionError("GX suite has no resolved execution targets", failure_code="GX_SUITE_NOT_RUNNABLE")

    return expectations, target_ids, _extract_primary_key_fields(envelope)


# ---------------------------------------------------------------------------
# Source override helpers
# ---------------------------------------------------------------------------


def _extract_source_overrides(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_overrides = payload.get("source_overrides_by_data_object_version_id") or payload.get("source_overrides")
    overrides_by_target: dict[str, dict[str, Any]] = {}
    if isinstance(raw_overrides, dict):
        for key, value in raw_overrides.items():
            target_id = str(key).strip()
            if not target_id or not isinstance(value, dict):
                continue
            overrides_by_target[target_id] = dict(value)
    return overrides_by_target


def _resolve_locations_for_targets(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    correlation_id: str,
    target_ids: list[str],
    payload: dict[str, Any],
) -> dict[str, SourceLocation]:
    locations_by_target: dict[str, SourceLocation] = {}
    overrides_by_target = _extract_source_overrides(payload)

    for target_id in target_ids:
        override = overrides_by_target.get(target_id)
        if override is None:
            continue
        uri = str(override.get("uri") or "").strip()
        fmt = str(override.get("format") or "").strip().lower()
        options_raw = override.get("options")
        if not uri or not fmt:
            raise GxWorkerExecutionError(
                "GX dispatch source override is missing required fields (uri/format)",
                failure_code="GX_WORKER_INVALID_SOURCE_OVERRIDE",
            )
        if fmt not in {"parquet", "delta"}:
            raise GxWorkerExecutionError(
                f"GX dispatch source override has unsupported format '{fmt}'",
                failure_code="GX_WORKER_UNSUPPORTED_STORAGE_FORMAT",
            )
        if options_raw is not None and not isinstance(options_raw, dict):
            raise GxWorkerExecutionError(
                "GX dispatch source override options must be an object",
                failure_code="GX_WORKER_INVALID_SOURCE_OVERRIDE",
            )
        locations_by_target[target_id] = SourceLocation(uri=uri, format=fmt, options=dict(options_raw or {}))

    for target_id in target_ids:
        if target_id in locations_by_target:
            continue
        version_payload = _api_get_data_object_version(
            config,
            token_provider,
            version_id=target_id,
            correlation_id=correlation_id,
        )
        locations_by_target[target_id] = _coerce_source_location(version_payload, data_object_version_id=target_id)

    return locations_by_target


def _resolve_join_pair_location(
    *,
    payload: dict[str, Any],
    envelope: dict[str, Any],
    target_ids: list[str],
) -> SourceLocation:
    overrides_by_target = _extract_source_overrides(payload)
    override_candidates: list[SourceLocation] = []
    for target_id in target_ids:
        override = overrides_by_target.get(target_id)
        if override is None:
            continue
        uri = str(override.get("uri") or "").strip()
        fmt = str(override.get("format") or "").strip().lower()
        options_raw = override.get("options")
        if not uri or not fmt:
            raise GxWorkerExecutionError(
                "GX dispatch join_pair source override is missing required fields (uri/format)",
                failure_code="GX_WORKER_INVALID_SOURCE_OVERRIDE",
            )
        if fmt not in {"parquet", "delta"}:
            raise GxWorkerExecutionError(
                f"GX dispatch join_pair source override has unsupported format '{fmt}'",
                failure_code="GX_WORKER_UNSUPPORTED_STORAGE_FORMAT",
            )
        if options_raw is not None and not isinstance(options_raw, dict):
            raise GxWorkerExecutionError(
                "GX dispatch join_pair source override options must be an object",
                failure_code="GX_WORKER_INVALID_SOURCE_OVERRIDE",
            )
        override_candidates.append(SourceLocation(uri=uri, format=fmt, options=dict(options_raw or {})))

    if override_candidates:
        first = override_candidates[0]
        distinct = {(item.uri, item.format, json.dumps(item.options, sort_keys=True)) for item in override_candidates}
        if len(distinct) > 1:
            raise GxWorkerExecutionError(
                "GX join_pair execution received conflicting source overrides across targets",
                failure_code="GX_WORKER_INVALID_SOURCE_OVERRIDE",
            )
        return first

    execution_contract = envelope.get("execution_contract") if isinstance(envelope.get("execution_contract"), dict) else None
    source_materialization = execution_contract.get("source_materialization") if isinstance(execution_contract, dict) else None
    if not isinstance(source_materialization, dict):
        raise GxWorkerExecutionError(
            "GX join_pair execution requires source_materialization in the suite execution contract",
            failure_code="GX_WORKER_MISSING_SOURCE_LOCATION",
        )

    return _infer_materialized_source_location(output_location=str(source_materialization.get("output_location") or ""))


def _resolve_join_pair_report_storage_uri(
    *,
    payload: dict[str, Any],
    envelope: dict[str, Any],
    target_ids: list[str],
    join_pair_location: SourceLocation,
) -> str:
    overrides_by_target = _extract_source_overrides(payload)
    for target_id in target_ids:
        override = overrides_by_target.get(target_id)
        if not isinstance(override, dict):
            continue
        override_uri = str(override.get("uri") or "").strip()
        if override_uri:
            return override_uri

    execution_contract = envelope.get("execution_contract") if isinstance(envelope.get("execution_contract"), dict) else None
    source_materialization = execution_contract.get("source_materialization") if isinstance(execution_contract, dict) else None
    if isinstance(source_materialization, dict):
        output_location = str(source_materialization.get("output_location") or "").strip()
        if output_location:
            return output_location

    return join_pair_location.uri


# ---------------------------------------------------------------------------
# Public API: suite envelope fetching
# ---------------------------------------------------------------------------


def _fetch_suite_envelope(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    suite_id: str,
    suite_version: int,
    correlation_id: str,
) -> dict[str, Any]:
    return _api_get_suite_envelope(
        config,
        token_provider,
        suite_id=suite_id,
        suite_version=suite_version,
        correlation_id=correlation_id,
    )
