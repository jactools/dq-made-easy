# EDR Migration Backlog

This document tracks the conversion of durable repository decisions into Engineering Decision Records (EDRs).

The goal is not to create one EDR per memory note. The goal is to make EDRs the long-term system of record for stable engineering decisions, while using repository memory notes and older markdown documents as source material.

## Conversion Rules

- Convert durable engineering policies and conventions into EDRs.
- Aggregate related memory notes into a single EDR when they describe the same stable rule.
- Keep one-off troubleshooting notes, platform-specific hacks, release-progress summaries, and runbook-only steps outside the EDR set unless they establish a lasting rule.
- Link source notes from each EDR's `Related Artifacts` section when they informed the final decision.
- Prefer backfilling the highest-reuse decisions first: contract rules, test architecture, worker/runtime behavior, auth/gateway behavior, data/seeding conventions, and observability patterns.

## Current Status

- Existing EDRs: 43
- Repository memory notes: 154 as of 2026-04-19
- Repository memory breakdown source: `/memories/repo/dq-rulebuilder-memory-domain-breakdown-note.md`
- Prefix/domain grouping source: `/memories/repo/dq-rulebuilder-memory-domain-prefix-mapping-note.md`

## Existing Coverage

Already covered by the current EDR set:
- [x] EDR-001-META: EDR system scope and usage
- [x] EDR-002-VAL: validator parallelism CLI control and case-catalog structure
- [x] EDR-003-WRK: fail-closed policy for fatal Spark and Py4J worker failures
- [x] EDR-004-VAL: case-level validator parallelism versus Spark queue serialization
- [x] EDR-005-OBS: execution-monitoring dashboard semantics
- [x] EDR-006-WRK: GX worker Spark memory and result-size guardrails
- [x] EDR-007-WRK: GX worker processing-queue recovery and stale-message handling
- [x] EDR-008-VAL: FastAPI test architecture and isolation rules
- [x] EDR-009-API: API data contract and snake_case naming rules
- [x] EDR-010-INF: Kong JWT bootstrap and Keycloak lifecycle rules
- [x] EDR-011-OBS: OpenTelemetry instrumentation and trace-context rules
- [x] EDR-012-DB: CSV-first seeding and schema bootstrap rules
- [x] EDR-013-UI: Frontend auth state and token ordering rules
- [x] EDR-014-DEL: Data-delivery selector resolution and materialization rules
- [x] EDR-015-DB: PostgreSQL transaction isolation and mutation semantics
- [x] EDR-016-ENG: Shared Spark runtime coordination rules
- [x] EDR-017-VAL: Data-generation fixtures and contract parity rules
- [x] EDR-018-API: GX execution contract and autopublish patterns
- [x] EDR-019-INF: OpenMetadata integration and data-contract resolution patterns
- [x] EDR-020-UI: Frontend async request tracking and profiling history patterns
- [x] EDR-021-DB: Rule-version metadata synchronization and snapshot rules
- [x] EDR-022-WRK: Profiling worker status transitions and queue lifecycle rules
- [x] EDR-023-API: Auth scope enforcement and role-based access rules
- [x] EDR-024-UI: Frontend workflow and rule-governance transition patterns
- [x] EDR-025-INF: Kong CORS and trace-header propagation rules
- [x] EDR-026-API: Rule-lifecycle validator and compiler kickoff patterns
- [x] EDR-027-API: Filter-expression and AST edge-case rules
- [x] EDR-028-OBS: Observability stack and structured log pipeline
- [x] EDR-029-UI: Frontend OpenTelemetry instrumentation and zone-context rules
- [x] EDR-030-INF: Zammad support integration and ticket payload mapping rules
- [x] EDR-031-DB: Delivery data consistency and foreign-key mapping rules
- [x] EDR-032-API: Dynamic grouping and execution-planning patterns
- [x] EDR-033-API: Source data resolution and materialization-selection rules
- [x] EDR-034-UI: Frontend preferences and stale-state management rules
- [x] EDR-035-INF: Container runtime and build-context setup rules
- [x] EDR-036-INF: OIDC callback base and public-endpoint registration rules
- [x] EDR-037-API: Validation policy legacy JSON and config-versioning rules
- [x] EDR-038-DB: Entity model ownership and versioned attribute attachment
- [x] EDR-039-UI: Frontend API base resolution and runtime configuration
- [x] EDR-040-API: JSON Schema required for API payload contracts
- [x] EDR-041-VAL: Python arm64 launcher required on Apple Silicon
- [x] EDR-042-VAL: Repository scripts must run on macOS and Linux
- [x] EDR-043-VAL: Environment-dependent smoke tests belong in scripts

