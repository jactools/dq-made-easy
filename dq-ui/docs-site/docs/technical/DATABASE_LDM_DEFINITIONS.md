# dq-made-easy Logical Data Model Definitions

This appendix is the detailed definition registry for [DATABASE_LDM.md](/docs/technical/DATABASE_LDM/).

It defines the logical entities and logical elements that belong to the normalized platform model, and it classifies each item as either:

- CDE: common data element or common logical concept, standardized across the platform
- BDE: business data element or domain-specific logical concept, specific to one bounded context or workflow

Technical UUID7 identifiers remain internal persistence keys. They are not part of the conceptual contract. ODCS sits above this layer and governs product-level delivery and quality contracts, while this appendix governs the semantic entities and elements those contracts reference.

## Identity & Access

### Entity definitions

| Entity | Definition | Class |
| --- | --- | --- |
| `workspace` | Tenant-scoped governance boundary for users, roles, catalog assets, and operational records. | CDE |
| `user` | Actor identity used for authentication, ownership, and workspace membership. | CDE |
| `role` | Workspace-scoped permission bundle assigned to users. | CDE |
| `user_role` | Assignment record linking a user to a role. | BDE |
| `exception_fact_access_request` | Request for temporary access to exception-fact data within a workspace. | BDE |

### Element definitions

| Entity | Element | Definition | Class |
| --- | --- | --- | --- |
| `workspace` | `business_key` | Stable public workspace identifier. | CDE |
| `workspace` | `name` | Human-readable workspace name. | CDE |
| `user` | `id` | Internal user identifier carried as the technical persistence key. | CDE |
| `user` | `external_id` | External identity subject used to align the user with an upstream identity provider. | CDE |
| `user` | `preferences` | User preference payload, including presentation or behavior settings. | BDE |
| `role` | `business_key` | Stable role identifier, typically derived from workspace and role name. | CDE |
| `role` | `workspace` | Workspace scope that owns the role. | CDE |
| `role` | `name` | Human-readable role name. | CDE |
| `role` | `permissions` | Permission payload describing the capabilities granted by the role. | BDE |
| `user_role` | `user_id` | User reference used in the membership mapping. | CDE |
| `user_role` | `role_id` | Role reference used in the membership mapping. | CDE |
| `exception_fact_access_request` | `requester_id` | User requesting access. | CDE |
| `exception_fact_access_request` | `workspace_id` | Workspace that owns the request scope. | CDE |
| `exception_fact_access_request` | `role_id` | Role being requested or referenced. | CDE |
| `exception_fact_access_request` | `status` | Lifecycle state of the access request. | CDE |

## Data Catalog

### Entity definitions

| Entity | Definition | Class |
| --- | --- | --- |
| `data_product` | Top-level business domain that groups related data assets. | CDE |
| `data_set` | Logical grouping within a data product. | CDE |
| `data_object` | Concrete business object that can be versioned and delivered. | CDE |
| `data_object_catalog` | Dataset-scoped catalog identity for a data object. | CDE |
| `data_object_version` | Versioned realization of a data object schema and its attributes. | CDE |
| `attribute_catalog` | Governed attribute entry that can attach to a data object or a specific version. | CDE |
| `attribute_definition_mapping` | Registry mapping from an attribute to a governed definition. | BDE |
| `data_delivery` | Operational record describing one delivered artifact for a data object version. | CDE |
| `data_delivery_note` | Read model for one concrete delivery, keyed by delivery identity and location. | CDE |

### Element definitions

