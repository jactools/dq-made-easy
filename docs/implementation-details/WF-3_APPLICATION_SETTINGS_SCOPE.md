# WF-3 Application Settings Scope

This document defines ownership and persistence scope for fields shown in the **Application Settings** UI.

## Scope Definitions

- `Global (app_config)`: Setting applies to the whole platform and must be stored in `app_config`.
- `Per-user (users.preferences)`: Setting is user-specific and should be stored in `users.preferences`.
- `Derived/runtime`: Value is computed or environment-driven and should not be saved directly from UI.

## ApplicationSettings Field Scope

| Field | Scope | Current State |
|---|---|---|
| `ssoEnabled` | Global (app_config) | Implemented |
| `ssoProvider` | Global (app_config) | Implemented |
| `ssoIssuerUrl` (`ssoIssuer`) | Global (app_config) | Implemented |
| `ssoClientId` | Global (app_config) | Implemented |
| `allowLocalAuth` | Global (app_config) | Implemented |
| `apiBaseUrl` | Per-user (users.preferences) | Implemented |
| `apiVersion` | Global (app_config) | Implemented (persisted, UI round-trip) |
| `apiRetryAttempts` | Global (app_config) | Implemented (persisted, UI round-trip) |
| `apiRetryDelay` | Global (app_config) | Implemented (persisted, UI round-trip) |
| `maxUsersPerWorkspace` | Global (app_config) | Implemented (runtime enforced in user/workspace membership updates) |
| `maxWorkspaces` | Global (app_config) | Implemented (runtime enforced on workspace creation) |
| `maxRulesPerWorkspace` | Global (app_config) | Implemented (runtime enforced on rule creation) |
| `maxTemplatesPerWorkspace` | Global (app_config) | Implemented (runtime enforced on template creation) |
| `maxConcurrentTests` | Global (app_config) | Implemented (runtime enforced via test job throttling) |
| `maintenanceMode` | Global (app_config) | Implemented (persisted via `PUT /system/v1/app-config`; runtime-enforced in middleware; UI maintenance screen + admin header badge; enable/disable both confirmed working) |
| `maintenanceMessage` | Global (app_config) | Implemented (persisted; shown in API 503 response + frontend maintenance page) |
| `allowSignup` | Global (app_config) | Implemented (runtime enforced for new OIDC user provisioning) |
| `requireEmailVerification` | Global (app_config) | Implemented (persisted, UI round-trip; runtime enforcement pending) |
| `defaultUserRole` | Global (app_config) | Implemented (runtime applied for new OIDC users) |
| `logLevel` | Global (app_config) | Implemented (persisted, UI round-trip; runtime wiring pending) |
| `enableAnalytics` | Global (app_config) | Implemented (persisted, UI round-trip; runtime wiring pending) |
| `enableCrashReporting` | Global (app_config) | Implemented (persisted, UI round-trip; runtime wiring pending) |
| `enableSuggestions` | Global (app_config) | Partially implemented (stored as app setting, overlaps existing feature flags) |
| `enableBulkOperations` | Global (app_config) | Implemented (persisted, UI round-trip; runtime guards pending) |
| `enableVersioning` | Global (app_config) | Implemented (persisted, UI round-trip; runtime guards pending) |
| `enableExport` | Global (app_config) | Implemented (persisted, UI round-trip; runtime guards pending) |
| `auditLogRetentionDays` | Global (app_config) | Implemented (persisted, UI round-trip; retention jobs pending) |
| `testResultsRetentionDays` | Global (app_config) | Implemented (persisted, UI round-trip; retention jobs pending) |
| `deletedItemsRetentionDays` | Global (app_config) | Implemented (persisted, UI round-trip; retention jobs pending) |
| `exceptionFactJitRequestTimeoutMinutes` | Global (app_config) | Implemented (persisted, UI round-trip; governs automatic JIT request timeout) |
| `updatedAt` | Derived/runtime | Not applicable |

## Additional Global App Config Already In Use

These are already in `app_config` and wired in backend/frontend logic:

- `metricsForwardingEnabled`
- `metricsForwardUrl`
- `featureRuleValidation`
- `featureRuleLifecycleManagement`
- `featureRuleResultAggregation`
- `featureRuleSuggestions`
- `featureExceptionRecordHandling`
- `featureRuleExecutionMonitoring`
- `featureRuleValidationStage`
- `featureRuleLifecycleManagementStage`
- `featureRuleResultAggregationStage`
- `featureRuleSuggestionsStage`
- `featureExceptionRecordHandlingStage`
- `featureRuleExecutionMonitoringStage`

## Notes

- `apiBaseUrl` is intentionally per-user to support local development and environment-specific routing.
- Most operational limits and platform behavior toggles should be global.
- Remaining implementation work is primarily runtime behavior for currently persisted-only settings (`requireEmailVerification`, `logLevel`, analytics/crash toggles, bulk/versioning/export guards, and retention policy execution).

## API Access (Auth)

- Reading global app settings uses `GET /system/v1/app-config` and is available to authenticated users with `dq:rules:read`.
- Writing global app settings uses `PUT /system/v1/app-config` and requires `dq:config:manage`.
- User preferences are stored via `PUT /admin/v1/me` and require `dq:rules:read` (so user-level toggles like preview opt-in can be saved without broad write scopes).

## Known Issues Fixed (11 March 2026)

| Issue | Root Cause | Fix |
|---|---|---|
| Maintenance mode not saved on first attempt | `PUT /system/v1/app-config` was called without `Authorization` header — backend rejected silently | Added bearer token to save request; non-OK responses now propagate as errors |
| Maintenance mode cannot be disabled once active | Maintenance middleware blocked `PUT /system/v1/app-config` for non-admin users, preventing deactivation | `/system/v1/app-config` (all methods) is now in the maintenance-exempt route list; scope checks still protect it |
