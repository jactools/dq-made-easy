# Admin Workflow Guide

**Role:** Platform administrator responsible for workspace configuration, user management, alert routing, and application settings.
**Time to read:** 8 minutes
**Last updated:** 2026-05-31

## Responsibilities in scope

- Managing workspaces and workspace-level settings.
- Configuring alert-routing targets for Teams, Slack, email, and PagerDuty.
- Managing role assignments and SSO configuration.
- Reviewing application configuration for secrets and connectivity values.
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

## What to check when users cannot log in

1. Is the Keycloak container running and healthy?
2. Is the OIDC redirect URI registered for the environment's public URL?
3. Is the user assigned the correct composite role in the realm?
4. Did a recent configuration change modify `SSO_ENABLED`, `SSO_PUBLIC_ISSUER_URL`, or `SSO_CLIENT_ID`?

## Related guides

- [Governance Terminology Reference Card](./governance-terminology.md)
- [Operator Workflow Guide](./workflow-operator.md)
- [User Manuals index](./README.md)
