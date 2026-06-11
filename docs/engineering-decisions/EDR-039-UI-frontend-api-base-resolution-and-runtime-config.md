# EDR-039 [UI]: Frontend API Base Resolution and Runtime Configuration

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: UI

## Context
The frontend talks to several API groups, but earlier implementations let API targeting drift across components, startup scripts, and deployment modes.

Observed failures included:

- components hardcoding group URLs such as `/api/rulebuilder/v1/...` instead of using one shared resolver
- browser sessions opened on custom local domains accidentally targeting `localhost` instead of the active UI host
- container startup and local Vite startup inventing implicit API defaults that masked missing configuration
- runtime and build-time API base sources being mixed ad hoc across hooks, contexts, and settings flows

These are not isolated screen bugs. They define one stable frontend contract for how API origins and grouped v1 endpoints are resolved.

## Decision
- Frontend API base resolution must go through the centralized helper surface in `dq-ui/src/config/api.ts`; components, hooks, and contexts must not hardcode API origins or `/api/&lt;group&gt;/v1` paths.
- Runtime `window.__DQ_CONFIG__.API_BASE_URL` is the primary API base source for the frontend, with `VITE_API_URL` and `VITE_API_BASE_URL` as the build-time fallback sources.
- If no runtime or build-time API base is configured, frontend application code must fail fast rather than inventing a localhost or gateway default.
- Container deployments must inject `/runtime-config.js` from an explicit `KONG_PUBLIC_URL` or `VITE_API_URL`, and the frontend container entrypoint must fail fast when that value is missing or not an absolute `http(s)` URL.
- Local Vite/dev startup must use an explicit API proxy target for the backend origin; HTTPS dev may expose `/api` to the browser, but the proxy target behind that path must still be configured explicitly.
- Grouped API endpoints must be constructed through `normalizeApiBaseUrl()` and `toApiGroupV1Base()` so auth, admin, rulebuilder, data-catalog, system, and support flows all follow one URL-shaping rule.
- Compatibility rewrites for internal Docker host aliases and legacy API port mappings may remain only in the centralized API-base helper as a bounded shim; they must not spread into per-component fallback logic.

## Rationale
- One resolver surface is easier to audit and harder to bypass accidentally than repeated per-feature URL assembly.
- Runtime config needs precedence so one built frontend image can target different deployed API origins without rebuilds.
- Silent defaults hide configuration errors and produce misleading cross-origin or auth failures later.
- Relative `/api` browser paths are acceptable in HTTPS dev only when the actual backend target remains explicit in the dev proxy.
- Bounded compatibility rewrites are safer when centralized, visible, and not treated as a general fallback policy.

## Scope Boundaries
This decision applies to frontend API-base selection, grouped endpoint construction, runtime-config injection, and local dev proxy targeting in `dq-ui`.

It does not by itself define:
- auth token bootstrap ordering, which is covered by EDR-013
- general container build-context or stack bootstrap policy, which is covered by EDR-035
- backend API naming or snake_case response rules, which are covered by EDR-009
- every deployment environment's external DNS or gateway topology

## Consequences
**Positive**
- Frontend API targeting is more consistent across components, hooks, contexts, and deployment modes.
- Missing or invalid runtime configuration fails at startup or first resolution point instead of degrading into misleading network behavior.
- One built frontend artifact can still be retargeted at container start through `/runtime-config.js`.

**Negative**
- Local and container startup paths are stricter and require explicit API-target configuration.
- Tests and dev tooling must seed API-base values deliberately instead of relying on ambient localhost defaults.
- Compatibility rewrites remain a maintenance burden until the remaining legacy host and port assumptions are retired.

## Implementation Guidance
- Use `getConfiguredApiBaseUrl()`, `normalizeApiBaseUrl()`, and `toApiGroupV1Base()` for frontend API URL construction.
- Keep `/runtime-config.js` as the runtime injection point for deployed frontend containers.
- Validate `KONG_PUBLIC_URL`, `KONG_LOCAL_URL`, `VITE_API_URL`, or explicit proxy-target variables before starting frontend container or Vite dev flows.
- In HTTPS dev, keep the browser-facing base at `/api` only when the underlying proxy target is configured explicitly.
- Seed explicit API-base values in Vitest and component tests so fail-fast behavior remains intentional and deterministic.
- Keep any Docker-host or legacy-port rewrite logic centralized in `dq-ui/src/config/api.ts` and treat it as compatibility-only behavior.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-ui-api-base-localhost-rewrite-note.md`
- `dq-ui/src/config/api.ts`
- `dq-ui/scripts/start_local.sh`
- `dq-ui/scripts/docker-entrypoint-runtime-config.sh`
- `dq-ui/vite.config.ts`
- `dq-ui/index.html`
- `dq-ui/README.md`
- `dq-ui/DEPLOYMENT_GUIDE.md`
- `docs/engineering-decisions/EDR-013-UI-frontend-auth-state-and-token-ordering.md`
- `docs/engineering-decisions/EDR-035-INF-container-runtime-and-build-context-setup.md`