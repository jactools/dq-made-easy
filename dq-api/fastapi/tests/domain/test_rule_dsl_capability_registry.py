from __future__ import annotations

from app.domain.entities.rule_dsl_capability_registry import RULE_DSL_BACKEND_CAPABILITY_REGISTRY
from app.domain.entities.rule_dsl_capability_registry import get_rule_dsl_backend_capability_entry
from app.domain.entities.rule_dsl_capability_registry import rule_dsl_backend_capability_matrix


def test_rule_dsl_backend_capability_registry_exposes_expected_matrix() -> None:
    matrix = rule_dsl_backend_capability_matrix()

    assert set(matrix) == {
        "row_assertion",
        "metric_threshold",
        "metric_comparison",
        "schema_assertion",
        "reference_assertion",
        "reconciliation_assertion",
        "freshness_assertion",
        "distribution_assertion",
        "anomaly_assertion",
        "custom_query_assertion",
        "failed_rows_evidence_policy",
        "operational_metadata",
    }
    assert set(matrix["metric_threshold"]) == {"gx", "sodacl", "sql", "pyspark_native", "custom_worker"}
    assert matrix["metric_threshold"]["gx"]["support"] == "native"
    assert matrix["metric_threshold"]["gx"]["supported_subsets"] == [
        "row_count",
        "missing_count",
        "missing_percent",
        "duplicate_count",
        "duplicate_percent",
        "distinct_count",
        "min",
        "max",
        "avg",
        "sum",
        "stddev",
        "quantile",
        "freshness_age",
        "match_percent",
    ]
    assert matrix["schema_assertion"]["gx"]["support"] == "partial"
    assert matrix["schema_assertion"]["gx"]["supported_subsets"] == [
        "required_columns_present",
        "forbidden_columns_absent",
        "column_types_match",
        "column_count_between",
        "column_order_matches",
    ]
    assert matrix["custom_query_assertion"]["gx"]["support"] == "partial"
    assert matrix["anomaly_assertion"]["sql"]["support"] == "no"
    assert matrix["operational_metadata"]["sql"]["support"] == "custom"
    assert matrix["reconciliation_assertion"]["gx"]["support"] == "partial"
    assert matrix["reconciliation_assertion"]["sodacl"]["support"] == "partial"
    assert matrix["reconciliation_assertion"]["sql"]["support"] == "partial"
    assert matrix["reconciliation_assertion"]["pyspark_native"]["support"] == "native"
    assert matrix["reconciliation_assertion"]["custom_worker"]["support"] == "partial"
    assert matrix["reconciliation_assertion"]["pyspark_native"]["supported_subsets"] == [
        "cross_source_comparison",
        "matched_rows",
        "unmatched_rows",
        "cross_dataset_integrity",
    ]
    assert matrix["distribution_assertion"]["gx"]["supported_subsets"] == [
        "distribution_metrics",
        "quantile",
        "histogram",
        "distribution_drift",
        "outlier_detection",
        "entropy_drift",
        "probabilistic_threshold",
        "seasonality_stability",
    ]
    assert matrix["anomaly_assertion"]["pyspark_native"]["supported_subsets"] == [
        "history_window",
        "baseline_strategy",
        "anomaly_score",
        "distribution_drift",
        "outlier_detection",
        "entropy_drift",
        "probabilistic_threshold",
        "seasonality_stability",
    ]


def test_rule_dsl_backend_capability_registry_support_queries() -> None:
    entry = get_rule_dsl_backend_capability_entry("row_assertion", "gx")

    assert entry.compiler_behavior.startswith("Prefer native predicate lowering")
    assert RULE_DSL_BACKEND_CAPABILITY_REGISTRY.supports("row_assertion", "gx") is True
    assert RULE_DSL_BACKEND_CAPABILITY_REGISTRY.supports("metric_threshold", "gx", "row_count") is True
    assert RULE_DSL_BACKEND_CAPABILITY_REGISTRY.supports("metric_threshold", "gx", "not_a_subset") is False
    assert RULE_DSL_BACKEND_CAPABILITY_REGISTRY.supports("reconciliation_assertion", "pyspark_native", "cross_dataset_integrity") is True
    assert RULE_DSL_BACKEND_CAPABILITY_REGISTRY.supports("distribution_assertion", "gx", "distribution_drift") is True
    assert RULE_DSL_BACKEND_CAPABILITY_REGISTRY.supports("anomaly_assertion", "sql") is False