# Business Keys and Stable Identity Surfaces

Goal: define a stable business-key layer across the platform so core entities can be looked up, filtered, grouped, and reported on using canonical identifiers that remain stable across renames and version churn.

Technical UUID7 identifiers are internal persistence keys. They must not be exposed by non-UI public APIs; only UI-based APIs may surface them when the editing flow needs a direct technical reference.

## Why this exists

The platform currently exposes a mix of technical IDs, versioned IDs, and semantic names. That is sufficient for persistence, but it is not a good contract for discovery, reporting, or cross-entity grouping.

Business keys solve that by giving the platform a stable, human-meaningful identity layer that sits alongside technical IDs.

## Scope

### In scope

- Rules and rule versions
- Data products, data sets, data objects, and data object versions
- Data deliveries and delivery notes
- GX suites and run plans
- Approvals and governance records
- Execution and violation records where stable grouping is useful
- Internal technical identifiers that stay hidden from non-UI public APIs

### Out of scope

- Replacing technical primary keys
- Renaming persisted historical records in place
- Silent fallback to display names when a canonical business key is missing

## Initial contract

The first implementation slice is additive:

- keep technical IDs intact
- add business-key metadata fields where the entity already has a semantic envelope
- expose business keys in read models and query filters
- keep UUID7 identifiers internal except where a UI-based API explicitly needs them
- backfill and enforce uniqueness later, after the stable contract is in place

## Canonical naming rules

Use the most stable canonical source value available for each entity family.

- Prefer an immutable domain identifier over a display name when the entity already has one.
- Prefer a normalized semantic name when the entity family is represented by business terminology rather than a generated identifier.
- Prefer a canonical storage/location string when the location itself is the stable business identity.
- Keep the chosen business key immutable once minted.
- Keep technical IDs authoritative for joins, foreign keys, and lifecycle operations.

Current entity-family mapping:

- Rules and rule versions: use the normalized rule name as the public business key; rule versions use the rule business key plus version number.
- Workspaces, users, and roles: use workspace name, external identity, and workspace-plus-role-name composites as the stable business-key surface.
- Data products, data sets, data objects, and data object catalog entries: use the canonical business name, normalized to a stable lowercase hyphenated form.
- Data deliveries and delivery notes: use the canonical delivery location and layered location path.
- GX suites and GX artifact envelopes: keep the suite identity contract separate from the execution hints metadata.
- GX run plans: use the run-plan identifier as the public business key.
- Approvals: use the approval identifier as the public business key.
- Execution and violation records: use the parent execution identity and row identity as the public grouping keys, not display text.

## Table Registry

Every persisted table must have a business key definition, either as an explicit `business_key` column or as a documented composite key.

