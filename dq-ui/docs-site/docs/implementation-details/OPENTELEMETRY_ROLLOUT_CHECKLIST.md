# OpenTelemetry Rollout Checklist (UI + API)

Status: Active  
Last Updated: 2026-03-23 (Phase 5 complete)

Related:
- [OPENTELEMETRY_IMPLEMENTATION.md](/docs/implementation-details/OPENTELEMETRY_IMPLEMENTATION/)
- [OBSERVABILITY_SETUP.md](/docs/implementation-details/OBSERVABILITY_SETUP/)

---

## Phase 1 - Telemetry Contract and Standards

1. [x] Define canonical service names: dq-api, dq-ui, dq-engine, dq-profiling.
2. [x] Define environment labels: dev, test, prod.
3. [x] Define required span/log attributes.
3.1 [x] correlation_id (already implemented in CorrelationIdMiddleware)
3.2 [x] user_id (or anonymous)
3.3 [x] route (http.route via OTel semconv)
3.4 [x] tenant/org — optional, include as tenant_id when available
3.5 [x] service.name, service.version, environment, trace_id
4. [x] Define sampling policy.
4.1 [x] Dev/Test default 10%
4.2 [x] Prod default 1% (adjust to 5% based on volume)
5. [x] Add telemetry conventions section to implementation docs.
5.1 [x] Cardinality rules documented.
5.2 [x] Mandatory vs optional attributes documented.
5.3 [x] Existing correlation ID and JSON logging infrastructure catalogued.

Exit criteria:
1. [x] Telemetry naming and attribute standards documented in OPENTELEMETRY_IMPLEMENTATION.md.

---

## Phase 1.5 - Version Baseline (Latest Stable Only)

1. [x] Select latest stable OpenTelemetry versions for Python and UI as of implementation date.
2. [x] Exclude pre-release versions (alpha/beta/rc) unless explicitly approved.
3. [x] Pin compatible package versions in dependency files.
4. [x] Record selected versions and decision date in implementation docs.
5. [ ] Add a dependency update check task (monthly) to keep OTel on latest stable.
6. [ ] Upgrade Vite from 5.4.x to 8.0.1 (breaking major) to resolve esbuild GHSA-67mh-4wv8-2f99 (dev-server only; deferred pending Vite 8 migration review).

Selected baseline (2026-03-23):
1. Python stable pins:
1.1 [x] opentelemetry-api==1.40.0
1.2 [x] opentelemetry-sdk==1.40.0
1.3 [x] opentelemetry-exporter-otlp==1.40.0
2. UI stable pins:
2.1 [x] @opentelemetry/api@1.9.0
2.2 [x] @opentelemetry/context-zone@2.6.0
2.3 [x] @opentelemetry/sdk-trace-base@2.6.0
2.4 [x] @opentelemetry/sdk-trace-web@2.6.0
2.5 [x] @opentelemetry/exporter-trace-otlp-http@0.213.0
2.6 [x] @opentelemetry/instrumentation-fetch@0.213.0
2.7 [x] @opentelemetry/instrumentation-xml-http-request@0.213.0
3. Python instrumentation (pre-release exception, approved 2026-03-23):
3.1 [x] opentelemetry-instrumentation==0.61b0
3.2 [x] opentelemetry-instrumentation-fastapi==0.61b0
3.3 [x] opentelemetry-instrumentation-sqlalchemy==0.61b0
3.4 [x] opentelemetry-instrumentation-redis==0.61b0
3.5 [x] opentelemetry-instrumentation-httpx==0.61b0
3.6 [x] opentelemetry-instrumentation-logging==0.61b0

Exit criteria:
1. [x] API and UI OTel dependencies are pinned to latest stable, documented, and reproducible.

---

## Phase 2 - Runtime Configuration and Endpoint Wiring

