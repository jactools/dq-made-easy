from __future__ import annotations

import json
import logging

from app.core.log_event import log_event
from app.core.logging_config import configure_logging
from app.core.request_context import set_correlation_id


def _last_json_line(capsys) -> dict:
    captured = capsys.readouterr()
    lines = [line for line in captured.err.splitlines() if line.strip()]
    assert lines, "No log lines captured"
    return json.loads(lines[-1])


def test_log_event_redacts_sensitive_top_level_fields(capsys) -> None:
    configure_logging("INFO")
    set_correlation_id("cid-redact-1")

    logger = logging.getLogger("tests.redaction")
    log_event(
        logger,
        "security.auth.attempt",
        component="auth-api",
        password="super-secret-password",
        token="jwt-token-value",
        authorization="Bearer abc.def.ghi",
    )

    payload = _last_json_line(capsys)
    assert payload["correlationId"] == "cid-redact-1"
    assert payload["correlation_id"] == "cid-redact-1"
    assert payload["service_name"] == "dq-api"
    assert payload["environment"] == "dev"
    assert payload["password"] == "[REDACTED]"
    assert payload["token"] == "[REDACTED]"
    assert payload["authorization"] == "[REDACTED]"


def test_log_event_redacts_nested_sensitive_fields(capsys) -> None:
    configure_logging("INFO")
    set_correlation_id("cid-redact-2")

    logger = logging.getLogger("tests.redaction.nested")
    log_event(
        logger,
        "security.payload.received",
        component="auth-api",
        payload={
            "username": "alice",
            "clientSecret": "s3cr3t",
            "nested": {
                "api_key": "abc123",
                "Authorization": "Bearer nested-token",
            },
        },
    )

    payload = _last_json_line(capsys)
    assert payload["payload"]["username"] == "alice"
    assert payload["payload"]["clientSecret"] == "[REDACTED]"
    assert payload["payload"]["nested"]["api_key"] == "[REDACTED]"
    assert payload["payload"]["nested"]["Authorization"] == "[REDACTED]"


def test_log_event_redacts_raw_payload_rows(capsys) -> None:
    configure_logging("INFO")
    set_correlation_id("cid-redact-rows")

    logger = logging.getLogger("tests.redaction.rows")
    log_event(
        logger,
        "security.rows.received",
        component="testing-api",
        rows=[{"email": "alice@example.com", "ssn": "111-22-3333"}],
        raw_records=[{"id": 1, "value": "secret-ish"}],
        safe_summary={"rowCount": 1},
    )

    payload = _last_json_line(capsys)
    assert payload["rows"] == "[REDACTED]"
    assert payload["raw_records"] == "[REDACTED]"
    assert payload["safe_summary"]["rowCount"] == 1


def test_log_event_redacts_bearer_strings_nested_in_collections(capsys) -> None:
    configure_logging("INFO")
    set_correlation_id("cid-redact-bearer")

    logger = logging.getLogger("tests.redaction.bearer")
    log_event(
        logger,
        "security.bearer.received",
        component="auth-api",
        headers=["Bearer abc.def", "x-request-id: 1"],
        auth_tuple=("Bearer nested-token", "ok"),
    )

    payload = _last_json_line(capsys)
    assert payload["headers"][0] == "[REDACTED]"
    assert payload["headers"][1] == "x-request-id: 1"
    assert payload["auth_tuple"][0] == "[REDACTED]"
    assert payload["auth_tuple"][1] == "ok"


def test_log_event_omits_correlation_id_when_not_present(capsys) -> None:
    configure_logging("INFO")
    set_correlation_id(None)

    logger = logging.getLogger("tests.redaction.no-correlation")
    log_event(logger, "system.event.without-correlation", component="core")

    payload = _last_json_line(capsys)
    assert "correlationId" not in payload
    assert "correlation_id" not in payload
