#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FASTAPI_ROOT = REPO_ROOT / "dq-api" / "fastapi"
sys.path.insert(0, str(FASTAPI_ROOT))

from app.core.log_event import log_event  # noqa: E402
from app.core.logging_config import _JsonFormatter  # noqa: E402
from app.core.request_context import set_correlation_id  # noqa: E402


def _capture_payload(event: str, **context):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_JsonFormatter())

    logger = logging.getLogger("governance.log.redaction")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.INFO)

    set_correlation_id("cid-redaction-contract")
    log_event(logger, event, **context)
    raw = stream.getvalue().strip()
    if not raw:
        raise AssertionError("No structured log output captured")
    return json.loads(raw.splitlines()[-1])


def main() -> int:
    payload = _capture_payload(
        "security.redaction.contract",
        component="governance-test",
        password="super-secret",
        token="abc.def.ghi",
        authorization="Bearer nested.value",
        nested={"api_key": "xyz"},
        rows=[{"email": "alice@example.com"}],
        raw_records=[{"id": 1, "value": "raw"}],
    )

    expected_redacted = [
        payload.get("password"),
        payload.get("token"),
        payload.get("authorization"),
        payload.get("nested", {}).get("api_key"),
        payload.get("rows"),
        payload.get("raw_records"),
    ]
    if any(value != "[REDACTED]" for value in expected_redacted):
        raise AssertionError("Redaction contract failed for one or more sensitive/raw row fields")

    print("OK: log redaction contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())