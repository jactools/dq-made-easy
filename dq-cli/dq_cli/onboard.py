"""CLI command for onboarding rules via the proposal API.

Supports generating rule proposals for a workspace and optionally creating
a batch of draft rules from selected proposals.

Usage:
  dq-onboard --env dev --workspace "Retail Banking"
  dq-onboard --env dev --workspace "Retail Banking" --template "completeness-1" --submit
  dq-onboard --env prod --workspace-id "ws-123" --all --submit
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx


DEFAULT_API_PREFIX = "/rulebuilder/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0


class CliError(RuntimeError):
    pass


@dataclass(slots=True)
class OnboardConfig:
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
    workspace_id: str | None
    workspace_name: str | None
    template_filter: str | None
    all_proposals: bool
    dry_run: bool
    submit: bool


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _generated_request_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dq-onboard",
        description="Generate and optionally submit rule onboarding proposals for a workspace.",
    )
    parser.add_argument("--base-url", default=_env("KONG_PUBLIC_URL"), help="Base Kong URL for the API gateway.")
    parser.add_argument("--token", default=_env("DQ_ONBOARD_TOKEN"), help="Bearer token to use instead of password-grant auth.")
    parser.add_argument("--issuer-url", default=_env("SSO_PUBLIC_ISSUER_URL"), help="Keycloak issuer URL for password-grant token acquisition.")
    parser.add_argument("--client-id", default=_env("VITE_KEYCLOAK_CLIENT_ID"), help="Keycloak client id for password-grant token acquisition.")
    parser.add_argument("--username", default=_env("KEYCLOAK_JACCLOUD_USERNAME"), help="Keycloak username for password-grant token acquisition.")
    parser.add_argument("--password", default=_env("KEYCLOAK_JACCLOUD_PASSWORD"), help="Keycloak password for password-grant token acquisition.")
    parser.add_argument("--ca-cert", default=_env("KONG_CA_CERT"), help="Optional CA certificate path for TLS verification.")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout in seconds.")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Emit raw JSON responses.")
    parser.add_argument("--request-id", default=None, help="Explicit Kong request id header value.")
    parser.add_argument("--correlation-id", default=None, help="Explicit correlation id header value.")
    parser.add_argument("--workspace-id", default=None, help="Workspace id (or use --workspace for name-based resolution).")
    parser.add_argument("--workspace", dest="workspace_name", default=None, help="Workspace name (resolved via API).")
    parser.add_argument("--template", dest="template_filter", default=None, help="Optional template_id filter for proposals.")
    parser.add_argument("--all", dest="all_proposals", action="store_true", help="Include all uncovered proposals (default: first only).")
    parser.add_argument("--dry-run", action="store_true", help="Show proposals without creating a batch.")
    parser.add_argument("--submit", action="store_true", help="Create the batch after generating proposals.")

    return parser


def parse_args(argv: list[str] | None = None) -> OnboardConfig:
    parser = build_parser()
    namespace = parser.parse_args(argv)

    base_url = namespace.base_url
    if not base_url:
        raise CliError("--base-url or KONG_PUBLIC_URL is required")

    if not namespace.workspace_id and not namespace.workspace_name:
        raise CliError("--workspace-id or --workspace is required")

    request_id = namespace.request_id or _generated_request_id("dq-onboard-request")
    correlation_id = namespace.correlation_id or _generated_request_id("dq-onboard-correlation")

    return OnboardConfig(
        base_url=base_url.rstrip("/"),
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
        workspace_id=namespace.workspace_id,
        workspace_name=namespace.workspace_name,
        template_filter=namespace.template_filter,
        all_proposals=bool(namespace.all_proposals),
        dry_run=bool(namespace.dry_run),
        submit=bool(namespace.submit),
    )


def _create_client(config: OnboardConfig) -> httpx.Client:
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


def _get_token(config: OnboardConfig, client: httpx.Client) -> str:
    if config.token:
        return config.token

    issuer_url = _require(config.issuer_url, "--issuer-url or SSO_PUBLIC_ISSUER_URL")
    client_id = _require(config.client_id, "--client-id or VITE_KEYCLOAK_CLIENT_ID")
    username = _require(config.username, "--username or KEYCLOAK_JACCLOUD_USERNAME")
    password = _require(config.password, "--password or KEYCLOAK_JACCLOUD_PASSWORD")

    token_response = client.post(
        f"{issuer_url.rstrip('/')}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": client_id,
            "username": username,
            "password": password,
        },
    )

    if token_response.status_code != 200:
        raise CliError(_error_message(token_response, "Failed to acquire token"))

    data = _response_data(token_response)
    token = data.get("access_token")
    if not token:
        raise CliError("Token response did not include access_token")
    return token


def _resolve_workspace_id(config: OnboardConfig, client: httpx.Client, token: str) -> str:
    """Resolve workspace name to workspace ID via GET /workspaces endpoint."""
    if config.workspace_id:
        return config.workspace_id

    workspace_name = _require(config.workspace_name, "--workspace or --workspace-id")

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Request-ID": config.request_id,
        "X-Correlation-ID": config.correlation_id,
    }

    # Call GET /workspaces endpoint
    response = client.get(
        f"{DEFAULT_API_PREFIX}/workspaces",
        headers=headers,
    )

    if response.status_code != 200:
        raise CliError(_error_message(response, "Failed to list workspaces"))

    data = _response_data(response)
    workspaces = data.get("data", [])
    for ws in workspaces:
        if ws.get("name") == workspace_name:
            ws_id = ws.get("id")
            if ws_id:
                return ws_id

    raise CliError(f"Workspace not found: {workspace_name}")


def _print(text: str) -> None:
    """Print to stdout, respecting JSON-only mode."""
    print(text, file=sys.stdout)


def _log(text: str) -> None:
    """Print to stderr for status messages."""
    print(text, file=sys.stderr)


def run_onboard(config: OnboardConfig) -> int:
    """Execute the onboarding workflow: scope-summary → generate-proposals → [create-batch]."""
    try:
        client = _create_client(config)
        token = _get_token(config, client)
        workspace_id = _resolve_workspace_id(config, client, token)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Request-ID": config.request_id,
            "X-Correlation-ID": config.correlation_id,
        }

        # Step 1: scope-summary
        if not config.json_output:
            _log("[1/3] Fetching scope summary...")

        scope_summary_payload = {
            "scope_type": "workspace",
            "scope_id": workspace_id,
            "workspace_id": workspace_id,
        }
        scope_response = client.post(
            f"{DEFAULT_API_PREFIX}/onboarding/scope-summary",
            json=scope_summary_payload,
            headers=headers,
        )
        if scope_response.status_code != 200:
            raise CliError(_error_message(scope_response, "scope-summary failed"))

        scope_data = _response_data(scope_response)
        attribute_count = scope_data.get("attribute_count", 0)
        if not config.json_output:
            _log(f"  Found {attribute_count} attributes in workspace {workspace_id}")

        # Step 2: generate-proposals
        if not config.json_output:
            _log("[2/3] Generating proposals...")

        proposals_payload = {
            "scope_type": "workspace",
            "scope_id": workspace_id,
            "workspace_id": workspace_id,
        }
        proposals_response = client.post(
            f"{DEFAULT_API_PREFIX}/onboarding/generate-proposals",
            json=proposals_payload,
            headers=headers,
        )
        if proposals_response.status_code != 200:
            raise CliError(_error_message(proposals_response, "generate-proposals failed"))

        proposals_data = _response_data(proposals_response)
        total_proposals = proposals_data.get("total_proposals", 0)
        if not config.json_output:
            _log(f"  Generated {total_proposals} proposals")

        # Extract proposal IDs (uncovered only), optionally filtered by template name
        all_proposal_ids = []
        template_counts: dict[str, int] = {}

        for tg in proposals_data.get("proposals", []):
            template_id = tg.get("template_id", "")
            template_name = tg.get("template_name", "")

            # Skip if template filter is specified and template doesn't match
            if config.template_filter and config.template_filter.lower() not in template_name.lower():
                continue

            for og_list in tg.get("by_dataset", {}).values():
                for og in og_list:
                    for attr in og.get("attributes", []):
                        if not attr.get("already_covered", False):
                            proposal_id = f"{template_id}::{og.get('data_object_version_id')}::{attr.get('attribute_id')}"
                            all_proposal_ids.append(proposal_id)
                            template_counts[template_name] = template_counts.get(template_name, 0) + 1

        if not config.json_output:
            _log("\n  Proposals by template:")
            for tname in sorted(template_counts.keys()):
                _log(f"    {tname}: {template_counts[tname]}")
            if config.template_filter:
                _log(f"\n  Filtered to {len(all_proposal_ids)} proposals matching template '{config.template_filter}'")

        # Select proposals: all if --all, first if not filtering, or filtered set
        selected_proposal_ids = all_proposal_ids[:1] if not config.all_proposals and not config.template_filter else all_proposal_ids

        if not selected_proposal_ids:
            if not config.json_output:
                _log("  No proposals to submit.")
            return 0

        if not config.json_output:
            _log(f"\n  Selected {len(selected_proposal_ids)} proposal(s) for batch")

        # Dry-run mode: stop here
        if config.dry_run or not config.submit:
            if config.json_output:
                output = {
                    "workspace_id": workspace_id,
                    "attribute_count": attribute_count,
                    "total_proposals": total_proposals,
                    "selected_proposals": selected_proposal_ids,
                    "dry_run": config.dry_run,
                }
                _print(json.dumps(output, indent=2))
            return 0

        # Step 3: create-batch
        if not config.json_output:
            _log(f"\n[3/3] Creating batch ({len(selected_proposal_ids)} proposal(s))...")

        batch_payload = {
            "workspace_id": workspace_id,
            "accepted_proposal_ids": selected_proposal_ids,
        }
        batch_response = client.post(
            f"{DEFAULT_API_PREFIX}/onboarding/create-batch",
            json=batch_payload,
            headers=headers,
        )
        if batch_response.status_code != 200:
            raise CliError(_error_message(batch_response, "create-batch failed"))

        batch_data = _response_data(batch_response)
        batch_id = batch_data.get("batch_id")
        created = batch_data.get("created", 0)
        skipped = batch_data.get("skipped", 0)
        failed = batch_data.get("failed", 0)

        if config.json_output:
            _print(json.dumps(batch_data, indent=2))
        else:
            _log(f"  Batch {batch_id}: created={created} skipped={skipped} failed={failed}")
            _log("\nOnboarding complete!")

        return 0

    except CliError as exc:
        _log(f"Error: {exc}")
        return 1
    except Exception as exc:
        _log(f"Unexpected error: {exc}")
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    """Entry point for dq-onboard command."""
    config = parse_args(argv)
    return run_onboard(config)


if __name__ == "__main__":
    sys.exit(main())