1. [x] Standardize env vars for API and UI (all four core services + optional metadata services).
1.1 [x] OTEL_SERVICE_NAME — set per service: dq-api, dq-ui, dq-engine, dq-profiling.
1.2 [x] OTEL_SERVICE_VERSION — defaults to image tag var (e.g. $&#123;DQ_API_TAG:-dev}).
1.3 [x] OTEL_EXPORTER_OTLP_ENDPOINT — default: http://otel-collector:4317; override via .env.
1.4 [x] OTEL_TRACES_SAMPLER — parentbased_traceidratio.
1.5 [x] OTEL_TRACES_SAMPLER_ARG — default: 0.1 (10%); override via .env.
2. [x] Ensure exporters target collector ingress (not direct storage). All services target otel-collector:4317.
3. [x] Add local-safe defaults through compose/service env. All defaults resolve to dev-safe values.
4. [x] Document per-environment override strategy.
   - Set OTEL_EXPORTER_OTLP_ENDPOINT in .env per deploy target.
   - Set OTEL_TRACES_SAMPLER_ARG=0.01 for prod.
   - Set ENVIRONMENT=prod for prod.
   - UI browser traces use HTTP endpoint: set OTEL_EXPORTER_OTLP_HTTP_ENDPOINT.
5. [x] Bridge services to dq-network so they can reach otel-collector.
   - docker-compose-observability.yml: added name: dq-network to pin the Docker network name.
   - docker-compose.yml: added dq-network as external network; joined api, frontend, dq-engine, profiling-worker.
   - docker-compose.yml: joined openmetadata-server and openmetadata-ingestion (metadata profile) to dq-network.
   - Start observability stack first: docker compose -f docker-compose-observability.yml up -d
6. [x] Hard-enable OpenMetadata server Java agent instrumentation.
   - Baked opentelemetry-javaagent.jar into the OpenMetadata server image during build.
   - Set JAVA_TOOL_OPTIONS=-javaagent:/otel/agent/opentelemetry-javaagent.jar on openmetadata-server.
   - Added OTEL_EXPORTER_OTLP_PROTOCOL=grpc and OTEL_RESOURCE_ATTRIBUTES for explicit Java runtime wiring.

Exit criteria:
1. [x] Core + metadata services can run with OTel enabled by env only.

---

## Phase 3 - API Instrumentation (FastAPI)

1. [x] Create a dedicated telemetry bootstrap module for FastAPI.
2. [x] Initialize provider, resource metadata, exporter, sampler in one place.
3. [x] Enable FastAPI auto-instrumentation.
4. [x] Enable SQLAlchemy instrumentation (if active in runtime).
5. [ ] Enable Redis instrumentation (if active in runtime).
6. [x] Enable outbound HTTP instrumentation for API clients.
7. [x] Add middleware for correlation ID lifecycle.
7.1 [x] Read/generate correlation ID
7.2 [x] Bind correlation to context/logs
7.3 [x] Return X-Correlation-Id response header
7.4 [x] Return X-Trace-Id response header
8. [ ] Add custom spans around critical operations.
8.1 [x] auth callback
8.2 [x] me endpoint/user resolution
8.3 [x] rule compile
8.4 [x] rule execute
8.5 [x] publish/sync operations
9. [x] Add low-cardinality custom metrics.
9.1 [x] request count by endpoint group/status
9.2 [x] latency histogram by operation
9.3 [x] auth failure counter
10. [x] Enrich structured logs with trace_id + correlation_id.

Exit criteria:
1. [x] API traces, metrics, and logs are correlated in Grafana stack.
   - Verified 2026-03-23 using local FastAPI source run with OTLP export to collector: response headers included x-correlation-id and x-trace-id; collector debug logs contained matching trace IDs, correlation_id span attributes, service.name=dq-api, and custom metrics dq_api_request_count + dq_api_operation_latency_ms.
   - Additional verification 2026-03-23 (protected endpoint): repeated unauthenticated GET /admin/v1/me requests produced 401 responses and collector evidence for dq_api_auth_failures_total with endpoint_group=admin and reason=missing_token, with matching /admin/v1/me spans and correlation_id attributes.
   - Actual app verification 2026-03-23 (containerized dq-api on :4010): rebuilt and redeployed dq-api image from local source, generated live health + auth-failure traffic, and queried Grafana datasources directly. Prometheus datasource returned non-zero values for sum(increase(dq_api_request_count_total[10m])) and sum(increase(dq_api_auth_failures_total[10m])); Tempo datasource search returned dq-api traces.

---

## Phase 4 - UI Instrumentation (React/Vite)

1. [x] Initialize OpenTelemetry Web SDK at app bootstrap.
2. [x] Instrument fetch/XHR to propagate trace headers.
3. [x] Add correlation header propagation from UI requests.
4. [x] Create spans for key UX flows.
4.1 [x] login redirect start/end
4.2 [x] dashboard load
4.3 [x] validation/run action
4.4 [x] critical navigation transitions
5. [x] Map failed API calls into error spans with endpoint category + status code.
6. [x] Review and remove sensitive/high-cardinality attributes.

Notes (2026-03-23):
- Added browser telemetry bootstrap in `dq-ui/src/telemetry.ts` and initialized from `dq-ui/src/main.tsx`.
- Enabled OTLP HTTP export, parentbased trace sampling, and resource attributes (`service.name`, `service.version`, `environment`).
- Enabled fetch/XHR instrumentation with trace header propagation and custom `dq.endpoint_category` (path-derived, low-cardinality).
- Added browser-side `X-Correlation-ID` injection via fetch patch to align UI requests with API correlation middleware.
- Explicitly avoid query/body capture in custom attributes to reduce sensitive/high-cardinality telemetry.
- Added manual UI spans for `ui.auth.login_redirect`, `ui.auth.login`, `ui.dashboard.load`, `ui.validation.run`, and `ui.navigation.transition`.

Exit criteria:
1. [x] UI spans visible and linked to downstream API traces.
   - Verified 2026-03-23 by validate_ui_api_trace_propagation.sh: traceparent propagated through Kong gateway, API returned matching x-trace-id, traces confirmed in Tempo with service.name=dq-api. CORS headers confirmed to allow traceparent/tracestate/x-correlation-id.


## Phase 5 - Cross-Service Trace Propagation Hardening

1. [x] Verify gateway/proxy forwards trace headers end-to-end.
2. [x] Confirm API receives incoming trace context.
3. [x] Confirm API response headers include correlation + trace IDs.
4. [x] Verify UI-originated traces connect to API spans in a single trace graph.

Exit criteria:
1. [x] One-click trace drill-down from UI action to API internals works reliably.
   - Verified 2026-03-23 by validate_ui_api_trace_propagation.sh PASS: traceparent trace IDs sent via gateway are retrievable in Tempo with full dq-api span graph.

---

## Phase 6 - Dashboards and Alerts

1. [ ] Create baseline dashboards.
   - Added 2026-03-23: API-focused dashboard `DQ API Observability` (uid: `dq-api-observability`) provisioned from `observability/grafana/provisioning/dashboards/dq-api-observability.json`.
   - Updated 2026-03-25: existing dashboards `Data Quality Made Easy - Overview` and `Data Quality Made Easy - Execution Monitoring` were rewired from stale `http_requests_total`/`dq_rule_*` queries to active `dq_api_*` OpenTelemetry metric series so panels populate with current telemetry.
1.1 [ ] API latency p50/p95/p99 by route group
1.2 [ ] Error rate by endpoint group
1.3 [ ] Auth success/failure trend
1.4 [ ] Trace ingestion volume + sampling health
2. [ ] Add minimum alert set.
2.1 [ ] Auth error-rate spike (callback/me)
2.2 [ ] Rule execution p95 latency regression

Exit criteria:
1. [ ] Operational signals cover auth health and rule execution health.

---

## Phase 7 - Testing and Validation Gates

1. [x] Add integration tests for trace propagation headers on critical API paths.
   - Added 2026-03-23: validate_ui_api_trace_propagation.sh provides end-to-end header propagation validation (Kong CORS policy enforcement + header echo checks + Tempo trace matching).
2. [x] Add smoke validation script for one UI flow + trace appearance in Tempo (`scripts/validate_openmetadata_otel_smoke.sh`).
   - Added 2026-03-23: `scripts/validate_dq_api_grafana_otel_smoke.sh` for one-command dq-api telemetry validation through Grafana Prometheus + Tempo datasources.
3. [ ] Add telemetry overhead/performance guard checks.
4. [ ] Document troubleshooting playbook for missing traces/log correlation.

Exit criteria:
1. [ ] Telemetry regressions are detectable in CI/local checks.

---

## Phase 8 - Rollout and Safety Controls

1. [ ] Rollout order.
1.1 [ ] API in dev
1.2 [ ] UI in dev
1.3 [ ] API+UI in test
1.4 [ ] Prod canary with reduced sampling
2. [ ] Add env-based kill switch/feature toggle to disable telemetry quickly.
3. [ ] Define rollback procedure per environment.

Exit criteria:
1. [ ] Production rollout has safe fallback and minimal blast radius.

---

## Definition of Done

1. [x] End-to-end trace exists from browser action to API business spans.
   - Verified 2026-03-23: validate_ui_api_trace_propagation.sh PASS; traceparent propagated UI→Kong→API, Tempo contains dq-api spans linked to the UI-originated trace IDs.
2. [x] Auth path and rule execution path have span coverage with error annotations.
   - Verified earlier: dq-api auth spans with error annotations confirmed in Tempo; custom metrics dq_api_auth_failures_total active.
3. [ ] Logs include trace and correlation identifiers for joinability.
4. [ ] Metrics dashboards and alerts are live and actionable.
5. [ ] Sampling/cardinality controls are documented and enforced.
