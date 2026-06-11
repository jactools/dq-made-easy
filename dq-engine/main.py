import logging
import os
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from dq_utils.logging_utils import configure_logging
from rule_translator import translate

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


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readiness")
def readiness() -> dict[str, str]:
    return {"status": "ready"}


@app.post("/compile")
def compile_rule(req: CompileRequest):
    """Translate a rule to a GX expectation without executing it against source data."""
    if not str(req.type or "").strip() or not str(req.column or "").strip():
        return {
            "ok": True,
            "rule_id": req.id,
            "skipped": True,
            "reason": "compile skipped: rule type/column not provided (expression-based rule)",
        }

    try:
        expectation = translate(req.model_dump())
        return {
            "ok": True,
            "rule_id": req.id,
            "expectation": type(expectation).__name__,
            "kwargs": expectation.to_json_dict() if hasattr(expectation, "to_json_dict") else {},
        }
    except Exception as exc:
        return {
            "ok": False,
            "rule_id": req.id,
            "error": str(exc),
        }