| Table | Business key |
| --- | --- |
| `workspaces` | `name` |
| `users` | `external_id` when present; otherwise the seeded identity contract must mint one before publication |
| `roles` | `workspace + name` |
| `user_roles` | `user_id + role_id` |
| `exception_fact_access_requests` | `requester_id + workspace_id + role_id + requested_at` |
| `rules` | `workspace + normalized name` |
| `rule_versions` | `rule business key + version_number` |
| `rule_current_versions` | `rule_id` |
| `rule_version_diffs` | `rule_id + from_version_id + to_version_id` |
| `rule_rollbacks` | `rule_id + from_version_id + to_version_id + created_at` |
| `rule_version_relationships` | `parent_version_id + child_version_id + relationship_type` |
| `reusable_filters` | `workspace + name` |
| `rule_reusable_filters` | `rule_id + reusable_filter_id` |
| `reusable_joins` | `workspace + name` |
| `rule_attributes` | `rule_id + attribute_id` |
| `data_products` | `business_key` |
| `data_sets` | `business_key` |
| `data_objects` | `business_key` |
| `data_objects_catalog` | `business_key` |
| `data_object_versions` | `data_object business key + version` |
| `attributes_catalog` | `data_object_id + version_id + name` |
| `data_deliveries` | `layer + delivery_location` |
| `data_delivery_notes` | `data_delivery_id + layer + storage_location` |
| `approvals` | `business_key` |
| `audit` | `approval_id + action + timestamp` |
| `gx_suite_registry` | `suite_id + suite_version + artifact_version` |
| `gx_suite_rule_map` | `suite_id + suite_version + rule_id` |
| `gx_suite_execution_target_map` | `suite_id + suite_version + data_object_version_id` |
| `gx_run_plans` | `business_key` |
| `gx_run_plan_versions` | `run_plan_id + effective_from` |
| `gx_run_plan_transitions` | `run_plan_id + run_plan_version_id + action + occurred_at` |
| `gx_execution_runs` | `correlation_id` |
| `gx_execution_run_status_history` | `run_id + from_status + to_status + changed_at` |
| `gx_execution_violations` | `execution_run_id + rule_id + row_number` |
| `validation_artifact_registry` | `validation_artifact_id + validation_artifact_version` |
| `validation_artifact_status_history` | `validation_artifact_id + validation_artifact_version + changed_at` |
| `validation_run_plans` | `business_key` |
| `validation_run_plan_versions` | `run_plan_id + effective_from` |
| `validation_run_plan_transitions` | `run_plan_id + run_plan_version_id + action + occurred_at` |
| `validation_runs` | `workspace + run_at` |
| `validation_run_items` | `run_id + rule_id + version_number` |
| `suggestions` | `user_id + data_source_id + rule_type + created_at` |
| `suggestion_interactions` | `suggestion_id + user_id + action + created_at` |
| `data_source_metadata` | `data_source_id` |
| `data_source_profiling_requests` | `data_source_id + requested_at` |
| `test_proofs` | `ruleid + test_date + tested_by` |
| `batch_test_requests` | `workspace + completed_at + proof_id` |
| `app_config` | `config_key` |
| `system_info` | `info_key` |

The registry is the canonical contract for the current model set. If a table gets a new column family or a new derived lookup path, add a business-key definition here at the same time.

## Phases

### Phase 1 - Canonical metadata and read/write contract

Add the additive business-key fields to the most visible contract surfaces and prove the serialization path end to end.

#### Outcomes

- Rule publishing can carry business-key metadata.
- GX artifact envelopes can carry business-key metadata.
- Attribute catalog entries can mark whether an attribute participates in a business key.
- Public API payloads can expose business-key metadata without changing existing technical IDs.

#### Deliverables

- Pydantic schema updates for business-key fields
- repository round-trip support for additive metadata
- focused tests for serialization and persistence

### Phase 2 - Entity expansion and uniqueness rules

Extend the business-key layer to the remaining entity families and define uniqueness by entity scope.

#### Outcomes

- Rules, data objects, deliveries, GX suites, run plans, and approvals have explicit business-key surfaces.
- Uniqueness rules are defined per entity family.
- Historical records keep technical joins intact.

#### Deliverables

- entity-specific business-key fields and constraints
- backfill plan for existing rows
- collision detection and migration scripts

### Phase 3 - Public lookup and filter support

Expose business keys in the lookup and filter surfaces that consumers actually use.

#### Outcomes

- API clients can filter or fetch by business key where appropriate.
- Read models return the canonical business key alongside technical IDs.
- Reporting and admin flows can group related records across versions.

#### Deliverables

- endpoint query filters
- read-model enrichment
- contract updates and response tests

### Phase 4 - Backfill and governance hardening

Backfill existing records, enforce uniqueness, and document the governance model.

#### Outcomes

- Existing records have stable business keys.
- Duplicate keys are resolved deterministically.
- The business-key policy is documented for future contributors.

#### Deliverables

- migration scripts
- collision-resolution policy
- final validation tests and docs

## Acceptance criteria

- Business keys are stable and immutable once minted.
- Technical IDs remain the authoritative primary keys.
- Public responses and filters can carry business-key metadata where it is useful.
- Existing records can be backfilled without breaking historical joins.
- The first implementation slice ships without requiring a full schema rewrite.

## Related references

- [ADR-019](/docs/architecture/adr/ADR-019-platform-business-keys-and-stable-identity-surfaces/)
- [ADR-018](/docs/architecture/adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii/)
- [ABS-2](/docs/status/current/ABS_2_DATA_CATALOG_MATERIALIZATION/)
- [ABS-3](/docs/status/current/ABS_3_DELIVERY_LINKED_RULE_EXECUTION/)