## Priority Backlog

### Tier 1

1. [x] `EDR-009-API-api-data-contract-and-snake-case-naming.md`
   Source clusters: `fastapi-gx-dispatch-snake-case-end-to-end-*`, `fastapi-structured-http-exception-detail-*`, `fastapi-view-model-from-attributes-*`, `fastapi-api-case-middleware-nested-dicts-*`
   Why first: this establishes the canonical backend contract rules and naming conventions.

2. [x] `EDR-010-INF-kong-jwt-bootstrap-and-keycloak-lifecycle.md`
   Source clusters: `kong-jwt-bootstrap-*`, `keycloak-composite-role-import-and-rebuild-*`, `keycloak-redirect-uri-import-order-*`, `keycloak-token-lifespan-*`
   Why first: auth and gateway bootstrap have repeated operational cost and should be stabilized as policy.

3. [x] `EDR-011-OBS-opentelemetry-instrumentation-and-trace-context.md`
   Source clusters: `dq-engine-gx-worker-otel-telemetry-*`, `fastapi-otel-*`, `otel-collector-*`, `ui-otel-*`
   Why first: observability behavior spans backend, worker, and UI and benefits from one canonical decision record.

4. [x] `EDR-012-DB-csv-first-seeding-and-schema-bootstrap.md`
   Source clusters: `contact-v3-seed-*`, `data-delivery-note-seed-csv-*`, `fastapi-rule-status-history-seed-*`, `seeded-smoke-schema-bootstrap-*`
   Why first: seeding and schema bootstrap behavior affects local setup, tests, and demos across the repository.

5. [x] `EDR-013-UI-frontend-auth-state-and-token-ordering.md`
   Source clusters: `ui-auth-*`, `ui-versioning-auth-bootstrap-*`, `ui-multi-workspace-login-*`, `ui-backend-scope-gating-*`
   Why first: frontend auth bugs are subtle and repeated; a canonical state model is high leverage.

6. [x] `EDR-014-DEL-data-delivery-selector-resolution-and-materialization.md`
   Source clusters: `abs2-*`, `delivery-*`, `data-deliveries-*`, `aistor-delivery-*`
   Why first: delivery/materialization rules are central to data consistency and runtime behavior.

7. [x] `EDR-015-DB-postgresql-transaction-isolation-and-mutation-semantics.md`
   Source clusters: `postgres-update-*`, `dqdb-*`, `fastapi-entity-migration-*`, `nonlegacy-scope-migration-*`
   Why first: transaction and migration rules are foundational and should stop living only in notes.

8. [x] `EDR-016-ENG-shared-spark-runtime-coordination.md`
   Source clusters: `shared-spark-runtime-*`, `dq-engine-offline-spark-jars-*`, `iceberg-spark-runtime-*`, `spark-ui-default-port-*`
   Why first: Spark coordination rules affect multiple workers and are larger than a single worker-specific EDR.

9. [x] `EDR-017-VAL-data-generation-fixtures-and-contract-parity.md`
    Source clusters: `fastapi-unified-queued-test-data-generation-*`, `fastapi-api67-seed-generator-*`, `fastapi-suggestions-fixture-csv-json-*`, `fastapi-test-proof-payload-contract-*`
    Why first: fixture and parity rules can be standardized early and reused broadly.

10. [x] `EDR-018-API-gx-execution-contract-and-autopublish-patterns.md`
    Source clusters: `fastapi-gx-autopublish-direct-checktype-builder-*`, `fastapi-gx-supported-rule-lifecycle-validator-*`, `gx-run-plan-validation-execution-contract-*`, `dq4-join-consistency-phase3-view-contract-*`
    Why first: execution contract shape and autopublish behavior span compiler, validator, and worker flows.

### Tier 2

