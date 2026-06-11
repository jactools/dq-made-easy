from copy import deepcopy


_ADMIN_USERS = [
    {
        "id": "user-admin",
        "name": "Platform Admin",
        "email": "admin@example.com",
        "roles": ["admin"],
        "workspaces": ["default", "retail-banking"],
        "preferences": {
            "profile": {"language": "en"},
            "display": {"theme": "dark"},
        },
    },
    {
        "id": "user-analyst",
        "name": "Data Analyst",
        "email": "analyst@example.com",
        "roles": ["analyst"],
        "workspaces": ["retail-banking"],
        "preferences": {"profile": {"language": "nl"}},
    },
    {
        "id": "user-steward",
        "name": "Data Steward",
        "email": "steward@example.com",
        "roles": ["data-steward"],
        "workspaces": ["governance"],
        "preferences": {"notifications": {"emailOnApproval": True}},
    },
]

_ADMIN_ROLES = [
    {"id": "viewer", "name": "Viewer", "workspace": "default", "permissions": ["dq:rules:read"]},
    {
        "id": "auditor",
        "name": "Auditor",
        "workspace": "global",
        "permissions": [
            "dq:rules:read",
            "dq:workspace:read",
            "dq:admin:read",
            "dq:data_catalog:read",
            "dq:reports:read",
            "dq:audit:read",
            "dq:templates:read",
            "dq:notifications:read",
        ],
    },
    {
        "id": "regulator",
        "name": "Regulator",
        "workspace": "global",
        "permissions": [
            "dq:rules:read",
            "dq:workspace:read",
            "dq:admin:read",
            "dq:data_catalog:read",
            "dq:reports:read",
            "dq:audit:read",
            "dq:templates:read",
            "dq:notifications:read",
        ],
    },
    {
        "id": "analyst",
        "name": "Analyst",
        "workspace": "default",
        "permissions": ["dq:rules:read", "dq:rules:create", "dq:rules:edit", "dq:rules:test", "dq:profiling:request"],
    },
    {
        "id": "data-steward",
        "name": "Data Steward",
        "workspace": "default",
        "permissions": ["dq:rules:read", "dq:rules:create", "dq:rules:edit", "dq:rules:test", "dq:profiling:request", "dq:rules:approve"],
    },
    {
        "id": "admin",
        "name": "Admin",
        "workspace": "default",
        "permissions": [
            "dq:rules:read",
            "dq:rules:write",
            "dq:rules:approve",
            "dq:rules:activate",
            "dq:users:manage",
            "dq:workspace:manage",
            "dq:config:manage",
            "dq:workspace:read",
            "dq:admin:read",
            "dq:profiling:request",
            "dq:data_catalog:read",
            "dq:reports:read",
            "dq:audit:read",
            "dq:templates:read",
            "dq:templates:write",
            "dq:notifications:read",
        ],
    },
    {
        "id": "exception-fact-reader",
        "name": "Exception Fact Reader",
        "workspace": "global",
        "permissions": ["dq:exceptions:read"],
    },
    {
        "id": "exception-fact-investigator",
        "name": "Exception Fact Investigator",
        "workspace": "global",
        "permissions": ["dq:exceptions:detail"],
    },
]

