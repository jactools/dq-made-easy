"""GX dispatch processing — routing dispatch messages by execution_shape (grouped/single/join-pair/spark expectations).

Owns the main dispatch routing logic: ``process_dispatch_message()`` routes to
``_process_grouped_dispatch_message``, ``_process_spark_expectations_dispatch_message``,
or the single-object/join-pair path based on ``execution_shape`` and ``engine_type``.
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from dq_utils.logging_utils import log_event
from execution_dispatch import (
    SUPPORTED_EXECUTION_ENGINES,
    execute_engine_rule_payload,
    normalize_execution_engine,
    parse_dispatch_payload,
    process_engine_dispatch_message,
)

from gx_dispatch_api import (
    _api_get_suite_envelope,
    _api_report_execution_progress,
    _api_report_run,
    _build_execution_progress,
)
from gx_dispatch_config import (
    _build_token_provider,
    _utc_now_iso,
)
from gx_dispatch_expectations import _evaluate_expectations_spark
from gx_dispatch_expectations import _column_is_available
from gx_dispatch_payload import (
    SourceLocation,
    _assert_runnable_suite,
    _extract_source_overrides,
    _resolve_join_pair_location,
    _resolve_join_pair_report_storage_uri,
    _resolve_locations_for_targets,
)
from gx_dispatch_runtime import (
    _assert_supported_uri,
    _coerce_source_location,
    _create_spark_session,
    _download_s3a_prefix_to_tempdir,
    _infer_materialized_source_location,
    _normalize_s3_uri,
    _require_s3_config_for_location,
    _safe_stop_spark_session,
    _spark_read_dataset,
)
from gx_dispatch_telemetry import (
    record_spark_expectations_observability,
    record_worker_duration,
    record_worker_expectation_results,
    traced_worker_span,
)
from gx_dispatch_types import GxWorkerConfig
from gx_dispatch_types import GxWorkerExecutionError


# ---------------------------------------------------------------------------
# Payload coercion helpers (thin wrappers around execution_dispatch)
# ---------------------------------------------------------------------------


def _parse_dispatch_payload(raw: str) -> dict[str, Any]:
    return parse_dispatch_payload(raw)


def _coerce_str(payload: dict[str, Any], *keys: str) -> str:
    from execution_dispatch import coerce_str

    return coerce_str(payload, *keys)


def _coerce_int(payload: dict[str, Any], *keys: str) -> int:
    from execution_dispatch import coerce_int

    return coerce_int(payload, *keys)


# ---------------------------------------------------------------------------
# Grouped dispatch processing
# ---------------------------------------------------------------------------


def _process_grouped_dispatch_message(
    config: GxWorkerConfig,
    *,
    payload: dict[str, Any],
    run_id: str,
    correlation_id: str,
    requested_by: str | None,
) -> None:
    logger = logging.getLogger(__name__)
    grouped_plan = payload.get("grouped_execution_plan") if isinstance(payload.get("grouped_execution_plan"), dict) else None
    if grouped_plan is None:
        raise GxWorkerExecutionError(
            "Grouped GX dispatch payload is missing grouped_execution_plan",
            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
        )

    batches = grouped_plan.get("batches")
    if not isinstance(batches, list) or not batches:
        raise GxWorkerExecutionError(
            "Grouped GX dispatch payload is missing execution batches",
            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
        )

    log_event(
        logger,
        "gx.worker.dispatch.received",
        component="dq-engine-gx-worker",
        correlation_id=correlation_id,
        run_id=run_id,
        execution_shape="grouped_scope",
        batch_count=grouped_plan.get("batch_count"),
        suite_count=grouped_plan.get("suite_count"),
    )

    token_provider = _build_token_provider()
    grouped_execution_started = time.perf_counter()
    total_steps = len(batches) + 1
    _api_report_execution_progress(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        changed_by=requested_by,
        reason="GX worker started grouped execution",
        details={"source": "dq-engine-gx-worker", "dispatch": payload},
        completed_steps=0,
        total_steps=total_steps,
        label="Queued for grouped execution",
    )

    target_ids = [
        str(batch.get("data_object_version_id") or "").strip()
        for batch in batches
        if isinstance(batch, dict)
    ]
    target_ids = [target_id for target_id in target_ids if target_id]
    if not target_ids:
        raise GxWorkerExecutionError(
            "Grouped GX dispatch payload does not define any data_object_version_id targets",
            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
        )

    locations_by_target = _resolve_locations_for_targets(
        config,
        token_provider,
        correlation_id=correlation_id,
        target_ids=target_ids,
        payload=payload,
    )

    _api_report_execution_progress(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        changed_by=requested_by,
        reason="GX worker resolved grouped execution inputs",
        details={"source": "dq-engine-gx-worker"},
        completed_steps=1,
        total_steps=total_steps,
        label=f"Resolved {len(batches)} grouped batches",
    )

    needs_delta = any(loc.format == "delta" for loc in locations_by_target.values())
    spark_session = _create_spark_session(config, enable_delta=needs_delta)
    tmpdirs: list[tempfile.TemporaryDirectory[str]] = []
    all_ok = True
    all_diagnostics: list[dict[str, Any]] = []
    batch_results: list[dict[str, Any]] = []
    total_suite_count = 0

    try:
        for batch_index, batch in enumerate(batches, start=1):
            if not isinstance(batch, dict):
                raise GxWorkerExecutionError(
                    "Grouped GX dispatch batch is invalid",
                    failure_code="GX_DISPATCH_INVALID_PAYLOAD",
                )
            target_id = str(batch.get("data_object_version_id") or "").strip()
            if not target_id:
                raise GxWorkerExecutionError(
                    "Grouped GX dispatch batch is missing data_object_version_id",
                    failure_code="GX_DISPATCH_INVALID_PAYLOAD",
                )
            suites = batch.get("suites")
            if not isinstance(suites, list) or not suites:
                raise GxWorkerExecutionError(
                    f"Grouped GX dispatch batch '{target_id}' does not include any suite envelopes",
                    failure_code="GX_DISPATCH_INVALID_PAYLOAD",
                )

            batch_started_at = time.perf_counter()
            batch_ok = True
            location = locations_by_target[target_id]
            normalized_uri = _normalize_s3_uri(location.uri)
            _assert_supported_uri(normalized_uri)
            _require_s3_config_for_location(config, uri=normalized_uri)
            read_uri = normalized_uri
            if normalized_uri.startswith("s3a://"):
                tmpdir, localized_path = _download_s3a_prefix_to_tempdir(config, uri=normalized_uri)
                tmpdirs.append(tmpdir)
                read_uri = localized_path

            with traced_worker_span(
                "gx.worker.batch",
                component="dq-engine-gx-worker",
                correlation_id=correlation_id,
                run_id=run_id,
                execution_shape="grouped_scope",
                batch_index=batch_index,
                data_object_version_id=target_id,
                suite_count=len(suites),
            ):
                source_read_started_at = time.perf_counter()
                df = _spark_read_dataset(
                    spark_session,
                    location=SourceLocation(uri=read_uri, format=location.format, options=location.options),
                    max_rows=config.max_rows,
                )
                record_worker_duration(
                    stage="source_read",
                    execution_shape="grouped_scope",
                    duration_ms=(time.perf_counter() - source_read_started_at) * 1000.0,
                    result="success",
                    source_format=location.format,
                    batch_count=len(batches),
                    suite_count=len(suites),
                    target_count=1,
                )

                suite_results: list[dict[str, Any]] = []
                for suite_payload in suites:
                    if not isinstance(suite_payload, dict):
                        raise GxWorkerExecutionError(
                            f"Grouped GX dispatch batch '{target_id}' contains an invalid suite envelope",
                            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
                        )
                    expectations, suite_targets, primary_key_fields = _assert_runnable_suite(suite_payload)
                    if target_id not in suite_targets:
                        raise GxWorkerExecutionError(
                            f"Grouped GX dispatch suite is not attached to target '{target_id}'",
                            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
                        )
                    ok, summary, diagnostics = _evaluate_expectations_spark(
                        df,
                        expectations,
                        primary_key_fields=primary_key_fields,
                    )
                    record_worker_expectation_results(
                        execution_shape="grouped_scope",
                        passed_count=int(summary.get("passed_expectation_count") or 0),
                        failed_count=int(summary.get("failed_expectation_count") or 0),
                    )
                    suite_id = str(suite_payload.get("suite_id") or "")
                    suite_version = int(suite_payload.get("suite_version") or 0)
                    compiled_from = suite_payload.get("compiled_from") if isinstance(suite_payload.get("compiled_from"), dict) else None
                    rule_ids = []
                    if isinstance(compiled_from, dict):
                        raw_rule_ids = compiled_from.get("rule_ids") or []
                        if isinstance(raw_rule_ids, list):
                            rule_ids = [str(item).strip() for item in raw_rule_ids if str(item).strip()]
                    suite_results.append(
                        {
                            "suite_id": suite_id,
                            "suite_version": suite_version,
                            "rule_ids": rule_ids,
                            "ok": ok,
                            "summary": summary,
                        }
                    )
                    total_suite_count += 1
                    if not ok:
                        batch_ok = False
                        all_ok = False
                    for diag in diagnostics:
                        diag["data_object_version_id"] = target_id
                        diag["storage_uri"] = normalized_uri
                        diag["storage_format"] = location.format
                        diag["suite_id"] = suite_id
                        diag["suite_version"] = suite_version
                        all_diagnostics.append(diag)

                batch_results.append(
                    {
                        "data_object_version_id": target_id,
                        "storage_uri": normalized_uri,
                        "storage_format": location.format,
                        "suite_count": len(suite_results),
                        "suite_results": suite_results,
                        "ok": batch_ok,
                    }
                )

                _api_report_execution_progress(
                    config,
                    token_provider,
                    run_id=run_id,
                    correlation_id=correlation_id,
                    changed_by=requested_by,
                    reason="GX worker evaluated a grouped batch",
                    details={"source": "dq-engine-gx-worker", "batch_index": batch_index},
                    completed_steps=batch_index + 1,
                    total_steps=total_steps,
                    label=f"Evaluated grouped batch {batch_index} of {len(batches)}",
                )

            record_worker_duration(
                stage="batch_execution",
                execution_shape="grouped_scope",
                duration_ms=(time.perf_counter() - batch_started_at) * 1000.0,
                result="success" if batch_ok else "failure",
                batch_count=len(batches),
                suite_count=len(suite_results),
                target_count=1,
            )
    finally:
        _safe_stop_spark_session(spark_session)
        for tmpdir in tmpdirs:
            tmpdir.cleanup()

    result_summary = {
        "selection_mode": "grouped_scope",
        "batch_count": len(batch_results),
        "suite_count": total_suite_count,
        "results": batch_results,
    }

    if all_ok:
        _api_report_run(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            new_status="succeeded",
            changed_by=requested_by,
            reason="GX worker completed grouped execution",
            details={"source": "dq-engine-gx-worker", "selection_mode": "grouped_scope"},
            execution_progress=_build_execution_progress(
                completed_steps=total_steps,
                total_steps=total_steps,
                label="Grouped execution completed",
            ),
            completed_at=_utc_now_iso(),
            result_summary=result_summary,
            diagnostics=[],
            failure_code=None,
            failure_message=None,
        )
        record_worker_duration(
            stage="dispatch",
            execution_shape="grouped_scope",
            duration_ms=(time.perf_counter() - grouped_execution_started) * 1000.0,
            result="success",
            batch_count=len(batch_results),
            suite_count=total_suite_count,
            target_count=len(target_ids),
        )
    else:
        _api_report_run(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            new_status="failed",
            changed_by=requested_by,
            reason="GX worker completed grouped execution with failures",
            details={"source": "dq-engine-gx-worker", "selection_mode": "grouped_scope", "failure_count": len(all_diagnostics)},
            execution_progress=_build_execution_progress(
                completed_steps=total_steps,
                total_steps=total_steps,
                label="Grouped execution completed with failures",
            ),
            completed_at=_utc_now_iso(),
            result_summary=result_summary,
            diagnostics=all_diagnostics,
            failure_code="GX_VALIDATION_FAILED",
            failure_message="One or more grouped-scope expectations failed",
        )
        record_worker_duration(
            stage="dispatch",
            execution_shape="grouped_scope",
            duration_ms=(time.perf_counter() - grouped_execution_started) * 1000.0,
            result="failure",
            batch_count=len(batch_results),
            suite_count=total_suite_count,
            target_count=len(target_ids),
        )


# ---------------------------------------------------------------------------
# Spark expectations dispatch (generic engine)
# ---------------------------------------------------------------------------


def _build_spark_expectations_report_summary(response_payload: dict[str, Any], *, output_dir: Any) -> dict[str, Any]:
    metrics = response_payload.get("metrics")
    return {
        "engine_type": "spark_expectations",
        "rule_id": response_payload.get("rule_id"),
        "result": response_payload.get("result", "passed"),
        "passed_count": response_payload.get("passed_count", 0),
        "failed_count": response_payload.get("failed_count", 0),
        "failure_code": response_payload.get("failure_code"),
        "failure_message": response_payload.get("failure_message"),
        "failed_check": response_payload.get("failed_check", {}),
        "failure_metrics": response_payload.get("failure_metrics", {}),
        "trace": response_payload.get("trace", {}),
        "summary": response_payload,
        "output_dir": output_dir,
        "execution_metadata": response_payload.get("execution_metadata", {}),
        "quarantine_artifact": response_payload.get("quarantine_artifact", {}),
        "error_management": response_payload.get("error_management", {}),
        "observability_summary": response_payload.get("observability_summary", {}),
        "metrics": metrics if isinstance(metrics, dict) else response_payload.get("observability_summary", {}),
    }


def _process_spark_expectations_dispatch_message(
    config: GxWorkerConfig,
    *,
    payload: dict[str, Any],
    run_id: str,
    correlation_id: str,
    requested_by: str | None,
) -> None:
    response_payload = process_engine_dispatch_message(
        config,
        payload=payload,
        run_id=run_id,
        correlation_id=correlation_id,
        requested_by=requested_by,
        report_run_fn=_api_report_run,
        report_progress_fn=_api_report_execution_progress,
        token_provider_factory=_build_token_provider,
        execute_payload_fn=execute_engine_rule_payload,
    )
    engine_type = str(response_payload.get("engine_type") or normalize_execution_engine(_coerce_str(payload, "engine_type")))
    if engine_type == "spark_expectations":
        record_spark_expectations_observability(
            observability_summary=response_payload.get("observability_summary"),
            result=response_payload.get("result") if isinstance(response_payload.get("result"), str) else response_payload.get("result_status"),
        )
    record_worker_duration(
        stage="dispatch",
        execution_shape=engine_type,
        duration_ms=0.0,
        result="success" if response_payload.get("ok") else "failure",
        batch_count=1,
        suite_count=1,
        target_count=1,
    )


# ---------------------------------------------------------------------------
# Main dispatch routing entry point
# ---------------------------------------------------------------------------


def process_dispatch_message(config: GxWorkerConfig, *, raw_message: str) -> None:
    """Route a raw dispatch message to the correct processing handler.

    Handles: grouped_scope, spark expectations (generic engines), single_object,
    and join_pair execution shapes.
    """
    payload = _parse_dispatch_payload(raw_message)

    run_id = _coerce_str(payload, "run_id", "queue_message_id")
    execution_shape = _coerce_str(payload, "execution_shape") or "single_object"
    suite_id = _coerce_str(payload, "suite_id")
    suite_version = _coerce_int(payload, "suite_version")
    correlation_id = _coerce_str(payload, "correlation_id") or f"corr-{uuid4().hex[:12]}"
    requested_by = _coerce_str(payload, "requested_by") or None

    if execution_shape == "grouped_scope":
        if not run_id:
            raise GxWorkerExecutionError(
                "GX dispatch payload is missing required run_id for grouped execution",
                failure_code="GX_DISPATCH_INVALID_PAYLOAD",
            )
        _process_grouped_dispatch_message(
            config,
            payload=payload,
            run_id=run_id,
            correlation_id=correlation_id,
            requested_by=requested_by,
        )
        return

    dispatch_engine_type = normalize_execution_engine(_coerce_str(payload, "engine_type"))
    if dispatch_engine_type in (SUPPORTED_EXECUTION_ENGINES - {"gx"}):
        _process_spark_expectations_dispatch_message(
            config,
            payload=payload,
            run_id=run_id,
            correlation_id=correlation_id,
            requested_by=requested_by,
        )
        return

    if not run_id or not suite_id or suite_version <= 0:
        raise GxWorkerExecutionError(
            "GX dispatch payload is missing required identifiers (run_id/suite_id/suite_version)",
            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
        )

    logger = logging.getLogger(__name__)
    log_event(
        logger,
        "gx.worker.dispatch.received",
        component="dq-engine-gx-worker",
        correlation_id=correlation_id,
        run_id=run_id,
        suite_id=suite_id,
        suite_version=suite_version,
    )

    token_provider = _build_token_provider()
    single_execution_started = time.perf_counter()

    _api_report_run(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        new_status="running",
        changed_by=requested_by,
        reason="GX worker started execution",
        details={"source": "dq-engine-gx-worker", "dispatch": payload},
        execution_progress=_build_execution_progress(
            completed_steps=0,
            total_steps=1,
            label="Queued for execution",
        ),
        started_at=_utc_now_iso(),
    )

    envelope = _api_get_suite_envelope(
        config,
        token_provider,
        suite_id=suite_id,
        suite_version=suite_version,
        correlation_id=correlation_id,
    )
    expectations, target_ids, primary_key_fields = _assert_runnable_suite(envelope)

    # Optional scope override (adhoc runs may choose a subset of the resolved targets).
    raw_scope_override = payload.get("executionScopeOverride") or payload.get("execution_scope_override")
    if isinstance(raw_scope_override, list):
        normalized_override = [str(v).strip() for v in raw_scope_override if str(v).strip()]
        if normalized_override:
            missing = [v for v in normalized_override if v not in target_ids]
            if missing:
                raise GxWorkerExecutionError(
                    "GX dispatch executionScopeOverride contains target(s) not attached to the suite",
                    failure_code="GX_WORKER_INVALID_SCOPE_OVERRIDE",
                )
            target_ids = normalized_override

    if execution_shape == "join_pair":
        join_pair_location = _resolve_join_pair_location(
            payload=payload,
            envelope=envelope,
            target_ids=target_ids,
        )
        total_steps = 2
        _api_report_execution_progress(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            changed_by=requested_by,
            reason="GX worker resolved join-pair source",
            details={"source": "dq-engine-gx-worker", "execution_shape": "join_pair"},
            completed_steps=1,
            total_steps=total_steps,
            label="Resolved joined source materialization",
        )

        needs_delta = join_pair_location.format == "delta"
        spark_session = _create_spark_session(config, enable_delta=needs_delta)
        normalized_uri = _normalize_s3_uri(join_pair_location.uri)
        _assert_supported_uri(normalized_uri)
        _require_s3_config_for_location(config, uri=normalized_uri)

        tmpdirs: list[tempfile.TemporaryDirectory[str]] = []
        try:
            read_uri = normalized_uri
            if normalized_uri.startswith("s3a://"):
                tmpdir, localized_path = _download_s3a_prefix_to_tempdir(config, uri=normalized_uri)
                tmpdirs.append(tmpdir)
                read_uri = localized_path

            with traced_worker_span(
                "gx.worker.join_pair",
                component="dq-engine-gx-worker",
                correlation_id=correlation_id,
                run_id=run_id,
                suite_id=suite_id,
                suite_version=suite_version,
                execution_shape="join_pair",
            ):
                source_read_started_at = time.perf_counter()
                df = _spark_read_dataset(
                    spark_session,
                    location=SourceLocation(uri=read_uri, format=join_pair_location.format, options=join_pair_location.options),
                    max_rows=config.max_rows,
                )
                record_worker_duration(
                    stage="source_read",
                    execution_shape="join_pair",
                    duration_ms=(time.perf_counter() - source_read_started_at) * 1000.0,
                    result="success",
                    source_format=join_pair_location.format,
                    target_count=len(target_ids),
                )

                ok, summary, diagnostics = _evaluate_expectations_spark(
                    df,
                    expectations,
                    primary_key_fields=primary_key_fields,
                )
                record_worker_expectation_results(
                    execution_shape="join_pair",
                    passed_count=int(summary.get("passed_expectation_count") or 0),
                    failed_count=int(summary.get("failed_expectation_count") or 0),
                )

            _api_report_execution_progress(
                config,
                token_provider,
                run_id=run_id,
                correlation_id=correlation_id,
                changed_by=requested_by,
                reason="GX worker evaluated join-pair source",
                details={"source": "dq-engine-gx-worker", "execution_shape": "join_pair"},
                completed_steps=2,
                total_steps=total_steps,
                label="Evaluated joined source materialization",
            )
        finally:
            _safe_stop_spark_session(spark_session)
            for tmpdir in tmpdirs:
                tmpdir.cleanup()

        result_summary = {
            "suite_id": suite_id,
            "suite_version": suite_version,
            "target_count": len(target_ids),
            "results": [
                {
                    "data_object_version_id": target_ids[0] if target_ids else None,
                    "storage_uri": _resolve_join_pair_report_storage_uri(
                        payload=payload,
                        envelope=envelope,
                        target_ids=target_ids,
                        join_pair_location=join_pair_location,
                    ),
                    "storage_format": join_pair_location.format,
                    "ok": ok,
                    "summary": summary,
                }
            ],
        }
        if ok:
            _api_report_run(
                config,
                token_provider,
                run_id=run_id,
                correlation_id=correlation_id,
                new_status="succeeded",
                changed_by=requested_by,
                reason="GX worker completed join-pair execution",
                details={"source": "dq-engine-gx-worker", "execution_shape": "join_pair"},
                execution_progress=_build_execution_progress(
                    completed_steps=total_steps,
                    total_steps=total_steps,
                    label="Execution completed",
                ),
                completed_at=_utc_now_iso(),
                result_summary=result_summary,
                diagnostics=[],
                failure_code=None,
                failure_message=None,
            )
            record_worker_duration(
                stage="dispatch",
                execution_shape="join_pair",
                duration_ms=(time.perf_counter() - single_execution_started) * 1000.0,
                result="success",
                target_count=len(target_ids),
            )
        else:
            _api_report_run(
                config,
                token_provider,
                run_id=run_id,
                correlation_id=correlation_id,
                new_status="failed",
                changed_by=requested_by,
                reason="GX worker completed join-pair execution with failures",
                details={"source": "dq-engine-gx-worker", "execution_shape": "join_pair", "failure_count": len(diagnostics)},
                execution_progress=_build_execution_progress(
                    completed_steps=total_steps,
                    total_steps=total_steps,
                    label="Execution completed with failures",
                ),
                completed_at=_utc_now_iso(),
                result_summary=result_summary,
                diagnostics=diagnostics,
                failure_code="GX_VALIDATION_FAILED",
                failure_message="One or more expectations failed",
            )
            record_worker_duration(
                stage="dispatch",
                execution_shape="join_pair",
                duration_ms=(time.perf_counter() - single_execution_started) * 1000.0,
                result="failure",
                target_count=len(target_ids),
            )
        return

    locations_by_target = _resolve_locations_for_targets(
        config,
        token_provider,
        correlation_id=correlation_id,
        target_ids=target_ids,
        payload=payload,
    )

    total_steps = len(target_ids) + 1
    _api_report_execution_progress(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        changed_by=requested_by,
        reason="GX worker resolved execution inputs",
        details={"source": "dq-engine-gx-worker"},
        completed_steps=1,
        total_steps=total_steps,
        label=f"Resolved {len(target_ids)} source targets",
    )

    needs_delta = any(loc.format == "delta" for loc in locations_by_target.values())
    spark_session = _create_spark_session(config, enable_delta=needs_delta)

    all_ok = True
    per_target_results: list[dict[str, Any]] = []
    all_diagnostics: list[dict[str, Any]] = []

    tmpdirs: list[tempfile.TemporaryDirectory[str]] = []

    try:
        for target_index, target_id in enumerate(target_ids, start=1):
            target_started_at = time.perf_counter()
            location = locations_by_target[target_id]
            normalized_uri = _normalize_s3_uri(location.uri)
            _assert_supported_uri(normalized_uri)
            _require_s3_config_for_location(config, uri=normalized_uri)

            read_uri = normalized_uri
            if normalized_uri.startswith("s3a://"):
                tmpdir, localized_path = _download_s3a_prefix_to_tempdir(config, uri=normalized_uri)
                tmpdirs.append(tmpdir)
                read_uri = localized_path

            with traced_worker_span(
                "gx.worker.target",
                component="dq-engine-gx-worker",
                correlation_id=correlation_id,
                run_id=run_id,
                suite_id=suite_id,
                suite_version=suite_version,
                execution_shape="single_object",
                target_index=target_index,
                data_object_version_id=target_id,
            ):
                source_read_started_at = time.perf_counter()
                df = _spark_read_dataset(
                    spark_session,
                    location=SourceLocation(uri=read_uri, format=location.format, options=location.options),
                    max_rows=config.max_rows,
                )
                record_worker_duration(
                    stage="source_read",
                    execution_shape="single_object",
                    duration_ms=(time.perf_counter() - source_read_started_at) * 1000.0,
                    result="success",
                    source_format=location.format,
                    target_count=len(target_ids),
                )

                ok, summary, diagnostics = _evaluate_expectations_spark(
                    df,
                    expectations,
                    primary_key_fields=primary_key_fields,
                )
                record_worker_expectation_results(
                    execution_shape="single_object",
                    passed_count=int(summary.get("passed_expectation_count") or 0),
                    failed_count=int(summary.get("failed_expectation_count") or 0),
                )
                per_target_results.append(
                    {
                        "data_object_version_id": target_id,
                        "storage_uri": normalized_uri,
                        "storage_format": location.format,
                        "ok": ok,
                        "summary": summary,
                    }
                )
                if not ok:
                    all_ok = False
                for diag in diagnostics:
                    diag["data_object_version_id"] = target_id
                    diag["storage_uri"] = normalized_uri
                    diag["storage_format"] = location.format
                    all_diagnostics.append(diag)

                _api_report_execution_progress(
                    config,
                    token_provider,
                    run_id=run_id,
                    correlation_id=correlation_id,
                    changed_by=requested_by,
                    reason="GX worker evaluated a source target",
                    details={"source": "dq-engine-gx-worker", "target_index": target_index},
                    completed_steps=target_index + 1,
                    total_steps=total_steps,
                    label=f"Evaluated source target {target_index} of {len(target_ids)}",
                )

            record_worker_duration(
                stage="target_execution",
                execution_shape="single_object",
                duration_ms=(time.perf_counter() - target_started_at) * 1000.0,
                result="success" if ok else "failure",
                source_format=location.format,
                target_count=len(target_ids),
            )
    finally:
        _safe_stop_spark_session(spark_session)
        for tmpdir in tmpdirs:
            tmpdir.cleanup()

    result_summary = {
        "suite_id": suite_id,
        "suite_version": suite_version,
        "target_count": len(target_ids),
        "results": per_target_results,
    }

    if all_ok:
        _api_report_run(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            new_status="succeeded",
            changed_by=requested_by,
            reason="GX worker completed execution",
            details={"source": "dq-engine-gx-worker"},
            execution_progress=_build_execution_progress(
                completed_steps=total_steps,
                total_steps=total_steps,
                label="Execution completed",
            ),
            completed_at=_utc_now_iso(),
            result_summary=result_summary,
            diagnostics=[],
            failure_code=None,
            failure_message=None,
        )
        record_worker_duration(
            stage="dispatch",
            execution_shape="single_object",
            duration_ms=(time.perf_counter() - single_execution_started) * 1000.0,
            result="success",
            target_count=len(target_ids),
        )
    else:
        _api_report_run(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            new_status="failed",
            changed_by=requested_by,
            reason="GX worker completed execution with failures",
            details={"source": "dq-engine-gx-worker", "failure_count": len(all_diagnostics)},
            execution_progress=_build_execution_progress(
                completed_steps=total_steps,
                total_steps=total_steps,
                label="Execution completed with failures",
            ),
            completed_at=_utc_now_iso(),
            result_summary=result_summary,
            diagnostics=all_diagnostics,
            failure_code="GX_VALIDATION_FAILED",
            failure_message="One or more expectations failed",
        )
        record_worker_duration(
            stage="dispatch",
            execution_shape="single_object",
            duration_ms=(time.perf_counter() - single_execution_started) * 1000.0,
            result="failure",
            target_count=len(target_ids),
        )
