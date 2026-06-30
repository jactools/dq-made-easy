import logging
import os
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from dq_utils.logging_utils import configure_logging
from runtime_lowerers import build_failure_envelope
from runtime_lowerers import build_compiled_artifact_for_engine
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
