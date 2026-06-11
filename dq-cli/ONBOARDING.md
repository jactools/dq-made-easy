# dq-onboard CLI: Workspace Onboarding Workflow

> **New Feature** — Automated rule onboarding for data workspaces based on template matching.
>
> **Version**: 1.0 | **Release Date**: June 1, 2026

## Overview

`dq-onboard` is a command-line tool for discovering, filtering, and bulk-submitting rule onboarding proposals for a data workspace. It automates the process of:

1. **Fetching a workspace scope summary** — counts attributes and data objects
2. **Generating proposals** — matches attributes against validation templates
3. **Filtering selections** — by template type, view all, or take a sample
4. **Submitting batch** — creates rules in bulk (optional, dry-run supported)

This is especially useful for:
- Onboarding new data domains with consistent quality rules
- Bulk-applying a specific rule template to all attributes of a given type
- Auditing what rules would be created before submission
- Automation workflows (CI/CD, scheduled tasks, data mesh platforms)

---

## Installation

The CLI is bundled with `dq-made-easy-cli` and available in the repository's virtual environment:

```bash
cd dq-cli
pip install -e .
```

Verify installation:
```bash
dq-onboard --help
```

---

## Command Syntax

```
dq-onboard [OPTIONS] --workspace WORKSPACE_NAME
```

### Required Arguments

| Argument | Description |
|----------|-------------|
| `--workspace WORKSPACE_NAME` | Name of the workspace to onboard (e.g., `"Retail Banking"`) |

### Authentication Options

| Option | Description | Default |
|--------|-------------|---------|
| `--base-url URL` | Kong API gateway URL | `$KONG_PUBLIC_URL` |
| `--token TOKEN` | Bearer token (skips password-grant auth) | — |
| `--issuer-url URL` | Keycloak issuer URL for password-grant | `$SSO_PUBLIC_ISSUER_URL` |
| `--client-id ID` | Keycloak client ID | `$VITE_KEYCLOAK_CLIENT_ID` |
| `--username USER` | Keycloak username for auth | `$KEYCLOAK_USERNAME` |
| `--password PASS` | Keycloak password for auth | `$KEYCLOAK_PASSWORD` |
| `--ca-cert PATH` | TLS CA certificate file | — |
| `--insecure` | Disable TLS verification (dev only) | false |

### Proposal Selection Options

| Option | Description | Default |
|--------|-------------|---------|
| `--template FILTER` | Case-insensitive substring filter on template name | — |
| `--all` | Select all proposals (not just first) | false |
| `--dry-run` | Show what would be submitted without creating batch | false |

### Output Options

| Option | Description |
|--------|-------------|
| `--json` | Output JSON (machine-readable) instead of human text |
| `--request-id ID` | Correlation ID for tracing | auto-generated |
| `--correlation-id ID` | Correlation ID for tracing | auto-generated |
| `--timeout SEC` | HTTP timeout in seconds | 30 |

---

## Verified Examples

All examples below use the seeded **Retail Banking** workspace, which contains:
- **157 attributes** across multiple data objects
- **356 total proposals** across 8 validation templates:
  - NULL Value Check (157)
  - Empty String Check (114)
  - Range Check (12)
  - Uniqueness (48)
  - Freshness Check (7)
  - Future Date Detection (7)
  - Email Format Check (6)
  - Phone Number Validation (5)

> **Setup**: Environment must be loaded via `source_selected_root_env_file` and seeded user credentials via `dq_source_seeded_user_credentials`

### Example 1: View Single Proposal (Dry-Run Sample)

**Goal**: Show what would be submitted by default (first uncovered proposal).

```bash
dq-onboard \
  --workspace "Retail Banking" \
  --insecure \
  --dry-run
```

**Output**:
```
[1/3] Fetching scope summary...
  Found 157 attributes in workspace retail-banking
[2/3] Generating proposals...
  Generated 356 proposals

  Proposals by template:
    Email Format Check: 6
    Empty String Check: 114
    Freshness Check: 7
    Future Date Detection: 7
    NULL Value Check: 157
    Phone Number Validation: 5
    Range Check: 12
    Uniqueness: 48

  Selected 1 proposal(s) for batch
```

**What's happening**:
- Fetches workspace and all available attributes
- Generates all 356 proposals (already_covered=false)
- Shows breakdown by template type
- Selects first proposal as a representative sample
- Returns exit code 0 without creating a batch

---

### Example 2: Filter by Template (NULL Value Check)

**Goal**: Select all NULL value check proposals (all 157 attributes).

```bash
dq-onboard \
  --workspace "Retail Banking" \
  --template "NULL Value" \
  --all \
  --insecure \
  --dry-run
```

**Output**:
```
[1/3] Fetching scope summary...
  Found 157 attributes in workspace retail-banking
[2/3] Generating proposals...
  Generated 356 proposals

  Proposals by template:
    NULL Value Check: 157

  Filtered to 157 proposals matching template 'NULL Value'

  Selected 157 proposal(s) for batch
```

**Key behaviors**:
- Template filter is case-insensitive substring match
- Reduces visible proposals to only those matching the filter
- `--all` with `--template` selects all matching proposals (not just first)
- Still in dry-run mode, so no batch is created