_APPROVALS = [
    {
        "id": "approval-001",
        "businessKey": "approval-001",
        "ruleId": "rule-email-format",
        "status": "pending",
        "requesterId": "user-analyst",
        "workspaceId": "retail-banking",
    },
    {
        "id": "approval-002",
        "businessKey": "approval-002",
        "ruleId": "rule-duplicate-customer",
        "status": "approved",
        "requesterId": "user-steward",
        "workspaceId": "governance",
    },
    {
        "id": "approval-003",
        "businessKey": "approval-003",
        "ruleId": "rule-iban-check",
        "status": "declined",
        "requesterId": "user-analyst",
        "workspaceId": "retail-banking",
    },
    {
        "id": "approval-004",
        "businessKey": "approval-004",
        "ruleId": "rule-email-format",
        "status": "pending",
        "requestType": "deactivation",
        "requesterId": "user-analyst",
        "workspaceId": "retail-banking",
        "comments": "Deactivate after release window",
    },
    {
        "id": "approval-005",
        "businessKey": "approval-005",
        "ruleId": "rule-email-format",
        "status": "approved",
        "requestType": "deactivation",
        "requesterId": "user-analyst",
        "workspaceId": "retail-banking",
        "reviewedBy": "user-admin",
        "reviewedAt": "2026-03-11T10:30:00Z",
        "comments": "Approved for controlled shutdown",
    },
    {
        "id": "approval-006",
        "businessKey": "approval-006",
        "ruleId": "rule-email-format",
        "status": "rejected",
        "requestType": "deactivation",
        "requesterId": "user-analyst",
        "workspaceId": "retail-banking",
        "reviewedBy": "user-steward",
        "reviewedAt": "2026-03-12T09:15:00Z",
        "comments": "Rejected while validation was still active",
    },
]

_APPROVAL_AUDIT = [
    {
        "id": "audit-001",
        "approvalId": "approval-001",
        "action": "created",
        "actorId": "user-analyst",
        "timestamp": "2026-03-01T10:00:00Z",
        "details": {"requesterId": "user-analyst"},
    },
    {
        "id": "audit-002",
        "approvalId": "approval-002",
        "action": "approved",
        "actorId": "user-admin",
        "timestamp": "2026-03-02T09:30:00Z",
        "details": {"status": "approved"},
    },
    {
        "id": "audit-003",
        "approvalId": "approval-004",
        "action": "created",
        "actorId": "user-analyst",
        "timestamp": "2026-03-11T09:45:00Z",
        "details": {"requestType": "deactivation", "status": "pending"},
    },
    {
        "id": "audit-004",
        "approvalId": "approval-005",
        "action": "created",
        "actorId": "user-analyst",
        "timestamp": "2026-03-11T10:00:00Z",
        "details": {"requestType": "deactivation", "status": "pending"},
    },
    {
        "id": "audit-005",
        "approvalId": "approval-005",
        "action": "approved",
        "actorId": "user-admin",
        "timestamp": "2026-03-11T10:30:00Z",
        "details": {"requestType": "deactivation", "status": "approved"},
    },
    {
        "id": "audit-006",
        "approvalId": "approval-006",
        "action": "created",
        "actorId": "user-analyst",
        "timestamp": "2026-03-12T09:00:00Z",
        "details": {"requestType": "deactivation", "status": "pending"},
    },
    {
        "id": "audit-007",
        "approvalId": "approval-006",
        "action": "rejected",
        "actorId": "user-steward",
        "timestamp": "2026-03-12T09:15:00Z",
        "details": {"requestType": "deactivation", "status": "rejected"},
    },
]

_WORKSPACES = [
    {"id": "default", "name": "Default", "description": "Default workspace"},
    {"id": "retail-banking", "name": "Retail Banking", "description": "Retail data domain"},
    {"id": "governance", "name": "Governance", "description": "Governance and controls"},
]

_TEST_PROOFS = [
    {
        "id": "tp-001",
        "ruleId": "rule-email-format",
        "testDate": "2026-02-20T10:00:00",
        "coverage": 0.98,
        "status": "passed",
        "recordsTestedCount": 1200,
        "failuresFound": 2,
    },
    {
        "id": "tp-002",
        "ruleId": "rule-email-format",
        "testDate": "2026-02-19T09:00:00",
        "coverage": 0.94,
        "status": "failed",
        "recordsTestedCount": 1150,
        "failuresFound": 11,
    },
]

_TESTING_VERSION_CATALOG = {
    "dov-23": {
        "version": 3,
        "data_object_id": "do-2",
        "attributes": [
            {"id": "attr-201", "name": "email", "type": "string"},
            {"id": "attr-202", "name": "status", "type": "string"},
        ],
    }
}

