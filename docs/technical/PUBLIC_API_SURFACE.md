# Public API Surface

Last updated: 2026-05-10

This inventory separates endpoints that are externally public at the Kong edge from routes that are internal-only service integrations or only appear public inside the FastAPI auth policy.

## Externally public endpoints

These endpoints are reachable without a JWT at the edge.

| Path | Method(s) | Notes |
|---|---|---|
| `/health` | `GET` | Container and edge health check |
| `/auth/v1/login` | `POST` | Login entrypoint |
| `/auth/v1/logout` | `GET`, `POST` | Logout entrypoint |
| `/auth/v1/redirect` | `GET` | OIDC redirect |
| `/auth/v1/callback` | `GET` | OIDC callback |
| `/system/v1/version-catalog` | `GET` | Version catalog |
| `/system/v1/system-info` | `GET` | System info |
| `/system/v1/health` | `GET` | System health |
| `/system/v1/readiness` | `GET` | Readiness probe |
| `/system/v1/live` | `GET` | Liveness probe |
| `/system/v1/ready` | `GET` | Readiness alias |
| `/api-docs` | `GET` | OpenAPI docs |
| `/api-docs-json` | `GET` | OpenAPI JSON |

## Internal-only service integrations

These routes are called from backend or worker code over the internal API base and should not be exposed as public edge routes.

| Path | Notes |
|---|---|
| `/rulebuilder/v1/profiling/enqueue` | Profiling request enqueue for worker processing |
| `/rulebuilder/v1/profiling/requests/{profiling_request_id}/report` | Profiling worker lifecycle report |

## App-public only, but not externally public

These routes are treated as public by the FastAPI auth helper, but the UI should still reach them through Kong rather than by calling the raw API service.

| Path | Why it matters |
|---|---|
| `/auth/v1/refresh` | Public in app auth policy, but still under the Kong-routed `/auth/v1` path |

## Notes

- The auth helper also recognizes `/api/...` equivalents by normalization, so the UI can keep using Kong-routed browser paths.
- `/admin/v1/me` is authenticated-only and intentionally not public.

## Reduction proposal

If the goal is to shrink the public edge surface, this is the recommended split.

### Keep public

These routes are needed for browser startup, auth flow, or probes.

| Path | Reason |
|---|---|
| `/health` | Edge and container health checks |
| `/auth/v1/login` | Browser login entrypoint |
| `/auth/v1/logout` | Browser logout entrypoint |
| `/auth/v1/redirect` | OIDC redirect |
| `/auth/v1/callback` | OIDC callback |
| `/system/v1/health` | API health check |
| `/system/v1/readiness` | API readiness probe |
| `/system/v1/live` | API liveness probe |
| `/system/v1/ready` | API readiness alias |

### Keep public only if the UI still needs them

These are convenient, but they are not intrinsically required by the auth flow.

| Path | Reduction note |
|---|---|
| `/system/v1/system-info` | Keep public only if the shell needs it before auth |
| `/system/v1/version-catalog` | Keep public only if the shell or login flow needs version discovery before auth |

### Move behind auth or internal-only routing

These are the first candidates to remove from the public edge.

| Path | Proposed action |
|---|---|
| `/api-docs` | Protect behind auth or restrict to operator-only access |
| `/api-docs-json` | Protect behind auth or restrict to operator-only access |
| `/rulebuilder/v1/profiling/enqueue` | Keep internal-only and remove from public edge exposure |
| `/rulebuilder/v1/profiling/requests/{profiling_request_id}/report` | Keep internal-only and remove from public edge exposure |

### Summary

- The smallest obvious public set is the login/logout/callback/redirect flow plus health probes.
- The biggest easy reduction is to stop exposing OpenAPI docs publicly.
- The profiling enqueue/report routes should be treated as internal integration surfaces and not exposed to browsers.