---

### Example 3: Submit All Proposals (Bulk Create)

**Goal**: Create rules for all 356 proposals in one batch.

```bash
dq-onboard \
  --workspace "Retail Banking" \
  --all \
  --insecure \
  --submit
```

**Output**:
```
[1/3] Fetching scope summary...
  Found 157 attributes in workspace retail-banking
[2/3] Generating proposals...
  Generated 356 proposals

  Proposals by template:
    Email Format Check: 6
    Empty String Check: 114
    Freshness Check: 7
    Future Date Detection: 7
    NULL Value Check: 157
    Phone Number Validation: 5
    Range Check: 12
    Uniqueness: 48

  Selected 356 proposal(s) for batch

[3/3] Creating batch (356 proposal(s))...
  Batch onb-1de48917628645bba4d9f6fc77f1fd88: created=1 skipped=0 failed=0

Onboarding complete!
```

**What happened**:
- All 356 proposals submitted to `/onboarding/create-batch`
- Backend processes each proposal:
  - Resolves proposal_id to (template, attribute)
  - Applies matching rule template
  - Creates rule with default parameters
- Batch response: `created=1 skipped=0 failed=0` (single batch outcome)
- Exit code: 0 (success)
- Batch ID can be used to track or audit the operation

---

### Example 4: JSON Output (Machine Consumption)

**Goal**: Extract structured output for automation (CI/CD, orchestration).

```bash
dq-onboard \
  --workspace "Retail Banking" \
  --all \
  --insecure \
  --dry-run \
  --json
```

**Output**:
```json
{
  "workspace_id": "retail-banking",
  "attribute_count": 157,
  "total_proposals": 356,
  "selected_proposals": [
    "template-completeness-1::019e0488-9a53-77fa-9a22-cff40798361e::019e0488-9a53-70ad-877e-04c870b6cb85",
    "template-completeness-1::019e0488-9a53-77fa-9a22-cff40798361e::019e0488-9a53-70ad-877e-04c870b6cb86",
    ...
  ],
  "dry_run": true
}
```

**Use cases**:
- Parse in shell/Python for conditional logic
- Feed to downstream orchestration systems
- Log to audit trails or data lineage systems
- Diff proposals between runs

---

### Example 5: Template Filter + Dry-Run (Preview)

**Goal**: Preview what would happen with Empty String checks.

```bash
dq-onboard \
  --workspace "Retail Banking" \
  --template "Empty String" \
  --insecure \
  --dry-run
```

**Output**:
```
[1/3] Fetching scope summary...
  Found 157 attributes in workspace retail-banking
[2/3] Generating proposals...
  Generated 356 proposals

  Proposals by template:
    Empty String Check: 114

  Filtered to 114 proposals matching template 'Empty String'

  Selected 1 proposal(s) for batch
```

**Behavior**:
- Shows all 114 empty string proposals
- Selects first one (default without `--all`)
- No batch created (dry-run)
- Safe to inspect before actual submission

---

## Integration with Repository Workflows

### Via Root Environment File

The CLI integrates with the repository's `scripts/supporting/root_env_file.sh` pattern:

```bash
source scripts/supporting/root_env_file.sh
init_root_env_file "$PWD"
consume_root_env_selection_args "$PWD" --env dev
validate_selected_root_env_file "$PWD" full
source_selected_root_env_file

# Now KONG_PUBLIC_URL, SSO_PUBLIC_ISSUER_URL, etc. are set
dq-onboard --workspace "Retail Banking" --insecure
```

### With Seeded Credentials

For smoke tests or CI/CD using the seeded user:

```bash
source scripts/supporting/auth.sh
dq_source_seeded_user_credentials --quiet
# Now KEYCLOAK_JACCLOUD_USERNAME and PASSWORD are loaded

dq-onboard --workspace "Retail Banking" --insecure
```

### In Bash Scripts

Example: batch onboarding with logging:

```bash
#!/usr/bin/env bash
set -euo pipefail

source scripts/supporting/root_env_file.sh
source_selected_root_env_file
source scripts/supporting/auth.sh
dq_source_seeded_user_credentials --quiet

echo "Starting onboarding for Retail Banking..."
if dq-onboard \
  --workspace "Retail Banking" \
  --all \
  --insecure \
  --submit \
  --json > /tmp/onboarding_result.json
then
  echo "✓ Onboarding succeeded"
  cat /tmp/onboarding_result.json | jq '.'
else
  echo "✗ Onboarding failed (exit code: $?)"
  exit 1
fi
```

---

## Proposal ID Format

Proposal IDs are constructed as:

```
{template_id}::{data_object_version_id}::{attribute_id}
```

Example:
```
template-completeness-1::019e0488-9a53-77fa-9a22-cff40798361e::019e0488-9a53-70ad-877e-04c870b6cb85
```

**Note**: Proposal IDs are ephemeral — they are generated on-the-fly during `generate-proposals` and are valid only for the current workspace scope. They are resolved via the data catalog during `create-batch`.

---

## Exit Codes