_TESTING_RULES = {
    "rule-email-format": {
        "name": "Email Format",
        "dimension": "validity",
        "description": "Valid email pattern",
        "expression": "email contains '@'",
    }
}

_DATA_PRODUCTS = [
    {
        "id": "prod-4",
        "name": "Analytics & Reporting",
        "description": "Business intelligence and reporting data warehouse",
        "owner": "Analytics Team",
        "created_at": "2025-05-01T10:00:00",
        "icon": "",
        "workspace_id": "corporate-banking",
        "business_key": "analytics-reporting",
        "tags": ["finance", "reporting"],
    },
    {
        "id": "prod-1",
        "name": "Customer & Order Management",
        "description": "Complete customer lifecycle and order processing data",
        "owner": "Customer Experience Team",
        "created_at": "2025-01-15T10:00:00",
        "icon": "",
        "workspace_id": "retail-banking",
        "business_key": "customer-order-management",
        "tags": ["pii", "customer"],
    },
    {
        "id": "prod-5",
        "name": "Customer Service & Support",
        "description": "Help desk and support ticketing system",
        "owner": "Customer Support Team",
        "created_at": "2025-08-01T10:00:00",
        "icon": "",
        "workspace_id": "risk-compliance",
        "business_key": "customer-service-support",
        "tags": ["support", "contact"],
    },
]

_DATA_SETS = [
    {
        "id": "ds-9",
        "product_id": "prod-6",
        "name": "Campaign Management",
        "description": "Marketing campaign and promotion data",
        "owner": "Marketing Analytics",
        "created_at": "2025-09-15T10:00:00",
        "workspace_id": "treasury",
        "business_key": "campaign-management",
    },
    {
        "id": "ds-1",
        "product_id": "prod-1",
        "name": "CRM System",
        "description": "Customer data from Salesforce CRM",
        "owner": "CRM Team",
        "created_at": "2025-01-15T10:00:00",
        "workspace_id": "retail-banking",
        "business_key": "crm-system",
        "tags": ["pii", "customer"],
    },
    {
        "id": "ds-5",
        "product_id": "prod-4",
        "name": "Data Warehouse",
        "description": "Aggregated and denormalized analytics tables",
        "owner": "Data Engineering",
        "created_at": "2025-05-01T10:00:00",
        "workspace_id": "corporate-banking",
        "business_key": "data-warehouse",
        "tags": ["finance", "reporting"],
    },
]

_DATA_OBJECTS = [
    {
        "id": "obj-15",
        "name": "Campaign",
        "description": "Marketing campaign definitions and metadata",
        "status": "active",
        "created_at": "2025-09-15T10:00:00",
        "business_key": "campaign",
    },
    {
        "id": "obj-10",
        "name": "ClickEvent",
        "description": "User click and interaction tracking",
        "status": "active",
        "created_at": "2025-06-10T10:00:00",
        "business_key": "click-event",
    },
    {
        "id": "obj-2",
        "name": "Contact",
        "description": "Contact and communication details",
        "status": "active",
        "created_at": "2025-02-01T10:00:00",
        "business_key": "contact",
        "tags": ["pii", "contact"],
    },
]

