# Engineering Decision Records

This folder contains repository-scoped Engineering Decision Records (EDRs).

EDRs complement the Architecture Decision Records under `architecture/adr/`.

Use an EDR when the decision is important and durable, but scoped to repository engineering practice rather than broad platform architecture. Typical examples include:
- Validation and testing workflow decisions
- Runtime and worker-operation conventions
- Observability implementation choices
- Tooling and repository workflow standards
- Documentation and operational conventions

Use an ADR when the decision changes or defines architecture-level system direction.

## Index

- [EDR-001-META](EDR-001-META-engineering-decision-records-scope-and-usage.md) - Engineering Decision Records scope and usage
- [EDR-002-VAL](EDR-002-VAL-gx-lifecycle-validator-parallelism-cli-control-and-external-case-catalog.md) - GX lifecycle validator parallelism, CLI control, and external case catalog
- [EDR-003-WRK](EDR-003-WRK-gx-worker-fail-closed-on-fatal-spark-runtime-failures.md) - GX worker fail-closed policy for fatal Spark and Py4J runtime failures
- [EDR-004-VAL](EDR-004-VAL-validator-case-parallelism-and-spark-queue-serialization.md) - Validator case parallelism and Spark queue serialization
- [EDR-005-OBS](EDR-005-OBS-execution-monitoring-dashboard-status-and-activity-semantics.md) - Execution monitoring dashboard status colors and activity-tile semantics
- [EDR-006-WRK](EDR-006-WRK-gx-worker-spark-memory-and-result-size-guardrails.md) - GX worker Spark memory and result-size guardrails
- [EDR-007-WRK](EDR-007-WRK-gx-worker-processing-queue-recovery-and-stale-message-handling.md) - GX worker processing-queue recovery and stale-message handling
- [EDR-008-VAL](EDR-008-VAL-fastapi-test-architecture-and-isolation.md) - FastAPI test architecture and isolation rules
- [EDR-009-API](EDR-009-API-api-data-contract-and-snake-case-naming.md) - API data contract and snake_case naming rules
- [EDR-010-INF](EDR-010-INF-kong-jwt-bootstrap-and-keycloak-lifecycle.md) - Kong JWT bootstrap and Keycloak lifecycle rules
- [EDR-011-OBS](EDR-011-OBS-opentelemetry-instrumentation-and-trace-context.md) - OpenTelemetry instrumentation and trace-context rules
- [EDR-012-DB](EDR-012-DB-csv-first-seeding-and-schema-bootstrap.md) - CSV-first seeding and schema bootstrap rules
- [EDR-013-UI](EDR-013-UI-frontend-auth-state-and-token-ordering.md) - Frontend auth state and token ordering rules
- [EDR-014-DEL](EDR-014-DEL-data-delivery-selector-resolution-and-materialization.md) - Data-delivery selector resolution and materialization rules
- [EDR-015-DB](EDR-015-DB-postgresql-transaction-isolation-and-mutation-semantics.md) - PostgreSQL transaction isolation and mutation semantics
- [EDR-016-ENG](EDR-016-ENG-shared-spark-runtime-coordination.md) - Shared Spark runtime coordination rules
- [EDR-017-VAL](EDR-017-VAL-data-generation-fixtures-and-contract-parity.md) - Data-generation fixtures and contract parity rules
- [EDR-018-API](EDR-018-API-gx-execution-contract-and-autopublish-patterns.md) - GX execution contract and autopublish patterns
- [EDR-019-INF](EDR-019-INF-openmetadata-integration-and-data-contract-resolution.md) - OpenMetadata integration and data-contract resolution patterns
- [EDR-020-UI](EDR-020-UI-frontend-async-request-tracking-and-profiling-history.md) - Frontend async request tracking and profiling history patterns
- [EDR-021-DB](EDR-021-DB-rule-version-metadata-synchronization-and-snapshots.md) - Rule-version metadata synchronization and snapshot rules
- [EDR-022-WRK](EDR-022-WRK-profiling-worker-status-transitions-and-queue-lifecycle.md) - Profiling worker status transitions and queue lifecycle rules
- [EDR-023-API](EDR-023-API-auth-scope-enforcement-and-role-based-access.md) - Auth scope enforcement and role-based access rules
- [EDR-024-UI](EDR-024-UI-frontend-workflow-and-rule-governance-transitions.md) - Frontend workflow and rule-governance transition patterns
- [EDR-025-INF](EDR-025-INF-kong-cors-and-trace-header-propagation.md) - Kong CORS and trace-header propagation rules
- [EDR-026-API](EDR-026-API-rule-lifecycle-validator-and-compiler-kickoff.md) - Rule-lifecycle validator and compiler kickoff patterns
- [EDR-027-API](EDR-027-API-filter-expression-and-ast-edge-cases.md) - Filter-expression and AST edge-case rules
- [EDR-028-OBS](EDR-028-OBS-observability-stack-and-structured-log-pipeline.md) - Observability stack and structured log pipeline
- [EDR-029-UI](EDR-029-UI-frontend-otel-instrumentation-and-zone-context.md) - Frontend OpenTelemetry instrumentation and zone-context rules
- [EDR-030-INF](EDR-030-INF-zammad-support-integration-and-ticket-payload-mapping.md) - Zammad support integration and ticket payload mapping rules
- [EDR-031-DB](EDR-031-DB-delivery-data-consistency-and-fk-mapping.md) - Delivery data consistency and foreign-key mapping rules
- [EDR-032-API](EDR-032-API-dynamic-grouping-and-execution-planning-patterns.md) - Dynamic grouping and execution-planning patterns
- [EDR-033-API](EDR-033-API-source-data-resolution-and-materialization-selection.md) - Source data resolution and materialization-selection rules
- [EDR-034-UI](EDR-034-UI-frontend-preferences-and-stale-state-management.md) - Frontend preferences and stale-state management rules
- [EDR-035-INF](EDR-035-INF-container-runtime-and-build-context-setup.md) - Container runtime and build-context setup rules
- [EDR-036-INF](EDR-036-INF-oidc-callback-base-and-public-endpoint-registration.md) - OIDC callback base and public-endpoint registration rules
- [EDR-037-API](EDR-037-API-validation-policy-legacy-json-and-config-versioning.md) - Validation policy legacy JSON and config-versioning rules
- [EDR-038-DB](EDR-038-DB-entity-model-ownership-and-versioned-attribute-attachment.md) - Entity model ownership and versioned attribute attachment
- [EDR-039-UI](EDR-039-UI-frontend-api-base-resolution-and-runtime-config.md) - Frontend API base resolution and runtime configuration
- [EDR-040-API](EDR-040-API-jsonschema-required-for-api-payload-contracts.md) - JSON Schema required for API payload contracts
- [EDR-041-VAL](EDR-041-VAL-python-arm64-launcher-required-on-apple-silicon.md) - Python arm64 launcher required on Apple Silicon
- [EDR-042-VAL](EDR-042-VAL-repository-scripts-must-run-on-macos-and-linux.md) - Repository scripts must run on macOS and Linux
- [EDR-043-VAL](EDR-043-VAL-environment-dependent-smoke-tests-belong-in-scripts.md) - Environment-dependent smoke tests belong in scripts
- [EDR-044-INF](EDR-044-INF-container-egress-enforcement-and-environment-specific-claims.md) - Container egress enforcement and environment-specific claims
- [EDR-045-META](EDR-045-META-user-manuals-docs-first-publishing-and-kebab-case-slug-convention.md) - User manuals docs-first publishing and kebab-case slug convention



