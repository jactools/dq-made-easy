import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from dq_utils.logging_utils import configure_logging
from runtime_lowerers import build_failure_envelope
from runtime_lowerers import build_compiled_artifact_for_engine
from spark_expectations_adapter import execute_spark_expectations_rule
from spark_expectations_metrics import render_prometheus_metrics

LOG_LEVEL = os.getenv("DQ_LOG_LEVEL", "INFO")

configure_logging(LOG_LEVEL)
logging.getLogger(__name__)

app = FastAPI(title="DQ Execution Engine")


class CompileRequest(BaseModel):
    id: int
    table: str
    column: str | None = None
    type: str
    params: dict[str, Any] | None = None
    engine_type: str | None = None


class ExecuteRequest(BaseModel):
    id: int
    table: str
    column: str | None = None
    type: str
    params: dict[str, Any] | None = None
    output_dir: str | None = None
    engine_type: str | None = None


def compile_rule_payload(rule: dict[str, Any], *, engine_type: str | None = None) -> dict[str, Any]:
    resolved_engine_type = (engine_type or "gx").strip().lower()

    if resolved_engine_type in {"gx", "soda", "spark_expectations", "trino"}:
        compiled = build_compiled_artifact_for_engine(rule, engine_type=resolved_engine_type)
        if not compiled.get("ok"):
            return compiled
        return compiled

    from rule_translator import translate

    try:
        expectation = translate(rule)
    except Exception as exc:
        return build_failure_envelope(
            rule,
            engine_type=resolved_engine_type,
            failure_code="DQ_LOWERER_FAILURE",
            failure_message=str(exc),
            exception=exc,
            failure_stage="compile",
        )

    return {
        "ok": True,
        "rule_id": rule.get("id"),
        "expectation": type(expectation).__name__,
        "kwargs": expectation.to_json_dict() if hasattr(expectation, "to_json_dict") else {},
    }


def _extract_failure_code(exc: Exception) -> str:
    failure_code = getattr(exc, "failure_code", None)
    if isinstance(failure_code, str) and failure_code.strip():
        return failure_code.strip()

    message = str(exc).strip().lower()
    if isinstance(exc, ValueError) and "unsupported engine type" in message:
        return "DQ_EXECUTION_UNSUPPORTED_ENGINE"
    return "DQ_EXECUTION_ERROR"


