#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from pyspark.sql import functions as F


def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _configure_sys_path() -> None:
    repo_root = _resolve_repo_root()
    dq_utils_src = repo_root / "dq-utils" / "src"
    if dq_utils_src.is_dir() and str(dq_utils_src) not in sys.path:
        sys.path.insert(0, str(dq_utils_src))


def _resolve_s3_endpoint() -> str | None:
    endpoint = os.getenv("DQ_S3_ENDPOINT") or os.getenv("AWS_ENDPOINT_URL")
    if endpoint and endpoint.strip():
        return endpoint.strip()
    return None


def _resolve_s3_access_key() -> str | None:
    value = os.getenv("DQ_S3_ACCESS_KEY") or os.getenv("AWS_ACCESS_KEY_ID")
    if value and value.strip():
        return value.strip()
    return None


def _resolve_s3_secret_key() -> str | None:
    value = os.getenv("DQ_S3_SECRET_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
    if value and value.strip():
        return value.strip()
    return None


def _resolve_s3_region() -> str | None:
    value = os.getenv("DQ_S3_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if value and value.strip():
        return value.strip()
    return None


def _resolve_s3_ssl_enabled(endpoint: str | None) -> bool:
    explicit = os.getenv("DQ_S3_SSL_ENABLED")
    if explicit and explicit.strip():
        return explicit.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(endpoint and endpoint.lower().startswith("https://"))


def _configure_s3_for_builder(builder: Any) -> Any:
    endpoint = _resolve_s3_endpoint()
    access_key = _resolve_s3_access_key()
    secret_key = _resolve_s3_secret_key()
    region = _resolve_s3_region()
    ssl_enabled = _resolve_s3_ssl_enabled(endpoint)

    if endpoint:
        builder = builder.config("spark.hadoop.fs.s3a.endpoint", endpoint)
        builder = builder.config("spark.hadoop.fs.s3a.path.style.access", "true")
        builder = builder.config(
            "spark.hadoop.fs.s3a.connection.ssl.enabled",
            "true" if ssl_enabled else "false",
        )

    if access_key and secret_key:
        builder = builder.config("spark.hadoop.fs.s3a.access.key", access_key)
        builder = builder.config("spark.hadoop.fs.s3a.secret.key", secret_key)
        builder = builder.config(
            "spark.hadoop.fs.s3a.aws.credentials.provider",
            "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
        )

    if region:
        builder = builder.config("spark.hadoop.fs.s3a.endpoint.region", region)

    return builder


def _build_spark_session(*, app_name: str, master: str):
    _configure_sys_path()

    from dq_utils.spark_runtime import build_spark_session_builder
    from pyspark.sql import SparkSession

    builder = build_spark_session_builder(
        SparkSession=SparkSession,
        app_name=app_name,
        master=master,
        session_timezone="UTC",
    )
    builder = _configure_s3_for_builder(builder)
    return builder.getOrCreate()


def _validate_rules(df, spark, *, row_expectation: str, agg_expectation: str) -> None:
    from spark_expectations.utils.validate_rules import SparkExpectationsValidateRules

    rules = [
        {
            "rule_type": "row_dq",
            "rule": "teller_machine_row_rule",
            "expectation": row_expectation,
            "action_if_failed": "drop",
        },
        {
            "rule_type": "agg_dq",
            "rule": "teller_machine_agg_rule",
            "expectation": agg_expectation,
            "action_if_failed": "fail",
        },
    ]

    invalid = SparkExpectationsValidateRules.validate_expectations(
        df,
        rules,
        spark,
        raise_exception=True,
    )
    if invalid:
        raise RuntimeError(f"Spark Expectations rule validation failed: {invalid}")


def _run_row_rule(df, *, row_expectation: str):
    rule_col = "__se_poc_row_rule_pass__"
    evaluated = df.withColumn(rule_col, F.expr(row_expectation))
    passed = evaluated.where(F.coalesce(F.col(rule_col).cast("boolean"), F.lit(False))).drop(rule_col)
    quarantined = evaluated.where(~F.coalesce(F.col(rule_col).cast("boolean"), F.lit(False))).drop(rule_col)
    return passed, quarantined


def _run_agg_rule(df, spark, *, agg_expectation: str) -> bool:
    df.createOrReplaceTempView("se_teller_machine_poc_source")
    query = (
        "SELECT CAST((" + agg_expectation + ") AS BOOLEAN) AS rule_pass "
        "FROM se_teller_machine_poc_source"
    )
    row = spark.sql(query).first()
    return bool(row and row["rule_pass"])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Spark Expectations POC over teller_machine data staged in AIStor",
    )
    parser.add_argument(
        "--input-uri",
        default=(
            "s3a://dq-landing-zone-retail-banking/"
            "gx/join-pairs/local-csv-staging/"
            "case_id=correct_atm_cash_movement_matches_customer_transaction_total/"
            "role=left/version_id=dov-9/format=parquet"
        ),
        help="Input dataset URI (expected to point at AIStor staged teller_machine parquet)",
    )
    parser.add_argument(
        "--row-expectation",
        default="transaction_id IS NOT NULL AND amount > 0",
        help="Row-level expectation expression",
    )
    parser.add_argument(
        "--agg-expectation",
        default="count(*) > 0",
        help="Aggregate expectation expression",
    )
    parser.add_argument(
        "--sample-failed-rows",
        type=int,
        default=20,
        help="Max quarantined rows to include in summary",
    )
    parser.add_argument(
        "--spark-master",
        default=os.getenv("DQ_SPARK_MASTER") or "local[*]",
        help="Spark master to use for the POC run",
    )
    parser.add_argument(
        "--app-name",
        default="dq-made-easy-spark-expectations-poc",
        help="Spark application name",
    )
    parser.add_argument(
        "--fail-on-agg-failure",
        action="store_true",
        help="Exit non-zero when aggregate rule evaluates to false",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    spark = _build_spark_session(app_name=args.app_name, master=args.spark_master)
    try:
        source_df = spark.read.parquet(args.input_uri)
        _validate_rules(
            source_df,
            spark,
            row_expectation=args.row_expectation,
            agg_expectation=args.agg_expectation,
        )

        passed_df, quarantined_df = _run_row_rule(source_df, row_expectation=args.row_expectation)
        agg_pass = _run_agg_rule(passed_df, spark, agg_expectation=args.agg_expectation)

        input_count = source_df.count()
        passed_count = passed_df.count()
        quarantined_count = quarantined_df.count()

        sample_limit = max(args.sample_failed_rows, 0)
        failed_samples: list[dict[str, Any]] = []
        if sample_limit > 0 and quarantined_count > 0:
            failed_samples = [json.loads(row) for row in quarantined_df.limit(sample_limit).toJSON().collect()]

        summary = {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "input_uri": args.input_uri,
            "row_expectation": args.row_expectation,
            "agg_expectation": args.agg_expectation,
            "input_count": input_count,
            "passed_count": passed_count,
            "quarantined_count": quarantined_count,
            "agg_rule_passed": agg_pass,
            "failed_row_samples": failed_samples,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))

        if args.fail_on_agg_failure and not agg_pass:
            return 2
        return 0
    finally:
        spark.stop()


if __name__ == "__main__":
    raise SystemExit(main())