_MASTER_RECORDS = [
    {
        "id": "mr-001",
        "domain": "customer",
        "display_name": "Acme Retail Holdings",
        "business_key": "cust-retail-001",
        "golden_record_id": "golden-cust-retail-001",
        "match_rule": "email_phone_tax_id",
        "survivorship_rule": "prefer_verified_source_then_most_recent",
        "resolution_status": "golden",
        "source_count": 3,
        "source_systems": ["crm", "core-banking", "support"],
        "merged_from_ids": ["crm-cust-771", "core-cust-1001"],
        "owner": "Customer Operations",
        "workspace_id": "retail-banking",
        "created_at": "2026-02-10T09:00:00Z",
        "updated_at": "2026-02-21T08:30:00Z",
    },
    {
        "id": "mr-002",
        "domain": "customer",
        "display_name": "Blue River Retail",
        "business_key": "cust-retail-002",
        "golden_record_id": "golden-cust-retail-002",
        "match_rule": "email_phone_tax_id",
        "survivorship_rule": "prefer_verified_source_then_longest_history",
        "resolution_status": "candidate",
        "source_count": 2,
        "source_systems": ["crm", "ecommerce"],
        "merged_from_ids": ["crm-cust-812"],
        "owner": "Customer Operations",
        "workspace_id": "retail-banking",
        "created_at": "2026-02-11T09:00:00Z",
        "updated_at": "2026-02-20T08:30:00Z",
    },
    {
        "id": "mr-003",
        "domain": "customer",
        "display_name": "Continental Corporate",
        "business_key": "cust-corp-001",
        "golden_record_id": "golden-cust-corp-001",
        "match_rule": "tax_id_company_name",
        "survivorship_rule": "prefer_system_of_record",
        "resolution_status": "golden",
        "source_count": 4,
        "source_systems": ["crm", "core-banking", "kyc", "support"],
        "merged_from_ids": ["kyc-cust-101", "crm-cust-303", "support-cust-44"],
        "owner": "Corporate Client Services",
        "workspace_id": "corporate-banking",
        "created_at": "2026-02-12T09:00:00Z",
        "updated_at": "2026-02-21T10:00:00Z",
    },
    {
        "id": "mr-004",
        "domain": "customer",
        "display_name": "Northwind Corporate",
        "business_key": "cust-corp-002",
        "golden_record_id": "golden-cust-corp-002",
        "match_rule": "tax_id_company_name",
        "survivorship_rule": "prefer_system_of_record",
        "resolution_status": "merged",
        "source_count": 3,
        "source_systems": ["crm", "core-banking", "kyc"],
        "merged_from_ids": ["crm-cust-404", "kyc-cust-228"],
        "owner": "Corporate Client Services",
        "workspace_id": "corporate-banking",
        "created_at": "2026-02-13T09:00:00Z",
        "updated_at": "2026-02-21T11:00:00Z",
    },
]

_RULE_ATTRIBUTES = [
    {"ruleId": "1", "attributeId": "attr-23"},
    {"ruleId": "1", "attributeId": "attr-25"},
    {"ruleId": "1", "attributeId": "attr-29"},
    {"ruleId": "1", "attributeId": "attr-5"},
    {"ruleId": "1", "attributeId": "attr-8"},
]

_DATA_OBJECTS_CATALOG = [
    {
        "id": "do-1",
        "dataset_id": "ds-1",
        "name": "Customer",
        "description": "Customer master data",
        "icon": "",
        "created_at": "2025-01-15T10:00:00",
        "latest_version_id": "dov-3",
        "business_key": "customer",
        "tags": ["customer", "pii"],
    },
    {
        "id": "do-3",
        "dataset_id": "ds-5",
        "name": "Order",
        "description": "Order and transaction data",
        "icon": "",
        "created_at": "2025-05-01T10:00:00",
        "latest_version_id": None,
        "business_key": "order",
        "tags": ["finance"],
    },
    {
        "id": "do-4",
        "dataset_id": "ds-5",
        "name": "Invoice",
        "description": "Invoicing and billing data",
        "icon": "",
        "created_at": "2025-05-01T10:00:00",
        "latest_version_id": None,
        "business_key": "invoice",
        "tags": ["finance"],
    },
    {
        "id": "do-15",
        "dataset_id": "ds-9",
        "name": "Campaign",
        "description": "Marketing campaign definitions and metadata",
        "icon": "",
        "created_at": "2025-09-15T10:00:00",
        "latest_version_id": "dov-30",
        "business_key": "campaign",
        "tags": ["marketing"],
    },
    {
        "id": "do-10",
        "dataset_id": "ds-6",
        "name": "ClickEvent",
        "description": "User click and interaction tracking",
        "icon": "",
        "created_at": "2025-06-10T10:00:00",
        "latest_version_id": "dov-18",
        "business_key": "click-event",
        "tags": ["event"],
    },
    {
        "id": "do-2",
        "dataset_id": "ds-1",
        "name": "Contact",
        "description": "Contact and communication details",
        "icon": "",
        "created_at": "2025-02-01T10:00:00",
        "latest_version_id": "dov-23",
        "business_key": "contact",
        "tags": ["pii", "contact"],
    },
]