def _persist_execute_payload(target_dir: Path, payload: dict[str, Any]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / "spark_expectations_execution.json"
    errors_path = target_dir / "spark_expectations_errors.json"

    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    errors_payload = {
        "engine_type": payload.get("engine_type", "spark_expectations"),
        "rule_id": payload.get("rule_id"),
        "error_count": payload.get("failed_count", 0),
        "storage_strategy": (payload.get("error_management") or {}).get("storage_strategy", "chunked"),
        "sampled_error_rows": (payload.get("error_management") or {}).get("sampled_error_rows", []),
        "execution_metadata": payload.get("execution_metadata", {}),
        "quarantine_artifact": payload.get("quarantine_artifact", {}),
        "observability_summary": payload.get("observability_summary", {}),
        "failure_code": payload.get("failure_code"),
        "failure_message": payload.get("failure_message"),
        "failed_check": payload.get("failed_check", {}),
        "failure_metrics": payload.get("failure_metrics", {}),
        "trace": payload.get("trace", {}),
    }
    errors_path.write_text(json.dumps(errors_payload, indent=2, sort_keys=True), encoding="utf-8")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readiness")
def readiness() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/metrics")
def metrics() -> str:
    return render_prometheus_metrics()


@app.post("/compile")
def compile_rule(req: CompileRequest):
    """Translate a rule to a runnable expectation artifact without executing it against source data."""
    if not str(req.type or "").strip() or not str(req.column or "").strip():
        return {
            "ok": True,
            "rule_id": req.id,
            "skipped": True,
            "reason": "compile skipped: rule type/column not provided (expression-based rule)",
        }

    try:
        engine_type = req.engine_type or os.getenv("DQ_ENGINE_TYPE", "gx")
        return compile_rule_payload(req.model_dump(), engine_type=engine_type)
    except Exception as exc:
        return {
            "ok": False,
            "rule_id": req.id,
            "error": str(exc),
        }


@app.post("/execute")
def execute_rule(req: ExecuteRequest):
    """Compile and execute a rule payload while persisting aggregate and error artifacts."""
    if not str(req.type or "").strip() or not str(req.column or "").strip():
        return {
            "ok": True,
            "rule_id": req.id,
            "skipped": True,
            "reason": "execution skipped: rule type/column not provided (expression-based rule)",
        }

    compiled: dict[str, Any] | None = None
    try:
        engine_type = req.engine_type or os.getenv("DQ_ENGINE_TYPE", "gx")
        resolved_engine_type = (engine_type or "gx").strip().lower()
        if resolved_engine_type != "spark_expectations":
            raise ValueError(f"unsupported engine type for execution: {resolved_engine_type!r}")

        compiled = compile_rule_payload(req.model_dump(), engine_type=resolved_engine_type)
        if not compiled.get("ok"):
            if req.output_dir:
                _persist_execute_payload(Path(req.output_dir), compiled)
            return compiled

        adapter_summary = execute_spark_expectations_rule(req)
        error_management = adapter_summary.get("error_management", {})
        adapter_observability = dict(adapter_summary.get("observability_summary", {}) or {})
        if not adapter_observability:
            adapter_observability = {
                "engine_type": "spark_expectations",
                "result": adapter_summary.get("result", "passed"),
                "passed_count": adapter_summary.get("passed_count", 0),
                "failed_count": adapter_summary.get("failed_count", 0),
                "rule_family": "row",
                "duration_ms": (adapter_summary.get("execution_metadata") or {}).get("duration_ms"),
                "storage_kind": (adapter_summary.get("quarantine_artifact") or {}).get("storage_kind"),
                "storage_uri": (adapter_summary.get("quarantine_artifact") or {}).get("storage_uri"),
            }
        else:
            adapter_observability.setdefault("engine_type", "spark_expectations")
            adapter_observability.setdefault("result", adapter_summary.get("result", "passed"))
            adapter_observability.setdefault("passed_count", adapter_summary.get("passed_count", 0))
            adapter_observability.setdefault("failed_count", adapter_summary.get("failed_count", 0))
            adapter_observability.setdefault("duration_ms", (adapter_summary.get("execution_metadata") or {}).get("duration_ms"))
            adapter_observability.setdefault("storage_kind", (adapter_summary.get("quarantine_artifact") or {}).get("storage_kind"))
            adapter_observability.setdefault("storage_uri", (adapter_summary.get("quarantine_artifact") or {}).get("storage_uri"))

        summary = {
            "ok": True,
            "engine_type": "spark_expectations",
            "rule_id": req.id,
            "result": adapter_summary.get("result", "passed"),
            "passed_count": adapter_summary.get("passed_count", 0),
            "failed_count": adapter_summary.get("failed_count", 0),
            "error_management": error_management,
            "execution_metadata": adapter_summary.get("execution_metadata", {}),
            "quarantine_artifact": adapter_summary.get("quarantine_artifact", {}),
            "compiled_artifact": compiled.get("compiled_artifact", {}),
            "metrics": adapter_summary.get("metrics", adapter_observability),
            "observability_summary": adapter_observability,
        }

        if req.output_dir:
            _persist_execute_payload(Path(req.output_dir), summary)

        return summary
    except Exception as exc:
        failure_summary = build_failure_envelope(
            req.model_dump(),
            engine_type=(req.engine_type or os.getenv("DQ_ENGINE_TYPE", "spark_expectations")).strip().lower() or "spark_expectations",
            failure_code=_extract_failure_code(exc),
            failure_message=str(exc),
            failure_stage="execute",
            exception=exc,
            compiled_artifact=(compiled or {}).get("compiled_artifact", {}),
        )

        if req.output_dir:
            _persist_execute_payload(Path(req.output_dir), failure_summary)

        return failure_summary
