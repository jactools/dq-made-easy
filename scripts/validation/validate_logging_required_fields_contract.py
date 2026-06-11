#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

# Add the FastAPI app code to the path so we can import logging utilities and test the log output format/fields contract.
FASTAPI_ROOT = REPO_ROOT / "dq-api" / "fastapi"
sys.path.insert(0, str(FASTAPI_ROOT))

from app.core.log_event import log_event  # noqa: E402
from app.core.logging_config import _JsonFormatter  # noqa: E402
from app.core.request_context import set_correlation_id  # noqa: E402


def _assert_has_keys(payload: dict, keys: list[str]) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise AssertionError(f"Missing required log keys: {missing}")


def main() -> int:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_JsonFormatter())

    logger = logging.getLogger("governance.log.required-fields")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.INFO)

    set_correlation_id("cid-contract-001")

    context = {
        "component": "contract-test",
        "runId": "run-001",
        "suiteId": "suite-001",
        "ruleId": "rule-001",
        "dataObjectId": "obj-001",
        "dataObjectVersionId": "objv-001",
        "datasetId": "ds-001",
        "dataProductId": "dp-001",
    }
    log_event(logger, "contract.required_fields.validated", **context)

    raw = stream.getvalue().strip()
    if not raw:
        raise AssertionError("No structured log output captured")

    payload = json.loads(raw.splitlines()[-1])

    _assert_has_keys(payload, ["event", "component", "correlationId", "ts", "level"])
    _assert_has_keys(
        payload,
        [
            "runId",
            "suiteId",
            "ruleId",
            "dataObjectId",
            "dataObjectVersionId",
            "datasetId",
            "dataProductId",
        ],
    )

    if payload["correlationId"] != "cid-contract-001":
        raise AssertionError("correlationId value mismatch")

    print("OK: logging required-fields contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())