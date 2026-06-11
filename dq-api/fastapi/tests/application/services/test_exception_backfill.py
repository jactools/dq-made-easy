from __future__ import annotations

from app.application.services.exception_backfill import build_object_storage_exception_backfill_plan
from app.application.services.exception_backfill import build_repository_exception_backfill_decision
from app.application.services.exception_backfill import normalize_legacy_reason_code


def test_normalize_legacy_reason_code_is_deterministic() -> None:
    assert normalize_legacy_reason_code("Customer ID differs from golden source") == "customer_id_differs_from_golden_source"


def test_build_repository_exception_backfill_decision_canonicalizes_legacy_row() -> None:
    decision = build_repository_exception_backfill_decision(
        {
            "id": "vio-1",
            "dataObjectVersionId": "dov-1",
            "executionRunId": "run-1",
            "ruleId": "rule-1",
            "dataPrimaryKey": "pk-123",
            "violationReason": "Customer ID differs from golden source",
            "detectedAt": "2026-04-20T10:00:00+00:00",
            "opsMetadata": {
                "suite_id": "gx_suite_1",
                "suite_version": "7",
                "rule_version_id": "rule-version-1",
            },
        }
    )

    assert decision.status == "backfilled"
    assert decision.updated_ops_metadata is not None
    assert decision.updated_ops_metadata["engine_type"] == "gx"
    assert decision.updated_ops_metadata["validation_artifact_id"] == "gx_suite_1"
    assert decision.updated_ops_metadata["validation_artifact_version"] == 7
    assert decision.updated_ops_metadata["record_identifier_type"] == "primary_key"
    assert decision.updated_ops_metadata["record_identifier_value"] == "pk-123"
    assert decision.updated_ops_metadata["reason_code"] == "customer_id_differs_from_golden_source"
    assert decision.updated_ops_metadata["reason_text"] == "Customer ID differs from golden source"
    assert decision.updated_ops_metadata["failure_class"] == "customer_id_differs_from_golden_source"
    assert decision.updated_ops_metadata["identifier_hash"].startswith("sha256:")
    assert len(decision.updated_ops_metadata["identifier_hash"]) == 71


def test_build_repository_exception_backfill_decision_skips_row_without_rule_version() -> None:
    decision = build_repository_exception_backfill_decision(
        {
            "id": "vio-2",
            "dataObjectVersionId": "dov-1",
            "executionRunId": "run-1",
            "ruleId": "rule-1",
            "dataPrimaryKey": "pk-123",
            "violationReason": "Customer ID differs from golden source",
            "detectedAt": "2026-04-20T10:00:00+00:00",
            "opsMetadata": {
                "suite_id": "gx_suite_1",
                "suite_version": "7",
            },
        }
    )

    assert decision.status == "skipped"
    assert decision.reason == "rule_version_id"


def test_build_object_storage_exception_backfill_plan_replays_legacy_batch() -> None:
    decisions, requires_replay = build_object_storage_exception_backfill_plan(
        {
            "schemaVersion": "v3",
            "violations": [
                {
                    "violationId": "vio-3",
                    "dataPrimaryKey": "pk-1",
                    "violationReason": "Null customer id",
                    "ruleId": "rule-1",
                    "ops": {
                        "dataObjectVersionId": "dov-1",
                        "executionRunId": "run-1",
                        "detectedAt": "2026-04-20T10:00:00+00:00",
                        "suiteId": "gx_suite_1",
                        "suiteVersion": 9,
                        "ruleVersionId": "rule-version-1",
                    },
                }
            ],
        }
    )

    assert requires_replay is True
    assert len(decisions) == 1
    assert decisions[0].status == "backfilled"
    assert decisions[0].canonical_violation is not None
    assert decisions[0].canonical_violation["ops_metadata"]["validation_artifact_id"] == "gx_suite_1"
    assert decisions[0].canonical_violation["ops_metadata"]["record_identifier_type"] == "primary_key"
    assert decisions[0].canonical_violation["ops_metadata"]["reason_code"] == "null_customer_id"


def test_build_object_storage_exception_backfill_plan_skips_canonical_v4_batch() -> None:
    decisions, requires_replay = build_object_storage_exception_backfill_plan(
        {
            "schemaVersion": "v4",
            "violations": [
                {
                    "violationId": "vio-4",
                    "violationFact": {
                        "recordIdentifierType": "primary_key",
                        "recordIdentifierValue": "pk-4",
                        "ruleId": "rule-4",
                        "reasonCode": "null_customer_id",
                        "reasonText": "Null customer id",
                    },
                    "ops": {
                        "dataObjectVersionId": "dov-4",
                        "executionRunId": "run-4",
                        "detectedAt": "2026-04-20T10:00:00+00:00",
                        "engineType": "gx",
                        "validationArtifactId": "gx_suite_4",
                        "validationArtifactVersion": 4,
                        "ruleVersionId": "rule-version-4",
                    },
                }
            ],
        }
    )

    assert requires_replay is False
    assert len(decisions) == 1
    assert decisions[0].status == "noop"