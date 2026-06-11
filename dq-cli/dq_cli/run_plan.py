from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import yaml


DEFAULT_API_PREFIX = "/rulebuilder/v1"
INTERNAL_API_PREFIX = f"/api{DEFAULT_API_PREFIX}"
DATA_CATALOG_API_PREFIX = f"{DEFAULT_API_PREFIX}/data-catalog/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_PAGE_SIZE = 100


class CliError(RuntimeError):
    pass


@dataclass(slots=True)
class CliConfig:
    base_url: str
    token: str | None
    issuer_url: str | None
    client_id: str | None
    username: str | None
    password: str | None
    ca_cert: str | None
    insecure: bool
    timeout: float
    json_output: bool
    request_id: str
    correlation_id: str
    command: str
    workspace_id: str | None = None
    workspace_name: str | None = None
    business_key: str | None = None
    planning_mode: str | None = None
    scheduled_at: str | None = None
    suite_id: str | None = None
    suite_version: int | None = None
    data_object_name: str | None = None
    dataset_name: str | None = None
    data_product_name: str | None = None
    status: str | None = None
    run_plan_id: str | None = None
    run_plan_name: str | None = None
    run_plan_file: str | None = None
    output_dir: str | None = None
    data_object_id: str | None = None
    data_object_version_id: str | None = None
    dataset_id: str | None = None
    data_product_id: str | None = None


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _generated_request_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dq-run-plan", description="List, initiate, replay, and export DQ run plans.")
    parser.add_argument("--base-url", default=_env("KONG_PUBLIC_URL"), help="Base Kong URL for the API gateway.")
    parser.add_argument("--token", default=_env("DQ_RUN_PLAN_TOKEN"), help="Bearer token to use instead of password-grant auth.")
    parser.add_argument("--issuer-url", default=_env("SSO_PUBLIC_ISSUER_URL"), help="Keycloak issuer URL used for password-grant token acquisition.")
    parser.add_argument("--client-id", default=_env("VITE_KEYCLOAK_CLIENT_ID"), help="Keycloak client id for password-grant token acquisition.")
    parser.add_argument("--username", default=_env("KEYCLOAK_JACCLOUD_USERNAME"), help="Keycloak username for password-grant token acquisition.")
    parser.add_argument("--password", default=_env("KEYCLOAK_JACCLOUD_PASSWORD"), help="Keycloak password for password-grant token acquisition.")
    parser.add_argument("--ca-cert", default=_env("KONG_CA_CERT"), help="Optional CA certificate path for TLS verification.")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout in seconds.")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Emit the raw JSON response.")
    parser.add_argument("--request-id", default=None, help="Explicit Kong request id header value.")
    parser.add_argument("--correlation-id", default=None, help="Explicit correlation id header value.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List DQ run plans.")
    list_parser.add_argument("--workspace-id", default=None, help="Filter by workspace id.")
    list_parser.add_argument("--business-key", default=None, help="Filter by business key.")
    list_parser.add_argument("--suite-id", default=None, help="Filter by suite id.")
    list_parser.add_argument("--status", default=None, help="Filter by status.")

    initiate_parser = subparsers.add_parser("initiate", help="Initiate a DQ run plan.")
    initiate_parser.add_argument("--workspace-id", default=None, help="Workspace id for the run plan.")
    initiate_parser.add_argument("--workspace-name", default=None, help="Workspace name for the run plan.")
    initiate_parser.add_argument("--scheduled-at", required=True, help="ISO 8601 scheduled timestamp for the run plan.")
    initiate_parser.add_argument(
        "--planning-mode",
        default="single_suite",
        choices=["single_suite", "grouped_scope"],
        help="Planning mode for the run plan.",
    )
    initiate_parser.add_argument("--suite-id", default=None, help="Suite id for single-suite initiation.")
    initiate_parser.add_argument("--suite-version", type=int, default=None, help="Suite version for single-suite initiation.")
    initiate_parser.add_argument("--data-object-id", default=None, help="Data object id for scope resolution.")
    initiate_parser.add_argument("--data-object-name", default=None, help="Data object name for scope resolution.")
    initiate_parser.add_argument("--data-object-version-id", default=None, help="Data object version id for scope resolution.")
    initiate_parser.add_argument("--dataset-id", default=None, help="Dataset id for scope resolution.")
    initiate_parser.add_argument("--dataset-name", default=None, help="Dataset name for scope resolution.")
    initiate_parser.add_argument("--data-product-id", default=None, help="Data product id for scope resolution.")
    initiate_parser.add_argument("--data-product-name", default=None, help="Data product name for scope resolution.")

    invoke_parser = subparsers.add_parser("invoke", help="Replay a specific DQ run plan.")
    invoke_parser.add_argument("--run-plan-id", default=None, help="Run-plan id to replay.")
    invoke_parser.add_argument("--run-plan-name", default=None, help="Run-plan business key to replay.")
    invoke_parser.add_argument(
        "--run-plan-file",
        default=None,
        help="JSON or YAML file containing a DQ Validation Plan or GX Suite to replay.",
    )

    export_parser = subparsers.add_parser("export", help="Export a specific DQ run plan.")
    export_parser.add_argument("--run-plan-id", required=True, help="Run-plan id to export.")
    export_parser.add_argument("--output-dir", required=True, help="Directory where export files are written.")

    return parser


