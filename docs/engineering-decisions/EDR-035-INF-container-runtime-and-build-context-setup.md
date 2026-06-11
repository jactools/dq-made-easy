# EDR-035 [INF]: Container Runtime and Build-Context Setup Rules

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: INF

## Context
Several stack failures came from mismatched Docker build contexts, hidden environment assumptions, host-specific readiness behavior, and duplicated orchestration ownership. These are durable repository integration rules rather than one-off local fixes.

## Decision
- Each container image must be built from the context directory that matches its Dockerfile copy assumptions; do not change build context ad hoc to make one service work locally.
- Stack bootstrap scripts must enforce required environment variables explicitly and fail fast when they are missing.
- Host-side readiness checks may use approved fallback hosts where local DNS aliases are not portable, but they must remain explicit and bounded.
- Frontend auth/runtime environment variables required by smoke and setup scripts must be exported intentionally rather than assumed from sourced files.
- Post-start orchestration responsibilities must have a single owner, with explicit skip flags where one stage needs to suppress another.

## Rationale
- Build-context mismatches usually appear as misleading missing-file errors later in Docker builds.
- Hidden environment defaults make bootstrap behavior machine-specific and hard to debug.
- Host-specific DNS behavior varies enough that explicit fallback is safer than ambient assumptions.
- Duplicate orchestration side effects create nondeterministic stack startup behavior.

## Scope Boundaries
This decision covers local/container runtime setup conventions and bootstrap ownership.

It does not by itself define:
- image publishing workflows
- cloud or Kubernetes deployment
- detailed compose networking and volumes

## Consequences
**Positive**
- Container startup behavior becomes more reproducible across developer machines.
- Setup failures surface at the actual missing prerequisite.

**Negative**
- Bootstrap scripts stay stricter and require more explicit configuration.
- Local scripts must keep documented ownership boundaries in sync.

## Implementation Guidance
- Document the intended build context near each build invocation.
- Validate required environment variables before bootstrap actions.
- Keep host fallback logic explicit and limited.
- Use opt-out flags where one orchestration stage must suppress another.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-fastapi-docker-build-context-root-note.md`
- `/memories/repo/dq-rulebuilder-keycloak-readiness-localhost-fallback-note.md`
- `/memories/repo/dq-rulebuilder-kong-bootstrap-strict-env-note.md`
- `/memories/repo/dq-rulebuilder-start-containers-kong-reconciliation-single-owner-note.md`
- `/memories/repo/dq-rulebuilder-dq-ui-dockerignore-dist-change-note.md`