## Authoring

- Start from [EDR_TEMPLATE.md](EDR_TEMPLATE.md)
- Name records `EDR-XXX-TAG-short-kebab-title.md`
- Use one uppercase tag abbreviation immediately after the record number to show the primary category
- Current tag set:
	- `META` - EDR system and documentation conventions
	- `VAL` - validation and test-runner behavior
	- `API` - API contracts, FastAPI behavior, and server-side semantics
	- `DB` - database schema, seeding, migrations, and persistence conventions
	- `DEL` - data delivery, selector resolution, and consistency rules
	- `ENG` - Spark engine and shared runtime coordination
	- `INF` - infrastructure and integration service behavior
	- `WRK` - worker, queue, and runtime execution behavior
	- `OBS` - observability, telemetry, and dashboard semantics
	- `UI` - frontend application behavior and UI runtime conventions
- Keep one stable decision per record
- Link related ADRs, implementation docs, code, and feature-tracker entries

## Migration Policy

- Durable repository decisions should end up in an EDR.
- Repository memory notes, fix summaries, and implementation-details documents are source material for EDR backfill, not the final system of record.
- Do not create one EDR per troubleshooting note or per incident unless the incident established a durable rule.
- Prefer one EDR per stable engineering decision, even if that EDR absorbs several related memory notes.
- Keep operational runbooks, transient troubleshooting notes, and environment-specific hacks outside the EDR set unless they define a lasting engineering policy.

See [EDR_MIGRATION_BACKLOG.md](EDR_MIGRATION_BACKLOG.md) for the current staged conversion backlog.

## Backfill Guidance

Existing decision material may currently live in:
- standalone markdown files
- implementation-details documents
- fix summaries
- repository memory notes

When a decision is durable and should become part of the long-term repo record, promote it into an EDR and link the source material.