| Code | Meaning | Example |
|------|---------|---------|
| 0 | Success | All steps completed or dry-run finished |
| 1 | Error | HTTP 5xx, auth failure, network error, no proposals found |

---

## Error Handling

All errors follow a fail-fast policy per repository standards:

- **HTTP Errors**: Structured error response with `error` code, `service` name, `correlation_id`
- **Auth Failure**: Keycloak token acquisition error (incorrect credentials, issuer unavailable)
- **Network/TLS**: Connection refused, certificate verification failed
- **No Proposals**: Exit 0 with message "No proposals to submit" (expected case)

Example error:
```
Error: Failed to acquire token: HTTP 400 - {"error":"invalid_grant","error_description":"Invalid user credentials"}
```

---

## Configuration via Environment Variables

The CLI reads from standard environment variables if CLI options are not provided:

| Option | Env Var | Example |
|--------|---------|---------|
| `--base-url` | `KONG_PUBLIC_URL` | `https://kong.example.com` |
| `--issuer-url` | `SSO_PUBLIC_ISSUER_URL` | `https://keycloak.example.com/realms/dq` |
| `--client-id` | `VITE_KEYCLOAK_CLIENT_ID` | `dq-frontend` |
| `--username` | `KEYCLOAK_USERNAME` | `alice@example.com` |
| `--password` | `KEYCLOAK_PASSWORD` | `<password>` |

---

## Frequently Asked Questions

### Q: How many proposals can I submit at once?

**A**: All of them. The CLI will submit however many you select (1, 157, 356, etc.). The backend processes each proposal independently, so scaling is determined by backend capacity, not the CLI.

### Q: What happens if I run the same batch twice?

**A**: The second run will likely show `skipped=1` (the rule already exists) unless the first run failed. Rules are deduplicated by (template, attribute) combination.

### Q: Can I filter by multiple templates?

**A**: Not yet. Currently `--template` is a single substring filter. You can work around this by running multiple times with different filters and combining the proposal IDs manually.

### Q: How do I cancel a submission after `--submit`?

**A**: The CLI doesn't support cancellation. Once `create-batch` succeeds, rules are created. Use the UI or API to manage rules after creation.

### Q: Is the CLI available on PyPI?

**A**: Not separately — it's part of the repository's `dq-cli` package. Install it from source: `pip install -e dq-cli`.

---

## Architecture & Design Notes

### Proposal ID Construction

The CLI does not read a `proposal_id` field from the API response. Instead, it constructs proposal IDs from the hierarchical response structure:

```python
for template in proposals:
    for dataset in template.by_dataset:
        for object_group in dataset:
            for attribute in object_group.attributes:
                proposal_id = f"{template_id}::{object_group.data_object_version_id}::{attribute_id}"
```

This ensures proposal IDs are **ephemeral** — they are derived from the current workspace state and need not be stored.

### Template Filtering

Template filtering is applied **during** proposal extraction, not after. This reduces memory overhead when selecting large subsets:

```python
if config.template_filter and config.template_filter.lower() not in template_name.lower():
    continue  # Skip this entire template group
```

### Dry-Run Mode

`--dry-run` (or lack of `--submit`) stops execution after step 2 (generate-proposals) and returns exit code 0. This allows safe preview of selections without touching the backend.

### Authentication

The CLI implements Keycloak password-grant flow:

1. POST to `{issuer_url}/protocol/openid-connect/token` with `grant_type=password`
2. Extract `access_token` from response
3. Use token in `Authorization: Bearer` header for API calls
4. No token caching (each run acquires fresh token)

---

## Implementation Details

**File**: `dq-cli/dq_cli/onboard.py`  
**Lines**: ~520  
**Entry Point**: `dq-onboard = "dq_cli.onboard:main"` (in `pyproject.toml`)

**Key Functions**:
- `run_onboard(config)` — Main workflow orchestrator
- `_get_token(config, client)` — Keycloak password-grant auth
- `_resolve_workspace_id(config, client, token)` — Workspace name → UUID lookup
- `_create_client(config)` — httpx client factory with TLS/timeout config

**Dependencies**: `httpx`, `PyYAML` (shared with CLI)

---

## Changelog

### Version 1.0 (June 1, 2026)

**Initial Release**

- [x] Scope-summary endpoint integration
- [x] Generate-proposals endpoint integration
- [x] Create-batch endpoint integration
- [x] Workspace name resolution (→ UUID)
- [x] Keycloak password-grant authentication
- [x] Template name filtering (case-insensitive substring)
- [x] `--all` flag for bulk selection
- [x] `--dry-run` mode for preview
- [x] `--json` output for automation
- [x] `--insecure` TLS override for development
- [x] Comprehensive error messages with correlation IDs
- [x] Integration with root_env_file.sh pattern
- [x] Tested with Retail Banking workspace (157 attributes, 356 proposals)

---

## Support & Feedback

For bugs, feature requests, or questions:
- Check logs for `correlation_id` when debugging API issues
- Verify environment setup with: `dq-onboard --help`
- Test dry-run mode first before `--submit`
- Use `--json` + `jq` for advanced filtering or reporting