_DATA_OBJECT_VERSIONS = [
    {
        "id": "dov-23",
        "data_object_id": "do-2",
        "version": 3,
        "created_at": "2026-02-10T11:30:00",
        "schema_hash": "contact_v3",
        "attribute_count": 9,
        "storage_uri": None,
        "storage_format": None,
        "tags": ["pii", "contact"],
        "storage_options_json": {
            "retention_policy": {
                "exception_fact_retention_days": 30,
                "exception_fact_archive_retention_days": 90,
                "exception_analytics_projection_retention_days": 365,
                "exception_fact_purge_batch_size": 1000,
            }
        },
    },
    {
        "id": "dov-3",
        "data_object_id": "do-1",
        "version": 3,
        "created_at": "2026-01-20T09:15:00",
        "schema_hash": "v3_ghi789",
        "attribute_count": 10,
        "storage_uri": None,
        "storage_format": None,
        "tags": ["customer", "pii"],
        "storage_options_json": {
            "retention_policy": {
                "exception_fact_retention_days": 30,
                "exception_fact_archive_retention_days": 90,
                "exception_analytics_projection_retention_days": 365,
                "exception_fact_purge_batch_size": 1000,
            }
        },
    },
    {
        "id": "dov-2",
        "data_object_id": "do-1",
        "version": 2,
        "created_at": "2025-06-10T14:30:00",
        "schema_hash": "v2_def456",
        "attribute_count": 8,
        "storage_uri": None,
        "storage_format": None,
        "tags": ["customer", "pii"],
        "storage_options_json": {
            "retention_policy": {
                "exception_fact_retention_days": 30,
                "exception_fact_archive_retention_days": 90,
                "exception_analytics_projection_retention_days": 365,
                "exception_fact_purge_batch_size": 1000,
            }
        },
    },
]

_ATTRIBUTES_CATALOG = [
    {
        "id": "attr-1",
        "name": "customer_id",
        "type": "string",
        "nullable": False,
        "format": "uuid",
        "is_cde": True,
        "is_primary_key": True,
        "data_object_id": "do-1",
        "version_id": "dov-1",
    },
    {
        "id": "attr-2v2",
        "name": "is_active",
        "type": "boolean",
        "nullable": False,
        "format": "",
        "is_cde": False,
        "is_primary_key": False,
        "is_business_key": True,
        "data_object_id": "do-1",
        "version_id": "dov-2",
    },
    {
        "id": "attr-10",
        "name": "is_active",
        "type": "boolean",
        "nullable": False,
        "format": "",
        "is_cde": False,
        "is_primary_key": False,
        "is_business_key": True,
        "data_object_id": "do-1",
        "version_id": "dov-3",
    },
    {
        "id": "attr-11",
        "name": "status_reason",
        "type": "string",
        "nullable": True,
        "format": "",
        "is_cde": False,
        "is_primary_key": False,
        "is_business_key": False,
        "data_object_id": "do-1",
        "version_id": "dov-3",
    },
    {
        "id": "attr-11c",
        "name": "contact_id",
        "type": "string",
        "nullable": False,
        "format": "uuid",
        "is_cde": False,
        "is_primary_key": True,
        "is_business_key": False,
        "data_object_id": "do-2",
        "version_id": "dov-23",
        "tags": ["pii", "contact"],
    },
    {
        "id": "attr-12c",
        "name": "customer_id",
        "type": "string",
        "nullable": False,
        "format": "uuid",
        "is_cde": True,
        "is_primary_key": False,
        "is_business_key": False,
        "data_object_id": "do-2",
        "version_id": "dov-23",
        "tags": ["pii"],
    },
    {
        "id": "attr-13c",
        "name": "contact_type",
        "type": "string",
        "nullable": False,
        "format": "",
        "is_cde": False,
        "is_primary_key": False,
        "is_business_key": False,
        "data_object_id": "do-2",
        "version_id": "dov-23",
        "tags": ["contact"],
    },
    {
        "id": "attr-14c",
        "name": "phone_number",
        "type": "string",
        "nullable": True,
        "format": "",
        "is_cde": True,
        "is_primary_key": False,
        "is_business_key": False,
        "data_object_id": "do-2",
        "version_id": "dov-23",
        "tags": ["pii", "contact"],
    },
    {
        "id": "attr-15c",
        "name": "email_address",
        "type": "string",
        "nullable": True,
        "format": "email",
        "is_cde": True,
        "is_primary_key": False,
        "is_business_key": False,
        "data_object_id": "do-2",
        "version_id": "dov-23",
        "tags": ["pii", "contact"],
    },
    {
        "id": "attr-16c",
        "name": "is_primary",
        "type": "boolean",
        "nullable": False,
        "format": "",
        "is_cde": False,
        "is_primary_key": False,
        "is_business_key": False,
        "data_object_id": "do-2",
        "version_id": "dov-23",
    },
    {
        "id": "attr-17c",
        "name": "verified_at",
        "type": "timestamp",
        "nullable": True,
        "format": "",
        "is_cde": False,
        "is_primary_key": False,
        "is_business_key": False,
        "data_object_id": "do-2",
        "version_id": "dov-23",
    },
    {
        "id": "attr-101",
        "name": "ticket_id",
        "type": "string",
        "nullable": False,
        "format": "uuid",
        "is_cde": False,
        "is_primary_key": True,
        "data_object_id": "do-13",
        "version_id": "dov-28",
    },
]

