import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from dq_utils.logging_utils import configure_logging
from spark_expectations_adapter import build_error_management_plan
from spark_expectations_adapter import execute_spark_expectations_rule
from spark_expectations_adapter import lower_rule_to_spark_expectations

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

    if resolved_engine_type == "spark_expectations":
        lowered_rule = lower_rule_to_spark_expectations(rule)
        error_plan = build_error_management_plan(
            (
                {"row_id": row_id, "reason": f"synthetic-failure-{row_id}"}
                for row_id in range(int(rule.get("params", {}).get("synthetic_error_count", 0)))
            ),
            chunk_size=int(rule.get("params", {}).get("error_chunk_size", 10_000)),
            max_samples=int(rule.get("params", {}).get("error_sample_size", 20)),
        )
        return {
            "ok": True,
            "rule_id": rule.get("id"),
            "engine_type": "spark_expectations",
            "lowered_rule": lowered_rule,
            "compiled_artifact": {
                "engine_type": "spark_expectations",
                "engine_target": "pyspark",
                "rule": lowered_rule,
                "error_management": error_plan,
            },
        }

    from rule_translator import translate

    expectation = translate(rule)
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

    try:
        engine_type = req.engine_type or os.getenv("DQ_ENGINE_TYPE", "gx")
        resolved_engine_type = (engine_type or "gx").strip().lower()
        if resolved_engine_type != "spark_expectations":
            raise ValueError(f"unsupported engine type for execution: {resolved_engine_type!r}")

        compiled = compile_rule_payload(req.model_dump(), engine_type=resolved_engine_type)
        if not compiled.get("ok"):
            raise RuntimeError(compiled.get("error", "compilation failed"))

        adapter_summary = execute_spark_expectations_rule(req)
        error_management = adapter_summary.get("error_management", {})

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
            "observability_summary": {
                "engine_type": "spark_expectations",
                "result": adapter_summary.get("result", "passed"),
                "passed_count": adapter_summary.get("passed_count", 0),
                "failed_count": adapter_summary.get("failed_count", 0),
                "storage_kind": (adapter_summary.get("quarantine_artifact") or {}).get("storage_kind"),
                "storage_uri": (adapter_summary.get("quarantine_artifact") or {}).get("storage_uri"),
            },
        }

        target_dir = Path(req.output_dir) if req.output_dir else None
        if target_dir is not None:
            target_dir.mkdir(parents=True, exist_ok=True)
            output_path = target_dir / "spark_expectations_execution.json"
            errors_path = target_dir / "spark_expectations_errors.json"
            output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
            errors_payload = {
                "engine_type": "spark_expectations",
                "rule_id": req.id,
                "error_count": summary.get("failed_count", 0),
                "storage_strategy": error_management.get("storage_strategy", "chunked"),
                "sampled_error_rows": error_management.get("sampled_error_rows", []),
                "execution_metadata": summary.get("execution_metadata", {}),
                "quarantine_artifact": summary.get("quarantine_artifact", {}),
                "observability_summary": summary.get("observability_summary", {}),
            }
            errors_path.write_text(json.dumps(errors_payload, indent=2, sort_keys=True), encoding="utf-8")

        return summary
    except Exception as exc:
        return {
            "ok": False,
            "rule_id": req.id,
            "error": str(exc),
        }
