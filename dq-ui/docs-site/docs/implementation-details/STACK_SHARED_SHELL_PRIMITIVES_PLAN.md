# Stack Shared Shell Primitives Plan

Status: [~] Draft — SHP-01 complete, SHP-02 complete, SHP-03 complete, SHP-04 complete, SHP-05 complete
Last updated: 2026-07-14

## Purpose

This plan covers the shared shell building blocks that multiple stack scripts can reuse once the start, stop, and seed flows are decomposed into technical blocks.

## Scope Guardrails

- Keep these helpers generic and reusable across scripts.
- Do not move service-specific orchestration into the shared layer.
- Do not change the mock-data CSV to SQL pipeline.
- Keep fail-fast behavior with no fallback or compatibility branches.

## Work Items

- [x] SHP-01 Centralize logging helpers
  - Keep one canonical logging module for info, warning, error, debug, and success output.
  - Preserve current log formatting and exit behavior.
  - Start by wiring one pilot script to the new logger structure before migrating additional callers.
  - Extract the first implementation module into `scripts/supporting/logging/core.sh`.
  - Make progress output consistent across startup, seeding, and reconciliation scripts.

- [x] SHP-02 Centralize env selection helpers
  - Reuse the canonical `--env` and `--env-file` selection logic everywhere.
  - Keep environment normalization in one place.
  - Fail fast when the selected env file is missing or invalid.
  - Build this pilot on top of the SHP-01 logging outcome without introducing any new logging surface.
  - Extract the first implementation module into `scripts/supporting/env/selection.sh`.
  - Pilot the module through `scripts/start_stack.sh` before migrating more scripts.

- [x] SHP-03 Centralize docker compose invocation helpers
  - Provide one wrapper for compose calls with repo env injection.
  - Keep compose profile selection and base path handling consistent.
  - Avoid re-implementing compose shell flags in each script.
  - Build this pilot on top of SHP-01 logging and SHP-02 env selection outcomes.
  - Extract the first implementation module into `scripts/supporting/compose/invocation.sh`.
  - Pilot the module through `scripts/start_stack.sh` before migrating more scripts.

- [x] SHP-04 Centralize seeded credential loading
  - Keep one canonical loader for seeded user credentials and smoke user lookup.
  - Load the matching stage-specific credential artifact from `tmp`.
  - Expose the canonical OpenMetadata seed username and password for callers that need them.

- [x] SHP-05 Centralize readiness checks
  - Provide reusable readiness helpers for Keycloak and any other required services.
  - Keep readiness loops and failure handling consistent.
  - Ensure readiness helpers stop immediately when dependencies never become healthy.

- [ ] SHP-06 Centralize Python runner selection
  - Keep one canonical entry point for `python_arm64.sh` usage.
  - Reuse it for scripts that need the repo Python environment on macOS.
  - Avoid ad hoc interpreter discovery in individual shell scripts.

- [ ] SHP-07 Centralize path and repo-root helpers
  - Provide one source of truth for repo root discovery.
  - Keep relative path handling consistent across scripts and modules.
  - Avoid duplicate `dirname`/`pwd` logic in each consumer.

- [ ] SHP-08 Centralize auth bootstrap helpers
  - Share the Keycloak/OpenMetadata auth token minting logic where needed.
  - Keep any auth helper generic enough to support OpenMetadata, Kong, and validation scripts.
  - Fail fast on invalid credentials or unreachable auth endpoints.

- [ ] SHP-09 Document helper ownership
  - Record which scripts consume each helper.
  - Keep service-specific helpers out of the shared primitives layer.
  - Note any migration boundaries where a helper is still transitional.

- [ ] SHP-10 Define helper module boundaries
  - Decide which helpers stay in `scripts/supporting/` and which should remain script-local.
  - Keep helper names canonical and avoid shims or aliases.
  - Make the helper boundaries explicit before extracting code.

- [x] SHP-11 Centralize stack lifecycle helpers
  - Add `scripts/supporting/stack_lifecycle.sh` for shared lifecycle operations used by `stack_destroy.sh`, `stack_start.sh`, `stack_stop.sh`, `stack_restart.sh`, and `stack_seed.sh`.
  - Admin password variable classification (`is_admin_password_var`).
  - Stateful volume detection and management (`stateful_volumes_exist`, `remove_stateful_volumes`).
  - Generated artifact cleanup (`remove_generated_artifacts`).
  - Generated env loading (`load_generated_env`).
  - Helper: [scripts/supporting/stack_lifecycle.sh](https://github.com/jactools/dq-rulebuilder/blob/main/scripts/supporting/stack_lifecycle.sh)

## Migration Approach

1. Build the new helper structure with one pilot script or script family.
2. Validate the new shape against the pilot before widening the change.
3. Migrate additional callers one at a time after the pilot is stable.
4. Keep the old path removed rather than dual-running both paths.

## Suggested Extraction Order

1. `root_env_file.sh` and compose invocation helpers.
2. `logging.sh` and common progress reporting.
3. `load_seeded_user_credentials.sh` and auth bootstrap helpers.
4. `keycloak_readiness.sh` and other reusable readiness loops.
5. `python_arm64.sh` call sites and repo-root helpers.
6. `stack_lifecycle.sh` for lifecycle-specific shared operations (volume detection, admin var classification, artifact cleanup).

## Explicit Non-Goals

- Adding fallback logic for missing services, credentials, or env files.
- Introducing compatibility layers for old helper names.
- Changing the generated SQL seed flow or its CSV conversion rules.
