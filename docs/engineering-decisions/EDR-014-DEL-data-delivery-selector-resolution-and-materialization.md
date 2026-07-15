# EDR-014 [DEL]: Data-Delivery Selector Resolution and Materialization

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: DEL

## Context
The repository supports generic ABS-2 materialization requests, delivery inventory inspection, AIStor-backed delivery object seeding, and data-delivery seed generation. Those flows all depend on one stable model of how delivery targets are selected, identified, materialized, and turned into logical versus physical storage paths.

Several recurring issues showed that these behaviors need explicit repository rules:

- generic materialization requests must start from exactly one selector type and resolve that selector into concrete delivery targets deterministically
- workers and API callbacks have different ownership boundaries for persistence and terminal status updates
- delivery records use logical layered paths, while inspectors and storage clients need synthesized physical S3 URIs
- source data may express delivery paths with names, but generated seed SQL still needs correct catalog-backed identifiers
- prototype reseed flows sometimes need explicit AIStor cleanup, which should be opt-in rather than implicit

These are stable data-delivery and materialization rules, not one-off implementation details.

## Decision
Adopt the following data-delivery and materialization rules:

- Generic ABS-2 materialization requests accept exactly one selector from the supported selector set and fail fast if that constraint is violated.
- FastAPI resolves the single selector into one or more concrete `data_object_version_id` targets, persists both requested and resolved target metadata on the request record, and workers process the resolved targets as one batch.
- Completion callbacks persist one delivery note per resolved target and return aggregate delivery summary information alongside per-target detail.
- FastAPI owns durable delivery-row and delivery-note persistence through repository callbacks; workers do not bypass the API with direct database writes for completion persistence.
- Workers remain responsible for their terminal request-record runtime state, including final Redis/request-status updates after successful processing.
- Delivery rows store logical layered delivery paths using `layer` plus `delivery_location`; the deprecated `business_key` model is not the delivery identity surface anymore.
- Delivery inventory and storage inspection must synthesize physical S3 URIs from the workspace bucket plus the catalog-backed data object name rather than treating the logical `delivery_location` as a direct storage URI.
- Data-delivery seed generation must map delivery rows back through the data-objects catalog and fail fast when source CSV data cannot be resolved consistently.
- AIStor cleanup for delivery reseeding remains an explicit operator choice through purge or wipe flags rather than an implicit side effect of reseed.

## Rationale
- Single-selector input keeps request semantics unambiguous while still allowing multi-target batch resolution after server-side expansion.
- Separating API persistence ownership from worker runtime-state ownership keeps the write model explicit and avoids direct DB coupling in workers.
- Logical delivery paths are useful domain identifiers, but storage inspection needs a fully resolved physical location.
- Catalog-backed resolution prevents seed and delivery drift between names, ids, and locations.
- Explicit cleanup flags are safer than implicit destructive reseed behavior in shared prototype environments.

## Scope Boundaries
This decision applies to ABS-2 materialization request selection, delivery persistence callbacks, delivery path semantics, delivery inventory resolution, and delivery-oriented seed/materialization flows.

It does not by itself define:
- every future generator control or aggregate reporting shape for materialization
- generic storage abstraction across all repository services
- non-delivery data-catalog behaviors outside materialization and inventory inspection
- full bucket lifecycle management policies beyond the provided explicit cleanup flags

## Consequences
**Positive**
- Materialization requests have a deterministic input and resolution model.
- API and worker responsibilities stay explicit instead of overlapping through direct database access.
- Logical delivery records remain stable while storage inspection still gets concrete URIs.
- Seed generation fails early when catalog mapping drifts instead of producing inconsistent imports.

**Negative**
- Selector handling is stricter and requires callers to be explicit.
- Adjacent services need to stay aligned with persisted requested/resolved target metadata and delivery summary shape.
- Operators must choose destructive AIStor cleanup intentionally when they want a fully clean reseed.

## Implementation Guidance
- Enforce exactly one selector at request validation time and persist both requested and resolved target metadata.
- Keep worker completion persistence behind FastAPI callbacks and reserve worker-owned state transitions for runtime/request-record completion.
- Store logical layered delivery paths in delivery rows and synthesize S3 URIs only when a storage client or inspector needs them.
- Use the data-objects catalog as the identifier-to-name mapping source when resolving delivery locations.
- Fail fast when delivery CSV inputs cannot be mapped back to catalog ids or when delivery metadata drifts from catalog expectations.
- Keep AIStor purge and wipe behaviors behind explicit CLI flags.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-abs2-selector-resolution-single-target-note.md`
- `/memories/repo/dq-rulebuilder-abs2-materialization-worker-api-callback-note.md`
- `/memories/repo/dq-rulebuilder-delivery-inventory-logical-path-resolution-note.md`
- `/memories/repo/dq-rulebuilder-delivery-business-key-normalization-note.md`
- `/memories/repo/dq-rulebuilder-delivery-object-seed-workspace-layer-name-note.md`
- `/memories/repo/dq-rulebuilder-data-deliveries-catalog-fk-map-note.md`
- `/memories/repo/dq-rulebuilder-aistor-delivery-cleanup-flags-note.md`
- `dq-db/mock-data/data-deliveries.csv`
- `docker-compose.yml` (`delivery-seed`)
- `dq-api/scripts/generate_sql_seeds.py`
- `scripts/seed_delivery_objects.py`
- `scripts/stack_seed.sh` (or `scripts/stack.sh dev seed`)