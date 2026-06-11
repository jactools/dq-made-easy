# Stack Script Modularization Work Plan

Status: [~] Draft — SMP-01 complete, SMP-02 complete, SMP-03 complete, SMP-04 complete, SMP-05 complete, SMP-06 complete, SMP-07 complete, SMP-08 complete, SMP-09 complete, SMP-10 complete, SMP-11 complete, SMP-12 complete
Last updated: 2026-05-09

## Purpose

This work plan breaks the current start, stop, and seed shell scripts into smaller technical blocks that can be composed by docker compose profiles and explicit container dependencies.

## Scope Guardrails

- Docker compose profiles remain the functional grouping layer.
- Technical blocks should operate on one container or one shared helper at a time.
- Mock-data CSV to SQL conversion and generated seed SQL flow stay unchanged.
- Shell behavior must remain fail-fast with no fallback paths or compatibility shims.

## Work Items

- [x] SMP-01 Define the service dependency manifest
  - Capture one canonical manifest for each stack service.
  - Record profile membership, dependencies, readiness checks, seed hooks, and stop order.
  - Use the manifest as the source of truth for orchestration order.
  - Manifest: [STACK_SERVICE_DEPENDENCY_MANIFEST.md](/docs/implementation-details/STACK_SERVICE_DEPENDENCY_MANIFEST/)

- [x] SMP-02 Extract shared shell primitives
  - Centralize logging helpers, compose invocation helpers, env selection, and error handling.
  - Keep these helpers technical and reusable across every stack script.
  - Avoid embedding service-specific behavior in the shared layer.
  - Plan: [STACK_SHARED_SHELL_PRIMITIVES_PLAN.md](/docs/implementation-details/STACK_SHARED_SHELL_PRIMITIVES_PLAN/)

- [x] SMP-03 Split start into named startup blocks
  - Extract each container or service-group startup into its own dedicated script.
  - Let `start_stack.sh` source or invoke those scripts instead of carrying the per-container logic inline.
  - Dispatch startup through a pre/post block loop so the inline per-container `if` chain is no longer the implementation.

- [x] SMP-04 Split stop into named teardown blocks
  - Add explicit teardown blocks for each container or service group.
  - Preserve dependency-aware stop ordering where one container depends on another.
  - Keep teardown logic symmetrical with startup logic where possible.

- [x] SMP-05 Split seed into named seed blocks
  - Separate artifact generation from applying seed state to a live container.
  - Create dedicated seed blocks for Postgres, Keycloak, OpenMetadata, Zammad, and delivery objects.
  - Keep the existing mock-data CSV to SQL generation path unchanged.

- [x] SMP-06 Add a shared auth helper
  - Provide one module for seeded credentials, smoke user lookup, and OIDC token minting.
  - Let any script reuse the same canonical seeded-user loading path.
  - Keep auth behavior fail-fast when required credentials are missing or invalid.
  - Helper: [scripts/supporting/auth.sh](https://github.com/jactools/dq-rulebuilder/blob/main/scripts/supporting/auth.sh)

- [x] SMP-07 Add readiness and health helpers
  - Provide service-specific readiness checks for containers that need them.
  - Make readiness helpers return explicit failure when a dependency is unavailable.
  - Reuse the same helper for startup, seed, and reconciliation flows.
  - Helper: [scripts/supporting/readiness.sh](https://github.com/jactools/dq-rulebuilder/blob/main/scripts/supporting/readiness.sh)

- [x] SMP-08 Add dependency planning
  - Compute the minimal ordered set of technical blocks needed for a requested profile or container.
  - Validate dependency closure before executing anything.
  - Stop immediately if a required dependency is absent or unhealthy.
  - Helper: [scripts/supporting/dependency_planning.sh](https://github.com/jactools/dq-rulebuilder/blob/main/scripts/supporting/dependency_planning.sh)

- [x] SMP-09 Separate reconciliation from startup
  - Keep post-start config passes as explicit technical blocks.
  - Treat Kong, Keycloak, and OpenMetadata reconciliation as separate actions.
  - Avoid hiding post-start setup inside generic start commands.
  - Entry point: [scripts/reconcile_stack.sh](https://github.com/jactools/dq-rulebuilder/blob/main/scripts/reconcile_stack.sh)

- [x] SMP-10 Add plan and dry-run output
  - Show the ordered actions that would run for a given profile or container request.
  - Make dry-run output read-only and non-mutating.
  - Use it to validate dependency graphs before changing runtime state.

- [x] SMP-11 Keep smoke validation separate
  - Move validation and smoke checks out of lifecycle actions.
  - Let start/stop/seed focus on state changes only.
  - Run smoke checks as explicit follow-up commands.
  - Entry point: [scripts/smoke_stack.sh](https://github.com/jactools/dq-rulebuilder/blob/main/scripts/smoke_stack.sh)

- [x] SMP-12 Document the script contract
  - Record the container-level commands, shared helpers, and dependency graph in markdown.
  - Keep this document updated as blocks move out of the monolithic scripts.
  - Note any intentional exclusions or unchanged flows here.
  - Doc: [STACK_SCRIPT_CONTRACT.md](/docs/implementation-details/STACK_SCRIPT_CONTRACT/)

## Suggested First Slice

1. Keycloak technical block: start, stop, seed, readiness, and seeded credential loading.
2. OpenMetadata technical block: start, auth bootstrap, OIDC token minting, and post-start config.
3. Shared shell helpers: logging, compose execution, env resolution, auth loading, and readiness.

## Explicit Non-Goals

- Changing the CSV-to-SQL mock-data conversion pipeline.
- Introducing fallback behavior for missing services or credentials.
- Adding legacy compatibility layers or dual-read shims.