#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import secrets
import sys
import time
from datetime import UTC, datetime
from typing import Any

import requests
import redis

WORKFLOW_LABEL = "validate_gx_worker_smoke"


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _optional_env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _pick(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def _run_state_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    execution_progress = _pick(payload, "executionProgress", "execution_progress", default=None)
    status_history_payload = _pick(
        payload,
        "statusHistory",
        "status_history",
        "lastStatusHistory",
        "last_status_history",
        default=[],
    )
    if isinstance(status_history_payload, dict):
        status_history = [status_history_payload]
    elif isinstance(status_history_payload, list):
        status_history = [item for item in status_history_payload if isinstance(item, dict)]
    else:
        status_history = []

    last_status_history = status_history[-1] if status_history else None
    status = str(_pick(payload, "status", default="")).strip().lower()
    if isinstance(last_status_history, dict):
        history_status = str(_pick(last_status_history, "toStatus", "to_status", default="")).strip().lower()
        if history_status:
            status = history_status

    return {
        "status": status,
        "updatedAt": _pick(payload, "updatedAt", "updated_at", default=None),
        "completedAt": _pick(payload, "completedAt", "completed_at", default=None),
        "failureCode": _pick(payload, "failureCode", "failure_code", default=None),
        "failureMessage": _pick(payload, "failureMessage", "failure_message", default=None),
        "executionProgress": execution_progress,
        "lastStatusHistory": last_status_history,
        "statusDetails": _pick(payload, "statusDetails", "status_details", default=None),
    }


def _summarize_execution_progress(execution_progress: Any) -> Any:
    if isinstance(execution_progress, dict):
        return {
            "percent": _pick(execution_progress, "percent", default=None),
            "label": _pick(execution_progress, "label", default=None),
            "updatedAt": _pick(execution_progress, "updatedAt", "updated_at", default=None),
        }
    return execution_progress


def _json_payload(response: requests.Response) -> Any:
    if not response.text.strip():
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"Expected JSON response from {response.request.method} {response.url}: {response.text}") from exc


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    token: str | None = None,
    cookie_header: str | None = None,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    expected_statuses: tuple[int, ...] = (200,),
) -> Any:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if cookie_header:
        headers["Cookie"] = cookie_header
    if body is not None:
        headers["Content-Type"] = "application/json"

    response = session.request(method, url, params=params, json=body, headers=headers, timeout=60)
    if response.status_code not in expected_statuses:
        payload = response.text.strip()
        raise RuntimeError(
            f"{method} {url} returned HTTP {response.status_code}: {payload or '<empty>'}"
        )
    return _json_payload(response)


def _mint_access_token(session: requests.Session) -> str:
    username = _require_env("KEYCLOAK_JACCLOUD_USERNAME")
    password = _require_env("KEYCLOAK_JACCLOUD_PASSWORD")
    return _mint_access_token_for_credentials(session, username=username, password=password)


