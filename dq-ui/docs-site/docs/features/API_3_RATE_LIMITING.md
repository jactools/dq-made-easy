# API-3 API Rate Limiting

Goal: Enforce consistent, configurable API request limits to protect service stability while preserving usability for legitimate workloads.

Related work: [API-7 Real DQ Rule Execution](/docs/features/API_7_REAL_DQ_RULE_EXECUTION/)

Current overlap assessment as of 2026-05-25:

- The suggestions profiling flow already enforces a per-data-source cooldown and returns `429` with structured payload fields such as `last_requested_at` and `minutes_remaining`, but that is a single workflow-specific throttle rather than a reusable API-wide rate-limit layer.
- The test-data materialization flow already rejects new requests with `429` when the Redis-backed queue is at capacity, but that is queue-capacity protection rather than request-rate enforcement.
- Global request metrics already exist through `RequestTimingMiddleware`, the in-process API metrics store, and OTEL request metrics, so per-route request counts, error rates, and short-window traffic trends are already observable.
- Redis connectivity, URL resolution, and queue-oriented helpers already exist in multiple services, so there is reusable infrastructure for distributed coordination, but not yet dedicated rate-limit counter storage.
- Generic governance patterns for policy review and audit already exist elsewhere in the product, but there is no rate-limit-policy surface yet.

What still remains is the reusable platform layer: canonical rate-limit policy contracts, centralized FastAPI enforcement, distributed counters/windows, standardized headers, explicit route overrides, throttling-specific telemetry, and governed policy tuning.

## Phase 1: Policy and Scope Definition

- Define rate-limit dimensions: per user, per client, per IP, and per route group.
- Define default policy tiers and override rules by role or workspace plan.
- Define burst vs sustained windows and exhaustion behavior.
- Define canonical error contract (`429`) including reset hints and shared response fields.

## Phase 2: Enforcement Implementation

- Implement centralized rate-limit middleware for FastAPI paths.
- Add distributed counter backend support (Redis) for multi-instance consistency.
- Add route-level overrides for critical endpoints.
- Add bypass options for internal health/ops paths where required.

## Phase 3: Visibility and Tuning

- Emit rate-limit headers (`X-RateLimit-*`, `Retry-After`).
- Add telemetry for allow/deny counts and near-limit signals.
- Add admin endpoints/settings for policy tuning.
- Add dashboards for throttling trends and top offenders.

## Phase 4: Reliability and Governance

- Add explicit fail-fast behavior for counter-backend outage.
- Add abuse protection escalation controls.
- Add audit trail for policy changes.
- Add regression tests for limit windows and edge timing cases.

## Acceptance Criteria

- Configurable limits can be applied without code changes.
- Clients receive stable and documented `429` behavior.
- Limits are consistent across horizontally scaled instances.
- Operators can monitor and tune limits from observable metrics.
- Counter-backend outages fail explicitly instead of silently disabling limits.
- Policy changes are auditable.

## Tracked Work Items (Current Status)

- [~] `API-3.1` Rate-limit policy schema and defaults
	- Existing overlap: workflow-specific thresholds already exist for suggestions profiling cooldowns and test-data queue-capacity checks, and the product already has generic review/audit patterns for governed policy changes.
	- Remaining: define one canonical rate-limit policy model for user/client/IP/route dimensions, burst and sustained windows, workspace or role overrides, and fail-fast counter-backend outage semantics.
- [ ] `API-3.2` FastAPI middleware enforcement layer
	- Remaining: the registered middleware stack currently covers auth, correlation, API casing, contract validation, Kong enforcement, and timing metrics, but no centralized rate-limit enforcement middleware exists.
- [~] `API-3.3` Redis-backed distributed counters
	- Existing overlap: Redis URL resolution, connectivity, and queue helpers already exist for profiling, natural-language drafting, and test-data materialization flows.
	- Remaining: add dedicated atomic rate-limit counters and time-window bookkeeping instead of reusing queue lengths or endpoint-specific repository checks.
- [~] `API-3.4` Standardized `429` response and headers
	- Existing overlap: the suggestions profiling flow and test-data materialization flow already return structured `429` responses.
	- Remaining: standardize the `429` body shape across the API and emit consistent `X-RateLimit-*` and `Retry-After` headers.
- [~] `API-3.5` Route-level policy overrides
	- Existing overlap: the existing metrics stack already defines explicit skip paths for `/health`, `/metrics`, `/docs`, `/redoc`, and related surfaces, which shows the codebase already has an established pattern for route exceptions.
	- Remaining: add rate-limit-specific overrides and bypass rules by route group, operation, or internal-only surface.
- [~] `API-3.6` Metrics, dashboards, and alert thresholds
	- Existing overlap: request timing middleware, the API metrics store, and OTEL request metrics already capture per-route request counts, error rates, and minute-level traffic trends.
	- Remaining: add throttling-specific allow/deny/near-limit signals, surface `429` volumes explicitly, and build dashboards and alerts around those signals.
- [ ] `WF-3.1` Abuse-response workflow hooks
	- Remaining: there is no rate-limit-triggered abuse workflow yet for escalation, temporary blocking, incident creation, or analyst review.
- [ ] `DOC-3.1` Client guidance for throttling and retries
	- Remaining: publish the canonical headers, retry expectations, backoff guidance, and examples showing how clients should react to `429` responses.

## Already Covered Elsewhere

- Workflow-specific profiling throttling for suggestions requests.
- Queue-capacity protection for Redis-backed test-data materialization.
- Request timing and request/error observability for the existing API surface.
- Redis infrastructure patterns that can be reused for distributed coordination.

## Remaining Platform Gap

The missing scope is not "return `429` somewhere" in general. The missing scope is a reusable API-rate-limiting product surface that can protect many routes consistently, expose one canonical contract to clients, and be tuned and audited as governance-controlled policy rather than as one-off logic inside individual endpoints.

## Delivery Milestones

- Milestone A (Policy): `API-3.1` to `API-3.2`
- Milestone B (Distribution): `API-3.3` to `API-3.5`
- Milestone C (Operations): `API-3.6`, `WF-3.1`, `DOC-3.1`
