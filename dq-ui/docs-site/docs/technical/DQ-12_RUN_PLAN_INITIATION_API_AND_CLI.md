# DQ-12 Run Plan Initiation API and Package CLI

This guide covers the implemented run-plan initiation and replay surface for dq-made-easy. It documents the standalone dq-made-easy-cli package entry point, the matching initiation route, and the configuration required to launch a DQ run plan from another application or from an operator shell.

The canonical external initiation flow is:

- `dq-run-plan initiate` for package CLI callers
- `POST /rulebuilder/v1/gx/run-plans/initiate` for HTTP callers

Both entry points reuse the same run-plan creation contract and fail fast when required configuration, authentication, or payload fields are missing.

Replay is not part of the public gateway-facing run-plan surface. Replay is an internal orchestration path that uses:

- `dq-run-plan invoke` for package CLI callers that can reach the internal API surface
- `POST /api/rulebuilder/v1/validation-run-plans/&#123;run_plan_id&#125;/replay` for HTTP callers on the internal API surface

The CLI accepts name aliases for the workspace and grouped-scope selectors:

- `--workspace-name`
- `--data-product-name`
- `--dataset-name`
- `--data-object-name`

Those aliases are resolved against the existing workspace and data-catalog APIs before the canonical ids are sent to the initiation route.

## Command surface

### `list`

Lists existing DQ run plans.

Supported filters:

- `--workspace-id`
- `--business-key`
- `--suite-id`
- `--status`

### `initiate`

Creates a new run plan for an external caller.

Required inputs:

- `--workspace-id` or `--workspace-name`
- `--scheduled-at`

Planning options:

- `--planning-mode` defaults to `single_suite`
- `single_suite` callers provide `--suite-id` and may provide `--suite-version`
- `grouped_scope` callers can resolve scope with `--data-object-id`, `--data-object-version-id`, `--dataset-id`, or `--data-product-id`

### `invoke`

Replays an existing run plan by id, business key, or exported plan file.

This command targets the internal validation-plan replay route rather than the public gateway-facing run-plan wrapper.

Supported replay inputs:

- `--run-plan-id`
- `--run-plan-name`
- `--run-plan-file`

The file input can point at a JSON or YAML document that contains a complete DQ Validation Plan or a GX Suite export. The CLI extracts the canonical run-plan id from the file and replays that plan.

### `export`

Exports an existing run plan to a directory on disk.

Required inputs:

- `--run-plan-id`
- `--output-dir`

## Examples

Initiate a single-suite run plan with ids:

```bash
dq-run-plan initiate \
	--workspace-id workspace-1 \
	--scheduled-at 2026-05-22T20:00:00Z \
	--suite-id gx_suite_1 \
	--suite-version 1
```

Initiate a grouped-scope run plan with names:

```bash
dq-run-plan initiate \
	--workspace-name "Sales Workspace" \
	--scheduled-at 2026-05-22T20:00:00Z \
	--planning-mode grouped_scope \
	--data-product-name "Sales Product" \
	--dataset-name "Orders Dataset" \
	--data-object-name "Orders Table"
```

Export a run plan for offline inspection:

```bash
dq-run-plan export \
	--run-plan-id run-plan-1 \
	--output-dir ./exports/run-plan-1
```

Replay a run plan by business key:

```bash
dq-run-plan invoke \
	--run-plan-name retail-banking:customer:filtered_row_count:single_suite
```

Replay a run plan from a JSON or YAML file:

```bash
dq-run-plan invoke \
	--run-plan-file ./exports/run-plan-1/validation-run-plan.json
```

Replay a run plan from a user-authored YAML file:

```bash
dq-run-plan invoke \
	--run-plan-file ./validation-run-plan.yml
```

## Installation

The CLI is published as the standalone `dq-made-easy-cli` package on PyPI.

```bash
pip install dq-made-easy-cli
```

## Configuration

The CLI uses the same fail-fast configuration model as the rest of the repo:

- `--base-url` or `KONG_PUBLIC_URL` is required
- `dq-run-plan invoke` callers must point `--base-url` at a Kong-routed internal API base that serves `/api/rulebuilder/v1/...`
- `--token` or `DQ_RUN_PLAN_TOKEN` can bypass password-grant auth
- `--issuer-url` or `SSO_PUBLIC_ISSUER_URL`
- `--client-id` or `VITE_KEYCLOAK_CLIENT_ID`
- `--username` or `KEYCLOAK_JACCLOUD_USERNAME`
- `--password` or `KEYCLOAK_JACCLOUD_PASSWORD`
- `--ca-cert` or `KONG_CA_CERT`
- `--insecure` disables TLS verification and cannot be combined with `--ca-cert`
- `--run-plan-name` and `--run-plan-file` are only valid for `dq-run-plan invoke`

The CLI generates request and correlation ids when callers do not pass explicit values, and it sends both headers with each API request.

## Output behavior

- `--json` emits the raw response payload
- without `--json`, the CLI prints a human-readable text summary
- HTTP errors and invalid JSON responses fail fast with a non-zero exit code

## Contract notes

- Field names on the wire remain snake_case
- The CLI posts the canonical create request payload to the initiation route
- Replay uses the internal validation-run-plan replay route and is not exposed on the public `/rulebuilder/v1/run-plan/&#123;run_plan_id&#125;/replay` path
- Replay resolves `--run-plan-name` through the run-plan catalog and resolves `--run-plan-file` by extracting a canonical run-plan id from the supplied JSON or YAML document
- The initiation route is write-gated under the `dq:rules:write` scope path
- The CLI does not invent fallback behavior when the API or auth service is unavailable

## Related references

- Feature tracker: [../features/DQ_FEATURES.md](/docs/features/DQ_FEATURES/)
- Internal API contract: [../contracts/internal-api/by-tag/gx/v1/openapi.json](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/internal-api/by-tag/gx/v1/openapi.json)