| Entity | Element | Definition | Class |
| --- | --- | --- | --- |
| `data_product` | `business_key` | Stable public product identifier. | CDE |
| `data_product` | `name` | Human-readable product name. | CDE |
| `data_set` | `business_key` | Stable public dataset identifier. | CDE |
| `data_set` | `name` | Human-readable dataset name. | CDE |
| `data_object` | `business_key` | Stable public data-object identifier. | CDE |
| `data_object` | `name` | Human-readable data-object name. | CDE |
| `data_object_catalog` | `business_key` | Stable public catalog identifier for the object. | CDE |
| `data_object_catalog` | `name` | Human-readable catalog name. | CDE |
| `data_object_version` | `data_object_id` | Reference to the owning data-object catalog entry. | CDE |
| `data_object_version` | `version` | Monotonic version number for the object schema. | CDE |
| `attribute_catalog` | `name` | Canonical attribute name. | CDE |
| `attribute_catalog` | `type` | Attribute type or semantic representation term. | BDE |
| `attribute_catalog` | `is_business_key` | Flag indicating that the attribute participates in a business key. | CDE |
| `attribute_definition_mapping` | `attribute_id` | Attribute reference used by the mapping registry. | CDE |
| `attribute_definition_mapping` | `mapping_state` | Mapping lifecycle state, such as mapped or unmapped. | CDE |
| `data_delivery` | `data_object_id` | Owning data-object catalog reference. | CDE |
| `data_delivery` | `version` | Data-object version represented by the delivery. | CDE |
| `data_delivery` | `delivery_location` | Canonical storage or delivery location for the output. | BDE |
| `data_delivery_note` | `data_delivery_id` | Stable delivery identifier used to retrieve the note. | CDE |
| `data_delivery_note` | `storage_location` | Canonical storage reference captured in the note. | BDE |

## Governance & Validation

### Entity definitions

| Entity | Definition | Class |
| --- | --- | --- |
| `rule` | Business rule definition that can be versioned, approved, and executed. | CDE |
| `rule_version` | Immutable revision of a rule. | CDE |
| `rule_current_version` | Pointer from a rule to its currently selected version. | BDE |
| `approval` | Governance record that captures the approval state of a rule or related asset. | CDE |
| `test_proof` | Evidence record that captures validation results for a rule. | CDE |
| `batch_test_request` | Workflow record that requests a batch of rule tests. | BDE |
| `validation_artifact_registry` | Registry entry for a governed validation artifact and its runtime envelope. | CDE |
| `validation_artifact_status_history` | Audit trail of validation-artifact lifecycle transitions. | BDE |
| `validation_run_plan` | Governed execution plan for validation runs. | CDE |
| `validation_run_plan_version` | Immutable snapshot of a validation run-plan version. | CDE |
| `validation_run_plan_transition` | Lifecycle event for a validation run plan. | BDE |
| `validation_run` | Operational record for one validation execution run. | CDE |
| `validation_run_item` | Per-rule result row inside a validation run. | BDE |

### Element definitions

