from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.pydantic_base import to_snake_alias


class RuleDslV2Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_snake_alias,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class RuleDslV2DatasetScope(RuleDslV2Model):
    dataObjectId: str | None = None
    dataObjectVersionId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = None

    @model_validator(mode="after")
    def _require_identifier(self) -> RuleDslV2DatasetScope:
        if any(
            value
            for value in (
                self.dataObjectId,
                self.dataObjectVersionId,
                self.datasetId,
                self.dataProductId,
            )
        ):
            return self
        raise ValueError("dataset scope must include at least one identifier")


class RuleDslV2RowPredicate(RuleDslV2Model):
    kind: Literal["row_predicate"] = "row_predicate"
    language: Literal["dq_predicate", "sql"]
    expression: str = Field(min_length=1)


class RuleDslV2JoinCondition(RuleDslV2Model):
    leftColumn: str = Field(min_length=1)
    operator: Literal["=", "!=", ">", ">=", "<", "<="]
    rightColumn: str = Field(min_length=1)


class RuleDslV2JoinScope(RuleDslV2Model):
    joinType: Literal["inner", "left", "right", "full"]
    conditions: list[RuleDslV2JoinCondition] = Field(min_length=1)


class RuleDslV2GroupingScope(RuleDslV2Model):
    keys: list[str] = Field(min_length=1)


class RuleDslV2TimeWindow(RuleDslV2Model):
    anchorColumn: str | None = None
    trailingDuration: str | None = None
    leadingDuration: str | None = None


class RuleDslV2JoinKey(RuleDslV2Model):
    leftColumn: str = Field(min_length=1)
    rightColumn: str = Field(min_length=1)


class RuleDslV2ComparisonScope(RuleDslV2Model):
    left: RuleDslV2DatasetScope
    right: RuleDslV2DatasetScope
    joinKeys: list[RuleDslV2JoinKey] = Field(default_factory=list)


class RuleDslV2Scope(RuleDslV2Model):
    dataset: RuleDslV2DatasetScope | None = None
    rowFilter: RuleDslV2RowPredicate | None = None
    join: RuleDslV2JoinScope | None = None
    grouping: RuleDslV2GroupingScope | None = None
    timeWindow: RuleDslV2TimeWindow | None = None
    comparison: RuleDslV2ComparisonScope | None = None

    @model_validator(mode="after")
    def _require_scope_boundary(self) -> RuleDslV2Scope:
        if any(
            value is not None
            for value in (
                self.dataset,
                self.rowFilter,
                self.join,
                self.grouping,
                self.timeWindow,
                self.comparison,
            )
        ):
            return self
        raise ValueError("scope must define at least one boundary")


class RuleDslV2Subject(RuleDslV2Model):
    column: str | None = None
    columns: list[str] | None = None

    @model_validator(mode="after")
    def _require_subject_target(self) -> RuleDslV2Subject:
        if self.column or (self.columns and len(self.columns) > 0):
            return self
        raise ValueError("subject must define column or columns")


class RuleDslV2RowPredicateMeasure(RuleDslV2Model):
    type: Literal["row_predicate"] = "row_predicate"
    predicate: RuleDslV2RowPredicate


class RuleDslV2MetricMeasure(RuleDslV2Model):
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
    subject: RuleDslV2Subject | None = None


class RuleDslV2SchemaMeasure(RuleDslV2Model):
    type: Literal["schema"] = "schema"
    schemaAssertion: Literal[
        "required_columns_present",
        "forbidden_columns_absent",
        "column_types_match",
        "column_count_between",
        "column_order_matches",
    ]


class RuleDslV2QueryMeasure(RuleDslV2Model):
    type: Literal["query"] = "query"
    queryLanguage: Literal["sql"] = "sql"
    query: str = Field(min_length=1)
    comparisonDataSourceName: str | None = None
    comparisonQuery: str | None = None

    @model_validator(mode="after")
    def _require_comparison_query_pair(self) -> RuleDslV2QueryMeasure:
        has_comparison_data_source = self.comparisonDataSourceName is not None
        has_comparison_query = self.comparisonQuery is not None
        if has_comparison_data_source == has_comparison_query:
            return self
        raise ValueError("query measure requires comparisonDataSourceName and comparisonQuery together")


RuleDslV2Measure = Annotated[
    RuleDslV2RowPredicateMeasure | RuleDslV2MetricMeasure | RuleDslV2SchemaMeasure | RuleDslV2QueryMeasure,
    Field(discriminator="type"),
]


