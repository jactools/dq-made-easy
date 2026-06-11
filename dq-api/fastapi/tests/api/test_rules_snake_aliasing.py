from __future__ import annotations

from app.api.v1.endpoints import rules


def test_rule_mutation_accepts_snake_case():
    payload = {
        "name": "my rule",
        "workspace_id": "ws-123",
        "taxonomy": {
            "owner": "alice@example.com",
            "data_steward": "alice@example.com",
            "domain_owner": "domain-owner@example.com",
            "technical_owner": "tech-owner@example.com",
            "sla_scope": "dataset",
            "execution_target": "gx",
        },
        "dsl": {
            "schema_version": "1.0.0",
            "source": {
                "kind": "check_type",
                "check_type": "THRESHOLD",
                "check_type_params": {"threshold": 10},
            },
        },
    }

    model = rules.RuleMutationRequest.model_validate(payload)

    assert model.name == "my rule"
    assert model.workspaceId == "ws-123"
    assert model.taxonomy is not None
    assert model.taxonomy.owner == "alice@example.com"
    assert model.taxonomy.dataSteward == "alice@example.com"
    assert model.taxonomy.domainOwner == "domain-owner@example.com"
    assert model.taxonomy.technicalOwner == "tech-owner@example.com"
    assert model.taxonomy.slaScope == "dataset"
    assert model.taxonomy.executionTarget == "gx"
    assert model.dsl.schemaVersion == "1.0.0"
    assert model.dsl.source.checkType == "THRESHOLD"
    assert model.dsl.source.checkTypeParams == {"threshold": 10}


def test_rule_mutation_accepts_semantic_dsl_v2_snake_case():
    payload = {
        "name": "semantic rule",
        "workspace_id": "ws-123",
        "dsl": {
            "schema_version": "2.0.0",
            "rule": {
                "kind": "metric_threshold",
                "scope": {
                    "dataset": {
                        "data_object_id": "do-1",
                    }
                },
                "measure": {
                    "type": "metric",
                    "metric": "missing_percent",
                    "subject": {
                        "column": "email",
                    },
                },
                "expectation": {
                    "type": "threshold",
                    "operator": "lte",
                    "value": 0.1,
                    "unit": "percent",
                },
                "evidence": {
                    "failed_rows": {
                        "mode": "sample",
                        "limit": 10,
                        "include_row_identifier": True,
                        "include_primary_key": True,
                    },
                    "emit_compiled_artifact": True,
                    "emit_generated_sql": False,
                },
                "operations": {
                    "severity": "critical",
                    "preferred_engines": ["gx", "sql"],
                    "fail_if_not_native": False,
                },
            },
        },
    }

    model = rules.RuleMutationRequest.model_validate(payload)

    assert model.workspaceId == "ws-123"
    assert model.dsl.schemaVersion == "2.0.0"
    assert model.dsl.rule.kind == "metric_threshold"
    assert model.dsl.rule.measure.metric == "missing_percent"
    assert model.dsl.rule.operations.preferredEngines == ["gx", "sql"]


def test_gx_auto_publish_accepts_snake_case():
    payload = {
        "data_object_id": "obj-1",
        "data_object_version_ids": ["v1"],
        "primary_key_fields": ["id"],
        "business_key_fields": ["customer_number"],
        "suite_version": 2,
    }

    model = rules.GxSuiteAutoPublishRequest.model_validate(payload)

    assert model.dataObjectId == "obj-1"
    assert model.dataObjectVersionIds == ["v1"]
    assert model.primaryKeyFields == ["id"]
    assert model.businessKeyFields == ["customer_number"]
    assert model.suiteVersion == 2