_ATTRIBUTE_DEFINITION_MAPPINGS = [
    {
        "id": "adm-attr-1",
        "attribute_id": "attr-1",
        "definition_id": "def.attribute.customer_id",
        "mapping_state": "mapped",
        "mapped_by": "data.steward@jaccloud.com",
        "created_at": "2026-01-01T08:00:00Z",
        "updated_at": "2026-01-01T08:00:00Z",
    },
    {
        "id": "adm-attr-2v2",
        "attribute_id": "attr-2v2",
        "definition_id": "def.attribute.customer_active_flag",
        "mapping_state": "mapped",
        "mapped_by": "data.steward@jaccloud.com",
        "created_at": "2026-02-01T08:00:00Z",
        "updated_at": "2026-02-01T08:00:00Z",
    },
]

_DATA_DELIVERIES = [
    {
        "id": "del-31",
        "data_object_id": "Customer",
        "data_object_version_id": "dov-1",
        "version": 1,
        "timestamp": "2026-02-21T15:30:00",
        "layer": "standardized",
        "delivery_location": "analytics/Customer/v1/LOAD_DTS=20260221T153000000Z",
        "record_count": 142900,
        "size_bytes": 45200000,
        "status": "completed",
        "attributes_count": 10,
    },
    {
        "id": "del-30",
        "data_object_id": "Transaction",
        "version": 2,
        "timestamp": "2026-02-21T14:45:00",
        "layer": "standardized",
        "delivery_location": "analytics/Transaction/v2/LOAD_DTS=20260221T144500000Z",
        "record_count": 2180000,
        "size_bytes": 460000000,
        "status": "completed",
        "attributes_count": 10,
    },
    {
        "id": "del-29",
        "data_object_id": "Order",
        "version": 2,
        "timestamp": "2026-02-21T12:00:00",
        "layer": "standardized",
        "delivery_location": "analytics/Order/v2/LOAD_DTS=20260221T120000000Z",
        "record_count": 345000,
        "size_bytes": 98200000,
        "status": "completed",
        "attributes_count": 9,
    },
    {
        "id": "del-28",
        "data_object_id": "Customer",
        "data_object_version_id": "dov-3",
        "version": 3,
        "timestamp": "2026-02-21T08:30:00",
        "layer": "standardized",
        "delivery_location": "analytics/Customer/v3/LOAD_DTS=20260221T083000000Z",
        "record_count": 146200,
        "size_bytes": 46100000,
        "status": "completed",
        "attributes_count": 10,
    },
]

