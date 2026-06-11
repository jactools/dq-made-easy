from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.entities.rule_dsl_v2 import RuleDslV2Document


class RuleDslIrModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class RuleDslIrDatasetScope(RuleDslIrModel):
    data_object_id: str | None = None
    data_object_version_id: str | None = None
    dataset_id: str | None = None
    data_product_id: str | None = None

    @model_validator(mode="after")
    def _require_identifier(self) -> RuleDslIrDatasetScope:
        if any(
            value
            for value in (
                self.data_object_id,
                self.data_object_version_id,
                self.dataset_id,
                self.data_product_id,
            )
        ):
            return self
        raise ValueError("dataset scope must include at least one identifier")


class RuleDslIrRowPredicate(RuleDslIrModel):
    kind: Literal["row_predicate"] = "row_predicate"
    language: Literal["dq_predicate", "sql"]
    expression: str = Field(min_length=1)


class RuleDslIrJoinCondition(RuleDslIrModel):
    left_column: str = Field(min_length=1)
    operator: Literal["=", "!=", ">", ">=", "<", "<="]
    right_column: str = Field(min_length=1)


class RuleDslIrJoinScope(RuleDslIrModel):
    join_type: Literal["inner", "left", "right", "full"]
    conditions: list[RuleDslIrJoinCondition] = Field(min_length=1)


class RuleDslIrGroupingScope(RuleDslIrModel):
    keys: list[str] = Field(min_length=1)


class RuleDslIrTimeWindow(RuleDslIrModel):
    anchor_column: str | None = None
    trailing_duration: str | None = None
    leading_duration: str | None = None


class RuleDslIrJoinKey(RuleDslIrModel):
    left_column: str = Field(min_length=1)
    right_column: str = Field(min_length=1)


class RuleDslIrComparisonScope(RuleDslIrModel):
    left: RuleDslIrDatasetScope
    right: RuleDslIrDatasetScope
    join_keys: list[RuleDslIrJoinKey] = Field(default_factory=list)


class RuleDslIrScope(RuleDslIrModel):
    dataset: RuleDslIrDatasetScope | None = None
    row_filter: RuleDslIrRowPredicate | None = None
    join: RuleDslIrJoinScope | None = None
    grouping: RuleDslIrGroupingScope | None = None
    time_window: RuleDslIrTimeWindow | None = None
    comparison: RuleDslIrComparisonScope | None = None

    @model_validator(mode="after")
    def _require_scope_boundary(self) -> RuleDslIrScope:
        if any(
            value is not None
            for value in (
                self.dataset,
                self.row_filter,
                self.join,
                self.grouping,
                self.time_window,
                self.comparison,
            )
        ):
            return self
        raise ValueError("scope must define at least one boundary")


class RuleDslIrSubject(RuleDslIrModel):
    column: str | None = None
    columns: list[str] | None = None

    @model_validator(mode="after")
    def _require_subject_target(self) -> RuleDslIrSubject:
        if self.column or (self.columns and len(self.columns) > 0):
            return self
        raise ValueError("subject must define column or columns")


class RuleDslIrRowPredicateMeasure(RuleDslIrModel):
    type: Literal["row_predicate"] = "row_predicate"
    predicate: RuleDslIrRowPredicate