| Entity | Element | Definition | Class |
| --- | --- | --- | --- |
| `rule` | `id` | Internal rule identifier used as the logical row key. | CDE |
| `rule` | `workspace` | Workspace scope that owns the rule. | CDE |
| `rule` | `name` | Human-readable rule name. | CDE |
| `rule_version` | `rule_id` | Owning rule reference. | CDE |
| `rule_version` | `version_number` | Immutable version number within the rule lifecycle. | CDE |
| `rule_current_version` | `rule_id` | Rule reference for the current-version pointer. | CDE |
| `rule_current_version` | `version_id` | Selected version reference. | CDE |
| `approval` | `business_key` | Stable approval identifier used in public lookup. | CDE |
| `approval` | `rule_id` | Rule being approved. | CDE |
| `approval` | `workspace_id` | Workspace that owns the approval record. | CDE |
| `test_proof` | `rule_id` | Rule being tested. | CDE |
| `test_proof` | `workspace` | Workspace scope for the proof record. | CDE |
| `batch_test_request` | `rule_id` | Rule being requested for batch test execution. | CDE |
| `batch_test_request` | `proof_id` | Proof record associated with the batch request. | CDE |
| `validation_artifact_registry` | `validation_artifact_id` | Stable validation-artifact identifier. | CDE |
| `validation_artifact_registry` | `validation_artifact_version` | Immutable validation-artifact version number. | CDE |
| `validation_artifact_registry` | `engine_type` | Engine family that can execute the artifact. | BDE |
| `validation_artifact_registry` | `status` | Lifecycle state of the validation artifact. | CDE |
| `validation_artifact_status_history` | `validation_artifact_id` | Validation-artifact identifier being tracked. | CDE |
| `validation_artifact_status_history` | `validation_artifact_version` | Validation-artifact version being tracked. | CDE |
| `validation_artifact_status_history` | `from_status` | Previous lifecycle state. | CDE |
| `validation_artifact_status_history` | `to_status` | New lifecycle state. | CDE |
| `validation_run_plan` | `business_key` | Stable public run-plan identifier. | CDE |
| `validation_run_plan` | `workspace_id` | Workspace that owns the plan. | CDE |
| `validation_run_plan` | `status` | Lifecycle state of the plan. | CDE |
| `validation_run_plan_version` | `run_plan_id` | Owning run-plan reference. | CDE |
| `validation_run_plan_version` | `artifact_id` | Selected validation-artifact reference. | CDE |
| `validation_run_plan_version` | `artifact_version` | Selected validation-artifact version. | CDE |
| `validation_run_plan_transition` | `run_plan_id` | Run-plan reference for the transition event. | CDE |
| `validation_run_plan_transition` | `run_plan_version_id` | Version reference associated with the transition. | CDE |
| `validation_run_plan_transition` | `action` | Lifecycle action that occurred. | CDE |
| `validation_run` | `workspace` | Workspace that owns the run. | CDE |
| `validation_run` | `triggered_by` | Actor or system that initiated the run. | BDE |
| `validation_run` | `status` | Lifecycle state of the run. | CDE |
| `validation_run_item` | `run_id` | Parent validation-run reference. | CDE |
| `validation_run_item` | `rule_id` | Rule evaluated by the item. | CDE |
| `validation_run_item` | `version_number` | Rule version evaluated by the item. | CDE |

## Profiling & Suggestions

### Entity definitions

| Entity | Definition | Class |
| --- | --- | --- |
| `data_source_metadata` | Registry record describing a profiled source system or dataset. | CDE |
| `data_source_profiling_request` | Request to profile a data source and persist the result. | BDE |
| `suggestion` | Generated suggestion derived from profiling or analysis. | CDE |
| `suggestion_interaction` | User interaction record for a suggestion. | BDE |
| `suggestion_preview_interaction` | User interaction record for a previewed suggestion. | BDE |

### Element definitions

| Entity | Element | Definition | Class |
| --- | --- | --- | --- |
| `data_source_metadata` | `data_source_id` | Stable external source identifier. | CDE |
| `data_source_metadata` | `name` | Human-readable source name. | CDE |
| `data_source_metadata` | `source_type` | Source-system type or category. | BDE |
| `data_source_profiling_request` | `data_source_id` | Source being profiled. | CDE |
| `data_source_profiling_request` | `requested_by_user_id` | User who requested profiling. | CDE |
| `data_source_profiling_request` | `status` | Lifecycle state of the profiling request. | CDE |
| `suggestion` | `user_id` | User associated with the suggestion. | CDE |
| `suggestion` | `data_source_id` | Source that produced or anchors the suggestion. | CDE |
| `suggestion` | `status` | Lifecycle state of the suggestion. | CDE |
| `suggestion_interaction` | `suggestion_id` | Suggestion being interacted with. | CDE |
| `suggestion_interaction` | `user_id` | User performing the interaction. | CDE |
| `suggestion_interaction` | `action` | Interaction action, such as accepted or dismissed. | BDE |
| `suggestion_preview_interaction` | `user_id` | User who previewed the suggestion. | CDE |
| `suggestion_preview_interaction` | `workspace_id` | Workspace that scoped the preview. | CDE |
| `suggestion_preview_interaction` | `action` | Preview action that was taken. | BDE |

## Classification Notes

- Use CDE for stable identifiers, relationship keys, version numbers, lifecycle states, and other standardized cross-domain elements.
- Use BDE for domain-specific payloads, workflow-specific action fields, and semantic properties that are specific to one bounded context.
- When a logical element is promoted to a shared contract surface, re-evaluate its class and update this appendix together with [BUSINESS_KEYS.md](/docs/features/BUSINESS_KEYS/).
