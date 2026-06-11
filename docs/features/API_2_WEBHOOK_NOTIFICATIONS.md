# API-2 Webhook Notifications

Goal: Provide reliable outbound webhook delivery for key platform events (rule lifecycle, approvals, test execution, and data-quality outcomes) with secure subscription management and operational visibility.

Related work: [API-7 Real DQ Rule Execution](../status/current/API_7_REAL_DQ_RULE_EXECUTION.md)

Current overlap assessment as of 2026-05-25:

- `DQ-12.5` already delivers workspace-scoped monitor notification preferences through `GET/PUT /rulebuilder/v1/governance/monitor-notification-preferences`, but that is user preference storage, not outbound webhook subscription management.
- `DQ-13.3` already delivers external incident/ticket integration through the incidents API and support flows, including outbound Zammad and Teams requests, but that is a small set of fixed integrations rather than a generic webhook platform.
- App-config secrets such as `assistanceRequestItsmAuthToken` are already encrypted at rest and redacted from API responses, so secret-handling groundwork exists even though webhook-specific secrets do not yet.

What still remains is the generic platform layer: canonical webhook event contracts, subscription persistence, signing, async retryable delivery, delivery history, consumer-facing verification docs, and webhook-specific operational alerting.

## Phase 1: Event and Subscription Model

- Define webhook event catalog and payload contracts.
- Add subscription model scoped by workspace/tenant, event type, and target URL.
- Support per-subscription secrets and signature algorithm configuration.
- Add validation for endpoint URL, retry policy, and enabled/disabled status.

## Phase 2: Delivery Pipeline

- Implement async delivery queue with retry/backoff and jitter.
- Add idempotency key and dedupe behavior for repeated event dispatches.
- Add timeout and circuit-breaker safeguards for failing endpoints.
- Store delivery attempts, response status, and error diagnostics.

## Phase 3: API + Operations Surface

- Add CRUD endpoints for webhook subscriptions.
- Add test-delivery endpoint for subscription verification.
- Add delivery history endpoint with filtering (status, time range, event type).
- Add operational health indicators for queue depth and failure rate.

## Phase 4: Security and Governance

- Sign payloads (HMAC) and include timestamp/nonce headers.
- Redact secrets in logs and responses.
- Add audit trail for subscription changes.
- Add alerting hooks for sustained delivery failures.

## Acceptance Criteria

- Users can register and manage webhook endpoints by event type.
- Delivery retries are resilient and observable.
- Failed deliveries include actionable diagnostics.
- Signed webhook requests can be verified by receivers.
- Secrets are never exposed in standard logs or API responses.

## Tracked Work Items (Current Status)

- [~] `API-2.1` Webhook event catalog and payload schemas
	- Existing overlap: DQ-13 incident payload builders and support/ITSM/Teams payloads already exist for narrow outbound integrations.
	- Remaining: define a canonical event catalog for rule lifecycle, approvals, test execution, monitor failures, incident updates, and other data-quality outcomes.
- [~] `API-2.2` Subscription model and persistence
	- Existing overlap: monitor notification preferences are already persisted per user and workspace.
	- Remaining: add first-class webhook subscriptions with target URL, event types, secret, retry policy, enabled state, and tenant/workspace scoping.
- [ ] `API-2.3` Secure signing and header contract
	- Remaining: introduce webhook-specific HMAC signing, timestamp/nonce headers, replay protection guidance, and receiver verification examples.
- [ ] `API-2.4` Async delivery worker with retry/backoff
	- Remaining: current outbound integrations are synchronous request/response calls and do not yet provide queueing, retry/backoff, dedupe, or circuit breaking.
- [ ] `API-2.5` Delivery history and diagnostics endpoints
	- Remaining: persist delivery attempts and expose filterable delivery history, response status, and failure diagnostics.
- [~] `API-2.6` Subscription CRUD and test-delivery endpoints
	- Existing overlap: monitor notification preference endpoints already exist.
	- Remaining: add webhook subscription CRUD plus a dedicated test-delivery or handshake endpoint for target verification.
- [~] `WF-2.1` Operational alerts for delivery failure thresholds
	- Existing overlap: DQ-12.5 alert routing and notification preferences exist, and outbound integration failures already increment operational failure metrics.
	- Remaining: add webhook-delivery-specific thresholds, queue-depth/failure-rate monitoring, and sustained-failure alerting.
- [ ] `DOC-2.1` Webhook consumer guide and verification examples
	- Remaining: publish the signing contract, sample headers, retry semantics, idempotency expectations, and receiver verification examples.

## Already Covered Elsewhere

- Workspace-scoped notification preferences for monitors: see `DQ-12.5`.
- Incident creation and status handoff to external ticketing or webhook-style integrations: see `DQ-13.3`.
- Secret encryption at rest and redaction from app-config API responses for outbound integration credentials.

## Remaining Platform Gap

The missing scope is not “send something externally” in general. The missing scope is a reusable webhook product surface that multiple event families can publish to without hardcoding Teams, Zammad, or one-off endpoint behavior into each feature slice.

## Delivery Milestones

- Milestone A (Model): `API-2.1` to `API-2.3`
- Milestone B (Delivery): `API-2.4` to `API-2.5`
- Milestone C (Surface/Hardening): `API-2.6`, `WF-2.1`, `DOC-2.1`