_DATA_DELIVERY_NOTES = {
    "del-31": {
        "id": "note-del-31",
        "layer": "standardized",
        "storage_location": "S3",
        "delivery_format": "parquet",
        "file_count": 3,
        "ingestor_name": "data-ingestor",
        "ingestor_run_id": "ing-20260221-1530",
        "source_system": "crm",
        "source_snapshot_id": "snap-20260221-1530",
        "checksum": "b2f3d8c2e1f4",
        "checksum_algorithm": "sha256",
        "metadata_json": {
            "workspace_id": "retail-banking",
            "batch_id": "20260221-1530",
            "object_storage_classification": "real_evidence",
            "evidence_classification": "real_evidence",
            "notes": ["validated", "published"],
        },
    }
}

_ATTRIBUTE_RULE_COUNTS = {
    "attr-23": 1,
    "attr-25": 1,
    "attr-29": 1,
    "attr-5": 1,
    "attr-8": 1,
}

_RULES = {
    "rule-email-format": {
        "id": "rule-email-format",
        "name": "Email format validation",
        "description": "Ensure customer email values match expected pattern",
        "expression": "email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'",
        "dimension": "validity",
        "active": True,
        "createdByUserId": "user-admin",
        "tagIds": ["tag-pii", "tag-contact"],
    }
}

_RULE_USERS = {
    "user-admin": {
        "id": "user-admin",
        "username": "admin",
        "display_name": "Platform Admin",
    }
}

_RULE_TAGS = {
    "tag-pii": {"id": "tag-pii", "name": "PII"},
    "tag-contact": {"id": "tag-contact", "name": "Contact"},
}

_RULE_VERSIONS = {
    "rule-email-format": [
        {
            "id": "rv-001",
            "ruleId": "rule-email-format",
            "versionNumber": 2,
            "createdAt": "2026-03-10T14:22:00Z",
            "createdBy": {
                "id": "user-admin",
                "name": "Platform Admin",
                "email": "admin@example.com",
            },
            "changeType": "modified",
            "changeDescription": "Tightened top-level domain validation",
            "markedForRollback": False,
            "validationStatus": "validated",
            "validatedAt": "2026-03-10T14:30:00Z",
            "validatedBy": "user-admin",
            "tags": ["production", "approved"],
            "rule": {
                "name": "Email format validation",
                "expression": "email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'",
                "dimension": "validity",
                "active": True,
            },
            "relationships": {
                "approvals": [],
                "testProofs": [],
            },
        },
        {
            "id": "rv-000",
            "ruleId": "rule-email-format",
            "versionNumber": 1,
            "createdAt": "2026-02-28T09:15:00Z",
            "createdBy": {
                "id": "user-admin",
                "name": "Platform Admin",
                "email": "admin@example.com",
            },
            "changeType": "created",
            "changeDescription": "Initial version",
            "markedForRollback": False,
            "validationStatus": None,
            "validatedAt": None,
            "validatedBy": None,
            "tags": ["baseline"],
            "rule": {
                "name": "Email format validation",
                "description": "Ensure customer email values match expected pattern",
                "expression": "email ~ '.+@.+'",
                "dimension": "validity",
                "active": True,
            },
            "relationships": {
                "approvals": [],
                "testProofs": [],
            },
        },
    ]
}

_ROLLBACK_HISTORY = {
    "rule-email-format": [
        {
            "id": "rb-000",
            "ruleId": "rule-email-format",
            "rolledBackAt": "2026-03-01T10:00:00Z",
            "rolledBackBy": "Platform Admin",
            "reason": "Initial rollback during testing phase",
            "fromVersionNumber": 2,
            "toVersionNumber": 1,
            "newVersionNumber": 3,
        }
    ]
}