11. [x] `EDR-019-INF-openmetadata-integration-and-data-contract-resolution.md`
12. [x] `EDR-020-UI-frontend-async-request-tracking-and-profiling-history.md`
13. [x] `EDR-021-DB-rule-version-metadata-synchronization-and-snapshots.md`
14. [x] `EDR-022-WRK-profiling-worker-status-transitions-and-queue-lifecycle.md`
15. [x] `EDR-023-API-api-auth-scope-enforcement-and-role-based-access.md`
16. [x] `EDR-024-UI-frontend-workflow-and-rule-governance-transitions.md`
17. [x] `EDR-025-INF-kong-cors-and-trace-header-propagation.md`
18. [x] `EDR-026-API-rule-lifecycle-validator-and-compiler-kickoff.md`
19. [x] `EDR-027-API-filter-expression-and-ast-edge-cases.md`
20. [x] `EDR-028-OBS-observability-stack-and-structured-log-pipeline.md`

### Tier 3

21. [x] `EDR-029-UI-frontend-otel-instrumentation-and-zone-context.md`
22. [x] `EDR-030-INF-zammad-support-integration-and-ticket-payload-mapping.md`
23. [x] `EDR-031-DB-delivery-data-consistency-and-fk-mapping.md`
24. [x] `EDR-032-API-dynamic-grouping-and-execution-planning-patterns.md`
25. [x] `EDR-033-API-source-data-resolution-and-materialization-selection.md`
26. [x] `EDR-034-UI-frontend-preferences-and-stale-state-management.md`
27. [x] `EDR-035-INF-container-runtime-and-build-context-setup.md`
28. [x] `EDR-036-INF-oidc-callback-base-and-public-endpoint-registration.md`
29. [x] `EDR-037-API-validation-policy-legacy-json-and-config-versioning.md`

## Keep as Memory Notes or Runbooks

These categories should usually not become standalone EDRs unless they are folded into a broader durable policy:

- release-progress notes such as `fastapi-api6-progress-note.md`
- memory system bookkeeping such as the memory breakdown and mapping notes
- dev-only troubleshooting notes like frontend port conflicts or platform-specific venv issues
- one-off dashboard sync quirks or macOS-specific tooling workarounds
- startup sequencing runbook notes that are operational instructions rather than lasting policy

## Post-Tier-3 Review of Remaining Notes

Reviewed on 2026-04-20.

Current disposition:
- Keep as memory/runbook material: release-progress tracking, memory bookkeeping, frontend port conflicts, Apple Silicon venv repair, one-off Grafana/macOS shell portability fixes, compose-metrics exporter troubleshooting, and seed/startup sequencing notes.
- Treat support-profile/startup ownership notes as already absorbed by accepted EDRs where applicable, especially EDR-030 and EDR-035.
- Do not promote `dq-rulebuilder-model-notes.md` as a single EDR. It is a mixed scratchpad and should only be mined into targeted records.

Potential revisit clusters from `dq-rulebuilder-model-notes.md` only if they become explicit repository contracts:
1. `DB/API` entity model ownership and legacy attribute deprecation:
   promote only if future work needs one stable rule covering `data_objects` lifecycle ownership, `data_object_versions` attribute attachment through `attributes_catalog`, and the retirement of legacy `attributes`-based behavior.
2. `UI/INF` frontend API endpoint resolution and runtime configuration:
   promote only if future work needs one stable rule covering centralized API base helpers, runtime-config injection, and the ban on hardcoded UI API targets.

Do not create EDRs for abstract invariants or generic override conventions by themselves. Promote only when the repository has made a concrete, durable engineering choice that multiple code paths are expected to follow.

Everything else currently left in memory/runbook scope is either already absorbed by EDR-010, EDR-013, EDR-019, EDR-023, EDR-030, EDR-035, or EDR-036, or is too narrow and operational to justify a standalone decision record.

## Deferred Follow-up Backlog

These items stay open for future work, but they are not accepted EDRs yet.

30. [x] `EDR-038-DB-entity-model-ownership-and-versioned-attribute-attachment.md`
31. [x] `EDR-039-UI-frontend-api-base-resolution-and-runtime-config.md`
32. [x] Audit invariants and conventions that are currently overridden in code, scripts, or configuration; remove accidental overrides, document approved exceptions, and promote only the remaining concrete repository rules.

### Reassessment Notes for Item 31

Reviewed on 2026-04-20.

