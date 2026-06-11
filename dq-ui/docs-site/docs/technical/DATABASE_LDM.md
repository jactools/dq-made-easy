# dq-made-easy Logical Data Model

This document defines the normalized logical data model for the platform. It is the contract for entity names, business keys, and cardinalities. It intentionally omits Postgres-specific storage details, indexes, and generated artifacts.

For full entity and element definitions, including BDE/CDE classification, see [DATABASE_LDM_DEFINITIONS.md](/docs/technical/DATABASE_LDM_DEFINITIONS/).

ODCS belongs above this layer: it governs product-level delivery and quality contracts, while this logical model governs the semantic entities and data elements that those contracts refer to.

## Contract

- Technical UUID7 identifiers remain internal persistence keys.
- Non-UI public APIs use business keys from [BUSINESS_KEYS.md](/docs/features/BUSINESS_KEYS/).
- Logical entities are modeled independently from physical table names.
- Versioned domains keep current pointers and history records separate.
- If a logical relationship changes, update the ERD and this document together.
- Use the companion definition appendix as the source of truth for BDE/CDE classification.

## Identity and Access


```mermaid
erDiagram
    workspace {
        string business_key
        string name
    }

    user {
        string id
        string external_id
        string preferences
    }

    role {
        string business_key
        string workspace
        string name
    }

    user_role {
        string user_id
        string role_id
    }

    exception_fact_access_request {
        string requester_id
        string workspace_id
        string role_id
        string status
    }

    workspace ||--o{ role : scopes
    workspace ||--o{ exception_fact_access_request : receives
    user ||--o{ user_role : assigned
    role ||--o{ user_role : grants
    user ||--o{ exception_fact_access_request : requests
    role ||--o{ exception_fact_access_request : targets
```

## Data Catalog

```mermaid
erDiagram
    data_product {
        string business_key
        string name
    }

    data_set {
        string business_key
        string name
    }

    data_object {
        string business_key
        string name
    }

    data_object_catalog {
        string business_key
        string name
    }

    data_object_version {
        string data_object_id
        int version
    }

    attribute_catalog {
        string name
        string type
        boolean is_business_key
    }

    attribute_definition_mapping {
        string attribute_id
        string mapping_state
    }

    data_delivery {
        string data_object_id
        int version
        string delivery_location
    }

    data_delivery_note {
        string data_delivery_id
        string storage_location
    }

    data_product ||--o{ data_set : contains
    data_set ||--o{ data_object_catalog : contains
    data_object ||--o{ data_object_catalog : canonicalizes
    data_object_catalog ||--o{ data_object_version : versions
    data_object_catalog ||--o{ attribute_catalog : attributes
    data_object_version ||--o{ attribute_catalog : version_attributes
    attribute_catalog ||--o{ attribute_definition_mapping : maps
    data_object_catalog ||--o{ data_delivery : deliveries
    data_delivery ||--o{ data_delivery_note : details
```

## Governance and Validation

```mermaid
erDiagram
    rule {
        string id
        string workspace
        string name
    }

    rule_version {
        string rule_id
        int version_number
    }

    rule_current_version {
        string rule_id
        string version_id
    }

    approval {
        string business_key
        string rule_id
        string workspace_id
    }

    test_proof {
        string rule_id
        string workspace
    }

    batch_test_request {
        string rule_id
        string proof_id
    }

    validation_artifact_registry {
        string validation_artifact_id
        int validation_artifact_version
        string engine_type
        string status
    }

    validation_artifact_status_history {
        string validation_artifact_id
        int validation_artifact_version
        string from_status
        string to_status
    }

    validation_run_plan {
        string business_key
        string workspace_id
        string status
    }

    validation_run_plan_version {
        string run_plan_id
        string artifact_id
        int artifact_version
    }

    validation_run_plan_transition {
        string run_plan_id
        string run_plan_version_id
        string action
    }

    validation_run {
        string workspace
        string triggered_by
        string status
    }

    validation_run_item {
        string run_id
        string rule_id
        int version_number
    }

    rule ||--o{ rule_version : snapshots
    rule_version ||--o{ rule_current_version : selected_version
    rule ||--o{ approval : governs
    rule ||--o{ test_proof : tested_by
    test_proof ||--o{ batch_test_request : proof_links
    validation_artifact_registry ||--o{ validation_artifact_status_history : history
    validation_run_plan ||--o{ validation_run_plan_version : versions
    validation_run_plan_version ||--o{ validation_run_plan_transition : lifecycle
    validation_run ||--o{ validation_run_item : items
```

## Profiling and Suggestions

```mermaid
erDiagram
    data_source_metadata {
        string data_source_id
        string name
        string source_type
    }

    data_source_profiling_request {
        string data_source_id
        string requested_by_user_id
        string status
    }

    suggestion {
        string user_id
        string data_source_id
        string status
    }

    suggestion_interaction {
        string suggestion_id
        string user_id
        string action
    }

    suggestion_preview_interaction {
        string user_id
        string workspace_id
        string action
    }

    data_source_metadata ||--o{ data_source_profiling_request : profiles
    data_source_profiling_request ||--o{ suggestion : seeds
    suggestion ||--o{ suggestion_interaction : interactions
```

## Notes

- The logical model is intentionally broader than the ERD table set. It captures entity families, business keys, and stable relationships, not storage mechanics.
- When a logical entity gets a new public lookup path, update [BUSINESS_KEYS.md](/docs/features/BUSINESS_KEYS/) at the same time.
- If a table is added to the physical schema, the logical model should be checked for the matching business entity and relationship.
- The detailed entity and element registry lives in [DATABASE_LDM_DEFINITIONS.md](/docs/technical/DATABASE_LDM_DEFINITIONS/).
