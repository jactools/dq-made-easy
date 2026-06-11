from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.infrastructure.repositories.postgres_gx_suite_repository import PostgresGxSuiteRepository


def test_build_envelope_includes_execution_contract() -> None:
    row = SimpleNamespace(
        suite_id="gx_suite_1",
        suite_version=3,
        artifact_version="v1",
        status="active",
        data_object_id="do_1",
        dataset_id=None,
        data_product_id=None,
        gx_suite_json={
            "assignmentScope": {
                "dataObjectId": "do_1",
                "datasetId": None,
                "dataProductId": None,
            },
            "resolvedExecutionScope": {"dataObjectVersionIds": ["dov_1"]},
            "gxSuite": {"expectation_suite_name": "dq_suite", "expectations": [], "meta": {}},
            "compiledFrom": {
                "ruleIds": ["rule_1"],
                "compilerVersion": "dq-compiler-7.3",
                "generatedAt": "2026-03-22T10:30:00Z",
            },
            "executionHints": {
                "recommendedEngine": "pyspark",
                "primaryKeyFields": ["order_id"],
            },
            "executionContract": {
                "engineTarget": "pyspark",
                "executionShape": "single_object",
                "traceability": {
                    "ruleId": "rule_1",
                    "ruleVersionId": "rv_1",
                    "gxSuiteId": "gx_suite_1",
                    "gxSuiteVersion": 3,
                    "dataObjectVersionId": "dov_1",
                },
            },
        },
        compiler_version="dq-compiler-7.3",
        generated_at=datetime(2026, 3, 22, 10, 30, tzinfo=UTC),
        saved_by="user-a",
        source_pipeline="rule-compiler",
    )

    envelope = PostgresGxSuiteRepository._build_envelope(
        row,
        data_object_version_ids=["dov_1"],
        rule_ids=["rule_1"],
    )

    assert envelope["suiteId"] == "gx_suite_1"
    assert envelope["executionContract"]["traceability"]["ruleVersionId"] == "rv_1"
    assert envelope["executionContract"]["traceability"]["gxSuiteId"] == "gx_suite_1"
    assert envelope["executionContract"]["traceability"]["dataObjectVersionId"] == "dov_1"
    assert envelope["savedBy"] == "user-a"
    assert envelope["sourcePipeline"] == "rule-compiler"
