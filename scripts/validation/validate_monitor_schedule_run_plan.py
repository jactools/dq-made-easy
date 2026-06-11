#!/usr/bin/env python3
"""Validation helper: schedule a DQ run plan, execute it N times, verify monitor schedule persists."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import requests


WORKFLOW_LABEL = "validate_monitor_schedule_run_plan"

# Terminal states for a GX execution run
_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"[{WORKFLOW_LABEL}] Missing required environment variable: {name}")
    return value


def _optional_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _json_payload(response: requests.Response) -> Any:
    if not response.text.strip():
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Expected JSON from {response.request.method} {response.url}: {response.text}"
        ) from exc


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    token: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    expected_statuses: tuple[int, ...] = (200,),
) -> Any:
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    response = session.request(method, url, params=params, json=body, headers=headers, timeout=60)
    if response.status_code not in expected_statuses:
        raise RuntimeError(
            f"{method} {url} → HTTP {response.status_code}: {response.text.strip() or '<empty>'}"
        )
    return _json_payload(response)


def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}{path}"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def _mint_token(session: requests.Session) -> str:
    sso_enabled = _optional_env("SSO_ENABLED").lower() == "true"
    if sso_enabled:
        issuer_url = _require_env("SSO_PUBLIC_ISSUER_URL")
        token_url = f"{issuer_url.rstrip('/')}/protocol/openid-connect/token"
    else:
        kc_url = _require_env("KEYCLOAK_PUBLIC_URL")
        kc_realm = _require_env("KEYCLOAK_REALM")
        token_url = f"{kc_url.rstrip('/')}/realms/{kc_realm}/protocol/openid-connect/token"

    client_id = _require_env("KEYCLOAK_CLIENT_ID")
    username = _require_env("KEYCLOAK_JACCLOUD_USERNAME")
    password = _require_env("KEYCLOAK_JACCLOUD_PASSWORD")

    resp = session.post(
        token_url,
        data={"grant_type": "password", "client_id": client_id, "username": username, "password": password},
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Keycloak token request failed HTTP {resp.status_code}: {resp.text.strip()}")
    payload = _json_payload(resp)
    token = str((payload or {}).get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Keycloak response did not include access_token")
    return token


# ---------------------------------------------------------------------------
# Monitor schedule helpers
# ---------------------------------------------------------------------------


def _save_monitor_schedule(
    session: requests.Session,
    kong_url: str,
    token: str,
    *,
    scope_kind: str,
    scope_id: str,
    workspace_id: str,
    cron_expression: str,
) -> dict[str, Any]:
    payload = _request_json(
        session,
        "PUT",
        _url(kong_url, "/rulebuilder/v1/governance/monitor-schedules"),
        token=token,
        body={
            "scope_kind": scope_kind,
            "scope_id": scope_id,
            "workspace_id": workspace_id,
            "cron_expression": cron_expression,
            "timezone": "UTC",
            "window_minutes": 1440,
            "enabled": True,
        },
    )
    schedules = (payload or {}).get("monitor_schedules") or []
    if not schedules:
        raise RuntimeError(f"Save monitor-schedule returned no records: {payload}")
    return schedules[0]


def _get_monitor_schedule(
    session: requests.Session,
    kong_url: str,
    token: str,
    *,
    scope_kind: str,
    scope_id: str,
) -> dict[str, Any] | None:
    """Fetch a single monitor schedule by scope; returns None on 404."""
    response = session.get(
        _url(kong_url, f"/rulebuilder/v1/governance/monitor-schedules/{scope_kind}/{scope_id}"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise RuntimeError(
            f"GET monitor-schedule by scope failed HTTP {response.status_code}: "
            f"{response.text.strip() or '<empty>'}"
        )
    payload = _json_payload(response)
    return (payload or {}).get("monitor_schedule") or None


# ---------------------------------------------------------------------------
# Run plan helpers
# ---------------------------------------------------------------------------


def _resolve_run_plan(
    session: requests.Session,
    kong_url: str,
    token: str,
    run_plan_id: str,
) -> dict[str, Any]:
    payload = _request_json(
        session,
        "GET",
        _url(kong_url, f"/rulebuilder/v1/run-plan"),
        token=token,
        params={"businessKey": run_plan_id},
    )
    plans: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        plans = list(payload.get("plans") or payload.get("run_plans") or [])
        if not plans:
            # try treating the response itself as a single plan
            plan_id = str(payload.get("id") or payload.get("run_plan_id") or "").strip()
            if plan_id:
                plans = [payload]
    if not plans:
        raise RuntimeError(
            f"No run plan found for id/businessKey={run_plan_id!r}; response={payload}"
        )
    # Return the plan whose id matches directly, falling back to first
    for plan in plans:
        if str(plan.get("id") or plan.get("run_plan_id") or "").strip() == run_plan_id:
            return plan
    return plans[0]


def _replay_run_plan(
    session: requests.Session,
    kong_url: str,
    token: str,
    run_plan_id: str,
) -> dict[str, Any]:
    """POST replay for a run plan; returns the replay handoff payload."""
    payload = _request_json(
        session,
        "POST",
        _url(kong_url, f"/rulebuilder/v1/run-plan/{run_plan_id}/replay"),
        token=token,
        body={},
        expected_statuses=(200, 202),
    )
    return payload or {}


# ---------------------------------------------------------------------------
# Run polling
# ---------------------------------------------------------------------------


def _pick(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def _run_status(payload: dict[str, Any]) -> str:
    """Extract the current status string from a GX execution run payload."""
    # prefer status_history last entry
    status_history = _pick(payload, "statusHistory", "status_history", default=[])
    if isinstance(status_history, list) and status_history:
        last = status_history[-1]
        if isinstance(last, dict):
            history_status = str(_pick(last, "toStatus", "to_status", default="")).strip().lower()
            if history_status:
                return history_status
    return str(_pick(payload, "status", default="")).strip().lower()


def _wait_for_run_terminal(
    session: requests.Session,
    kong_url: str,
    token: str,
    run_id: str,
) -> dict[str, Any]:
    timeout_seconds = int(_optional_env("DQ_SMOKE_GX_TIMEOUT_SECONDS", "300"))
    deadline = time.time() + timeout_seconds

    while True:
        response = session.get(
            _url(kong_url, f"/rulebuilder/v1/gx/runs/{run_id}"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        if response.status_code == 401:
            raise RuntimeError("GX run poll returned 401; token refresh not supported mid-run")
        if response.status_code != 200:
            raise RuntimeError(
                f"GX run poll failed HTTP {response.status_code}: {response.text.strip() or '<empty>'}"
            )
        payload = _json_payload(response)
        if not isinstance(payload, dict):
            raise RuntimeError(f"GX run poll returned unexpected payload type: {payload!r}")

        status = _run_status(payload)
        if status in _TERMINAL_STATUSES:
            return payload

        if time.time() >= deadline:
            raise RuntimeError(
                f"Timed out after {timeout_seconds}s waiting for run {run_id}; last status={status!r}"
            )
        time.sleep(2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _main() -> int:
    kong_url = _require_env("KONG_PUBLIC_URL")
    run_plan_id = _require_env("DQ_VALIDATION_RUN_PLAN_ID")
    run_count = int(_optional_env("DQ_VALIDATION_RUN_COUNT", "3"))
    if run_count < 1:
        raise SystemExit(f"[{WORKFLOW_LABEL}] DQ_VALIDATION_RUN_COUNT must be >= 1, got {run_count}")

    scope_kind = _optional_env("DQ_VALIDATION_SCOPE_KIND", "data_asset")
    scope_id_override = _optional_env("DQ_VALIDATION_SCOPE_ID", "")
    workspace_id_override = _optional_env("DQ_VALIDATION_WORKSPACE_ID", "")

    print(f"[{WORKFLOW_LABEL}] run_plan_id={run_plan_id!r} run_count={run_count} kong_url={kong_url!r}")

    ca_bundle = os.environ.get("REQUESTS_CA_BUNDLE", "")
    session = requests.Session()
    if ca_bundle and os.path.isfile(ca_bundle):
        session.verify = ca_bundle

    # --- Authenticate ---
    print(f"[{WORKFLOW_LABEL}] Minting access token …")
    token = _mint_token(session)

    # --- Resolve run plan metadata ---
    print(f"[{WORKFLOW_LABEL}] Resolving run plan {run_plan_id!r} …")
    run_plan = _resolve_run_plan(session, kong_url, token, run_plan_id)
    resolved_id = str(_pick(run_plan, "id", "run_plan_id", default=run_plan_id)).strip() or run_plan_id
    workspace_id = str(
        workspace_id_override
        or _pick(run_plan, "workspaceId", "workspace_id", default="")
        or ""
    ).strip()
    scope_id = str(
        scope_id_override
        or _pick(run_plan, "businessKey", "business_key", "id", "run_plan_id", default=resolved_id)
    ).strip() or resolved_id

    print(
        f"[{WORKFLOW_LABEL}] Run plan resolved: id={resolved_id!r} workspace_id={workspace_id!r}"
    )

    if not workspace_id:
        print(
            f"[{WORKFLOW_LABEL}] WARNING: workspace_id could not be derived from run plan; "
            "monitor schedule will be saved with empty workspace_id. "
            "Pass --workspace-id to override."
        )

    # --- Save monitor schedule ---
    cron_expression = "0 6 * * *"
    print(
        f"[{WORKFLOW_LABEL}] Saving monitor schedule: scope_kind={scope_kind!r} "
        f"scope_id={scope_id!r} workspace_id={workspace_id!r} cron={cron_expression!r} …"
    )
    saved_schedule = _save_monitor_schedule(
        session, kong_url, token,
        scope_kind=scope_kind,
        scope_id=scope_id,
        workspace_id=workspace_id,
        cron_expression=cron_expression,
    )
    schedule_id = str(saved_schedule.get("id") or "").strip()
    print(f"[{WORKFLOW_LABEL}] Monitor schedule saved: id={schedule_id!r}")

    # --- Replay run plan N times and track results ---
    run_results: list[dict[str, Any]] = []

    for run_index in range(1, run_count + 1):
        print(f"[{WORKFLOW_LABEL}] Run {run_index}/{run_count}: replaying run plan {resolved_id!r} …")
        replay_payload = _replay_run_plan(session, kong_url, token, resolved_id)

        run_id = str(
            _pick(replay_payload, "runId", "run_id", "id", default="")
        ).strip()
        queue_message_id = str(
            _pick(replay_payload, "queueMessageId", "queue_message_id", default="")
        ).strip()

        if not run_id and not queue_message_id:
            raise RuntimeError(
                f"Replay response missing run_id and queue_message_id on run {run_index}: {replay_payload}"
            )

        effective_run_id = run_id or queue_message_id
        print(
            f"[{WORKFLOW_LABEL}] Run {run_index}/{run_count}: enqueued run_id={effective_run_id!r} …"
        )

        terminal_payload = _wait_for_run_terminal(
            session, kong_url, token, effective_run_id
        )
        final_status = _run_status(terminal_payload)
        completed_at = str(
            _pick(terminal_payload, "completedAt", "completed_at", default="")
        ).strip()
        failure_code = str(
            _pick(terminal_payload, "failureCode", "failure_code", default="")
        ).strip()

        run_results.append(
            {
                "run_index": run_index,
                "run_id": effective_run_id,
                "final_status": final_status,
                "completed_at": completed_at,
                "failure_code": failure_code or None,
            }
        )
        print(
            f"[{WORKFLOW_LABEL}] Run {run_index}/{run_count}: terminal — "
            f"status={final_status!r} completed_at={completed_at!r}"
            + (f" failure_code={failure_code!r}" if failure_code else "")
        )

        # Verify monitor schedule still present after each run
        current_schedule = _get_monitor_schedule(
            session, kong_url, token, scope_kind=scope_kind, scope_id=scope_id
        )
        if current_schedule is None:
            raise RuntimeError(
                f"Monitor schedule for scope_kind={scope_kind!r} scope_id={scope_id!r} "
                f"was absent after run {run_index}/{run_count}. "
                "The schedule must persist across runs."
            )
        current_cron = str(current_schedule.get("cron_expression") or "").strip()
        if current_cron != cron_expression:
            raise RuntimeError(
                f"Monitor schedule cron_expression mutated after run {run_index}: "
                f"expected {cron_expression!r}, got {current_cron!r}"
            )
        print(
            f"[{WORKFLOW_LABEL}] Run {run_index}/{run_count}: monitor schedule intact ✓"
        )

    # --- Final assertions ---
    non_succeeded = [r for r in run_results if r["final_status"] not in {"succeeded", "failed"}]
    if non_succeeded:
        raise RuntimeError(
            f"One or more runs did not reach a valid terminal state: "
            + json.dumps(non_succeeded, indent=2)
        )

    # Final schedule readback
    final_schedule = _get_monitor_schedule(
        session, kong_url, token, scope_kind=scope_kind, scope_id=scope_id
    )
    if final_schedule is None:
        raise RuntimeError(
            f"Monitor schedule for scope_kind={scope_kind!r} scope_id={scope_id!r} "
            "was absent after all runs completed."
        )

    result = {
        "run_plan_id": resolved_id,
        "run_count": run_count,
        "scope_kind": scope_kind,
        "scope_id": scope_id,
        "schedule_id": schedule_id,
        "schedule_cron": cron_expression,
        "schedule_persisted_across_all_runs": True,
        "runs": run_results,
        "completed_at": datetime.now(UTC).isoformat(),
    }

    print(f"\n[{WORKFLOW_LABEL}] Summary")
    print(f"  Run plan : {resolved_id}")
    print(f"  Runs     : {run_count}")
    print(f"  Schedule : {schedule_id or '(no id returned)'} @ {cron_expression}")
    print()
    for r in run_results:
        failure_note = f"  failure_code={r['failure_code']!r}" if r["failure_code"] else ""
        print(f"  [{r['run_index']:>2}/{run_count}] {r['run_id']:40s}  {r['final_status']}{failure_note}")
    print()
    print(json.dumps(result, indent=2))

    print(f"\n[{WORKFLOW_LABEL}] PASSED: all {run_count} run(s) completed and monitor schedule persisted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
