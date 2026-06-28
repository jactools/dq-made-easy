from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DQ_UTILS_ROOT = ROOT.parent / "dq-utils" / "src"
if str(DQ_UTILS_ROOT) not in sys.path:
    sys.path.insert(0, str(DQ_UTILS_ROOT))

from spark_expectations_adapter import lower_rule_to_spark_expectations

DEFAULT_PARQUET_URI = (
    "s3a://retail-banking/"
    "standardized/analytics/"
    "Currency/v1/"
    "LOAD_DTS=20260220T071500000Z"
)


def _resolve_s3_ssl_enabled(endpoint: str | None) -> bool:
    explicit = os.getenv("DQ_S3_SSL_ENABLED")
    if explicit and explicit.strip():
        return explicit.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(endpoint and endpoint.lower().startswith("https://"))


def _build_spark_session() -> SparkSession:
    from dq_utils.spark_runtime import build_spark_session_builder
    from dq_utils.spark_jars import configure_spark_builder_with_local_jars

    active_session = SparkSession.getActiveSession()
    if active_session is not None:
        active_session.stop()

    builder = build_spark_session_builder(
        SparkSession=SparkSession,
        app_name="dq-spark-expectations-real-validation",
        master=os.getenv("DQ_SPARK_MASTER") or "local[*]",
        session_timezone="UTC",
    )
    builder = configure_spark_builder_with_local_jars(builder)

    endpoint = os.getenv("DQ_S3_ENDPOINT") or os.getenv("AWS_ENDPOINT_URL")
    if endpoint:
        builder = builder.config("spark.hadoop.fs.s3a.endpoint", endpoint)
        builder = builder.config("spark.hadoop.fs.s3a.path.style.access", "true")
        builder = builder.config(
            "spark.hadoop.fs.s3a.connection.ssl.enabled",
            "true" if _resolve_s3_ssl_enabled(endpoint) else "false",
        )

    access_key = os.getenv("DQ_S3_ACCESS_KEY") or os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("DQ_S3_SECRET_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
    if access_key and secret_key:
        os.environ["AWS_ACCESS_KEY_ID"] = access_key
        os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
        builder = builder.config("spark.hadoop.fs.s3a.access.key", access_key)
        builder = builder.config("spark.hadoop.fs.s3a.secret.key", secret_key)
        builder = builder.config("spark.hadoop.fs.s3a.aws.credentials.provider", "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider")
        builder = builder.config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")

    region = os.getenv("DQ_S3_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if region:
        os.environ.setdefault("AWS_REGION", region)
        os.environ.setdefault("AWS_DEFAULT_REGION", region)
        builder = builder.config("spark.hadoop.fs.s3a.endpoint.region", region)

    return builder.getOrCreate()


@pytest.fixture(scope="module")
def spark_session() -> SparkSession:
    spark = _build_spark_session()
    try:
        yield spark
    finally:
        spark.stop()


@pytest.fixture(scope="module")
def source_df(spark_session: SparkSession):
    parquet_uri = os.getenv("SPARK_EXPECTATIONS_VALIDATION_INPUT_URI", DEFAULT_PARQUET_URI)
    return spark_session.read.parquet(parquet_uri)


def _prepare_dataframe_for_rule_type(df, rule_type: str):
    if rule_type in {"equals", "not_equal", "in", "not_in", "contains", "starts_with", "ends_with", "min_length", "max_length", "regex"}:
        return df.withColumn("__validation_rule_string__", F.lit("A"))

    if rule_type == "is_null":
        return df.withColumn("__validation_is_null__", F.lit(None).cast("string"))

    return df


def _make_rule_payload(rule_type: str, df, *, column: str) -> dict[str, Any]:
    if rule_type == "not_null":
        return {"id": 1, "table": "currency", "column": "currency_code", "type": rule_type, "params": {}}

    if rule_type == "min":
        min_amount = float(df.agg(F.min("decimal_places").alias("minimum")).collect()[0]["minimum"] or 0.0)
        return {"id": 2, "table": "currency", "column": "decimal_places", "type": rule_type, "params": {"min": min_amount - 1.0}}

    if rule_type == "max":
        max_amount = float(df.agg(F.max("decimal_places").alias("maximum")).collect()[0]["maximum"] or 0.0)
        return {"id": 3, "table": "currency", "column": "decimal_places", "type": rule_type, "params": {"max": max_amount + 1.0}}

    if rule_type == "equals":
        return {"id": 4, "table": "currency", "column": "__validation_rule_string__", "type": rule_type, "params": {"expected": "A"}}

    if rule_type == "not_equal":
        return {"id": 5, "table": "currency", "column": "__validation_rule_string__", "type": rule_type, "params": {"expected": "B"}}

    if rule_type == "between":
        min_amount = float(df.agg(F.min("decimal_places")).collect()[0][0] or 0.0)
        max_amount = float(df.agg(F.max("decimal_places")).collect()[0][0] or 0.0)
        return {"id": 6, "table": "currency", "column": "decimal_places", "type": rule_type, "params": {"min": min_amount - 1.0, "max": max_amount + 1.0}}

    if rule_type == "in":
        return {"id": 7, "table": "currency", "column": "__validation_rule_string__", "type": rule_type, "params": {"values": ["A"]}}

    if rule_type == "not_in":
        return {"id": 8, "table": "currency", "column": "__validation_rule_string__", "type": rule_type, "params": {"values": ["B"]}}

    if rule_type == "is_null":
        return {"id": 9, "table": "currency", "column": "__validation_is_null__", "type": rule_type, "params": {}}

    if rule_type == "contains":
        return {"id": 10, "table": "currency", "column": "__validation_rule_string__", "type": rule_type, "params": {"value": "A"}}

    if rule_type == "starts_with":
        return {"id": 11, "table": "currency", "column": "__validation_rule_string__", "type": rule_type, "params": {"value": "A"}}

    if rule_type == "ends_with":
        return {"id": 12, "table": "currency", "column": "__validation_rule_string__", "type": rule_type, "params": {"value": "A"}}

    if rule_type == "min_length":
        return {"id": 13, "table": "currency", "column": "__validation_rule_string__", "type": rule_type, "params": {"min": 1}}

    if rule_type == "unique":
        return {"id": 14, "table": "currency", "column": "currency_code", "type": rule_type, "params": {}}

    if rule_type == "max_length":
        return {"id": 15, "table": "currency", "column": "__validation_rule_string__", "type": rule_type, "params": {"max": 1}}

    if rule_type == "regex":
        return {"id": 16, "table": "currency", "column": "__validation_rule_string__", "type": rule_type, "params": {"pattern": "^A$"}}

    if rule_type == "count":
        actual_count = int(df.count())
        return {"id": 17, "table": "currency", "column": "currency_code", "type": rule_type, "params": {"expected_count": actual_count}}

    if rule_type == "sum":
        actual_sum = float(df.agg(F.sum("decimal_places")).collect()[0][0] or 0.0)
        return {"id": 18, "table": "currency", "column": "decimal_places", "type": rule_type, "params": {"expected_value": actual_sum}}

    if rule_type == "avg":
        actual_avg = float(df.agg(F.avg("decimal_places")).collect()[0][0] or 0.0)
        return {"id": 19, "table": "currency", "column": "decimal_places", "type": rule_type, "params": {"expected_value": actual_avg}}

    if rule_type == "stddev":
        actual_stddev = float(df.agg(F.stddev("decimal_places")).collect()[0][0] or 0.0)
        return {"id": 20, "table": "currency", "column": "decimal_places", "type": rule_type, "params": {"expected_value": actual_stddev}}

    if rule_type == "row_count":
        actual_count = int(df.count())
        return {"id": 21, "table": "currency", "column": "currency_code", "type": rule_type, "params": {"expected_count": actual_count}}

    if rule_type == "missing_count":
        actual_missing_count = int(df.where(F.col("currency_code").isNull()).count())
        return {"id": 22, "table": "currency", "column": "currency_code", "type": rule_type, "params": {"expected_count": actual_missing_count}}

    if rule_type == "duplicate_count":
        actual_duplicate_count = int(df.groupBy("currency_code").count().where(F.col("count") > 1).count())
        return {"id": 23, "table": "currency", "column": "currency_code", "type": rule_type, "params": {"expected_count": actual_duplicate_count}}

    if rule_type == "distinct_count":
        actual_distinct_count = int(df.select(F.countDistinct("currency_code")).collect()[0][0])
        return {"id": 24, "table": "currency", "column": "currency_code", "type": rule_type, "params": {"expected_count": actual_distinct_count}}

    if rule_type == "query":
        actual_count = int(df.count())
        return {
            "id": 25,
            "table": "currency",
            "column": "currency_code",
            "type": rule_type,
            "params": {"query": "SELECT COUNT(*) AS row_count FROM source", "expected_count": actual_count},
        }

    raise ValueError(f"Unsupported rule type for validation harness: {rule_type}")


def _evaluate_rule(df, spark: SparkSession, rule_payload: dict[str, Any]) -> bool:
    rule_type = str(rule_payload["type"])
    column = str(rule_payload["column"])
    params = rule_payload.get("params") or {}

    if rule_type == "not_null":
        predicate = F.col(column).isNotNull()
        return bool(df.where(predicate).count() == df.count())

    if rule_type == "min":
        minimum = params["min"]
        predicate = F.col(column).isNotNull() & (F.col(column) >= F.lit(minimum))
        return bool(df.where(predicate).count() == df.count())

    if rule_type == "max":
        maximum = params["max"]
        predicate = F.col(column).isNotNull() & (F.col(column) <= F.lit(maximum))
        return bool(df.where(predicate).count() == df.count())

    if rule_type == "equals":
        predicate = F.col(column) == F.lit(params["expected"])
        return bool(df.where(predicate).count() == df.count())

    if rule_type == "not_equal":
        predicate = F.col(column) != F.lit(params["expected"])
        return bool(df.where(predicate).count() == df.count())

    if rule_type == "between":
        predicate = F.col(column).between(params["min"], params["max"])
        return bool(df.where(predicate).count() == df.count())

    if rule_type == "in":
        predicate = F.col(column).isin(params["values"])
        return bool(df.where(predicate).count() == df.count())

    if rule_type == "not_in":
        predicate = ~F.col(column).isin(params["values"])
        return bool(df.where(predicate).count() == df.count())

    if rule_type == "is_null":
        predicate = F.col(column).isNull()
        return bool(df.where(predicate).count() == df.count())

    if rule_type == "contains":
        predicate = F.col(column).contains(params["value"])
        return bool(df.where(predicate).count() == df.count())

    if rule_type == "starts_with":
        predicate = F.col(column).startswith(params["value"])
        return bool(df.where(predicate).count() == df.count())

    if rule_type == "ends_with":
        predicate = F.col(column).endswith(params["value"])
        return bool(df.where(predicate).count() == df.count())

    if rule_type == "min_length":
        predicate = F.length(F.col(column)) >= params["min"]
        return bool(df.where(predicate).count() == df.count())

    if rule_type == "unique":
        duplicated = df.groupBy(column).count().where(F.col("count") > 1)
        return bool(duplicated.count() == 0)

    if rule_type == "max_length":
        predicate = F.length(F.col(column)) <= params["max"]
        return bool(df.where(predicate).count() == df.count())

    if rule_type == "regex":
        predicate = F.col(column).rlike(params["pattern"])
        return bool(df.where(predicate).count() == df.count())

    if rule_type == "count":
        return bool(df.count() == params["expected_count"])

    if rule_type == "sum":
        actual_value = float(df.agg(F.sum(column)).collect()[0][0] or 0.0)
        return bool(actual_value == params["expected_value"])

    if rule_type == "avg":
        actual_value = float(df.agg(F.avg(column)).collect()[0][0] or 0.0)
        return bool(actual_value == params["expected_value"])

    if rule_type == "stddev":
        actual_value = float(df.agg(F.stddev(column)).collect()[0][0] or 0.0)
        return bool(actual_value == params["expected_value"])

    if rule_type == "row_count":
        return bool(df.count() == params["expected_count"])

    if rule_type == "missing_count":
        actual_missing_count = int(df.where(F.col(column).isNull()).count())
        return bool(actual_missing_count == params["expected_count"])

    if rule_type == "duplicate_count":
        actual_duplicate_count = int(df.groupBy(column).count().where(F.col("count") > 1).count())
        return bool(actual_duplicate_count == params["expected_count"])

    if rule_type == "distinct_count":
        actual_distinct_count = int(df.select(F.countDistinct(column)).collect()[0][0])
        return bool(actual_distinct_count == params["expected_count"])

    if rule_type == "query":
        df.createOrReplaceTempView("source")
        actual_count = int(spark.sql(params["query"]).collect()[0][0])
        return bool(actual_count == params["expected_count"])

    raise ValueError(f"Unsupported rule type for evaluation harness: {rule_type}")


@pytest.mark.parametrize(
    "rule_type",
    [
        "not_null",
        "min",
        "max",
        "equals",
        "not_equal",
        "between",
        "in",
        "not_in",
        "is_null",
        "contains",
        "starts_with",
        "ends_with",
        "min_length",
        "max_length",
        "regex",
        "count",
        "sum",
        "avg",
        "stddev",
        "unique",
        "missing_count",
        "duplicate_count",
        "distinct_count",
        "row_count",
        "query",
    ],
)
def test_supported_spark_expectations_constructs_against_aistor_parquet(
    source_df,
    spark_session: SparkSession,
    rule_type: str,
) -> None:
    df = _prepare_dataframe_for_rule_type(source_df, rule_type)

    if rule_type == "query":
        df.createOrReplaceTempView("source")

    rule_payload = _make_rule_payload(rule_type, df, column="currency_code")
    lowered = lower_rule_to_spark_expectations(rule_payload)

    assert lowered["engine_type"] == "spark_expectations"
    assert lowered["engine_target"] == "pyspark"
    assert lowered["action_if_failed"] == "quarantine"

    assert _evaluate_rule(df, spark_session, rule_payload) is True, f"Rule {rule_type} did not evaluate successfully against AIStor parquet"


@pytest.mark.parametrize(
    ("rule", "expected_fragment"),
    [
        (
            {
                "id": 26,
                "table": "currency",
                "column": "currency_code",
                "type": "not_null",
                "params": {"expression": "currency_code IS NOT NULL"},
            },
            "custom expression",
        ),
        (
            {
                "id": 27,
                "table": "currency",
                "column": "currency_code",
                "type": "not_null",
                "params": {"sql_predicate": "currency_code IS NOT NULL"},
            },
            "SQL predicate",
        ),
        (
            {
                "id": 28,
                "table": "currency",
                "column": "currency_code",
                "type": "not_null",
                "params": {"window": "row_number() over (partition by currency_code)"},
            },
            "window",
        ),
        (
            {
                "id": 29,
                "table": "currency",
                "column": "currency_code",
                "type": "query",
                "params": {"query": "SELECT currency_code, decimal_places FROM source", "expected_count": 1},
            },
            "complex query",
        ),
        (
            {
                "id": 30,
                "table": "currency",
                "column": "currency_code",
                "type": "equals",
                "params": {"expected": "USD", "columns": ["currency_code", "decimal_places"]},
            },
            "multi-column",
        ),
    ],
)
def test_unsupported_spark_expectations_constructs_fail_fast_against_aistor_parquet(
    source_df,
    rule: dict[str, Any],
    expected_fragment: str,
) -> None:
    with pytest.raises(ValueError, match=expected_fragment):
        lower_rule_to_spark_expectations(rule)


