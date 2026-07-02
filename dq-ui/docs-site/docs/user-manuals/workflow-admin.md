# Admin Workflow Guide

**Role:** Platform administrator responsible for workspace configuration, user management, alert routing, and application settings.
**Time to read:** 8 minutes
**Last updated:** 2026-07-02

## Responsibilities in scope

- Managing workspaces and workspace-level settings.
- Configuring alert-routing targets for Teams, Slack, email, and PagerDuty.
- Managing role assignments and SSO configuration.
- Reviewing application configuration for secrets and connectivity values.
- Managing custom UI styles and component bundles through the UI registry.
- Seeding or resetting reference data for a workspace.

## Core workflows

### 1. Create and configure a workspace

1. Open **Admin** → **Workspaces**.
2. Select **New Workspace**.
3. Provide the workspace name, domain scope, and ownership metadata.
4. Save the workspace and verify it appears in the workspace selector.

### 2. Configure alert-routing targets

1. Open **Admin** → **App Settings**.
2. Navigate to the **Alert Routing** section.
3. Add or update a target for Teams, Slack, email, or PagerDuty.
4. Enter the connectivity values (webhook URL, channel, or email address).
5. Save. Secrets and tokens entered here are stored encrypted and are not readable back through the UI.

> If you need to rotate a webhook URL, re-enter the new value and save. The old value is replaced and not retained.

### 3. Assign roles to a user

Role assignments are managed through the identity provider (Keycloak) in the default configuration. For local dev:

1. Open the Keycloak admin console.
2. Navigate to the realm and find the user.
3. Assign the appropriate composite role: `dq:users:manage`, `dq:rules:approve`, or other scoped roles.
4. The user's scope is enforced at the API layer on every request.

For production, manage roles through your organisation's SSO provider and the configured OIDC realm.

### 4. Review or reset application configuration

1. Open **Admin** → **App Settings**.
2. Review the current connectivity settings for external systems such as OpenMetadata, observability endpoints, and ITSM connectors.
3. Redacted secrets display as masked values. Re-enter a value to replace it.
4. Use **Validate** actions where available to smoke-test a saved connectivity value without leaving the settings page.

### 5. Manage notification routing per workspace

1. Open **Admin** → **Workspaces** → select the workspace.
2. Open **Notification Routing** for that workspace.
3. Map alert policy triggers to routing targets.
4. Save routing rules. The API enforces routing at event-publication time.

### 6. Configure custom UI styles and component bundles

Use this workflow when you have already downloaded or prepared custom UI styles or component bundles and want to apply them as an admin.

1. Open **Admin** → **App Settings**.
2. Review the **UI Registry** snapshot to confirm the registry loaded correctly.
3. In the **Style Packages** section, select the imported stylesheet entry you want to activate.
4. In the **Component Bundles** section, select the component bundle or icon provider you want to use.
5. Save the settings so the app stores the registry identifier and required runtime metadata.
6. Refresh the app and verify the new styles and components are active.

> If the registry snapshot is missing, invalid, or incomplete, stop here and correct the registry source first. The app falls back to built-in defaults, but the custom entry should not be treated as active until the snapshot is valid.

### 7. Check whether a bundle is valid and usable

A custom UI style or component bundle is considered usable only when all of these are true:

1. The entry appears in the **UI Registry** snapshot on **Admin** → **App Settings**.
2. The style asset has already been imported and is served from a local API URL, not a raw remote stylesheet URL.
3. The component bundle has a resolver, adapter, or fallback path in the registry.
4. The entry is not marked inactive or unmapped in the registry snapshot.
5. The selected value is saved as a registry identifier, and the app still shows the entry after refresh.

If any of those checks fail, treat the bundle as not ready for admin activation and correct the registry first.

## What to check when users cannot log in

1. Is the Keycloak container running and healthy?
2. Is the OIDC redirect URI registered for the environment's public URL?
3. Is the user assigned the correct composite role in the realm?
4. Did a recent configuration change modify `SSO_ENABLED`, `SSO_PUBLIC_ISSUER_URL`, or `SSO_CLIENT_ID`?

## Related guides

- [Governance Terminology Reference Card](/docs/user-manuals/governance-terminology/)
- [Operator Workflow Guide](/docs/user-manuals/workflow-operator/)
- [User Manuals index](/docs/user-manuals/)