Current judgment:
- The frontend now uses one centralized API-base contract in `dq-ui/src/config/api.ts`: runtime `window.__DQ_CONFIG__.API_BASE_URL` takes precedence over `VITE_API_URL` and `VITE_API_BASE_URL`, and app code fails fast when no base URL is configured.
- Container deployments inject runtime configuration through `/runtime-config.js`, loaded from `dq-ui/index.html` and generated by `dq-ui/scripts/docker-entrypoint-runtime-config.sh`.
- Local dev startup also resolves the API target explicitly in `dq-ui/scripts/start_local.sh`, rather than relying on per-component hardcoded URLs.
- The helper surface `normalizeApiBaseUrl()` and `toApiGroupV1Base()` is now used broadly across contexts, hooks, and components, including auth, settings, rules, data-catalog, governance, system, and support flows.
- The earlier hardcoded compare-path drift was removed, active documentation was aligned to the current fail-fast helper behavior, and bootstrap helpers were tightened so they no longer invent implicit API defaults.

Remaining caveats:
- Test scaffolding still seeds local API-base values explicitly in Vitest setup and component tests.

Implication for item 31:
- This cluster is now promoted into EDR-039.

### Reassessment Notes for Item 30

Reviewed on 2026-04-20 after targeted cleanup of active doc references.

Current judgment:
- The supported runtime stack now reads as one coherent model: `data_objects` for lifecycle identity, `data_objects_catalog` for catalog identity, `data_object_versions` for version truth, and `attributes_catalog` for the active attribute surface.
- Active documentation was cleaned to stop advertising legacy `/attributes` endpoints or old `dq-rules-ui/dist` build wording.
- The historical `dq-rules-ui` subtree is now explicitly quarantined as unsupported legacy material. Its generated seed/mock files and object-level `attributeIds` data are excluded from repository-wide model claims.
- Remaining `dq-rules-ui` references outside that subtree are primarily Keycloak client-id naming, not active frontend or entity-model ownership.

Implication for item 30:
- The `dq-rules-ui` subtree no longer blocks promotion of item 30.
- Item 30 is now promoted into EDR-038.

### Resolution Notes for Item 32

Reviewed on 2026-04-20.

Item 32 is closed. The concrete override and fallback cases identified in the audit were either removed, retired, or explicitly constrained as bounded compatibility exceptions.

Remaining scoped exceptions that may remain acceptable only while kept explicit and bounded:
- `dq-ui/src/config/api.ts` intentionally rewrites internal Docker host aliases and legacy API port `4001` to browser-safe/public values. Treat this as a temporary compatibility shim, not as a general override convention.
- validation harness scripts may keep seeded host, user, and password defaults when they are clearly test-only fixtures and not reused as production/bootstrap configuration.

Concrete follow-up targets:
1. [x] `dq-ui/src/components/RuleVersionComparison.tsx` was updated to use centralized API-base helpers instead of hardcoded `/api/rulebuilder/v1/...` paths.
2. [x] `dq-ui/src/contexts/SettingsContext.tsx` no longer seeds `assistanceRequestItsmEndpointUrl` with the internal container URL `http://zammad-nginx:8080/api/v1/tickets`; the default is now unset.
3. [x] `openmetadata-configure` and `dq-metadata/scripts/configure_openmetadata_container.sh` no longer use local-login fallback behavior when Keycloak/OIDC is unavailable; they now fail fast.
4. [x] `dq-api/scripts/legacy/init-db.js` was retired because it had no remaining consumers and still encoded the legacy `attributes` table and `data_objects.attributeIds` model.

Current audit judgment:
- The main remaining risk is not abstract invariants; it is compatibility shims and legacy defaults silently becoming normal behavior.
- Item 32 is considered complete because the audited accidental overrides were either removed or retired, and the remaining exceptions are now explicitly bounded.
- Future EDR promotion should happen only if one of these bounded exceptions hardens into an intentional repository-wide contract.

## Working Rule for Future Backfill

When a decision source is encountered during implementation work:
- If it defines a stable rule and no EDR exists, add or update the appropriate EDR candidate.
- If it is a narrow troubleshooting fact, keep it in repository memory or the relevant runbook.
- If several related notes point to one recurring engineering rule, promote that cluster into one EDR instead of many.