def _mint_access_token_for_credentials(session: requests.Session, *, username: str, password: str) -> str:
    sso_enabled = _optional_env("SSO_ENABLED").lower() == "true"
    if sso_enabled:
        issuer_url = _require_env("SSO_PUBLIC_ISSUER_URL")
        token_url = f"{issuer_url.rstrip('/')}/protocol/openid-connect/token"
    else:
        keycloak_public_url = _require_env("KEYCLOAK_PUBLIC_URL")
        keycloak_realm = _require_env("KEYCLOAK_REALM")
        token_url = f"{keycloak_public_url.rstrip('/')}/realms/{keycloak_realm}/protocol/openid-connect/token"

    client_id = _require_env("KEYCLOAK_CLIENT_ID")

    response = session.post(
        token_url,
        data={
            "grant_type": "password",
            "client_id": client_id,
            "username": username,
            "password": password,
        },
        timeout=60,
        verify=session.verify,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Keycloak token request failed with HTTP {response.status_code}: {response.text.strip() or '<empty>'}")

    payload = _json_payload(response)
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Keycloak token response did not include access_token")
    return token


def _create_rule_approval(session: requests.Session, kong_url: str, token: str, *, rule_id: str, workspace_id: str) -> str:
    response = _request_json(
        session,
        "POST",
        _url(kong_url, "/rulebuilder/v1/approvals"),
        token=token,
        body={"rule_id": rule_id, "workspace_id": workspace_id, "status": "pending"},
        expected_statuses=(200,),
    )
    approval_id = str(_pick(response, "id", default="")).strip()
    if not approval_id:
        raise RuntimeError(f"Approval create response missing id: {response}")
    return approval_id


def _approve_rule_approval(session: requests.Session, kong_url: str, token: str, *, approval_id: str) -> None:
    _request_json(
        session,
        "PUT",
        _url(kong_url, f"/rulebuilder/v1/approvals/{approval_id}"),
        token=token,
        body={"status": "approved"},
        expected_statuses=(200,),
    )


def _grafana_login(session: requests.Session) -> None:
    grafana_url = _require_env("GRAFANA_PUBLIC_URL")
    grafana_admin_user = _require_env("GRAFANA_ADMIN_USER")
    grafana_admin_password = _require_env("GRAFANA_ADMIN_PASSWORD")

    response = session.post(
        f"{grafana_url.rstrip('/')}/login",
        json={"user": grafana_admin_user, "password": grafana_admin_password},
        timeout=60,
        verify=session.verify,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Grafana login failed with HTTP {response.status_code}: {response.text.strip() or '<empty>'}")
    payload = _json_payload(response)
    if not isinstance(payload, dict) or payload.get("message") != "Logged in":
        raise RuntimeError(f"Grafana login did not report success: {payload}")

    health_response = session.get(f"{grafana_url.rstrip('/')}/api/user", timeout=60, verify=session.verify)
    if health_response.status_code != 200:
        raise RuntimeError(f"Grafana session check failed with HTTP {health_response.status_code}: {health_response.text.strip() or '<empty>'}")


def _prom_query_value(session: requests.Session, grafana_url: str, prom_uid: str, query: str) -> float:
    response = session.get(
        f"{grafana_url.rstrip('/')}/api/datasources/proxy/uid/{prom_uid}/api/v1/query",
        params={"query": query},
        timeout=60,
        verify=session.verify,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Prometheus query failed with HTTP {response.status_code}: {response.text.strip() or '<empty>'}")

    payload = _json_payload(response)
    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise RuntimeError(f"Unexpected Prometheus response for query {query!r}: {payload}")

    result = payload.get("data", {}).get("result", [])
    if not result:
        return 0.0
    value = result[0].get("value", [None, "0"])[1]
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Prometheus query {query!r} returned a non-numeric value: {value!r}") from exc


def _wait_for_prom_metric(session: requests.Session, grafana_url: str, prom_uid: str, query: str, *, minimum: float, timeout_seconds: int = 120) -> float:
    deadline = time.time() + timeout_seconds
    last_value = 0.0
    while True:
        last_value = _prom_query_value(session, grafana_url, prom_uid, query)
        if last_value >= minimum:
            return last_value
        if time.time() >= deadline:
            raise RuntimeError(f"Timed out waiting for Prometheus metric {query!r} to reach {minimum}; last value={last_value}")
        time.sleep(2)


def _url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def _choose_first_dov(session: requests.Session, kong_url: str, token: str) -> dict[str, Any]:
    payload = _request_json(
        session,
        "GET",
        _url(kong_url, "/data-catalog/v1/data-object-versions"),
        token=token,
        params={"page": 1, "limit": 25},
    )
    rows = payload.get("data") or []
    if not rows:
        raise RuntimeError("data-catalog returned no data object versions")
    return rows[0]


def _discover_primary_attribute(session: requests.Session, kong_url: str, token: str, data_object_version_id: str) -> str:
    payload = _request_json(
        session,
        "GET",
        _url(kong_url, "/data-catalog/v1/attributes-catalog"),
        token=token,
        params={"versionId": data_object_version_id, "page": 1, "limit": 1},
    )
    rows = payload.get("data") or []
    if not rows:
        raise RuntimeError(f"No attributes found for data_object_version_id={data_object_version_id}")

    attribute_name = str(_pick(rows[0], "name", "attribute_name", "attributeName", default="")).strip()
    if not attribute_name:
        raise RuntimeError(f"Attribute payload missing name field: {rows[0]}")
    return attribute_name


def _discover_rule(session: requests.Session, kong_url: str, token: str) -> str:
    payload = _request_json(
        session,
        "GET",
        _url(kong_url, "/rulebuilder/v1/rules"),
        token=token,
        params={"page": 1, "limit": 1},
    )
    rows = payload.get("data") or []
    if not rows:
        raise RuntimeError("rulebuilder returned no rules")

    rule_id = str(_pick(rows[0], "id", "rule_id", "ruleId", default="")).strip()
    if not rule_id:
        raise RuntimeError(f"Rule payload missing id field: {rows[0]}")
    return rule_id


def _create_impossible_rule(
    session: requests.Session,
    kong_url: str,
    token: str,
    *,
    data_object_id: str,
) -> tuple[str, str]:
    rule_name = f"GX smoke impossible {secrets.token_hex(6)}"
    payload = {
        "name": rule_name,
        "description": "Temporary GX smoke rule that must fail on every run",
        "dimension": "validation",
        "active": False,
        "workspace": "validation-smoke",
        "dsl": {
            "schema_version": "1.0.0",
            "source": {
                "kind": "filter_expression",
                "expression": "customer_id = '__validation_expected_failure__'",
            },
        },
    }
    response = _request_json(
        session,
        "POST",
        _url(kong_url, "/rulebuilder/v1/rules"),
        token=token,
        body=payload,
        expected_statuses=(200,),
    )
    rule_id = str(_pick(response, "id", "rule_id", default="")).strip()
    if not rule_id:
        raise RuntimeError(f"Rule create response missing rule id: {response}")
    return rule_id, rule_name


def _activate_rule_with_autopublish(
    session: requests.Session,
    kong_url: str,
    token: str,
    *,
    rule_id: str,
    data_object_id: str,
    data_object_version_id: str,
) -> None:
    response = _request_json(
        session,
        "POST",
        _url(kong_url, f"/rulebuilder/v1/rules/{rule_id}/activate"),
        token=token,
        params={},
        body={
            "data_object_id": data_object_id,
            "data_object_version_ids": [data_object_version_id],
            "suite_version": 1,
        },
        expected_statuses=(200,),
    )
    if not isinstance(response, dict):
        raise RuntimeError(f"Rule activation returned unexpected payload: {response}")


def _find_run_by_correlation_id(
    session: requests.Session,
    kong_url: str,
    token: str,
    *,
    correlation_id: str,
) -> str:
    timeout_seconds = int(_optional_env("DQ_SMOKE_GX_TIMEOUT_SECONDS") or "900")
    deadline = time.time() + timeout_seconds
    while True:
        runs = _request_json(
            session,
            "GET",
            _url(kong_url, "/rulebuilder/v1/gx/runs"),
            token=token,
            params={"lookbackAmount": 720, "lookbackUnit": "hours", "limit": 100},
        )
        if isinstance(runs, list):
            for item in runs:
                if not isinstance(item, dict):
                    continue
                item_correlation_id = str(item.get("correlationId") or item.get("correlation_id") or "").strip()
                if item_correlation_id != correlation_id:
                    continue
                run_id = str(item.get("id") or "").strip()
                if run_id:
                    return run_id
        if time.time() >= deadline:
            raise RuntimeError(f"Timed out waiting to resolve GX run for correlationId={correlation_id}")
        time.sleep(2)


def _seed_failing_suite(
    session: requests.Session,
    kong_url: str,
    token: str,
    *,
    suite_id: str,
    suite_version: int,
    data_object_id: str,
    data_object_version_id: str,
    rule_id: str,
    attribute_name: str,
) -> tuple[str, int]:
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    suite_envelope = {
        "suite_id": suite_id,
        "suite_version": suite_version,
        "artifact_version": "v1",
        "assignment_scope": {"data_object_id": data_object_id},
        "resolved_execution_scope": {"data_object_version_ids": [data_object_version_id]},
        "gx_suite": {
            "expectation_suite_name": f"failure_{data_object_version_id}",
            "expectations": [
                {
                    "expectation_type": "expect_table_row_count_to_be_between",
                    "kwargs": {
                        "min_value": 1,
                    },
                }
            ],
            "meta": {},
        },
        "compiled_from": {
            "rule_ids": [rule_id],
            "compiler_version": "validation",
            "generated_at": generated_at,
        },
        "execution_hints": {
            "recommended_engine": "pyspark",
            "primary_key_fields": [],
        },
        "execution_contract": {
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "traceability": {
                "rule_id": rule_id,
                "rule_version_id": f"rulever-{rule_id}",
                "gx_suite_id": suite_id,
                "gx_suite_version": suite_version,
                "data_object_version_id": data_object_version_id,
            },
        },
    }

    response = session.post(
        _url(kong_url, "/rulebuilder/v1/gx/suites?status=active&sourcePipeline=validation"),
        headers={"Authorization": f"Bearer {token}"},
        json=suite_envelope,
        timeout=60,
        verify=session.verify,
    )
    if response.status_code in {200, 201}:
        payload = _json_payload(response)
        saved_suite_id = str(_pick(payload, "suiteId", "suite_id", default=suite_id)).strip()
        saved_suite_version = int(_pick(payload, "suiteVersion", "suite_version", default=suite_version) or suite_version)
        return saved_suite_id, saved_suite_version
    if response.status_code == 409:
        reuse = session.get(
            _url(kong_url, f"/rulebuilder/v1/gx/suites/{suite_id}"),
            headers={"Authorization": f"Bearer {token}"},
            params={"status": "active"},
            timeout=60,
            verify=session.verify,
        )
        if reuse.status_code != 200:
            raise RuntimeError(f"Failed to reuse suite {suite_id} after 409: {reuse.text.strip() or '<empty>'}")
        payload = _json_payload(reuse)
        saved_suite_id = str(_pick(payload, "suiteId", "suite_id", default=suite_id)).strip()
        saved_suite_version = int(_pick(payload, "suiteVersion", "suite_version", default=suite_version) or suite_version)
        return saved_suite_id, saved_suite_version

    raise RuntimeError(f"Failed to seed GX suite {suite_id}: HTTP {response.status_code}: {response.text.strip() or '<empty>'}")


def _create_materialization(session: requests.Session, kong_url: str, token: str, *, data_object_version_id: str) -> tuple[str, str]:
    sample_count = int(_optional_env("DQ_SMOKE_SAMPLE_COUNT") or "1000")
    output_format = _optional_env("DQ_SMOKE_OUTPUT_FORMAT") or "parquet"
    refresh_value = _optional_env("DQ_SMOKE_REFRESH") or "false"
    refresh = refresh_value.lower() == "true"

    response = _request_json(
        session,
        "POST",
        _url(kong_url, "/rulebuilder/v1/test-data/materializations"),
        token=token,
        body={
            "data_object_version_id": data_object_version_id,
            "sample_count": sample_count,
            "output_format": output_format,
            "refresh": refresh,
        },
        expected_statuses=(200, 202),
    )
    request_id = str(_pick(response, "request_id", "requestId", default="")).strip()
    if not request_id:
        raise RuntimeError(f"Materialization response missing request_id: {response}")

    timeout_seconds = int(_optional_env("DQ_SMOKE_MATERIALIZATION_TIMEOUT_SECONDS") or "180")
    deadline = time.time() + timeout_seconds
    while True:
        current = _request_json(
            session,
            "GET",
            _url(kong_url, f"/rulebuilder/v1/test-data/materializations/{request_id}"),
            token=token,
        )
        status = str(_pick(current, "status", default="")).strip()
        if status == "completed":
            output_uri = str(_pick(current, "output_uri", "result.output_uri", default="")).strip()
            output_format_value = str(_pick(current, "output_format", "result.output_format", default="")).strip()
            if not output_uri or not output_format_value:
                raise RuntimeError(f"Materialization completed but output_uri/output_format missing: {current}")
            return output_uri, output_format_value
        if status == "failed":
            raise RuntimeError(f"Materialization failed: {current}")
        if time.time() >= deadline:
            raise RuntimeError(f"Timed out waiting for materialization {request_id}: last status={status}")
        time.sleep(2)


def _enqueue_failure_run(
    session: requests.Session,
    kong_url: str,
    token: str,
    *,
    data_object_version_id: str,
    output_uri: str,
    output_format: str,
) -> str:
    response = _request_json(
        session,
        "POST",
        _url(kong_url, "/rulebuilder/v1/gx/runs/adhoc"),
        token=token,
        body={
            "data_object_version_id": data_object_version_id,
            "target_data_object_version_ids": [data_object_version_id],
            "source_override_uri": output_uri,
            "source_override_format": output_format,
        },
        expected_statuses=(200, 202),
    )
    run_id = str(_pick(response[0] if isinstance(response, list) and response else response, "run_id", "runId", default="")).strip()
    if not run_id:
        raise RuntimeError(f"Ad-hoc run response missing run_id: {response}")
    return run_id


def _wait_for_run_terminal(
    session: requests.Session,
    kong_url: str,
    token: str,
    *,
    run_id: str,
) -> dict[str, Any]:
    timeout_seconds = int(_optional_env("DQ_SMOKE_GX_TIMEOUT_SECONDS") or "300")
    deadline = time.time() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while True:
        response = session.get(
            _url(kong_url, f"/rulebuilder/v1/gx/runs/{run_id}"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
            verify=session.verify,
        )
        if response.status_code == 401:
            raise RuntimeError("GX run poll returned 401; the helper does not refresh bearer tokens mid-run")
        if response.status_code != 200:
            raise RuntimeError(f"GX run poll failed with HTTP {response.status_code}: {response.text.strip() or '<empty>'}")

        payload = _json_payload(response)
        if not isinstance(payload, dict):
            raise RuntimeError(f"GX run poll returned unexpected payload: {payload}")
        last_payload = payload
        snapshot = _run_state_snapshot(payload)
        status = str(snapshot["status"]).strip().lower()
        if status in {"succeeded", "failed", "cancelled"}:
            return payload
        if time.time() >= deadline:
            progress_summary = _summarize_execution_progress(snapshot["executionProgress"])
            raise RuntimeError(
                f"Timed out waiting for GX run {run_id}; "
                f"last_state={{"
                f"status={status!r}, "
                f"updatedAt={snapshot['updatedAt']!r}, "
                f"completedAt={snapshot['completedAt']!r}, "
                f"failureCode={snapshot['failureCode']!r}, "
                f"failureMessage={snapshot['failureMessage']!r}, "
                f"executionProgress={progress_summary!r}, "
                f"lastStatusHistory={snapshot['lastStatusHistory']!r}, "
                f"statusDetails={snapshot['statusDetails']!r}"
                f"}}"
            )
        time.sleep(2)


def _wait_for_run_started(
    session: requests.Session,
    kong_url: str,
    token: str,
    redis_url: str,
    queue_key: str,
    processing_queue_key: str,
    heartbeat_key: str,
    *,
    run_id: str,
) -> dict[str, Any]:
    timeout_seconds = int(_optional_env("DQ_SMOKE_GX_START_TIMEOUT_SECONDS") or "120")
    deadline = time.time() + timeout_seconds
    while True:
        response = session.get(
            _url(kong_url, f"/rulebuilder/v1/gx/runs/{run_id}"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
            verify=session.verify,
        )
        if response.status_code == 401:
            raise RuntimeError("GX run poll returned 401; the helper does not refresh bearer tokens mid-run")
        if response.status_code != 200:
            raise RuntimeError(f"GX run poll failed with HTTP {response.status_code}: {response.text.strip() or '<empty>'}")

        payload = _json_payload(response)
        if not isinstance(payload, dict):
            raise RuntimeError(f"GX run poll returned unexpected payload: {payload}")

        snapshot = _run_state_snapshot(payload)
        status = str(snapshot["status"]).strip().lower()
        worker_status = _fetch_run_worker_status(
            redis_url,
            queue_key,
            processing_queue_key,
            heartbeat_key,
            queue_message_id=run_id,
        )
        dispatch_queue = worker_status["dispatch_queue"]
        processing_queue = worker_status["processing_queue"]
        heartbeat = worker_status["worker_heartbeat"]
        if status != "pending":
            return payload
        if time.time() >= deadline:
            progress_summary = _summarize_execution_progress(snapshot["executionProgress"])
            raise RuntimeError(
                f"Timed out waiting for GX run {run_id} to leave pending after dequeuing; "
                f"last_state={{"
                f"status={status!r}, "
                f"updatedAt={snapshot['updatedAt']!r}, "
                f"completedAt={snapshot['completedAt']!r}, "
                f"failureCode={snapshot['failureCode']!r}, "
                f"failureMessage={snapshot['failureMessage']!r}, "
                f"executionProgress={progress_summary!r}, "
                f"lastStatusHistory={snapshot['lastStatusHistory']!r}, "
                f"statusDetails={snapshot['statusDetails']!r}, "
                f"dispatchQueue={dispatch_queue!r}, "
                f"processingQueue={processing_queue!r}, "
                f"workerHeartbeat={heartbeat!r}"
                f"}}"
            )
        time.sleep(2)


def _resolve_execution_redis_url() -> str:
    redis_host_port = _require_env("REDIS_HOST_PORT")
    return f"redis://127.0.0.1:{redis_host_port}/0"


def _resolve_execution_queue_key() -> str:
    return _require_env("GX_EXECUTION_QUEUE_KEY")


def _resolve_execution_processing_queue_key(queue_key: str) -> str:
    configured = _optional_env("GX_EXECUTION_PROCESSING_QUEUE_KEY")
    if configured:
        return configured
    return f"{queue_key}:processing"


def _resolve_execution_worker_heartbeat_key(queue_key: str) -> str:
    configured = _optional_env("GX_EXECUTION_WORKER_HEARTBEAT_KEY")
    if configured:
        return configured
    return f"{queue_key}:worker-heartbeat"


def _queue_message_index(payloads: list[str], queue_message_id: str) -> int | None:
    target = str(queue_message_id or "").strip()
    if not target:
        return None

    for index, raw_payload in enumerate(payloads):
        if not raw_payload:
            continue
        try:
            parsed = json.loads(raw_payload)
        except ValueError:
            continue
        if not isinstance(parsed, dict):
            continue
        candidate = str(
            _pick(
                parsed,
                "queue_message_id",
                "queueMessageId",
                "run_id",
                "runId",
                default="",
            )
        ).strip()
        if candidate == target:
            return index
    return None


def _fetch_run_queue_status(
    redis_url: str,
    queue_key: str,
    *,
    queue_message_id: str,
    scan_limit: int = 500,
) -> dict[str, Any]:
    client = redis.Redis.from_url(redis_url, decode_responses=True)
    try:
        queue_length = int(client.llen(queue_key))
        if queue_length <= 0:
            payloads: list[str] = []
        else:
            depth = min(queue_length, max(int(scan_limit), 1))
            payloads = list(client.lrange(queue_key, 0, depth - 1) or [])
    finally:
        close_method = getattr(client, "close", None)
        if callable(close_method):
            close_method()

    index_from_head = _queue_message_index(payloads, queue_message_id)
    found = index_from_head is not None
    index_from_tail = max(queue_length - 1 - int(index_from_head), 0) if found else None
    return {
        "queue_key": queue_key,
        "queue_length": queue_length,
        "inspected_depth": len(payloads),
        "found": found,
        "index_from_head": index_from_head,
        "index_from_tail": index_from_tail,
    }


def _fetch_worker_heartbeat_status(redis_url: str, heartbeat_key: str) -> dict[str, Any]:
    client = redis.Redis.from_url(redis_url, decode_responses=True)
    try:
        heartbeat_payload = client.get(heartbeat_key)
    finally:
        close_method = getattr(client, "close", None)
        if callable(close_method):
            close_method()

    heartbeat_value = str(heartbeat_payload or "").strip()
    return {
        "heartbeat_key": heartbeat_key,
        "present": bool(heartbeat_value),
        "payload": heartbeat_payload,
    }


def _fetch_run_worker_status(
    redis_url: str,
    queue_key: str,
    processing_queue_key: str,
    heartbeat_key: str,
    *,
    queue_message_id: str,
) -> dict[str, Any]:
    dispatch_queue = _fetch_run_queue_status(
        redis_url,
        queue_key,
        queue_message_id=queue_message_id,
    )
    processing_queue = _fetch_run_queue_status(
        redis_url,
        processing_queue_key,
        queue_message_id=queue_message_id,
    )
    heartbeat = _fetch_worker_heartbeat_status(redis_url, heartbeat_key)
    return {
        "dispatch_queue": dispatch_queue,
        "processing_queue": processing_queue,
        "worker_heartbeat": heartbeat,
    }


def _wait_for_run_dequeue(
    redis_url: str,
    queue_key: str,
    *,
    queue_message_id: str,
) -> dict[str, Any]:
    timeout_seconds = int(_optional_env("DQ_SMOKE_GX_QUEUE_TIMEOUT_SECONDS") or "180")
    deadline = time.time() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while True:
        payload = _fetch_run_queue_status(
            redis_url,
            queue_key,
            queue_message_id=queue_message_id,
        )
        last_payload = payload
        found = bool(_pick(payload, "found", default=False))
        if not found:
            return payload
        if time.time() >= deadline:
            raise RuntimeError(
                f"Timed out waiting for GX run {queue_message_id} to leave the dispatch queue; last queue status={last_payload}"
            )
        time.sleep(2)


def _describe_queue_state(queue_status: dict[str, Any]) -> str:
    if bool(_pick(queue_status, "found", default=False)):
        return "run is still in the queue"
    return "run is no longer in the queue"


def _fetch_exception_analytics(
    session: requests.Session,
    kong_url: str,
    token: str,
    *,
    data_object_version_id: str,
) -> dict[str, Any]:
    response = _request_json(
        session,
        "GET",
        _url(kong_url, "/rulebuilder/v1/gx/exception-analytics"),
        token=token,
        params={
            "lookbackAmount": 24,
            "lookbackUnit": "hours",
            "dataObjectVersionId": data_object_version_id,
        },
    )
    if not isinstance(response, dict):
        raise RuntimeError(f"Exception analytics returned unexpected payload: {response}")
    return response


def _find_prometheus_uid(session: requests.Session, grafana_url: str) -> str:
    response = session.get(
        f"{grafana_url.rstrip('/')}/api/datasources/name/Prometheus",
        timeout=60,
        verify=session.verify,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Grafana Prometheus datasource lookup failed with HTTP {response.status_code}: {response.text.strip() or '<empty>'}")
    payload = _json_payload(response)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected Grafana datasource payload: {payload}")
    uid = str(_pick(payload, "uid", default="")).strip()
    if not uid:
        raise RuntimeError(f"Grafana Prometheus datasource response missing uid: {payload}")
    return uid


def _main() -> int:
    kong_url = _require_env("KONG_PUBLIC_URL")
    grafana_url = _require_env("GRAFANA_PUBLIC_URL")
    grafana_admin_user = _require_env("GRAFANA_ADMIN_USER")
    grafana_admin_password = _require_env("GRAFANA_ADMIN_PASSWORD")
    curl_ca_bundle = _optional_env("CURL_CA_BUNDLE")

    session = requests.Session()
    session.verify = curl_ca_bundle if curl_ca_bundle else True

    token = _mint_access_token(session)
    reviewer_username = _optional_env("SMOKE_LOGIN_EMAIL") or "dq-admin@jaccloud.nl"
    reviewer_password = _optional_env("SMOKE_LOGIN_PASSWORD") or _optional_env("KEYCLOAK_USER_PASSWORD") or "password"
    reviewer_token = _mint_access_token_for_credentials(
        session,
        username=reviewer_username,
        password=reviewer_password,
    )

    seed_dov = _choose_first_dov(session, kong_url, token)
    data_object_version_id = str(_pick(seed_dov, "id", "data_object_version_id", "dataObjectVersionId", default="")).strip()
    data_object_id = str(_pick(seed_dov, "data_object_id", "dataObjectId", default="")).strip()
    if not data_object_version_id or not data_object_id:
        raise RuntimeError(f"Selected data object version is missing required identifiers: {seed_dov}")

    attribute_name = _discover_primary_attribute(session, kong_url, token, data_object_version_id)
    rule_id, rule_name = _create_impossible_rule(session, kong_url, token, data_object_id=data_object_id)
    approval_id = _create_rule_approval(session, kong_url, token, rule_id=rule_id, workspace_id="validation-smoke")
    _approve_rule_approval(session, kong_url, reviewer_token, approval_id=approval_id)
    _activate_rule_with_autopublish(
        session,
        kong_url,
        token,
        rule_id=rule_id,
        data_object_id=data_object_id,
        data_object_version_id=data_object_version_id,
    )
    suite_id = f"gx_{rule_id}"

    print(f"[{WORKFLOW_LABEL}] data_object_version_id={data_object_version_id}")
    print(f"[{WORKFLOW_LABEL}] attribute={attribute_name}")
    print(f"[{WORKFLOW_LABEL}] rule_id={rule_id}")
    print(f"[{WORKFLOW_LABEL}] rule_name={rule_name}")
    print(f"[{WORKFLOW_LABEL}] suite_id={suite_id}")

    suite_run = _request_json(
        session,
        "POST",
        _url(kong_url, f"/rulebuilder/v1/gx/suites/{suite_id}/runs/start"),
        token=token,
        params={"status": "active"},
        expected_statuses=(200, 202),
    )
    correlation_id = str(
        _pick(suite_run, "correlation_id", "correlationId", "business_key", "businessKey", default="")
    ).strip()
    if not correlation_id:
        raise RuntimeError(f"Suite run start response missing correlation_id: {suite_run}")
    run_id = _find_run_by_correlation_id(session, kong_url, token, correlation_id=correlation_id)
    print(f"[{WORKFLOW_LABEL}] run_id={run_id}")

    redis_url = _resolve_execution_redis_url()
    queue_key = _resolve_execution_queue_key()
    processing_queue_key = _resolve_execution_processing_queue_key(queue_key)
    heartbeat_key = _resolve_execution_worker_heartbeat_key(queue_key)
    queue_status = _wait_for_run_dequeue(redis_url, queue_key, queue_message_id=run_id)
    worker_status = _fetch_run_worker_status(
        redis_url,
        queue_key,
        processing_queue_key,
        heartbeat_key,
        queue_message_id=run_id,
    )
    print(
        f"[{WORKFLOW_LABEL}] queue_state={_describe_queue_state(queue_status)} "
        f"queue_length={_pick(queue_status, 'queue_length', default=0)} "
        f"index_from_tail={_pick(queue_status, 'index_from_tail', default=None)} "
        f"processing_queue_state={_describe_queue_state(worker_status['processing_queue'])} "
        f"worker_heartbeat={'present' if bool(_pick(worker_status['worker_heartbeat'], 'present', default=False)) else 'missing'}"
    )

    run_payload = _wait_for_run_started(
        session,
        kong_url,
        token,
        redis_url,
        queue_key,
        processing_queue_key,
        heartbeat_key,
        run_id=run_id,
    )
    run_snapshot = _run_state_snapshot(run_payload)
    print(
        f"[{WORKFLOW_LABEL}] run_state={run_snapshot['status']} "
        f"progress={_summarize_execution_progress(run_snapshot['executionProgress'])}"
    )

    run_payload = _wait_for_run_terminal(session, kong_url, token, run_id=run_id)
    run_status = str(_pick(run_payload, "status", default="")).strip().lower()
    if run_status != "failed":
        raise RuntimeError(f"Expected GX run to fail but got status={run_status}: {run_payload}")

    diagnostics = _pick(run_payload, "diagnostics", default=[])
    if not isinstance(diagnostics, list) or not diagnostics:
        raise RuntimeError(f"Failed GX run did not emit diagnostics: {run_payload}")

    result_summary = _pick(run_payload, "result_summary", "resultSummary", default={})
    print(f"[{WORKFLOW_LABEL}] diagnostics={len(diagnostics)}")

    analytics = _fetch_exception_analytics(
        session,
        kong_url,
        token,
        data_object_version_id=data_object_version_id,
    )
    total_failed_records = int(_pick(analytics, "total_failed_records", "totalFailedRecords", default=0) or 0)
    runs_with_failures = int(_pick(analytics, "runs_with_failures", "runsWithFailures", default=0) or 0)
    if total_failed_records <= 0 or runs_with_failures <= 0:
        raise RuntimeError(f"Canonical exception analytics did not reflect the failing run: {analytics}")

    grafana_session = requests.Session()
    grafana_session.verify = session.verify
    _grafana_login(grafana_session)
    prom_uid = _find_prometheus_uid(grafana_session, grafana_url)
    canonical_age = _wait_for_prom_metric(
        grafana_session,
        grafana_url,
        prom_uid,
        "max(dq_exception_latest_canonical_detected_age_seconds)",
        minimum=0.0,
        timeout_seconds=120,
    )
    noncanonical_total = _prom_query_value(
        grafana_session,
        grafana_url,
        prom_uid,
        "sum(dq_exception_noncanonical_facts)",
    )

    payload = {
        "data_object_version_id": data_object_version_id,
        "run_id": run_id,
        "run_status": run_status,
        "diagnostic_count": len(diagnostics),
        "result_summary": result_summary,
        "exception_analytics": {
            "total_failed_records": total_failed_records,
            "runs_with_failures": runs_with_failures,
        },
        "grafana": {
            "prometheus_uid": prom_uid,
            "canonical_age_seconds": canonical_age,
            "noncanonical_total": noncanonical_total,
        },
        "docker_note": "real GX flow executed by existing API and worker containers",
    }

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