class RuleDslV2ThresholdExpectation(RuleDslV2Model):
    type: Literal["threshold"] = "threshold"
    operator: Literal["gt", "gte", "lt", "lte", "between"]
    value: int | float | str | None = None
    minValue: int | float | str | None = None
    maxValue: int | float | str | None = None
    unit: Literal["count", "percent", "duration", "raw"] | None = None

    @model_validator(mode="after")
    def _validate_threshold_shape(self) -> RuleDslV2ThresholdExpectation:
        if self.operator == "between":
            if self.minValue is None or self.maxValue is None:
                raise ValueError("threshold expectation with operator 'between' requires min_value and max_value")
            return self
        if self.value is None:
            raise ValueError("threshold expectation requires value when operator is not 'between'")
        return self


class RuleDslV2EqualityExpectation(RuleDslV2Model):
    type: Literal["equality"] = "equality"
    mode: Literal["exact", "case_insensitive", "numeric_tolerance"]
    tolerance: float | None = Field(default=None, ge=0)


class RuleDslV2SetMembershipExpectation(RuleDslV2Model):
    type: Literal["set_membership"] = "set_membership"
    allowedValues: list[str] | None = None
    blockedValues: list[str] | None = None

    @model_validator(mode="after")
    def _require_membership_values(self) -> RuleDslV2SetMembershipExpectation:
        if self.allowedValues or self.blockedValues:
            return self
        raise ValueError("set_membership expectation requires allowed_values or blocked_values")


class RuleDslV2SchemaContractExpectation(RuleDslV2Model):
    type: Literal["schema_contract"] = "schema_contract"
    requiredColumns: list[str] | None = None
    forbiddenColumns: list[str] | None = None
    expectedTypes: dict[str, str] | None = None
    orderedColumns: list[str] | None = None
    minColumnCount: int | None = Field(default=None, ge=0)
    maxColumnCount: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _require_schema_clause(self) -> RuleDslV2SchemaContractExpectation:
        if any(
            value is not None and value != {}
            for value in (
                self.requiredColumns,
                self.forbiddenColumns,
                self.expectedTypes,
                self.orderedColumns,
                self.minColumnCount,
                self.maxColumnCount,
            )
        ):
            return self
        raise ValueError("schema_contract expectation requires at least one schema clause")


class RuleDslV2BaselineExpectation(RuleDslV2Model):
    type: Literal["baseline"] = "baseline"
    strategy: Literal["dynamic_parameters", "forecast", "historical_band"]
    lookbackRuns: int | None = Field(default=None, ge=1)
    sensitivity: float | None = Field(default=None, ge=0)


RuleDslV2Expectation = Annotated[
    RuleDslV2ThresholdExpectation
    | RuleDslV2EqualityExpectation
    | RuleDslV2SetMembershipExpectation
    | RuleDslV2SchemaContractExpectation
    | RuleDslV2BaselineExpectation,
    Field(discriminator="type"),
]


class RuleDslV2FailedRowsPolicy(RuleDslV2Model):
    mode: Literal["none", "sample", "all_with_limit"]
    limit: int | None = Field(default=None, ge=1)
    includeRowIdentifier: bool
    includePrimaryKey: bool

    @model_validator(mode="after")
    def _require_limit_for_sampling(self) -> RuleDslV2FailedRowsPolicy:
        if self.mode in {"sample", "all_with_limit"} and self.limit is None:
            raise ValueError("failed_rows.limit is required when mode is 'sample' or 'all_with_limit'")
        return self


class RuleDslV2Evidence(RuleDslV2Model):
    failedRows: RuleDslV2FailedRowsPolicy
    emitCompiledArtifact: bool
    emitGeneratedSql: bool


class RuleDslV2Operations(RuleDslV2Model):
    severity: Literal["critical", "warning", "info"]
    preferredEngines: list[Literal["gx", "sodacl", "sql", "pyspark_native", "custom_worker"]] = Field(min_length=1)
    failIfNotNative: bool


class RuleDslV2Rule(RuleDslV2Model):
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
    scope: RuleDslV2Scope
    measure: RuleDslV2Measure
    expectation: RuleDslV2Expectation
    evidence: RuleDslV2Evidence
    operations: RuleDslV2Operations
    reusableJoinId: str | None = None
    reusableFilterIds: list[str] = Field(default_factory=list)


class RuleDslV2Document(RuleDslV2Model):
    schemaVersion: Literal["2.0.0"] = "2.0.0"
    rule: RuleDslV2Rule