class RuleDslIrMetricMeasure(RuleDslIrModel):
    type: Literal["metric"] = "metric"
    metric: Literal[
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
    subject: RuleDslIrSubject | None = None


class RuleDslIrSchemaMeasure(RuleDslIrModel):
    type: Literal["schema"] = "schema"
    schema_assertion: Literal[
        "required_columns_present",
        "forbidden_columns_absent",
        "column_types_match",
        "column_count_between",
        "column_order_matches",
    ]


class RuleDslIrQueryMeasure(RuleDslIrModel):
    type: Literal["query"] = "query"
    query_language: Literal["sql"] = "sql"
    query: str = Field(min_length=1)
    comparison_data_source_name: str | None = None
    comparison_query: str | None = None

    @model_validator(mode="after")
    def _require_comparison_query_pair(self) -> RuleDslIrQueryMeasure:
        has_comparison_data_source = self.comparison_data_source_name is not None
        has_comparison_query = self.comparison_query is not None
        if has_comparison_data_source == has_comparison_query:
            return self
        raise ValueError("query measure requires comparison_data_source_name and comparison_query together")


RuleDslIrMeasure = Annotated[
    RuleDslIrRowPredicateMeasure | RuleDslIrMetricMeasure | RuleDslIrSchemaMeasure | RuleDslIrQueryMeasure,
    Field(discriminator="type"),
]


class RuleDslIrThresholdExpectation(RuleDslIrModel):
    type: Literal["threshold"] = "threshold"
    operator: Literal["gt", "gte", "lt", "lte", "between"]
    value: int | float | str | None = None
    min_value: int | float | str | None = None
    max_value: int | float | str | None = None
    unit: Literal["count", "percent", "duration", "raw"] | None = None

    @model_validator(mode="after")
    def _validate_threshold_shape(self) -> RuleDslIrThresholdExpectation:
        if self.operator == "between":
            if self.min_value is None or self.max_value is None:
                raise ValueError("threshold expectation with operator 'between' requires min_value and max_value")
            return self
        if self.value is None:
            raise ValueError("threshold expectation requires value when operator is not 'between'")
        return self


class RuleDslIrEqualityExpectation(RuleDslIrModel):
    type: Literal["equality"] = "equality"
    mode: Literal["exact", "case_insensitive", "numeric_tolerance"]
    tolerance: float | None = Field(default=None, ge=0)


class RuleDslIrSetMembershipExpectation(RuleDslIrModel):
    type: Literal["set_membership"] = "set_membership"
    allowed_values: list[str] | None = None
    blocked_values: list[str] | None = None

    @model_validator(mode="after")
    def _require_membership_values(self) -> RuleDslIrSetMembershipExpectation:
        if self.allowed_values or self.blocked_values:
            return self
        raise ValueError("set_membership expectation requires allowed_values or blocked_values")


class RuleDslIrSchemaContractExpectation(RuleDslIrModel):
    type: Literal["schema_contract"] = "schema_contract"
    required_columns: list[str] | None = None
    forbidden_columns: list[str] | None = None
    expected_types: dict[str, str] | None = None
    ordered_columns: list[str] | None = None
    min_column_count: int | None = Field(default=None, ge=0)
    max_column_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _require_schema_clause(self) -> RuleDslIrSchemaContractExpectation:
        if any(
            value is not None and value != {}
            for value in (
                self.required_columns,
                self.forbidden_columns,
                self.expected_types,
                self.ordered_columns,
                self.min_column_count,
                self.max_column_count,
            )
        ):
            return self
        raise ValueError("schema_contract expectation requires at least one schema clause")


class RuleDslIrBaselineExpectation(RuleDslIrModel):
    type: Literal["baseline"] = "baseline"
    strategy: Literal["dynamic_parameters", "forecast", "historical_band"]
    lookback_runs: int | None = Field(default=None, ge=1)
    sensitivity: float | None = Field(default=None, ge=0)


RuleDslIrExpectation = Annotated[
    RuleDslIrThresholdExpectation
    | RuleDslIrEqualityExpectation
    | RuleDslIrSetMembershipExpectation
    | RuleDslIrSchemaContractExpectation
    | RuleDslIrBaselineExpectation,
    Field(discriminator="type"),
]


class RuleDslIrFailedRowsPolicy(RuleDslIrModel):
    mode: Literal["none", "sample", "all_with_limit"]
    limit: int | None = Field(default=None, ge=1)
    include_row_identifier: bool
    include_primary_key: bool

    @model_validator(mode="after")
    def _require_limit_for_sampling(self) -> RuleDslIrFailedRowsPolicy:
        if self.mode in {"sample", "all_with_limit"} and self.limit is None:
            raise ValueError("failed_rows.limit is required when mode is 'sample' or 'all_with_limit'")
        return self


class RuleDslIrEvidence(RuleDslIrModel):
    failed_rows: RuleDslIrFailedRowsPolicy
    emit_compiled_artifact: bool
    emit_generated_sql: bool


class RuleDslIrOperations(RuleDslIrModel):
    severity: Literal["critical", "warning", "info"]
    preferred_engines: list[Literal["gx", "sodacl", "sql", "pyspark_native", "custom_worker"]] = Field(min_length=1)
    fail_if_not_native: bool


class RuleDslIrRule(RuleDslIrModel):
    kind: Literal[
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
    ]
    scope: RuleDslIrScope
    measure: RuleDslIrMeasure
    expectation: RuleDslIrExpectation
    evidence: RuleDslIrEvidence
    operations: RuleDslIrOperations
    reusable_join_id: str | None = None
    reusable_filter_ids: list[str] = Field(default_factory=list)


class RuleDslIrDocument(RuleDslIrModel):
    schema_version: Literal["2.0.0"] = "2.0.0"
    rule: RuleDslIrRule


def build_rule_dsl_v2_semantic_ir(*, semantic_model: RuleDslV2Document) -> RuleDslIrDocument:
    normalized_payload = semantic_model.model_dump(mode="python", by_alias=True, exclude_none=True)
    return RuleDslIrDocument.model_validate(normalized_payload)


__all__ = [
    "RuleDslIrBaselineExpectation",
    "RuleDslIrComparisonScope",
    "RuleDslIrDatasetScope",
    "RuleDslIrDocument",
    "RuleDslIrEvidence",
    "RuleDslIrExpectation",
    "RuleDslIrFailedRowsPolicy",
    "RuleDslIrGroupingScope",
    "RuleDslIrJoinCondition",
    "RuleDslIrJoinKey",
    "RuleDslIrJoinScope",
    "RuleDslIrMeasure",
    "RuleDslIrMetricMeasure",
    "RuleDslIrModel",
    "RuleDslIrOperations",
    "RuleDslIrQueryMeasure",
    "RuleDslIrRule",
    "RuleDslIrRowPredicate",
    "RuleDslIrRowPredicateMeasure",
    "RuleDslIrSchemaContractExpectation",
    "RuleDslIrSchemaMeasure",
    "RuleDslIrScope",
    "RuleDslIrSetMembershipExpectation",
    "RuleDslIrSubject",
    "RuleDslIrThresholdExpectation",
    "RuleDslIrTimeWindow",
    "build_rule_dsl_v2_semantic_ir",
]