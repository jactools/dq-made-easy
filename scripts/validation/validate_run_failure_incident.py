#!/usr/bin/env python3
"""Validation helper: assert a DQ engine run failed and create a technical_run_error incident.

Flow:
  1. Auth — mint a Keycloak/SSO access token.
  2. If DQ_VALIDATION_RUN_ID is set, resolve that specific run directly.
     Otherwise, replay DQ_VALIDATION_RUN_PLAN_ID once and wait for a terminal state.
  3. Assert the run status is "failed".
  4. POST /rulebuilder/v1/incidents with incident_kind="technical_run_error" and
     create_itsm_ticket=DQ_VALIDATION_CREATE_ITSM_TICKET.
  5. Assert the response is 201 and contains an incident ID.
  6. Report the incident ID and, if available, the Zammad ticket reference.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any

import requests


WORKFLOW_LABEL = "validate_run_failure_incident"

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
        data={
            "grant_type": "password",
            "client_id": client_id,
            "username": username,
            "password": password,
        },
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Keycloak token request failed HTTP {resp.status_code}: {resp.text.strip()}"
        )
    payload = _json_payload(resp)
    token = str((payload or {}).get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Keycloak response did not include access_token")
    return token


# ---------------------------------------------------------------------------
# Run helpers
# ---------------------------------------------------------------------------


def _pick(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def _run_status(payload: dict[str, Any]) -> str:
    status_history = _pick(payload, "statusHistory", "status_history", default=[])
    if isinstance(status_history, list) and status_history:
        last = status_history[-1]
        if isinstance(last, dict):
            history_status = str(_pick(last, "toStatus", "to_status", default="")).strip().lower()
            if history_status:
                return history_status
    return str(_pick(payload, "status", default="")).strip().lower()


def _get_run(
    session: requests.Session,
    kong_url: str,
    token: str,
    run_id: str,
) -> dict[str, Any]:
    response = session.get(
        _url(kong_url, f"/rulebuilder/v1/gx/runs/{run_id}"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"GX run lookup failed HTTP {response.status_code}: {response.text.strip() or '<empty>'}"
        )
    payload = _json_payload(response)
    if not isinstance(payload, dict):
        raise RuntimeError(f"GX run lookup returned unexpected payload type: {payload!r}")
    return payload


def _wait_for_run_terminal(
    session: requests.Session,
    kong_url: str,
    token: str,
    run_id: str,
) -> dict[str, Any]:
    timeout_seconds = int(_optional_env("DQ_SMOKE_GX_TIMEOUT_SECONDS", "300"))
    deadline = time.time() + timeout_seconds

    while True:
        payload = _get_run(session, kong_url, token, run_id)
        status = _run_status(payload)
        if status in _TERMINAL_STATUSES:
            return payload

        if time.time() >= deadline:
            raise RuntimeError(
                f"Timed out after {timeout_seconds}s waiting for run {run_id}; "
                f"last status={status!r}"
            )
        time.sleep(2)


def _list_run_plans(
    session: requests.Session,
    kong_url: str,
    token: str,
) -> list[dict[str, Any]]:
    payload = _request_json(
        session,
        "GET",
        _url(kong_url, "/rulebuilder/v1/run-plan"),
        token=token,
    )
    if isinstance(payload, dict):
        plans = list(
            payload.get("validation_run_plans")
            or payload.get("plans")
            or payload.get("run_plans")
            or []
        )
        return plans
    return []


def _select_run_plan_interactively(
    session: requests.Session,
    kong_url: str,
    token: str,
) -> tuple[str, dict[str, Any]]:
    """Fetch all run plans, print a numbered menu, return (run_plan_id, plan_dict)."""
    print(f"[{WORKFLOW_LABEL}] Fetching available run plans …")
    plans = _list_run_plans(session, kong_url, token)
    if not plans:
        raise SystemExit(f"[{WORKFLOW_LABEL}] No run plans found — nothing to select.")

    print(f"\nAvailable run plans ({len(plans)}):")
    for i, plan in enumerate(plans, start=1):
        plan_id = str(plan.get("run_plan_id") or plan.get("id") or "").strip()
        label = str(plan.get("business_key") or plan.get("name") or plan_id).strip()
        status = str(plan.get("status") or "").strip()
        ws = str(plan.get("workspace_id") or "").strip()
        detail = f"  ({status})" if status else ""
        ws_detail = f"  [{ws}]" if ws else ""
        print(f"  [{i}] {label}{detail}{ws_detail}")
        print(f"       {plan_id}")
    print()

    while True:
        try:
            raw = input(f"Select run plan [1-{len(plans)}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit(f"\n[{WORKFLOW_LABEL}] Aborted.")
        if not raw:
            continue
        try:
            choice = int(raw)
        except ValueError:
            print(f"  Please enter a number between 1 and {len(plans)}.")
            continue
        if 1 <= choice <= len(plans):
            selected = plans[choice - 1]
            selected_id = str(selected.get("run_plan_id") or selected.get("id") or "").strip()
            if not selected_id:
                raise SystemExit(f"[{WORKFLOW_LABEL}] Selected plan has no ID.")
            label = str(selected.get("business_key") or selected.get("name") or selected_id).strip()
            print(f"  → Selected: {label} ({selected_id})\n")
            return selected_id, selected
        print(f"  Please enter a number between 1 and {len(plans)}.")


def _resolve_run_plan(
    session: requests.Session,
    kong_url: str,
    token: str,
    run_plan_id: str,
) -> dict[str, Any]:
    candidate_payloads = [
        _request_json(
            session,
            "GET",
            _url(kong_url, "/rulebuilder/v1/run-plan"),
            token=token,
            params={"businessKey": run_plan_id},
        )
    ]
    plans: list[dict[str, Any]] = []
    for payload in candidate_payloads:
        if isinstance(payload, dict):
            plans = list(
                payload.get("validation_run_plans")
                or payload.get("plans")
                or payload.get("run_plans")
                or []
            )
            if not plans:
                plan_id = str(payload.get("id") or payload.get("run_plan_id") or "").strip()
                if plan_id:
                    plans = [payload]
        if plans:
            break
    if not plans:
        payload = _request_json(
            session,
            "GET",
            _url(kong_url, "/rulebuilder/v1/run-plan"),
            token=token,
        )
        if isinstance(payload, dict):
            plans = list(
                payload.get("validation_run_plans")
                or payload.get("plans")
                or payload.get("run_plans")
                or []
            )
    if not plans:
        raise RuntimeError(
            f"No run plan found for id/businessKey={run_plan_id!r}; response={payload}"
        )
    for plan in plans:
        plan_id = str(plan.get("id") or plan.get("run_plan_id") or "").strip()
        business_key = str(plan.get("businessKey") or plan.get("business_key") or "").strip()
        if plan_id == run_plan_id or business_key == run_plan_id:
            return plan
    return plans[0]


def _replay_run_plan(
    session: requests.Session,
    kong_url: str,
    token: str,
    run_plan_id: str,
) -> dict[str, Any]:
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
# Incident creation
# ---------------------------------------------------------------------------


def _create_incident(
    session: requests.Session,
    kong_url: str,
    token: str,
    *,
    run_id: str,
    run_plan_id: str,
    workspace_id: str,
    scope_kind: str,
    scope_id: str,
    failure_code: str,
    failure_message: str,
    create_itsm_ticket: bool,
) -> dict[str, Any]:
    title = f"DQ engine run failed: {run_id}"
    if failure_code:
        title = f"DQ engine run failed ({failure_code}): {run_id}"

    body: dict[str, Any] = {
        "incident_kind": "technical_run_error",
        "title": title,
        "run_id": run_id or None,
        "run_plan_id": run_plan_id or None,
        "workspace_id": workspace_id or None,
        "scope_kind": scope_kind or None,
        "scope_id": scope_id or None,
        "failure_code": failure_code or None,
        "failure_message": failure_message or None,
        "create_itsm_ticket": create_itsm_ticket,
    }

    response = session.post(
        _url(kong_url, "/rulebuilder/v1/incidents"),
        json=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    if response.status_code != 201:
        raise RuntimeError(
            f"POST /rulebuilder/v1/incidents failed HTTP {response.status_code}: "
            f"{response.text.strip() or '<empty>'}"
        )
    payload = _json_payload(response)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Incident creation returned unexpected payload: {payload!r}")
    return payload


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _main() -> int:
    kong_url = _require_env("KONG_PUBLIC_URL")
    run_id_override = _optional_env("DQ_VALIDATION_RUN_ID")
    run_plan_id = _optional_env("DQ_VALIDATION_RUN_PLAN_ID")
    workspace_id = _optional_env("DQ_VALIDATION_WORKSPACE_ID")
    scope_kind = _optional_env("DQ_VALIDATION_SCOPE_KIND", "data_asset")
    scope_id = _optional_env("DQ_VALIDATION_SCOPE_ID")
    create_itsm_ticket = _optional_env("DQ_VALIDATION_CREATE_ITSM_TICKET", "true").lower() == "true"

    ca_bundle = os.environ.get("REQUESTS_CA_BUNDLE", "")
    session = requests.Session()
    if ca_bundle and os.path.isfile(ca_bundle):
        session.verify = ca_bundle

    print(f"[{WORKFLOW_LABEL}] Minting access token …")
    token = _mint_token(session)

    preselected_plan: dict[str, Any] | None = None
    if not run_id_override and not run_plan_id:
        run_plan_id, preselected_plan = _select_run_plan_interactively(session, kong_url, token)

    effective_run_id = run_id_override
    run_payload: dict[str, Any] = {}

    if effective_run_id:
        # --- Use the provided run ID directly ---
        print(f"[{WORKFLOW_LABEL}] Fetching run {effective_run_id!r} …")
        run_payload = _get_run(session, kong_url, token, effective_run_id)
    else:
        # --- Replay the run plan once and wait for terminal ---
        if preselected_plan is not None:
            run_plan = preselected_plan
            print(f"[{WORKFLOW_LABEL}] Using selected run plan {run_plan_id!r} …")
        else:
            print(f"[{WORKFLOW_LABEL}] Resolving run plan {run_plan_id!r} …")
            run_plan = _resolve_run_plan(session, kong_url, token, run_plan_id)
        resolved_plan_id = str(
            _pick(run_plan, "id", "run_plan_id", default=run_plan_id)
        ).strip() or run_plan_id

        if not workspace_id:
            workspace_id = str(
                _pick(run_plan, "workspaceId", "workspace_id", default="")
            ).strip()
        if not scope_id:
            scope_id = str(
                _pick(run_plan, "businessKey", "business_key", "id", default=resolved_plan_id)
            ).strip()
        run_plan_id = resolved_plan_id

        print(f"[{WORKFLOW_LABEL}] Replaying run plan {resolved_plan_id!r} …")
        replay = _replay_run_plan(session, kong_url, token, resolved_plan_id)
        effective_run_id = str(
            _pick(replay, "runId", "run_id", "id", default="")
        ).strip() or str(
            _pick(replay, "queueMessageId", "queue_message_id", default="")
        ).strip()
        if not effective_run_id:
            raise RuntimeError(
                f"Replay response missing run_id and queue_message_id: {replay}"
            )

        print(f"[{WORKFLOW_LABEL}] Waiting for run {effective_run_id!r} to reach terminal state …")
        run_payload = _wait_for_run_terminal(session, kong_url, token, effective_run_id)

    final_status = _run_status(run_payload)
    failure_code = str(_pick(run_payload, "failureCode", "failure_code", default="")).strip()
    failure_message = str(_pick(run_payload, "failureMessage", "failure_message", default="")).strip()
    workspace_id = workspace_id or str(
        _pick(run_payload, "workspaceId", "workspace_id", default="")
    ).strip()
    run_plan_id = run_plan_id or str(
        _pick(run_payload, "runPlanId", "run_plan_id", default="")
    ).strip()
    scope_id = scope_id or effective_run_id

    print(
        f"[{WORKFLOW_LABEL}] Run {effective_run_id!r} terminal state: status={final_status!r}"
        + (f" failure_code={failure_code!r}" if failure_code else "")
    )

    # --- Assert failure ---
    if final_status != "failed":
        raise SystemExit(
            f"[{WORKFLOW_LABEL}] SKIP: run {effective_run_id!r} has status={final_status!r}; "
            "expected 'failed'. Pass a failed run or a run plan whose execution fails."
        )

    # --- Create incident ---
    print(
        f"[{WORKFLOW_LABEL}] Creating technical_run_error incident "
        f"(create_itsm_ticket={create_itsm_ticket}) …"
    )
    result = _create_incident(
        session, kong_url, token,
        run_id=effective_run_id,
        run_plan_id=run_plan_id,
        workspace_id=workspace_id,
        scope_kind=scope_kind,
        scope_id=scope_id,
        failure_code=failure_code,
        failure_message=failure_message,
        create_itsm_ticket=create_itsm_ticket,
    )

    incident = result.get("incident") or {}
    incident_id = str(incident.get("id") or "").strip()
    itsm_ticket_number = str(incident.get("itsm_ticket_number") or "").strip()
    itsm_ticket_id = str(incident.get("itsm_ticket_id") or "").strip()
    correlation_id = str(result.get("correlation_id") or "").strip()

    if not incident_id:
        raise RuntimeError(
            f"Incident creation response missing incident.id: {result}"
        )

    summary = {
        "run_id": effective_run_id,
        "run_plan_id": run_plan_id,
        "failure_code": failure_code or None,
        "incident_id": incident_id,
        "itsm_ticket_number": itsm_ticket_number or None,
        "itsm_ticket_id": itsm_ticket_id or None,
        "correlation_id": correlation_id,
        "completed_at": datetime.now(UTC).isoformat(),
    }

    print(f"\n[{WORKFLOW_LABEL}] Summary")
    print(f"  Run ID          : {effective_run_id}")
    print(f"  Failure code    : {failure_code or '(none)'}")
    print(f"  Incident ID     : {incident_id}")
    if itsm_ticket_number:
        print(f"  Zammad ticket # : {itsm_ticket_number}")
    if itsm_ticket_id:
        print(f"  Zammad ticket ID: {itsm_ticket_id}")
    print()
    print(json.dumps(summary, indent=2))

    print(f"\n[{WORKFLOW_LABEL}] PASSED: technical_run_error incident created for failed run {effective_run_id!r}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
