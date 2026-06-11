<!-- Provenance: DOC-1.5 connector onboarding runbook; keep aligned with the connector registry, persisted instances, and audit trail. -->
# Connector Onboarding Runbook

This runbook covers the canonical dq-made-easy flow for onboarding a connector after the registry entry exists. It assumes the provider is implemented, the workspace is authorized, and the backend is the source of truth.

## When to use

Use this runbook when an operator or admin needs to:
- create a persisted connector instance,
- validate a provider configuration,
- discover assets,
- run metadata sync, or
- verify the audit trail for a connector action.

## Inputs you need

- Provider name from the registry, such as `external_api` or `postgresql`.
- Workspace ID and optional tenant ID.
- Provider-specific connection settings.
- Authorization token for an admin user.

## Canonical flow

### 1. Confirm the provider exists in the registry

Call `GET /api/rulebuilder/v1/connectors/registry` and confirm the provider is listed with the expected capabilities.

If the provider is missing, stop and escalate to the backend owner. Do not invent a local config or bypass the registry.

### 2. Create a persisted connector instance

Post the connector configuration to `POST /api/rulebuilder/v1/connectors/instances`.

Example payload:

```json
{
  "configuration": {
    "provider": "external_api",
    "workspace_id": "workspace-1",
    "base_url": "https://api.example.com"
  }
}
```

Record the returned `id` as the `connector_instance_id`. That ID is the canonical link for later actions and audit events.

### 3. Validate the connection

Call `POST /api/rulebuilder/v1/connectors/{provider}/test-connection` with the same configuration and the saved `connector_instance_id`.

Example:

```json
{
  "connector_instance_id": "connector-instance-1",
  "configuration": {
    "provider": "external_api",
    "workspace_id": "workspace-1",
    "base_url": "https://api.example.com"
  }
}
```

Verify:
- `status` is healthy or the expected provider-specific success state,
- the response includes a `correlation_id` on errors,
- the request body uses snake_case.

### 4. Discover assets

Call `POST /api/rulebuilder/v1/connectors/{provider}/discover-assets` with the same saved `connector_instance_id`.

Review the returned assets for:
- expected counts,
- expected names and identifiers,
- any access or schema errors.

### 5. Run sync

Call `POST /api/rulebuilder/v1/connectors/{provider}/sync` with the same saved `connector_instance_id`.

Confirm:
- the sync job is created,
- the status transitions to completion,
- the returned `synced_count` matches expectations,
- timestamps are present for the job lifecycle.

### 6. Verify the audit trail

Call `GET /api/rulebuilder/v1/connectors/audit-events?provider={provider}`.

Confirm the latest audit events include:
- the provider,
- the saved `connector_instance_id`,
- a sanitized configuration snapshot,
- a correlation ID for troubleshooting.

## Troubleshooting

- If registry loading fails, verify the backend is healthy and the provider is registered.
- If instance creation fails, check required provider fields and workspace scope.
- If test connection fails, use the returned `correlation_id` to trace the request in logs.
- If discovery returns no items, confirm the connected system actually exposes assets and that the credentials can list them.
- If audit events are missing the instance ID, stop and fix the backend seam before proceeding. Do not add a UI-side workaround.

## Escalation

Escalate to the backend owner when:
- the provider is absent from the registry,
- instance creation returns a validation error you cannot resolve,
- connection or discovery fails after valid credentials are confirmed,
- sync never reaches a terminal success or failure state,
- audit events do not record the connector instance linkage.
