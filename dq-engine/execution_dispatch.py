from __future__ import annotations

import json
import logging
import time
from types import SimpleNamespace
from typing import Any, Callable

import requests

from dq_utils.auth_utils import TokenProvider
from dq_utils.auth_utils import build_oidc_token_provider_from_env
from dq_utils.logging_utils import log_event
from gx_dispatch_types import GxWorkerConfig

# Optional Kafka client
try:
    from kafka_client import KafkaExceptionPublisher
except ImportError:
    KafkaExceptionPublisher = None  # type: ignore
from gx_dispatch_types import GxWorkerConfigError
from gx_dispatch_types import GxWorkerExecutionError
from runtime_lowerers import build_failure_envelope


logger = logging.getLogger(__name__)

SUPPORTED_EXECUTION_ENGINES = {"gx", "soda", "sql", "pyspark", "spark", "spark_expectations", "trino"}
ENGINE_ALIASES = {
    "great_expectations": "gx",
    "great-expectations": "gx",
    "pyspark_native": "pyspark",
    "spark": "pyspark",
}
REPORT_RUN_PATH_TEMPLATE = "/rulebuilder/v1/gx/runs/{run_id}/report"


def normalize_execution_engine(engine_type: str | None) -> str:
    normalized = str(engine_type or "").strip().lower()
    return ENGINE_ALIASES.get(normalized, normalized)