def parse_args(argv: list[str] | None = None) -> CliConfig:
    parser = build_parser()
    namespace = parser.parse_args(argv)

    if namespace.base_url is None:
        raise CliError("--base-url or KONG_PUBLIC_URL is required")

    if namespace.insecure and namespace.ca_cert:
        raise CliError("--insecure cannot be combined with --ca-cert")

    if namespace.command == "invoke":
        provided_sources = [
            _normalize_text(getattr(namespace, "run_plan_id", None)),
            _normalize_text(getattr(namespace, "run_plan_name", None)),
            _normalize_text(getattr(namespace, "run_plan_file", None)),
        ]
        source_count = sum(bool(value) for value in provided_sources)
        if source_count == 0:
            raise CliError("--run-plan-id, --run-plan-name, or --run-plan-file is required")
        if source_count > 1:
            raise CliError("Only one of --run-plan-id, --run-plan-name, or --run-plan-file may be provided")

    request_id = namespace.request_id or _generated_request_id("dq-run-plan-request")
    correlation_id = namespace.correlation_id or _generated_request_id("dq-run-plan-correlation")

    return CliConfig(
        base_url=namespace.base_url,
        token=namespace.token,
        issuer_url=namespace.issuer_url,
        client_id=namespace.client_id,
        username=namespace.username,
        password=namespace.password,
        ca_cert=namespace.ca_cert,
        insecure=bool(namespace.insecure),
        timeout=float(namespace.timeout),
        json_output=bool(namespace.json_output),
        request_id=request_id,
        correlation_id=correlation_id,
        command=str(namespace.command),
        workspace_id=getattr(namespace, "workspace_id", None),
        workspace_name=getattr(namespace, "workspace_name", None),
        business_key=getattr(namespace, "business_key", None),
        planning_mode=getattr(namespace, "planning_mode", None),
        scheduled_at=getattr(namespace, "scheduled_at", None),
        suite_id=getattr(namespace, "suite_id", None),
        suite_version=getattr(namespace, "suite_version", None),
        data_object_name=getattr(namespace, "data_object_name", None),
        dataset_name=getattr(namespace, "dataset_name", None),
        data_product_name=getattr(namespace, "data_product_name", None),
        status=getattr(namespace, "status", None),
        run_plan_id=getattr(namespace, "run_plan_id", None),
        run_plan_name=getattr(namespace, "run_plan_name", None),
        run_plan_file=getattr(namespace, "run_plan_file", None),
        output_dir=getattr(namespace, "output_dir", None),
        data_object_id=getattr(namespace, "data_object_id", None),
        data_object_version_id=getattr(namespace, "data_object_version_id", None),
        dataset_id=getattr(namespace, "dataset_id", None),
        data_product_id=getattr(namespace, "data_product_id", None),
    )


def _create_client(config: CliConfig) -> httpx.Client:
    verify: bool | str = True
    if config.insecure:
        verify = False
    elif config.ca_cert:
        if not os.path.exists(config.ca_cert):
            raise CliError(f"CA certificate not found: {config.ca_cert}")
        verify = config.ca_cert

    return httpx.Client(base_url=config.base_url.rstrip("/"), timeout=config.timeout, verify=verify)


def _require(value: str | None, flag_name: str) -> str:
    if value is None or not value.strip():
        raise CliError(f"{flag_name} is required")
    return value.strip()


