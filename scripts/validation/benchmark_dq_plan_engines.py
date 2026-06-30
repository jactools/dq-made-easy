#!/usr/bin/env python3
"""Benchmark DQ plan execution through the containerized API.

Purpose:
- Replays configured DQ validation run plans through the API running in the stack.
- Measures API enqueue latency and end-to-end terminal latency per engine plan.
- Records skipped engines explicitly when no API-backed run plan is configured yet.
- Does not import or execute engine code locally.

validate: groups=api,engine,performance
Version: 2.0
Last modified: 2026-06-30
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


ROOT_DIR = Path(__file__).resolve().parents[2]
APP_VERSION = os.environ.get("APP_VERSION", "0.11.5").strip() or "0.11.5"
WORKFLOW_LABEL = "dq-plan-engine-api-benchmark"
DEFAULT_ENGINES = ("gx", "spark_expectations", "pyspark", "soda", "sql", "trino")
DEFAULT_GROUPED_PLAN_ENGINES = {"gx", "spark_expectations", "pyspark", "soda", "trino"}
DEFAULT_GROUPED_PLAN_ID = "019e0488-9a56-7d10-b001-000000000001"
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


@dataclass(frozen=True)
class EnginePlan:
    engine: str
    run_plan_id: str | None
    source: str


def _default_output_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return ROOT_DIR / "test-results" / "evidence" / APP_VERSION / "api" / f"{timestamp}-{WORKFLOW_LABEL}" / "benchmark.json"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _split_engines(value: str) -> list[str]:
    engines = [_normalize_engine(engine) for engine in value.split(",") if engine.strip()]
    if not engines:
        raise argparse.ArgumentTypeError("at least one engine is required")
    return engines


def _normalize_engine(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    aliases = {
        "great_expectations": "gx",
        "spark": "pyspark",
        "pyspark_native": "pyspark",
        "trino_sql": "trino",
        "sparkexpectations": "spark_expectations",
    }
    return aliases.get(normalized, normalized)


def _parse_engine_plan(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("engine plan must be ENGINE=RUN_PLAN_ID")
    engine, run_plan_id = value.split("=", 1)
    engine = _normalize_engine(engine)
    run_plan_id = run_plan_id.strip()
    if not engine or not run_plan_id:
        raise argparse.ArgumentTypeError("engine plan must include both ENGINE and RUN_PLAN_ID")
    return engine, run_plan_id


def _load_plan_file(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise SystemExit(f"Plan map file must contain a JSON object: {path}")

    raw_map = payload.get("plans", payload)
    if not isinstance(raw_map, dict):
        raise SystemExit(f"Plan map JSON must contain object values: {path}")

    plan_map: dict[str, str] = {}
    for raw_engine, raw_value in raw_map.items():
        engine = _normalize_engine(str(raw_engine))
        if isinstance(raw_value, dict):
            run_plan_id = str(raw_value.get("run_plan_id") or raw_value.get("runPlanId") or "").strip()
        else:
            run_plan_id = str(raw_value or "").strip()
        if run_plan_id:
            plan_map[engine] = run_plan_id
    return plan_map


def _load_env_plan_map() -> dict[str, str]:
    plan_map: dict[str, str] = {}
    raw_json = os.environ.get("DQ_BENCHMARK_PLAN_MAP", "").strip()
    if raw_json:
        payload = json.loads(raw_json)
        if not isinstance(payload, dict):
            raise SystemExit("DQ_BENCHMARK_PLAN_MAP must be a JSON object")
        for raw_engine, raw_value in payload.items():
            run_plan_id = str(raw_value or "").strip()
            if run_plan_id:
                plan_map[_normalize_engine(str(raw_engine))] = run_plan_id

    for engine in DEFAULT_ENGINES:
        env_name = f"DQ_BENCHMARK_{engine.upper()}_RUN_PLAN_ID"
        run_plan_id = os.environ.get(env_name, "").strip()
        if run_plan_id:
            plan_map[engine] = run_plan_id
    trino_sql_plan = os.environ.get("DQ_BENCHMARK_TRINO_SQL_RUN_PLAN_ID", "").strip()
    if trino_sql_plan:
        plan_map["trino"] = trino_sql_plan
    return plan_map


def _configured_engine_plans(args: argparse.Namespace) -> list[EnginePlan]:
    plan_map = _load_env_plan_map()
    if args.plan_file is not None:
        plan_map.update(_load_plan_file(args.plan_file))
    for engine, run_plan_id in args.plan:
        plan_map[engine] = run_plan_id
    if not args.no_default_grouped_plan:
        for engine in args.engines:
            if engine in DEFAULT_GROUPED_PLAN_ENGINES:
                plan_map.setdefault(engine, args.grouped_plan_id)

    plans: list[EnginePlan] = []
    for engine in args.engines:
        run_plan_id = plan_map.get(engine)
        source = "configured" if run_plan_id else "missing"
        plans.append(EnginePlan(engine=engine, run_plan_id=run_plan_id, source=source))
    return plans


def _first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _json_payload(response: requests.Response) -> Any:
    if not response.text.strip():
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"Expected JSON from {response.request.method} {response.url}: {response.text}") from exc


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    token: str,
    body: dict[str, Any] | None = None,
    expected_statuses: tuple[int, ...] = (200,),
    timeout_seconds: int = 60,
) -> Any:
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    response = session.request(method, url, json=body, headers=headers, timeout=timeout_seconds)
    if response.status_code not in expected_statuses:
        raise RuntimeError(f"{method} {url} -> HTTP {response.status_code}: {response.text.strip() or '<empty>'}")
    return _json_payload(response)


def _mint_token(session: requests.Session, args: argparse.Namespace) -> str:
    token = args.token or _first_env("DQ_RUN_PLAN_TOKEN", "DQ_BENCHMARK_TOKEN")
    if token:
        return token

    issuer_url = args.issuer_url or _first_env("SSO_PUBLIC_ISSUER_URL", "KEYCLOAK_PUBLIC_URL")
    if not issuer_url:
        raise SystemExit("--issuer-url or SSO_PUBLIC_ISSUER_URL/KEYCLOAK_PUBLIC_URL is required when --token is not provided")
    if issuer_url.rstrip("/").endswith("/protocol/openid-connect"):
        token_url = f"{issuer_url.rstrip('/')}/token"
    elif issuer_url.rstrip("/").endswith("/token"):
        token_url = issuer_url.rstrip("/")
    elif "/realms/" in issuer_url:
        token_url = f"{issuer_url.rstrip('/')}/protocol/openid-connect/token"
    else:
        realm = _first_env("KEYCLOAK_REALM")
        if not realm:
            raise SystemExit("KEYCLOAK_REALM is required when issuer URL does not include a realm")
        token_url = f"{issuer_url.rstrip('/')}/realms/{realm}/protocol/openid-connect/token"

    client_id = args.client_id or _first_env("KEYCLOAK_CLIENT_ID", "VITE_KEYCLOAK_CLIENT_ID", "DQ_RUN_PLAN_CLIENT_ID")
    username = args.username or _first_env("KEYCLOAK_JACCLOUD_USERNAME", "DQ_RUN_PLAN_USERNAME")
    password = args.password or _first_env("KEYCLOAK_JACCLOUD_PASSWORD", "DQ_RUN_PLAN_PASSWORD")
    missing = [name for name, value in (("client id", client_id), ("username", username), ("password", password)) if not value]
    if missing:
        raise SystemExit(f"Missing token credential values: {', '.join(missing)}")

    response = session.post(
        token_url,
        data={"grant_type": "password", "client_id": client_id, "username": username, "password": password},
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Keycloak token request failed HTTP {response.status_code}: {response.text.strip()}")
    payload = _json_payload(response)
    access_token = str((payload or {}).get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("Keycloak response did not include access_token")
    return access_token


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


def _summarize_durations(durations_ms: list[float]) -> dict[str, Any]:
    if not durations_ms:
        return {"iterations": 0, "mean_ms": None, "median_ms": None, "p95_ms": None, "min_ms": None, "max_ms": None}
    ordered = sorted(durations_ms)
    p95_index = int(round((len(ordered) - 1) * 0.95))
    return {
        "iterations": len(durations_ms),
        "mean_ms": statistics.mean(durations_ms),
        "median_ms": statistics.median(durations_ms),
        "p95_ms": ordered[p95_index],
        "min_ms": min(durations_ms),
        "max_ms": max(durations_ms),
    }


def _replay_run_plan(
    session: requests.Session,
    args: argparse.Namespace,
    *,
    token: str,
    engine_plan: EnginePlan,
) -> tuple[float, dict[str, Any]]:
    assert engine_plan.run_plan_id is not None
    path = args.replay_path_template.format(run_plan_id=engine_plan.run_plan_id)
    body = {"triggerType": "manual", "sourcePipeline": WORKFLOW_LABEL}
    started = time.perf_counter()
    payload = _request_json(
        session,
        "POST",
        _url(args.base_url, path),
        token=token,
        body=body,
        expected_statuses=(200, 202),
        timeout_seconds=args.http_timeout_seconds,
    )
    return (time.perf_counter() - started) * 1000.0, payload or {}


def _poll_run_terminal(
    session: requests.Session,
    args: argparse.Namespace,
    *,
    token: str,
    run_id: str,
) -> dict[str, Any]:
    deadline = time.time() + args.poll_timeout_seconds
    while True:
        path = args.poll_path_template.format(run_id=run_id)
        payload = _request_json(
            session,
            "GET",
            _url(args.base_url, path),
            token=token,
            expected_statuses=(200,),
            timeout_seconds=args.http_timeout_seconds,
        )
        if not isinstance(payload, dict):
            raise RuntimeError(f"Run poll returned unexpected payload: {payload!r}")
        last_status = _run_status(payload)
        if last_status in TERMINAL_STATUSES:
            return payload
        if time.time() >= deadline:
            raise RuntimeError(f"Timed out after {args.poll_timeout_seconds}s waiting for run {run_id}; last status={last_status!r}")
        time.sleep(args.poll_interval_seconds)


def _run_engine_plan(
    session: requests.Session,
    args: argparse.Namespace,
    *,
    token: str,
    engine_plan: EnginePlan,
) -> dict[str, Any]:
    if not engine_plan.run_plan_id:
        return {
            "engine": engine_plan.engine,
            "run_plan_id": None,
            "status": "skipped",
            "skip_reason": "No API-backed validation run plan id configured for this engine",
            "api_enqueue": _summarize_durations([]),
            "end_to_end": _summarize_durations([]),
            "runs": [],
        }

    enqueue_durations: list[float] = []
    terminal_durations: list[float] = []
    runs: list[dict[str, Any]] = []

    try:
        for iteration in range(1, args.iterations + 1):
            iteration_started = time.perf_counter()
            enqueue_ms, replay_payload = _replay_run_plan(session, args, token=token, engine_plan=engine_plan)
            enqueue_durations.append(enqueue_ms)

            run_id = str(_pick(replay_payload, "runId", "run_id", "id", default="")).strip()
            queue_message_id = str(_pick(replay_payload, "queueMessageId", "queue_message_id", default="")).strip()
            effective_run_id = run_id or queue_message_id
            if not effective_run_id:
                raise RuntimeError(f"Replay response did not include run id or queue message id: {replay_payload}")

            terminal_payload = _poll_run_terminal(session, args, token=token, run_id=effective_run_id)
            terminal_ms = (time.perf_counter() - iteration_started) * 1000.0
            terminal_durations.append(terminal_ms)
            final_status = _run_status(terminal_payload)
            runs.append(
                {
                    "iteration": iteration,
                    "run_id": effective_run_id,
                    "queue_message_id": queue_message_id or None,
                    "api_enqueue_ms": enqueue_ms,
                    "end_to_end_ms": terminal_ms,
                    "final_status": final_status,
                    "replay": _summarize_replay_payload(replay_payload),
                    "terminal": _summarize_terminal_payload(terminal_payload),
                }
            )

        failed_runs = [run for run in runs if run["final_status"] != "succeeded"]
        return {
            "engine": engine_plan.engine,
            "run_plan_id": engine_plan.run_plan_id,
            "status": "failed" if failed_runs else "passed",
            "api_enqueue": _summarize_durations(enqueue_durations),
            "end_to_end": _summarize_durations(terminal_durations),
            "runs": runs,
        }
    except Exception as exc:
        return {
            "engine": engine_plan.engine,
            "run_plan_id": engine_plan.run_plan_id,
            "status": "failed",
            "api_enqueue": _summarize_durations(enqueue_durations),
            "end_to_end": _summarize_durations(terminal_durations),
            "runs": runs,
            "failure": {"exception_type": exc.__class__.__name__, "message": str(exc)},
        }


def _summarize_replay_payload(payload: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "runId",
        "queueMessageId",
        "runPlanId",
        "runPlanVersionId",
        "selectionMode",
        "suiteId",
        "suiteVersion",
        "engineType",
        "engineTarget",
        "executionShape",
        "dispatchMode",
        "queueKey",
        "correlationId",
    )
    return {key: payload.get(key) for key in keys if key in payload}


def _summarize_terminal_payload(payload: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "runId",
        "run_plan_id",
        "runPlanId",
        "status",
        "completedAt",
        "completed_at",
        "failureCode",
        "failure_code",
        "engineType",
        "engine_type",
        "engineTarget",
        "engine_target",
    )
    summary = {key: payload.get(key) for key in keys if key in payload}
    summary["resolved_status"] = _run_status(payload)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark DQ validation run plans through the containerized API replay path.")
    parser.add_argument("--base-url", default=_first_env("DQ_BENCHMARK_API_BASE_URL", "DQ_API_LOCAL_URL", "DQ_API_INTERNAL_URL", "KONG_PUBLIC_URL"), help="Base URL for the API container or Kong route")
    parser.add_argument("--replay-path-template", default=os.environ.get("DQ_BENCHMARK_REPLAY_PATH_TEMPLATE", "/api/rulebuilder/v1/validation-run-plans/{run_plan_id}/replay"), help="Replay path template relative to --base-url")
    parser.add_argument("--poll-path-template", default=os.environ.get("DQ_BENCHMARK_POLL_PATH_TEMPLATE", "/rulebuilder/v1/gx/runs/{run_id}"), help="Run status poll path template relative to --base-url")
    parser.add_argument("--output", type=Path, default=_default_output_path(), help="Path to write benchmark JSON evidence")
    parser.add_argument("--engines", type=_split_engines, default=list(DEFAULT_ENGINES), help="Comma-separated engine labels to benchmark")
    parser.add_argument("--plan", action="append", type=_parse_engine_plan, default=[], help="Engine run plan mapping, repeatable: ENGINE=RUN_PLAN_ID")
    parser.add_argument("--plan-file", type=Path, default=None, help="JSON object mapping engine labels to run_plan_id values")
    parser.add_argument("--grouped-plan-id", default=os.environ.get("DQ_BENCHMARK_GROUPED_RUN_PLAN_ID", DEFAULT_GROUPED_PLAN_ID), help="Grouped multi-engine run plan used by default for engines included in the seeded grouped scope")
    parser.add_argument("--no-default-grouped-plan", action="store_true", help="Do not map the seeded grouped multi-engine run plan to engines without explicit --plan mappings")
    parser.add_argument("--iterations", type=_positive_int, default=int(os.environ.get("DQ_BENCHMARK_ITERATIONS", "3")), help="Measured API replay iterations per configured engine plan")
    parser.add_argument("--poll-timeout-seconds", type=_positive_int, default=int(os.environ.get("DQ_BENCHMARK_POLL_TIMEOUT_SECONDS", "300")), help="Maximum seconds to wait for each run to reach a terminal status")
    parser.add_argument("--poll-interval-seconds", type=float, default=float(os.environ.get("DQ_BENCHMARK_POLL_INTERVAL_SECONDS", "2")), help="Seconds between run status polls")
    parser.add_argument("--http-timeout-seconds", type=_positive_int, default=int(os.environ.get("DQ_BENCHMARK_HTTP_TIMEOUT_SECONDS", "60")), help="HTTP request timeout")
    parser.add_argument("--token", default=os.environ.get("DQ_RUN_PLAN_TOKEN", ""), help="Bearer token; if omitted the script mints one from Keycloak env vars")
    parser.add_argument("--issuer-url", default=os.environ.get("SSO_PUBLIC_ISSUER_URL", ""), help="OIDC issuer URL used when minting a token")
    parser.add_argument("--client-id", default=_first_env("KEYCLOAK_CLIENT_ID", "VITE_KEYCLOAK_CLIENT_ID", "DQ_RUN_PLAN_CLIENT_ID"), help="OIDC client id used when minting a token")
    parser.add_argument("--username", default=_first_env("KEYCLOAK_JACCLOUD_USERNAME", "DQ_RUN_PLAN_USERNAME"), help="Username used when minting a token")
    parser.add_argument("--password", default=_first_env("KEYCLOAK_JACCLOUD_PASSWORD", "DQ_RUN_PLAN_PASSWORD"), help="Password used when minting a token")
    parser.add_argument("--ca-cert", type=Path, default=Path(os.environ.get("REQUESTS_CA_BUNDLE", "")) if os.environ.get("REQUESTS_CA_BUNDLE") else None, help="CA bundle for HTTPS API calls")
    parser.add_argument("--dry-run", action="store_true", help="Resolve configuration and write evidence without calling the API")
    parser.add_argument("--fail-on-skipped", action="store_true", help="Return non-zero when any requested engine has no configured API-backed plan")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.base_url and not args.dry_run:
        raise SystemExit("--base-url or DQ_BENCHMARK_API_BASE_URL/DQ_API_LOCAL_URL/DQ_API_INTERNAL_URL/KONG_PUBLIC_URL is required")
    if args.poll_interval_seconds <= 0:
        raise SystemExit("--poll-interval-seconds must be > 0")

    engine_plans = _configured_engine_plans(args)
    skipped_config = [plan for plan in engine_plans if not plan.run_plan_id]
    results: list[dict[str, Any]] = []

    if args.dry_run:
        results = [
            {
                "engine": plan.engine,
                "run_plan_id": plan.run_plan_id,
                "status": "configured" if plan.run_plan_id else "skipped",
                "skip_reason": None if plan.run_plan_id else "No API-backed validation run plan id configured for this engine",
            }
            for plan in engine_plans
        ]
    else:
        session = requests.Session()
        if args.ca_cert is not None and args.ca_cert.is_file():
            session.verify = str(args.ca_cert)
        token = _mint_token(session, args)
        for plan in engine_plans:
            results.append(_run_engine_plan(session, args, token=token, engine_plan=plan))

    failed = [result for result in results if result["status"] == "failed"]
    skipped = [result for result in results if result["status"] == "skipped"]
    status = "failed" if failed or (args.fail_on_skipped and skipped) else "passed"
    payload = {
        "validation": WORKFLOW_LABEL,
        "status": status,
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "api": {
            "base_url": args.base_url,
            "replay_path_template": args.replay_path_template,
            "poll_path_template": args.poll_path_template,
            "execution_contract": "All configured benchmark entries are replayed through the containerized validation-run-plan API; no local engine modules are imported or executed.",
        },
        "settings": {
            "engines": args.engines,
            "iterations": args.iterations,
            "poll_timeout_seconds": args.poll_timeout_seconds,
            "poll_interval_seconds": args.poll_interval_seconds,
            "dry_run": args.dry_run,
            "fail_on_skipped": args.fail_on_skipped,
        },
        "plan_configuration": [plan.__dict__ for plan in engine_plans],
        "summary": {
            "requested_engine_count": len(results),
            "configured_engine_count": sum(1 for plan in engine_plans if plan.run_plan_id),
            "skipped_engine_count": len(skipped_config) if args.dry_run else len(skipped),
            "failed_engine_count": len(failed),
            "passed_engine_count": sum(1 for result in results if result["status"] == "passed"),
        },
        "results": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