def parse_dispatch_payload(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except Exception as exc:
        raise GxWorkerExecutionError("Execution dispatch message is not valid JSON", failure_code="GX_DISPATCH_INVALID_JSON") from exc
    if not isinstance(payload, dict):
        raise GxWorkerExecutionError("Execution dispatch message must be a JSON object", failure_code="GX_DISPATCH_INVALID_JSON")
    return payload


def coerce_str(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text_value = str(value).strip()
        if text_value:
            return text_value
    return ""


def coerce_int(payload: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            parsed = int(value)
            if parsed >= 1:
                return parsed
        except Exception:
            continue
    return 0


def build_token_provider() -> TokenProvider:
    try:
        return build_oidc_token_provider_from_env()
    except Exception:
        raise GxWorkerConfigError("Failed to initialize API token provider") from None


def _build_api_request_headers(config: GxWorkerConfig, token_provider: TokenProvider, *, correlation_id: str) -> dict[str, str]:
    token = token_provider.get_token(correlation_id=correlation_id)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Correlation-ID": correlation_id,
        "X-Request-Source": "dq-engine-execution-worker",
        "X-Api-Url": config.api_url,
    }


def api_request(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    method: str,
    path: str,
    correlation_id: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    url = f"{config.api_url.rstrip('/')}{path}"
    headers = _build_api_request_headers(config, token_provider, correlation_id=correlation_id)
    try:
        response = requests.request(method=method.upper(), url=url, headers=headers, params=params, json=json_body, timeout=30)
    except requests.RequestException as exc:  # pragma: no cover
        raise GxWorkerExecutionError(f"API request failed: {exc}", failure_code="GX_API_REQUEST_FAILED") from exc

    if response.status_code >= 400:
        raise GxWorkerExecutionError(
            f"API request failed with {response.status_code}: {response.text}",
            failure_code="GX_API_REQUEST_FAILED",
            status_code=response.status_code,
        )

    try:
        return response.json() if response.content else None
    except ValueError:
        return response.text


async def report_run(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    run_id: str,
    correlation_id: str,
    new_status: str,
    changed_by: str | None,
    reason: str | None,
    details: dict[str, Any] | None = None,
    execution_progress: dict[str, Any] | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    result_summary: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
    failure_code: str | None = None,
    failure_message: str | None = None,
    kafka_publisher: KafkaExceptionPublisher | None = None,
) -> None:
    # Separate diagnostics (violations) from metadata
    violation_diagnostics = diagnostics if diagnostics else []
    
    # Publish violations to Kafka if available
    if kafka_publisher and violation_diagnostics:
        await kafka_publisher.publish_violations(violation_diagnostics)
        logger.info("Published %d violations to Kafka for run %s", len(violation_diagnostics), run_id)
    
    # Only send summary metadata via API (not full violation details)
    api_payload = {
        "new_status": new_status,
        "changed_by": changed_by,
        "reason": reason,
        "details": details,
        "execution_progress": execution_progress,
        "started_at": started_at,
        "completed_at": completed_at,
        "result_summary": result_summary,
        "metrics": metrics,
        # Send summary counts, not full diagnostics
        "violation_count": len(violation_diagnostics),
        "diagnostics_count": min(len(violation_diagnostics), 100),  # Only first 100 for debugging
        "failure_code": failure_code,
        "failure_message": failure_message,
    }
    
    _ = api_request(
        config,
        token_provider,
        method="POST",
        path=REPORT_RUN_PATH_TEMPLATE.format(run_id=run_id),
        correlation_id=correlation_id,
        json_body=api_payload,
    )


def build_execution_progress(*, completed_steps: int, total_steps: int, label: str, source: str = "dq-engine-execution-worker") -> dict[str, Any]:
    percent = 0 if total_steps <= 0 else int(round((completed_steps / total_steps) * 100))
    return {
        "percent": max(0, min(percent, 100)),
        "label": label,
        "completed_steps": completed_steps,
        "total_steps": total_steps,
        "source": source,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def report_execution_progress(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    run_id: str,
    correlation_id: str,
    changed_by: str | None,
    reason: str,
    details: dict[str, Any] | None,
    completed_steps: int,
    total_steps: int,
    label: str,
) -> None:
    report_run(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        new_status="running",
        changed_by=changed_by,
        reason=reason,
        details=details,
        execution_progress=build_execution_progress(
            completed_steps=completed_steps,
            total_steps=total_steps,
            label=label,
        ),
    )


def log_dispatch_received(*, correlation_id: str, run_id: str, suite_id: str | None = None, suite_version: int | None = None, execution_shape: str | None = None, **extra: Any) -> None:
    log_event(
        logger,
        "execution.worker.dispatch.received",
        component="dq-engine-execution-worker",
        correlation_id=correlation_id,
        run_id=run_id,
        suite_id=suite_id,
        suite_version=suite_version,
        execution_shape=execution_shape,
        **extra,
    )


def _request_from_rule_payload(rule_payload: dict[str, Any], *, engine_type: str, output_dir: str | None) -> Any:
    return SimpleNamespace(
        id=rule_payload.get("id"),
        table=str(rule_payload.get("table") or ""),
        column=rule_payload.get("column"),
        type=str(rule_payload.get("type") or ""),
        params=rule_payload.get("params") if isinstance(rule_payload.get("params"), dict) else None,
        output_dir=output_dir,
        engine_type=engine_type,
    )


def execute_engine_rule_payload(
    *,
    engine_type: str,
    rule_payload: dict[str, Any],
    output_dir: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_engine = normalize_execution_engine(engine_type)
    if normalized_engine not in SUPPORTED_EXECUTION_ENGINES:
        return build_failure_envelope(
            rule_payload,
            engine_type=normalized_engine,
            failure_code="DQ_EXECUTION_UNSUPPORTED_ENGINE",
            failure_message=f"unsupported execution engine: {engine_type!r}",
            failure_stage="dispatch",
        )

    if normalized_engine in {"spark_expectations", "pyspark"}:
        from execution_contract import persist_execution_payload
        from spark_expectations_adapter import execute_spark_expectations_rule

        request = _request_from_rule_payload(rule_payload, engine_type="spark_expectations", output_dir=output_dir)
        result = execute_spark_expectations_rule(request)
        result.setdefault("engine_type", "spark_expectations")
        result.setdefault("rule_id", rule_payload.get("id"))
        if output_dir:
            persist_execution_payload(output_dir, result, artifact_prefix="spark_expectations")
        return result

    if normalized_engine == "trino":
        from trino_execution_pipeline import create_trino_execution_plan
        from trino_execution_pipeline import execute_trino_pipeline

        plan = create_trino_execution_plan(rule_payload, config=config or {})
        return execute_trino_pipeline(plan, output_dir=output_dir)

    return build_failure_envelope(
        rule_payload,
        engine_type=normalized_engine,
        failure_code="DQ_EXECUTION_NOT_IMPLEMENTED",
        failure_message=f"execution engine {normalized_engine!r} is not implemented in the rule dispatch executor",
        failure_stage="dispatch",
    )


def _result_status(payload: dict[str, Any]) -> str:
    observability = payload.get("observability_summary") if isinstance(payload.get("observability_summary"), dict) else {}
    explicit_status = payload.get("result_status") or observability.get("result")
    if isinstance(explicit_status, str) and explicit_status.strip():
        return explicit_status.strip().lower()
    result = payload.get("result")
    if isinstance(result, str) and result.strip():
        return result.strip().lower()
    if isinstance(result, dict) and isinstance(result.get("passed"), bool):
        return "passed" if result.get("passed") else "failed"
    return "passed" if payload.get("ok") else "failed"


def build_execution_report_summary(response_payload: dict[str, Any], *, output_dir: Any = None) -> dict[str, Any]:
    metrics = response_payload.get("metrics")
    return {
        "engine_type": response_payload.get("engine_type"),
        "rule_id": response_payload.get("rule_id"),
        "result": _result_status(response_payload),
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


def build_execution_report_details(response_payload: dict[str, Any], *, output_dir: Any = None) -> dict[str, Any]:
    details = {
        "source": "dq-engine-execution-worker",
        "engine_type": response_payload.get("engine_type"),
        "rule_id": response_payload.get("rule_id"),
        "result": _result_status(response_payload),
        "passed_count": response_payload.get("passed_count", 0),
        "failed_count": response_payload.get("failed_count", 0),
        "execution_metadata": response_payload.get("execution_metadata", {}),
        "quarantine_artifact": response_payload.get("quarantine_artifact", {}),
        "error_management": response_payload.get("error_management", {}),
        "observability_summary": response_payload.get("observability_summary", {}),
        "output_dir": output_dir,
    }
    if not response_payload.get("ok"):
        details.update(
            {
                "failure_code": response_payload.get("failure_code"),
                "failure_message": response_payload.get("failure_message") or response_payload.get("error"),
                "failed_check": response_payload.get("failed_check", {}),
                "failure_metrics": response_payload.get("failure_metrics", {}),
                "trace": response_payload.get("trace", {}),
            }
        )
    return details


ReportRunFn = Callable[..., None]
ReportProgressFn = Callable[..., None]
TokenProviderFactory = Callable[[], TokenProvider]
ExecutePayloadFn = Callable[..., dict[str, Any]]


async def process_engine_dispatch_message(
    config: GxWorkerConfig,
    *,
    payload: dict[str, Any],
    run_id: str,
    correlation_id: str,
    requested_by: str | None,
    report_run_fn: ReportRunFn = report_run,
    report_progress_fn: ReportProgressFn | None = None,
    token_provider_factory: TokenProviderFactory = build_token_provider,
    execute_payload_fn: ExecutePayloadFn = execute_engine_rule_payload,
) -> dict[str, Any]:
    rule_payload = payload.get("rule_payload")
    if not isinstance(rule_payload, dict):
        raise GxWorkerExecutionError(
            "Execution dispatch payload is missing rule_payload",
            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
        )

    engine_type = normalize_execution_engine(coerce_str(payload, "engine_type") or coerce_str(rule_payload, "engine_type"))
    if engine_type not in SUPPORTED_EXECUTION_ENGINES:
        raise GxWorkerExecutionError(
            f"Unsupported execution dispatch engine type: {engine_type!r}",
            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
        )

    token_provider = token_provider_factory()
    execution_started = time.perf_counter()
    output_dir = str(payload.get("output_dir")) if payload.get("output_dir") is not None else None
    
    # Initialize Kafka publisher for streaming violations
    kafka_publisher = None
    try:
        kafka_publisher = await build_kafka_publisher()
        if kafka_publisher:
            await kafka_publisher.start()
    except Exception as exc:
        logger.warning("Failed to initialize Kafka publisher: %s", exc)

    try:
        await report_run_fn(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            new_status="running",
            changed_by=requested_by,
            reason=f"Execution worker routed {engine_type} execution",
            details={"source": "dq-engine-execution-worker", "engine_type": engine_type, "rule_payload": rule_payload},
            execution_progress=build_execution_progress(
                completed_steps=1,
                total_steps=2,
                label=f"Invoking {engine_type} execution",
            ),
            metrics={"engine_type": engine_type, "stage": "started"},
            kafka_publisher=kafka_publisher,
        )

        response_payload = execute_payload_fn(
            engine_type=engine_type,
            rule_payload=rule_payload,
            output_dir=output_dir,
            config=payload.get("config") if isinstance(payload.get("config"), dict) else None,
        )
        if not isinstance(response_payload, dict):
            raise GxWorkerExecutionError(
                f"{engine_type} execution failed",
                failure_code="GX_WORKER_EXECUTION_ERROR",
            )

        report_summary = build_execution_report_summary(response_payload, output_dir=payload.get("output_dir"))
        report_details = build_execution_report_details(response_payload, output_dir=payload.get("output_dir"))
        metrics = response_payload.get("metrics") if isinstance(response_payload.get("metrics"), dict) else response_payload.get("observability_summary", {})
        
        # Extract diagnostics for violation streaming
        diagnostics = response_payload.get("diagnostics") or []
        
        status = "succeeded" if response_payload.get("ok") else "failed"
        label = f"{engine_type} execution completed" if status == "succeeded" else f"{engine_type} execution completed with failures"
        failure_code = None if status == "succeeded" else response_payload.get("failure_code") or "GX_WORKER_EXECUTION_ERROR"
        failure_message = None if status == "succeeded" else response_payload.get("failure_message") or response_payload.get("error") or f"{engine_type} execution failed"

        if report_progress_fn is not None:
            await report_progress_fn(
                config,
                token_provider,
                run_id=run_id,
                correlation_id=correlation_id,
                changed_by=requested_by,
                reason=label,
                details=report_details,
                completed_steps=2,
                total_steps=2,
                label=label,
            )

        await report_run_fn(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            new_status=status,
            changed_by=requested_by,
            reason=label,
            details=report_details,
            execution_progress=build_execution_progress(
                completed_steps=2,
                total_steps=2,
                label=label,
            ),
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            result_summary=report_summary,
            metrics=metrics,
            diagnostics=diagnostics,
            failure_code=failure_code,
            failure_message=failure_message,
            kafka_publisher=kafka_publisher,
        )

        record_duration = payload.get("record_duration")
        if callable(record_duration):
            record_duration(engine_type=engine_type, status=status, duration_ms=(time.perf_counter() - execution_started) * 1000.0)

        return response_payload
    finally:
        # Stop Kafka publisher and flush
        if kafka_publisher:
            await kafka_publisher.stop()