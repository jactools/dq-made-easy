from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RuleDslCapabilityTarget = Literal["gx", "sodacl", "soda", "sql", "pyspark_native", "spark_expectations", "trino", "custom_worker"]
RuleDslCapabilitySupport = Literal["native", "partial", "sql", "custom", "no"]
RuleDslCapabilityFamily = Literal[
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
]

ROW_ASSERTION_SUBSETS: tuple[str, ...] = (
    "row_filter",
    "row_predicate",
    "threshold_percent",
    "failed_rows",
)

METRIC_THRESHOLD_SUBSETS: tuple[str, ...] = (
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
)

METRIC_COMPARISON_SUBSETS: tuple[str, ...] = (
    "grouped_comparison",
    "cross_source_comparison",
)

SCHEMA_ASSERTION_SUBSETS: tuple[str, ...] = (
    "required_columns_present",
    "forbidden_columns_absent",
    "column_types_match",
    "column_count_between",
    "column_order_matches",
)

REFERENCE_ASSERTION_SUBSETS: tuple[str, ...] = (
    "comparison_scope",
    "single_join_key",
    "ref_data_object_id",
    "ref_data_object_version_id",
)

RECONCILIATION_ASSERTION_SUBSETS: tuple[str, ...] = (
    "cross_source_comparison",
    "matched_rows",
    "unmatched_rows",
    "cross_dataset_integrity",
)

FRESHNESS_ASSERTION_SUBSETS: tuple[str, ...] = (
    "freshness_age",
    "duration_iso8601_days",
    "anchor_now",
)

DISTRIBUTION_ASSERTION_SUBSETS: tuple[str, ...] = (
    "distribution_metrics",
    "quantile",
    "histogram",
    "distribution_drift",
    "outlier_detection",
    "entropy_drift",
    "probabilistic_threshold",
    "seasonality_stability",
)

ANOMALY_ASSERTION_SUBSETS: tuple[str, ...] = (
    "history_window",
    "baseline_strategy",
    "anomaly_score",
    "distribution_drift",
    "outlier_detection",
    "entropy_drift",
    "probabilistic_threshold",
    "seasonality_stability",
)

CUSTOM_QUERY_ASSERTION_SUBSETS: tuple[str, ...] = ("sql_query",)

FAILED_ROWS_EVIDENCE_SUBSETS: tuple[str, ...] = (
    "summary_only",
    "sample",
    "all_with_limit",
    "include_row_identifier",
    "include_primary_key",
    "emit_compiled_artifact",
    "emit_generated_sql",
)

OPERATIONAL_METADATA_SUBSETS: tuple[str, ...] = (
    "severity",
    "preferred_engines",
    "fail_if_not_native",
)


class RuleDslCapabilityModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
        frozen=True,
    )


class RuleDslBackendCapabilityEntry(RuleDslCapabilityModel):
    construct_family: RuleDslCapabilityFamily
    target: RuleDslCapabilityTarget
    support: RuleDslCapabilitySupport
    supported_subsets: tuple[str, ...] = Field(default_factory=tuple)
    compiler_behavior: str
    notes: str