_RULE_STATUS_HISTORY = {
    "rule-email-format": [
        {
            "id": "rsh-000",
            "ruleId": "rule-email-format",
            "action": "create",
            "fromStatus": None,
            "toStatus": "draft",
            "changedBy": "user-admin",
            "changedAt": "2026-03-10T08:00:00Z",
            "reason": "Seeded rule",
        },
        {
            "id": "rsh-001",
            "ruleId": "rule-email-format",
            "action": "transition",
            "fromStatus": "draft",
            "toStatus": "testing",
            "changedBy": "user-analyst",
            "changedAt": "2026-03-10T08:15:00Z",
            "reason": "Prepared validation run",
        },
        {
            "id": "rsh-002",
            "ruleId": "rule-email-format",
            "action": "transition",
            "fromStatus": "testing",
            "toStatus": "tested",
            "changedBy": "user-analyst",
            "changedAt": "2026-03-10T08:30:00Z",
            "reason": "Automated tests completed",
        },
        {
            "id": "rsh-003",
            "ruleId": "rule-email-format",
            "action": "transition",
            "fromStatus": "tested",
            "toStatus": "pending-approval",
            "changedBy": "user-analyst",
            "changedAt": "2026-03-10T09:00:00Z",
            "reason": "Submitted for approval",
        },
        {
            "id": "rsh-004",
            "ruleId": "rule-email-format",
            "action": "approve",
            "fromStatus": "pending-approval",
            "toStatus": "approved",
            "changedBy": "user-steward",
            "changedAt": "2026-03-10T09:30:00Z",
            "reason": "Approved by governance",
        },
        {
            "id": "rsh-005",
            "ruleId": "rule-email-format",
            "action": "activate",
            "fromStatus": "approved",
            "toStatus": "activated",
            "changedBy": "user-admin",
            "changedAt": "2026-03-10T10:00:00Z",
            "reason": "Activated after approval",
        }
    ]
}


def admin_seed_data() -> tuple[list[dict], list[dict]]:
    return deepcopy(_ADMIN_USERS), deepcopy(_ADMIN_ROLES)


def approvals_seed_data() -> tuple[list[dict], list[dict]]:
    return deepcopy(_APPROVALS), deepcopy(_APPROVAL_AUDIT)


def workspaces_seed_data() -> list[dict]:
    return deepcopy(_WORKSPACES)


def testing_seed_data() -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
    return deepcopy(_TEST_PROOFS), deepcopy(_TESTING_VERSION_CATALOG), deepcopy(_TESTING_RULES)


def data_catalog_seed_data() -> dict[str, object]:
    return {
        "data_products": deepcopy(_DATA_PRODUCTS),
        "data_sets": deepcopy(_DATA_SETS),
        "data_objects": deepcopy(_DATA_OBJECTS),
        "rule_attributes": deepcopy(_RULE_ATTRIBUTES),
        "data_objects_catalog": deepcopy(_DATA_OBJECTS_CATALOG),
        "data_object_versions": deepcopy(_DATA_OBJECT_VERSIONS),
        "attributes_catalog": deepcopy(_ATTRIBUTES_CATALOG),
        "attribute_definition_mappings": deepcopy(_ATTRIBUTE_DEFINITION_MAPPINGS),
        "data_deliveries": deepcopy(_DATA_DELIVERIES),
        "data_delivery_notes": deepcopy(_DATA_DELIVERY_NOTES),
        "attribute_rule_counts": deepcopy(_ATTRIBUTE_RULE_COUNTS),
    }


def master_data_seed_data() -> dict[str, object]:
    return {
        "master_records": deepcopy(_MASTER_RECORDS),
    }


def rules_seed_data() -> dict[str, object]:
    return {
        "rules": deepcopy(_RULES),
        "users": deepcopy(_RULE_USERS),
        "tags": deepcopy(_RULE_TAGS),
        "rule_versions": deepcopy(_RULE_VERSIONS),
        "rollback_history": deepcopy(_ROLLBACK_HISTORY),
        "status_history": deepcopy(_RULE_STATUS_HISTORY),
    }