def _response_data(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise CliError(f"Response was not valid JSON: {response.text.strip() or '<empty>'}") from exc


def _error_message(response: httpx.Response, context: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return f"{context}: {detail}"
        if isinstance(detail, dict):
            detail_text = json.dumps(detail, sort_keys=True)
            return f"{context}: {detail_text}"
    text = response.text.strip()
    return f"{context}: HTTP {response.status_code}{f' - {text}' if text else ''}"


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip()


def _load_yaml_or_json_file(path: Path) -> Any:
    if not path.is_file():
        raise CliError(f"Run-plan file not found: {path}")

    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CliError(f"Run-plan file was not valid JSON or YAML: {path}") from exc


def _extract_run_plan_identity(payload: Any, *, context: str) -> tuple[str | None, str | None]:
    if not isinstance(payload, dict):
        raise CliError(f"{context} did not contain a JSON or YAML object")

    run_plan_id = _normalize_text(payload.get("run_plan_id") or payload.get("runPlanId"))
    business_key = _normalize_text(payload.get("business_key") or payload.get("businessKey"))
    if run_plan_id or business_key:
        return run_plan_id or None, business_key or None

    for nested_key in (
        "validation_run_plan",
        "validationRunPlan",
        "gx_run_plan",
        "gxRunPlan",
        "run_plan",
        "runPlan",
        "plan",
    ):
        nested_payload = payload.get(nested_key)
        if isinstance(nested_payload, dict):
            return _extract_run_plan_identity(nested_payload, context=context)
        if isinstance(nested_payload, list):
            nested_objects = [item for item in nested_payload if isinstance(item, dict)]
            if len(nested_objects) == 1:
                return _extract_run_plan_identity(nested_objects[0], context=context)
            if len(nested_objects) > 1:
                raise CliError(f"{context} contained multiple run plans; provide a file with a single run plan")

    for nested_key in ("validation_run_plans", "validationRunPlans"):
        nested_payload = payload.get(nested_key)
        if isinstance(nested_payload, list):
            nested_objects = [item for item in nested_payload if isinstance(item, dict)]
            if len(nested_objects) == 1:
                nested_run_plan_id, nested_business_key = _extract_run_plan_identity(nested_objects[0], context=context)
                if nested_run_plan_id or nested_business_key:
                    return nested_run_plan_id, nested_business_key
                continue
            if len(nested_objects) > 1:
                raise CliError(f"{context} contained multiple run plans; provide a file with a single run plan")

    return None, None


def _extract_gx_suite_identity(payload: Any, *, context: str) -> tuple[str | None, int | None]:
    if not isinstance(payload, dict):
        raise CliError(f"{context} did not contain a JSON or YAML object")

    candidate_suite_id = _normalize_text(payload.get("gx_suite_id") or payload.get("gxSuiteId"))
    candidate_suite_version = payload.get("gx_suite_version") or payload.get("gxSuiteVersion")
    if candidate_suite_id:
        return candidate_suite_id, int(candidate_suite_version) if candidate_suite_version not in (None, "") else None

    candidate_suite_id = _normalize_text(payload.get("suite_id") or payload.get("suiteId"))
    candidate_suite_version = payload.get("suite_version") or payload.get("suiteVersion")
    if candidate_suite_id:
        return candidate_suite_id, int(candidate_suite_version) if candidate_suite_version not in (None, "") else None

    for nested_key in ("executionContract", "execution_contract"):
        execution_contract = payload.get(nested_key)
        if not isinstance(execution_contract, dict):
            continue
        for traceability_key in ("traceability",):
            traceability = execution_contract.get(traceability_key)
            if not isinstance(traceability, dict):
                continue
            candidate_suite_id = _normalize_text(
                traceability.get("gxSuiteId")
                or traceability.get("gx_suite_id")
                or traceability.get("suite_id")
                or traceability.get("suiteId")
            )
            if not candidate_suite_id:
                continue
            candidate_suite_version = (
                traceability.get("gxSuiteVersion")
                or traceability.get("gx_suite_version")
                or traceability.get("suite_version")
                or traceability.get("suiteVersion")
            )
            return (
                candidate_suite_id,
                int(candidate_suite_version) if candidate_suite_version not in (None, "") else None,
            )

    return None, None


def _fetch_json(client: httpx.Client, config: CliConfig, token: str, path: str, *, params: dict[str, Any] | None = None, context: str) -> Any:
    response = client.get(path, params=params or {}, headers=_build_headers(config, token))
    if response.status_code != 200:
        raise CliError(_error_message(response, context))
    return _response_data(response)


def _payload_items(payload: Any, *, context: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise CliError(f"{context} was not a JSON object")

    for key in (
        "data",
        "items",
        "results",
        "workspaces",
        "data_products",
        "data_sets",
        "data_objects",
        "validation_run_plans",
        "validation_suites",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    raise CliError(f"{context} did not contain a list payload")


def _fetch_paginated_items(
    client: httpx.Client,
    config: CliConfig,
    token: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    context: str,
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = _fetch_json(
            client,
            config,
            token,
            path,
            params={**(params or {}), "page": page, "limit": DEFAULT_PAGE_SIZE},
            context=context,
        )
        collected.extend(_payload_items(payload, context=context))
        pagination = payload.get("pagination") if isinstance(payload, dict) else None
        has_next = False
        if isinstance(pagination, dict):
            has_next = bool(pagination.get("has_next"))
        elif pagination is not None:
            has_next = bool(getattr(pagination, "has_next", False))
        if not has_next:
            break
        page += 1
    return collected


def _resolve_named_entity(
    *,
    label: str,
    requested_name: str | None,
    requested_id: str | None,
    candidates: list[dict[str, Any]],
) -> str | None:
    normalized_name = _normalize_text(requested_name)
    normalized_id = _normalize_text(requested_id)
    if not normalized_name:
        return normalized_id or None

    matches = [candidate for candidate in candidates if _normalize_text(candidate.get("name")) == normalized_name]
    if not matches:
        raise CliError(f"{label} '{requested_name}' was not found")

    if len(matches) > 1:
        matching_ids = ", ".join(_normalize_text(match.get("id")) for match in matches[:5])
        raise CliError(f"{label} '{requested_name}' is ambiguous; matching ids: {matching_ids}")

    resolved_id = _normalize_text(matches[0].get("id"))
    if normalized_id and normalized_id != resolved_id:
        raise CliError(f"{label} name '{requested_name}' resolves to id '{resolved_id}', not '{requested_id}'")
    return resolved_id


def _resolve_workspace_id(client: httpx.Client, config: CliConfig, token: str) -> str:
    if not _normalize_text(config.workspace_name):
        return _require(config.workspace_id, "--workspace-id or --workspace-name")

    return _resolve_named_entity(
        label="Workspace",
        requested_name=config.workspace_name,
        requested_id=config.workspace_id,
        candidates=_fetch_paginated_items(
            client,
            config,
            token,
            f"{DEFAULT_API_PREFIX}/workspaces",
            context="Workspace list request failed",
        ),
    ) or _require(config.workspace_id, "--workspace-id or --workspace-name")


def _resolve_data_product_id(client: httpx.Client, config: CliConfig, token: str, workspace_id: str) -> str | None:
    if not _normalize_text(config.data_product_name):
        return _normalize_text(config.data_product_id) or None

    return _resolve_named_entity(
        label="Data product",
        requested_name=config.data_product_name,
        requested_id=config.data_product_id,
        candidates=_fetch_paginated_items(
            client,
            config,
            token,
            f"{DATA_CATALOG_API_PREFIX}/data-products",
            params={"workspace": workspace_id},
            context="Data product list request failed",
        ),
    )


def _resolve_dataset_id(client: httpx.Client, config: CliConfig, token: str, workspace_id: str, data_product_id: str | None) -> str | None:
    if not _normalize_text(config.dataset_name):
        return _normalize_text(config.dataset_id) or None

    params: dict[str, Any] = {"workspace": workspace_id}
    if data_product_id is not None:
        params["productId"] = data_product_id
    return _resolve_named_entity(
        label="Dataset",
        requested_name=config.dataset_name,
        requested_id=config.dataset_id,
        candidates=_fetch_paginated_items(
            client,
            config,
            token,
            f"{DATA_CATALOG_API_PREFIX}/data-sets",
            params=params,
            context="Dataset list request failed",
        ),
    )


def _resolve_data_object_id(
    client: httpx.Client,
    config: CliConfig,
    token: str,
    workspace_id: str,
    data_product_id: str | None,
    dataset_id: str | None,
) -> str | None:
    if not _normalize_text(config.data_object_name):
        return _normalize_text(config.data_object_id) or None

    if dataset_id is not None:
        candidates = _fetch_paginated_items(
            client,
            config,
            token,
            f"{DATA_CATALOG_API_PREFIX}/data-objects-catalog",
            params={"dataSetId": dataset_id},
            context="Data object catalog request failed",
        )
    else:
        dataset_rows = _fetch_paginated_items(
            client,
            config,
            token,
            f"{DATA_CATALOG_API_PREFIX}/data-sets",
            params={"workspace": workspace_id, **({"productId": data_product_id} if data_product_id is not None else {})},
            context="Dataset list request failed",
        )
        candidates = []
        for dataset in dataset_rows:
            dataset_candidates = _fetch_paginated_items(
                client,
                config,
                token,
                f"{DATA_CATALOG_API_PREFIX}/data-objects-catalog",
                params={"dataSetId": _normalize_text(dataset.get("id"))},
                context="Data object catalog request failed",
            )
            candidates.extend(dataset_candidates)

    return _resolve_named_entity(
        label="Data object",
        requested_name=config.data_object_name,
        requested_id=config.data_object_id,
        candidates=candidates,
    )


def _build_headers(config: CliConfig, token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Kong-Request-Id": config.request_id,
        "X-Correlation-ID": config.correlation_id,
    }


def _acquire_access_token(client: httpx.Client, config: CliConfig) -> str:
    token = config.token
    if token is not None and token.strip():
        return token.strip()

    issuer_url = _require(config.issuer_url, "--issuer-url or SSO_PUBLIC_ISSUER_URL")
    client_id = _require(config.client_id, "--client-id or VITE_KEYCLOAK_CLIENT_ID")
    username = _require(config.username, "--username or KEYCLOAK_JACCLOUD_USERNAME")
    password = _require(config.password, "--password or KEYCLOAK_JACCLOUD_PASSWORD")

    token_url = issuer_url.rstrip("/") + "/protocol/openid-connect/token"
    response = client.post(
        token_url,
        data={
            "grant_type": "password",
            "client_id": client_id,
            "username": username,
            "password": password,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code >= 400:
        raise CliError(_error_message(response, "Keycloak token request failed"))

    payload = _response_data(response)
    if not isinstance(payload, dict):
        raise CliError("Keycloak token response was not a JSON object")

    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise CliError("Keycloak token response did not include access_token")
    return access_token.strip()


def _run_list(client: httpx.Client, config: CliConfig, token: str | None = None) -> dict[str, Any]:
    params: dict[str, str] = {}
    if config.workspace_id is not None:
        params["workspaceId"] = config.workspace_id
    if config.business_key is not None:
        params["businessKey"] = config.business_key
    if config.suite_id is not None:
        params["suiteId"] = config.suite_id
    if config.status is not None:
        params["status"] = config.status

    response = client.get(
        f"{DEFAULT_API_PREFIX}/run-plan",
        params=params,
        headers=_build_headers(config, token or _acquire_access_token(client, config)),
    )
    if response.status_code != 200:
        raise CliError(_error_message(response, "Run-plan list request failed"))

    payload = _response_data(response)
    if not isinstance(payload, dict):
        raise CliError("Run-plan list response was not a JSON object")
    return payload


def _select_run_plan_by_business_key(catalog: dict[str, Any], business_key: str) -> dict[str, Any]:
    normalized_business_key = _normalize_text(business_key)
    matches = [run_plan for run_plan in catalog.get("validation_run_plans", []) if isinstance(run_plan, dict) and _normalize_text(run_plan.get("business_key")) == normalized_business_key]
    if not matches:
        raise CliError(f"Run-plan '{business_key}' was not found in the catalog")
    if len(matches) > 1:
        matching_ids = ", ".join(_normalize_text(match.get("run_plan_id")) for match in matches[:5])
        raise CliError(f"Run-plan '{business_key}' is ambiguous; matching ids: {matching_ids}")
    return matches[0]


def _resolve_run_plan_id_by_business_key(client: httpx.Client, config: CliConfig, token: str, business_key: str) -> str:
    catalog_config = replace(config, business_key=business_key)
    catalog = _load_catalog(client, catalog_config, token)
    selected_plan = _select_run_plan_by_business_key(catalog, business_key)
    return _require(selected_plan.get("run_plan_id"), f"Run-plan '{business_key}'")


def _resolve_run_plan_id_by_gx_suite_identity(
    client: httpx.Client,
    config: CliConfig,
    token: str,
    suite_id: str,
    suite_version: int | None,
) -> str:
    catalog = _load_catalog(client, config, token)
    normalized_suite_id = _normalize_text(suite_id)
    normalized_suite_version = _normalize_text(str(suite_version)) if suite_version is not None else None
    matching_run_plan_ids: list[str] = []

    for suite in catalog.get("validation_suites", []):
        if not isinstance(suite, dict):
            continue
        candidate_suite_id = _normalize_text(suite.get("artifact_id") or suite.get("suite_id"))
        if candidate_suite_id != normalized_suite_id:
            continue
        candidate_suite_version = _normalize_text(suite.get("artifact_version") or suite.get("suite_version"))
        if normalized_suite_version is not None and candidate_suite_version != normalized_suite_version:
            continue
        candidate_run_plan_id = _normalize_text(suite.get("run_plan_id"))
        if candidate_run_plan_id:
            matching_run_plan_ids.append(candidate_run_plan_id)

    if not matching_run_plan_ids:
        for run_plan in catalog.get("validation_run_plans", []):
            if not isinstance(run_plan, dict):
                continue
            candidate_run_plan_id = _normalize_text(run_plan.get("run_plan_id"))
            if not candidate_run_plan_id:
                continue
            versions = run_plan.get("versions") or []
            if not isinstance(versions, list):
                continue
            for version in versions:
                if not isinstance(version, dict):
                    continue
                artifact_id = _normalize_text(version.get("artifact_id"))
                artifact_version = _normalize_text(version.get("artifact_version"))
                if artifact_id == normalized_suite_id and (
                    normalized_suite_version is None or artifact_version == normalized_suite_version
                ):
                    matching_run_plan_ids.append(candidate_run_plan_id)
                    break
                artifact_snapshot = version.get("artifact_snapshot")
                if isinstance(artifact_snapshot, dict):
                    snapshot_suite_id = _normalize_text(artifact_snapshot.get("suiteId") or artifact_snapshot.get("suite_id"))
                    snapshot_suite_version = _normalize_text(
                        artifact_snapshot.get("suiteVersion") or artifact_snapshot.get("suite_version")
                    )
                    if snapshot_suite_id == normalized_suite_id and (
                        normalized_suite_version is None or snapshot_suite_version == normalized_suite_version
                    ):
                        matching_run_plan_ids.append(candidate_run_plan_id)
                        break

    unique_run_plan_ids = sorted(set(matching_run_plan_ids))
    if not unique_run_plan_ids:
        if normalized_suite_version is None:
            raise CliError(f"Run-plan for GX suite '{suite_id}' was not found in the catalog")
        raise CliError(f"Run-plan for GX suite '{suite_id}' version '{suite_version}' was not found in the catalog")

    if len(unique_run_plan_ids) > 1:
        matching_ids = ", ".join(unique_run_plan_ids[:5])
        if normalized_suite_version is None:
            raise CliError(f"Run-plan for GX suite '{suite_id}' is ambiguous; matching ids: {matching_ids}")
        raise CliError(
            f"Run-plan for GX suite '{suite_id}' version '{suite_version}' is ambiguous; matching ids: {matching_ids}"
        )

    return unique_run_plan_ids[0]


def _resolve_invoke_run_plan_id(client: httpx.Client, config: CliConfig, token: str) -> str:
    if _normalize_text(config.run_plan_id):
        return _require(config.run_plan_id, "--run-plan-id")

    if _normalize_text(config.run_plan_file):
        plan_file = Path(_require(config.run_plan_file, "--run-plan-file")).expanduser()
        payload = _load_yaml_or_json_file(plan_file)
        run_plan_id, business_key = _extract_run_plan_identity(payload, context=f"Run-plan file {plan_file}")
        if run_plan_id:
            return run_plan_id
        if business_key:
            return _resolve_run_plan_id_by_business_key(client, config, token, business_key)
        gx_suite_id, gx_suite_version = _extract_gx_suite_identity(payload, context=f"Run-plan file {plan_file}")
        if gx_suite_id:
            return _resolve_run_plan_id_by_gx_suite_identity(client, config, token, gx_suite_id, gx_suite_version)
        raise CliError(f"Run-plan file {plan_file} did not include run_plan_id, business_key, or GX suite traceability")

    run_plan_name = _require(config.run_plan_name, "--run-plan-name")
    return _resolve_run_plan_id_by_business_key(client, config, token, run_plan_name)


def _load_catalog(client: httpx.Client, config: CliConfig, token: str | None = None) -> dict[str, Any]:
    payload = _run_list(client, config, token)
    if not isinstance(payload, dict):
        raise CliError("Run-plan catalog response was not a JSON object")
    return payload


def _select_run_plan(catalog: dict[str, Any], run_plan_id: str) -> dict[str, Any]:
    for run_plan in catalog.get("validation_run_plans", []):
        if isinstance(run_plan, dict) and str(run_plan.get("run_plan_id") or "").strip() == run_plan_id:
            return run_plan
    raise CliError(f"Run-plan '{run_plan_id}' was not found in the catalog")


def _is_gx_only_run_plan(catalog: dict[str, Any], run_plan_id: str) -> bool:
    matching_suites = [suite for suite in catalog.get("validation_suites", []) if isinstance(suite, dict) and str(suite.get("run_plan_id") or "").strip() == run_plan_id]
    if not matching_suites:
        return False
    for suite in matching_suites:
        if str(suite.get("engine_type") or "").strip().lower() != "gx":
            return False
    return True


def _run_get_gx_run_plan(client: httpx.Client, config: CliConfig, run_plan_id: str) -> dict[str, Any]:
    token = _acquire_access_token(client, config)
    response = client.get(
        f"{DEFAULT_API_PREFIX}/gx/run-plans/{run_plan_id}",
        headers=_build_headers(config, token),
    )
    if response.status_code != 200:
        raise CliError(_error_message(response, "GX run-plan export request failed"))

    payload = _response_data(response)
    if not isinstance(payload, dict):
        raise CliError("GX run-plan export response was not a JSON object")
    return payload


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise CliError(f"Export target already exists: {path}")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_export(client: httpx.Client, config: CliConfig) -> dict[str, Any]:
    run_plan_id = _require(config.run_plan_id, "--run-plan-id")
    output_dir = Path(_require(config.output_dir, "--output-dir"))
    if output_dir.exists() and not output_dir.is_dir():
        raise CliError(f"Export target must be a directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    token = _acquire_access_token(client, config)
    catalog = _load_catalog(client, config, token)
    selected_plan = _select_run_plan(catalog, run_plan_id)
    neutral_plan_payload = selected_plan

    neutral_path = output_dir / "validation-run-plan.json"
    _write_json_file(neutral_path, neutral_plan_payload)

    exported_files = [str(neutral_path)]
    gx_exported = False

    if _is_gx_only_run_plan(catalog, run_plan_id):
        gx_path = output_dir / "gx-run-plan.json"
        gx_payload = _run_get_gx_run_plan(client, config, run_plan_id)
        _write_json_file(gx_path, gx_payload)
        exported_files.append(str(gx_path))
        gx_exported = True

    return {
        "run_plan_id": run_plan_id,
        "export_dir": str(output_dir),
        "exported_files": exported_files,
        "gx_run_plan_exported": gx_exported,
    }


def _run_initiate(client: httpx.Client, config: CliConfig) -> dict[str, Any]:
    token = _acquire_access_token(client, config)
    workspace_id = _resolve_workspace_id(client, config, token)
    data_product_id = _resolve_data_product_id(client, config, token, workspace_id)
    dataset_id = _resolve_dataset_id(client, config, token, workspace_id, data_product_id)
    data_object_id = _resolve_data_object_id(client, config, token, workspace_id, data_product_id, dataset_id)
    request_body = {
        "workspace_id": workspace_id,
        "planning_mode": config.planning_mode or "single_suite",
        "suite_id": config.suite_id,
        "suite_version": config.suite_version,
        "scheduled_at": _require(config.scheduled_at, "--scheduled-at"),
        "data_object_id": data_object_id or config.data_object_id,
        "data_object_version_id": config.data_object_version_id,
        "dataset_id": dataset_id or config.dataset_id,
        "data_product_id": data_product_id or config.data_product_id,
    }

    response = client.post(
        f"{DEFAULT_API_PREFIX}/gx/run-plans/initiate",
        json={key: value for key, value in request_body.items() if value is not None},
        headers=_build_headers(config, token),
    )
    if response.status_code != 201:
        raise CliError(_error_message(response, "Run-plan initiation request failed"))

    payload = _response_data(response)
    if not isinstance(payload, dict):
        raise CliError("Run-plan initiation response was not a JSON object")

    returned_run_plan_id = payload.get("run_plan_id")
    if not isinstance(returned_run_plan_id, str) or not returned_run_plan_id.strip():
        raise CliError("Run-plan initiation response did not include run_plan_id")

    return payload


def _run_invoke(client: httpx.Client, config: CliConfig) -> dict[str, Any]:
    token = _acquire_access_token(client, config)
    run_plan_id = _resolve_invoke_run_plan_id(client, config, token)

    response = client.post(
        f"{INTERNAL_API_PREFIX}/validation-run-plans/{run_plan_id}/replay",
        headers=_build_headers(config, token),
    )
    if response.status_code != 202:
        raise CliError(_error_message(response, "Run-plan replay request failed"))

    payload = _response_data(response)
    if not isinstance(payload, dict):
        raise CliError("Run-plan replay response was not a JSON object")

    returned_run_plan_id = payload.get("run_plan_id")
    if returned_run_plan_id != run_plan_id:
        raise CliError(f"Run-plan replay response returned run_plan_id={returned_run_plan_id!r}, expected {run_plan_id!r}")

    if not isinstance(payload.get("queue_message_id"), str) or not payload["queue_message_id"].strip():
        raise CliError("Run-plan replay response did not include queue_message_id")

    if not isinstance(payload.get("run_id"), str) or not payload["run_id"].strip():
        raise CliError("Run-plan replay response did not include run_id")

    return payload


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _print_list_text(payload: dict[str, Any]) -> None:
    summary = payload.get("validation_summary") if isinstance(payload.get("validation_summary"), dict) else {}
    run_plan_count = summary.get("run_plan_count", 0)
    suite_count = summary.get("suite_count", 0)
    print(f"DQ run plans: {run_plan_count} plan(s), {suite_count} suite(s)")
    for run_plan in payload.get("validation_run_plans", []):
        if not isinstance(run_plan, dict):
            continue
        print(
            "- {run_plan_id} status={status} workspace_id={workspace_id} business_key={business_key} active_version_id={current_active_version_id}".format(
                run_plan_id=run_plan.get("run_plan_id", ""),
                status=run_plan.get("status", ""),
                workspace_id=run_plan.get("workspace_id", ""),
                business_key=run_plan.get("business_key", ""),
                current_active_version_id=run_plan.get("current_active_version_id", ""),
            )
        )


def _print_invoke_text(payload: dict[str, Any]) -> None:
    print("DQ run plan replay accepted")
    print(f"- run_plan_id: {payload.get('run_plan_id', '')}")
    print(f"- run_id: {payload.get('run_id', '')}")
    print(f"- queue_message_id: {payload.get('queue_message_id', '')}")
    print(f"- run_plan_version_id: {payload.get('run_plan_version_id', '')}")
    print(f"- scheduled_at: {payload.get('scheduled_at', '')}")


def _print_initiate_text(payload: dict[str, Any]) -> None:
    print("DQ run plan initiation accepted")
    print(f"- run_plan_id: {payload.get('run_plan_id', '')}")
    print(f"- workspace_id: {payload.get('workspace_id', '')}")
    print(f"- planning_mode: {payload.get('planning_mode', '')}")
    print(f"- status: {payload.get('status', '')}")


def execute(config: CliConfig) -> dict[str, Any]:
    with _create_client(config) as client:
        if config.command == "list":
            return _run_list(client, config)
        if config.command == "initiate":
            return _run_initiate(client, config)
        if config.command == "invoke":
            return _run_invoke(client, config)
        if config.command == "export":
            return _run_export(client, config)
        raise CliError(f"Unsupported command: {config.command}")


def main(argv: list[str] | None = None) -> int:
    try:
        config = parse_args(argv)
        payload = execute(config)
        if config.json_output:
            _print_json(payload)
        elif config.command == "list":
            _print_list_text(payload)
        elif config.command == "initiate":
            _print_initiate_text(payload)
        elif config.command == "export":
            print(f"Exported run plan to {payload['export_dir']}")
            for exported_file in payload.get("exported_files", []):
                print(f"- {exported_file}")
            if payload.get("gx_run_plan_exported"):
                print("- GX companion export created")
        else:
            _print_invoke_text(payload)
        return 0
    except CliError as exc:
        print(f"dq-run-plan: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())