class RuleDslBackendCapabilityRegistry(RuleDslCapabilityModel):
    schema_version: Literal["2.0.0"] = "2.0.0"
    entries: tuple[RuleDslBackendCapabilityEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _require_unique_entries(self) -> RuleDslBackendCapabilityRegistry:
        seen: set[tuple[str, str]] = set()
        for entry in self.entries:
            key = (entry.construct_family, entry.target)
            if key in seen:
                raise ValueError(f"duplicate capability entry for {entry.construct_family}.{entry.target}")
            seen.add(key)
        return self

    def get_entry(self, construct_family: RuleDslCapabilityFamily, target: RuleDslCapabilityTarget) -> RuleDslBackendCapabilityEntry:
        for entry in self.entries:
            if entry.construct_family == construct_family and entry.target == target:
                return entry
        raise KeyError(f"No capability entry registered for {construct_family}.{target}")

    def supports(self, construct_family: RuleDslCapabilityFamily, target: RuleDslCapabilityTarget, subset: str | None = None) -> bool:
        entry = self.get_entry(construct_family, target)
        if entry.support == "no":
            return False
        if subset is None:
            return True
        return subset in entry.supported_subsets

    def matrix_by_family(self) -> dict[str, dict[str, dict[str, Any]]]:
        matrix: dict[str, dict[str, dict[str, Any]]] = {}
        for entry in self.entries:
            family_rows = matrix.setdefault(entry.construct_family, {})
            family_rows[entry.target] = entry.model_dump(mode="json", exclude_none=True)
        return matrix


TARGETS: tuple[RuleDslCapabilityTarget, ...] = ("gx", "sodacl", "soda", "sql", "pyspark_native", "spark_expectations", "trino", "custom_worker")


def _build_family_entries(
    *,
    construct_family: RuleDslCapabilityFamily,
    support_by_target: dict[RuleDslCapabilityTarget, RuleDslCapabilitySupport],
    supported_subsets: tuple[str, ...],
    compiler_behavior: str,
    notes: str,
) -> tuple[RuleDslBackendCapabilityEntry, ...]:
    return tuple(
        RuleDslBackendCapabilityEntry(
            construct_family=construct_family,
            target=target,
            support=support_by_target[target],
            supported_subsets=supported_subsets,
            compiler_behavior=compiler_behavior,
            notes=notes,
        )
        for target in TARGETS
    )


def _build_schema_assertion_entries() -> tuple[RuleDslBackendCapabilityEntry, ...]:
    return (
        RuleDslBackendCapabilityEntry(
            construct_family="schema_assertion",
            target="gx",
            support="partial",
            supported_subsets=("required_columns_present", "forbidden_columns_absent", "column_types_match", "column_count_between", "column_order_matches"),
            compiler_behavior="Prefer native schema checks where the table shape can be expressed directly",
            notes="GX supports required and forbidden column membership, ordered columns, column counts, and column type checks, but not every schema contract clause is represented natively.",
        ),
        RuleDslBackendCapabilityEntry(
            construct_family="schema_assertion",
            target="sodacl",
            support="native",
            supported_subsets=SCHEMA_ASSERTION_SUBSETS,
            compiler_behavior="Prefer native schema checks when the target can expose table shape directly.",
            notes="SodaCL can express the full canonical schema contract family here.",
        ),
        RuleDslBackendCapabilityEntry(
            construct_family="schema_assertion",
            target="soda",
            support="native",
            supported_subsets=SCHEMA_ASSERTION_SUBSETS,
            compiler_behavior="Prefer native schema checks when the target can expose table shape directly.",
            notes="Soda (normalized from sodacl) can express the full canonical schema contract family.",
        ),
        RuleDslBackendCapabilityEntry(
            construct_family="schema_assertion",
            target="sql",
            support="sql",
            supported_subsets=SCHEMA_ASSERTION_SUBSETS,
            compiler_behavior="Use SQL metadata introspection for schema assertions.",
            notes="SQL remains the portable schema-introspection target.",
        ),
        RuleDslBackendCapabilityEntry(
            construct_family="schema_assertion",
            target="pyspark_native",
            support="custom",
            supported_subsets=SCHEMA_ASSERTION_SUBSETS,
            compiler_behavior="Use Spark metadata and catalog access for schema assertions.",
            notes="Spark-native support is implementation-defined and stays outside GX constraints.",
        ),
        RuleDslBackendCapabilityEntry(
            construct_family="schema_assertion",
            target="spark_expectations",
            support="custom",
            supported_subsets=SCHEMA_ASSERTION_SUBSETS,
            compiler_behavior="Use Spark metadata and catalog access for schema assertions.",
            notes="Spark Expectations support is implementation-defined and stays outside GX constraints.",
        ),
        RuleDslBackendCapabilityEntry(
            construct_family="schema_assertion",
            target="trino",
            support="native",
            supported_subsets=SCHEMA_ASSERTION_SUBSETS,
            compiler_behavior="Use Trino metadata introspection for schema assertions.",
            notes="Trino can expose table shape directly for schema validation.",
        ),
        RuleDslBackendCapabilityEntry(
            construct_family="schema_assertion",
            target="custom_worker",
            support="custom",
            supported_subsets=SCHEMA_ASSERTION_SUBSETS,
            compiler_behavior="Delegate schema assertions to the custom worker contract.",
            notes="Custom workers can decide how to inspect and enforce schema shape.",
        ),
    )


def _build_custom_query_assertion_entries() -> tuple[RuleDslBackendCapabilityEntry, ...]:
    return (
        RuleDslBackendCapabilityEntry(
            construct_family="custom_query_assertion",
            target="gx",
            support="partial",
            supported_subsets=CUSTOM_QUERY_ASSERTION_SUBSETS,
            compiler_behavior="Lower query-comparison assertions only when both SQL queries and the comparison data source name are provided.",
            notes="GX can compare two SQL result sets through ExpectQueryResultsToMatchComparison.",
        ),
        RuleDslBackendCapabilityEntry(
            construct_family="custom_query_assertion",
            target="sodacl",
            support="no",
            supported_subsets=CUSTOM_QUERY_ASSERTION_SUBSETS,
            compiler_behavior="No repo-controlled SodaCL lowerer exists yet for custom query assertions.",
            notes="SodaCL support remains future work.",
        ),
        RuleDslBackendCapabilityEntry(
            construct_family="custom_query_assertion",
            target="soda",
            support="no",
            supported_subsets=CUSTOM_QUERY_ASSERTION_SUBSETS,
            compiler_behavior="No repo-controlled Soda lowerer exists yet for custom query assertions.",
            notes="Soda support remains future work.",
        ),
        RuleDslBackendCapabilityEntry(
            construct_family="custom_query_assertion",
            target="sql",
            support="no",
            supported_subsets=CUSTOM_QUERY_ASSERTION_SUBSETS,
            compiler_behavior="No repo-controlled SQL lowerer exists yet for custom query assertions.",
            notes="SQL execution support remains future work.",
        ),
        RuleDslBackendCapabilityEntry(
            construct_family="custom_query_assertion",
            target="pyspark_native",
            support="no",
            supported_subsets=CUSTOM_QUERY_ASSERTION_SUBSETS,
            compiler_behavior="No repo-controlled Spark-native lowerer exists yet for custom query assertions.",
            notes="Spark-native support remains future work.",
        ),
        RuleDslBackendCapabilityEntry(
            construct_family="custom_query_assertion",
            target="spark_expectations",
            support="no",
            supported_subsets=CUSTOM_QUERY_ASSERTION_SUBSETS,
            compiler_behavior="No repo-controlled Spark Expectations lowerer exists yet for custom query assertions.",
            notes="Spark Expectations support remains future work.",
        ),
        RuleDslBackendCapabilityEntry(
            construct_family="custom_query_assertion",
            target="trino",
            support="no",
            supported_subsets=CUSTOM_QUERY_ASSERTION_SUBSETS,
            compiler_behavior="No repo-controlled Trino lowerer exists yet for custom query assertions.",
            notes="Trino support remains future work.",
        ),
        RuleDslBackendCapabilityEntry(
            construct_family="custom_query_assertion",
            target="custom_worker",
            support="no",
            supported_subsets=CUSTOM_QUERY_ASSERTION_SUBSETS,
            compiler_behavior="No repo-controlled custom-worker lowerer exists yet for custom query assertions.",
            notes="Custom-worker support remains future work.",
        ),
    )


RULE_DSL_BACKEND_CAPABILITY_REGISTRY = RuleDslBackendCapabilityRegistry(
    entries=(
        *_build_family_entries(
            construct_family="row_assertion",
            support_by_target={
                "gx": "native",
                "sodacl": "partial",
                "soda": "native",
                "sql": "native",
                "pyspark_native": "native",
                "spark_expectations": "native",
                "trino": "native",
                "custom_worker": "native",
            },
            supported_subsets=ROW_ASSERTION_SUBSETS,
            compiler_behavior="Prefer native predicate lowering and preserve row scope and evidence policy.",
            notes="SodaCL support remains constrained to the canonical dq_predicate subset.",
        ),
        *_build_family_entries(
            construct_family="metric_threshold",
            support_by_target={
                "gx": "native",
                "sodacl": "native",
                "soda": "native",
                "sql": "native",
                "pyspark_native": "native",
                "spark_expectations": "native",
                "trino": "native",
                "custom_worker": "native",
            },
            supported_subsets=METRIC_THRESHOLD_SUBSETS,
            compiler_behavior="Treat this as the main cross-engine deterministic construct.",
            notes="The supported metric subset mirrors the canonical 2.0.0 metric vocabulary.",
        ),
        *_build_family_entries(
            construct_family="metric_comparison",
            support_by_target={
                "gx": "partial",
                "sodacl": "partial",
                "soda": "partial",
                "sql": "native",
                "pyspark_native": "custom",
                "spark_expectations": "custom",
                "trino": "native",
                "custom_worker": "custom",
            },
            supported_subsets=METRIC_COMPARISON_SUBSETS,
            compiler_behavior="Prefer SQL for broadest fidelity when comparing grouped or cross-source metrics.",
            notes="Cross-source metric comparison remains partially supported in direct engines.",
        ),
        *_build_schema_assertion_entries(),
        *_build_family_entries(
            construct_family="reference_assertion",
            support_by_target={
                "gx": "partial",
                "sodacl": "native",
                "soda": "native",
                "sql": "native",
                "pyspark_native": "custom",
                "spark_expectations": "custom",
                "trino": "native",
                "custom_worker": "custom",
            },
            supported_subsets=REFERENCE_ASSERTION_SUBSETS,
            compiler_behavior="Prefer SQL for portable existence checks across sources.",
            notes="Reference assertions need exact join-key and reference-source preservation.",
        ),
        *_build_family_entries(
            construct_family="reconciliation_assertion",
            support_by_target={
                "gx": "partial",
                "sodacl": "partial",
                "soda": "partial",
                "sql": "partial",
                "pyspark_native": "native",
                "spark_expectations": "native",
                "trino": "partial",
                "custom_worker": "partial",
            },
            supported_subsets=RECONCILIATION_ASSERTION_SUBSETS,
            compiler_behavior="Use the existing PySpark worker path for reconciliation semantics",
            notes="Current reconciliation runs through the existing join-pair PySpark worker container",
        ),
        *_build_family_entries(
            construct_family="freshness_assertion",
            support_by_target={
                "gx": "partial",
                "sodacl": "native",
                "soda": "native",
                "sql": "native",
                "pyspark_native": "native",
                "spark_expectations": "native",
                "trino": "native",
                "custom_worker": "native",
            },
            supported_subsets=FRESHNESS_ASSERTION_SUBSETS,
            compiler_behavior="Normalize time units and anchoring rules in the IR before lowering.",
            notes="Freshness support is portable only after duration normalization.",
        ),
        *_build_family_entries(
            construct_family="distribution_assertion",
            support_by_target={
                "gx": "native",
                "sodacl": "partial",
                "soda": "partial",
                "sql": "sql",
                "pyspark_native": "custom",
                "spark_expectations": "custom",
                "trino": "sql",
                "custom_worker": "custom",
            },
            supported_subsets=DISTRIBUTION_ASSERTION_SUBSETS,
            compiler_behavior="Prefer native statistical support; use SQL or custom runtime when portable semantics require it.",
            notes="Portable statistical semantics now include distribution drift, outlier detection, entropy drift",
        ),
        *_build_family_entries(
            construct_family="anomaly_assertion",
            support_by_target={
                "gx": "partial",
                "sodacl": "partial",
                "soda": "partial",
                "sql": "no",
                "pyspark_native": "custom",
                "spark_expectations": "custom",
                "trino": "no",
                "custom_worker": "custom",
            },
            supported_subsets=ANOMALY_ASSERTION_SUBSETS,
            compiler_behavior="Require a history-aware engine or custom worker; fail fast for SQL-only targets.",
            notes="Anomaly detection remains separated from deterministic SQL lowering",
        ),
        *_build_custom_query_assertion_entries(),
        *_build_family_entries(
            construct_family="failed_rows_evidence_policy",
            support_by_target={
                "gx": "partial",
                "sodacl": "native",
                "soda": "native",
                "sql": "native",
                "pyspark_native": "native",
                "spark_expectations": "native",
                "trino": "native",
                "custom_worker": "native",
            },
            supported_subsets=FAILED_ROWS_EVIDENCE_SUBSETS,
            compiler_behavior="Treat evidence emission as a separate concern from assertion semantics.",
            notes="Evidence policy covers summary-only results, sampling, identifiers, and artifact capture.",
        ),
        *_build_family_entries(
            construct_family="operational_metadata",
            support_by_target={
                "gx": "native",
                "sodacl": "native",
                "soda": "native",
                "sql": "custom",
                "pyspark_native": "custom",
                "spark_expectations": "custom",
                "trino": "custom",
                "custom_worker": "custom",
            },
            supported_subsets=OPERATIONAL_METADATA_SUBSETS,
            compiler_behavior="Preserve operational metadata even when the target ignores some fields.",
            notes="Alert-intent remains a future extension outside the current executable contract.",
        ),
    )
)


def build_rule_dsl_backend_capability_registry() -> RuleDslBackendCapabilityRegistry:
    return RULE_DSL_BACKEND_CAPABILITY_REGISTRY


def get_rule_dsl_backend_capability_entry(
    construct_family: RuleDslCapabilityFamily,
    target: RuleDslCapabilityTarget,
) -> RuleDslBackendCapabilityEntry:
    return RULE_DSL_BACKEND_CAPABILITY_REGISTRY.get_entry(construct_family, target)


def rule_dsl_backend_capability_matrix() -> dict[str, dict[str, dict[str, Any]]]:
    return RULE_DSL_BACKEND_CAPABILITY_REGISTRY.matrix_by_family()


__all__ = [
    "ANOMALY_ASSERTION_SUBSETS",
    "CUSTOM_QUERY_ASSERTION_SUBSETS",
    "DISTRIBUTION_ASSERTION_SUBSETS",
    "FAILED_ROWS_EVIDENCE_SUBSETS",
    "FRESHNESS_ASSERTION_SUBSETS",
    "METRIC_COMPARISON_SUBSETS",
    "METRIC_THRESHOLD_SUBSETS",
    "OPERATIONAL_METADATA_SUBSETS",
    "REFERENCE_ASSERTION_SUBSETS",
    "RECONCILIATION_ASSERTION_SUBSETS",
    "ROW_ASSERTION_SUBSETS",
    "RuleDslBackendCapabilityEntry",
    "RuleDslBackendCapabilityRegistry",
    "RuleDslCapabilityFamily",
    "RuleDslCapabilityModel",
    "RuleDslCapabilitySupport",
    "RuleDslCapabilityTarget",
    "RULE_DSL_BACKEND_CAPABILITY_REGISTRY",
    "SCHEMA_ASSERTION_SUBSETS",
    "build_rule_dsl_backend_capability_registry",
    "get_rule_dsl_backend_capability_entry",
    "rule_dsl_backend_capability_matrix",
]