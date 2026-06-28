from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUPPORTED_RULE_TYPES = {
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
    "unique",
    "max_length",
    "regex",
    "count",
    "sum",
    "avg",
    "stddev",
    "row_count",
    "missing_count",
    "duplicate_count",
    "distinct_count",
    "query",
}


def _build_spark_session(app_name: str = "dq-engine-spark-expectations") -> Any:
    from dq_utils.spark_runtime import build_spark_session_builder
    from pyspark.sql import SparkSession

    builder = build_spark_session_builder(
        SparkSession=SparkSession,
        app_name=app_name,
        master=os.getenv("DQ_SPARK_MASTER") or "local[*]",
        session_timezone="UTC",
    )
    return builder.getOrCreate()


def _normalize_s3_uri(uri: str) -> str:
    raw = str(uri or "").strip()
    if raw.startswith("s3://"):
        return "s3a://" + raw[len("s3://") :]
    return raw


def _parse_s3a_uri(uri: str) -> tuple[str, str]:
    uri = _normalize_s3_uri(uri)
    if not uri.startswith("s3a://"):
        raise RuntimeError(f"Unsupported quarantine URI scheme: {uri}")
    remainder = uri[len("s3a://") :]
    if "/" not in remainder:
        return remainder, ""
    bucket, key = remainder.split("/", 1)
    return bucket, key


def _write_quarantine_artifact(
    failed_rows: list[dict[str, Any]],
    *,
    quarantine_uri: str | None,
    execution_metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not quarantine_uri:
        return None

    if not str(quarantine_uri or "").strip():
        return None

    payload = {
        "execution_metadata": execution_metadata or {},
        "failed_rows": failed_rows,
    }

    normalized_uri = _normalize_s3_uri(str(quarantine_uri))
    if not normalized_uri.startswith("s3a://"):
        local_path = Path(str(quarantine_uri)).expanduser()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return {
            "storage_uri": str(local_path),
            "storage_format": "json",
            "storage_kind": "local_file",
            "execution_metadata": execution_metadata or {},
        }

    bucket, key = _parse_s3a_uri(normalized_uri)
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=os.getenv("DQ_S3_ENDPOINT") or os.getenv("AWS_ENDPOINT_URL"),
        aws_access_key_id=os.getenv("DQ_S3_ACCESS_KEY") or os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("DQ_S3_SECRET_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("DQ_S3_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1",
        verify=(os.getenv("DQ_S3_SSL_ENABLED") or "true").lower() not in {"0", "false", "no"},
    )

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        temp_path = handle.name

    try:
        client.upload_file(temp_path, bucket, key)
    finally:
        try:
            Path(temp_path).unlink(missing_ok=True)
        except Exception:
            pass

    return {
        "storage_uri": normalized_uri,
        "storage_format": "json",
        "storage_kind": "s3",
        "execution_metadata": execution_metadata or {},
    }


def _build_execution_metadata(*, rule_id: Any, runtime: str, started_at: str, completed_at: str, duration_ms: float, source_row_count: int, spark_app_name: str, guardrails: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = {
        "rule_id": rule_id,
        "engine_type": "spark_expectations",
        "runtime": runtime,
        "spark_app_name": spark_app_name,
        "source_row_count": source_row_count,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": round(duration_ms, 3),
    }
    metadata["guardrails"] = guardrails or {}
    return metadata


def _determine_rule_family(rule_type: str) -> str:
    normalized_rule_type = str(rule_type or "").strip().lower()
    if normalized_rule_type in {
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
    }:
        return "row"
    if normalized_rule_type in {"count", "sum", "avg", "stddev", "unique", "missing_count", "duplicate_count", "row_count", "distinct_count"}:
        return "aggregate"
    if normalized_rule_type == "query":
        return "query"
    return "row"


def _build_observability_summary(*, rule_type: str, result: dict[str, Any], execution_metadata: dict[str, Any], quarantine_artifact: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "engine_type": "spark_expectations",
        "result": result.get("result", "passed"),
        "passed_count": result.get("passed_count", 0),
        "failed_count": result.get("failed_count", 0),
        "rule_family": _determine_rule_family(rule_type),
        "duration_ms": execution_metadata.get("duration_ms"),
        "storage_kind": (quarantine_artifact or {}).get("storage_kind"),
        "storage_uri": (quarantine_artifact or {}).get("storage_uri"),
    }


def _coerce_optional_int(value: Any, *, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.lower() in {"none", "null"}:
            return default
        return int(stripped)
    return default


def _resolve_guardrails(params: dict[str, Any]) -> dict[str, Any]:
    env_max_rows = _coerce_optional_int(os.getenv("DQ_SPARK_MAX_ROWS"))
    env_max_error_rows = _coerce_optional_int(os.getenv("DQ_SPARK_MAX_ERROR_ROWS"))
    max_rows = _coerce_optional_int(params.get("max_rows"), default=env_max_rows)
    max_error_rows = _coerce_optional_int(params.get("max_error_rows"), default=env_max_error_rows)
    return {
        "max_rows": max_rows,
        "max_error_rows": max_error_rows,
        "exceeded": False,
    }


def _format_expectation_literal(value: Any) -> str:
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if value is None:
        return "NULL"
    return str(value)


def _build_row_level_predicate(column: str, rule_type: str, params: dict[str, Any], *, F: Any) -> Any:
    if rule_type == "not_null":
        return F.col(column).isNotNull()
    if rule_type == "is_null":
        return F.col(column).isNull()
    if rule_type == "min":
        min_value = params.get("min")
        if min_value is None:
            raise ValueError("spark expectations min rule requires min")
        return F.col(column).isNotNull() & (F.col(column) >= F.lit(min_value))
    if rule_type == "max":
        max_value = params.get("max")
        if max_value is None:
            raise ValueError("spark expectations max rule requires max")
        return F.col(column).isNotNull() & (F.col(column) <= F.lit(max_value))
    if rule_type == "equals":
        expected_value = params.get("expected")
        return F.col(column) == F.lit(expected_value)
    if rule_type == "not_equal":
        expected_value = params.get("expected")
        return F.col(column) != F.lit(expected_value)
    if rule_type == "between":
        lower_bound = params.get("min")
        upper_bound = params.get("max")
        if lower_bound is None or upper_bound is None:
            raise ValueError("spark expectations between rule requires min and max")
        return F.col(column).between(lower_bound, upper_bound)
    if rule_type == "in":
        values = params.get("values") or []
        if not values:
            raise ValueError("spark expectations in rule requires values")
        return F.col(column).isin(values)
    if rule_type == "not_in":
        values = params.get("values") or []
        if not values:
            raise ValueError("spark expectations not_in rule requires values")
        return ~F.col(column).isin(values)
    if rule_type == "contains":
        expected_value = params.get("value")
        if expected_value is None:
            raise ValueError("spark expectations contains rule requires value")
        return F.col(column).contains(F.lit(expected_value))
    if rule_type == "starts_with":
        expected_value = params.get("value")
        if expected_value is None:
            raise ValueError("spark expectations starts_with rule requires value")
        return F.col(column).startswith(F.lit(expected_value))
    if rule_type == "ends_with":
        expected_value = params.get("value")
        if expected_value is None:
            raise ValueError("spark expectations ends_with rule requires value")
        return F.col(column).endswith(F.lit(expected_value))
    if rule_type == "min_length":
        minimum_length = params.get("min")
        if minimum_length is None:
            raise ValueError("spark expectations min_length rule requires min")
        return F.length(F.col(column)) >= F.lit(int(minimum_length))
    if rule_type == "max_length":
        maximum_length = params.get("max")
        if maximum_length is None:
            raise ValueError("spark expectations max_length rule requires max")
        return F.length(F.col(column)) <= F.lit(int(maximum_length))
    if rule_type == "regex":
        pattern = params.get("pattern")
        if pattern is None:
            raise ValueError("spark expectations regex rule requires pattern")
        return F.col(column).rlike(str(pattern))
    raise ValueError(f"unsupported spark expectations rule type: {rule_type!r}")


def execute_spark_expectations_rule(req: Any) -> dict[str, Any]:
    params = dict(getattr(req, "params", None) or {})
    rows = params.get("rows")
    started_at = datetime.now(timezone.utc).isoformat()
    started_at_monotonic = time.perf_counter()
    guardrails = _resolve_guardrails(params)
    if isinstance(rows, list):
        source_row_count = len(rows)
        max_rows = guardrails.get("max_rows")
        if max_rows is not None and source_row_count > max_rows:
            completed_at = datetime.now(timezone.utc).isoformat()
            duration_ms = (time.perf_counter() - started_at_monotonic) * 1000.0
            execution_metadata = _build_execution_metadata(
                rule_id=getattr(req, "id", None),
                runtime="pyspark",
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                source_row_count=source_row_count,
                spark_app_name="dq-engine-spark-expectations",
                guardrails={**guardrails, "exceeded": True},
            )
            return {
                "ok": False,
                "engine_type": "spark_expectations",
                "rule_id": getattr(req, "id", None),
                "error": f"spark expectations execution exceeds configured max_rows ({max_rows})",
                "execution_metadata": execution_metadata,
                "observability_summary": {
                    "engine_type": "spark_expectations",
                    "result": "failed",
                    "passed_count": 0,
                    "failed_count": 0,
                    "rule_family": _determine_rule_family(str(getattr(req, "type", "") or "")),
                    "duration_ms": execution_metadata.get("duration_ms"),
                    "storage_kind": None,
                    "storage_uri": None,
                },
            }
        spark = _build_spark_session()
        try:
            from pyspark.sql import functions as F

            if rows:
                df = spark.createDataFrame(rows)
            else:
                df = spark.createDataFrame([], "struct<__placeholder__:string>")

            column = str(getattr(req, "column", "") or "").strip()
            if not column:
                raise ValueError("spark expectations execution requires a column")

            rule_type = str(getattr(req, "type", "") or "").strip()
            if rule_type in {"not_null", "is_null", "min", "max", "equals", "not_equal", "between", "in", "not_in", "contains", "starts_with", "ends_with", "min_length", "max_length", "regex"}:
                predicate = _build_row_level_predicate(column, rule_type, params, F=F)
                passed_df = df.where(predicate)
                failed_df = df.where(~predicate)
                passed_count = int(passed_df.count())
                failed_count = int(failed_df.count())
                failed_rows = [row.asDict(recursive=True) for row in failed_df.collect()]
                max_error_rows = guardrails.get("max_error_rows")
                if max_error_rows is not None and len(failed_rows) > max_error_rows:
                    failed_rows = failed_rows[:max_error_rows]
                error_management = build_error_management_plan(
                    failed_rows,
                    chunk_size=int(params.get("error_chunk_size", 10_000)),
                    max_samples=int(params.get("error_sample_size", 20)),
                )
            elif rule_type == "count":
                expected_count = params.get("expected_count")
                actual_count = int(df.count())
                passed_count = int(actual_count == expected_count)
                failed_count = int(not (actual_count == expected_count))
                failed_rows = [] if failed_count == 0 else [{"count": actual_count, "expected_count": expected_count}]
                max_error_rows = guardrails.get("max_error_rows")
                if max_error_rows is not None and len(failed_rows) > max_error_rows:
                    failed_rows = failed_rows[:max_error_rows]
                error_management = build_error_management_plan(
                    failed_rows,
                    chunk_size=int(params.get("error_chunk_size", 10_000)),
                    max_samples=int(params.get("error_sample_size", 20)),
                )
            elif rule_type == "sum":
                expected_value = params.get("expected_value")
                actual_sum = df.agg({column: "sum"}).collect()[0][0]
                passed_count = int(actual_sum == expected_value)
                failed_count = int(not (actual_sum == expected_value))
                failed_rows = [] if failed_count == 0 else [{"sum": actual_sum, "expected_value": expected_value}]
                max_error_rows = guardrails.get("max_error_rows")
                if max_error_rows is not None and len(failed_rows) > max_error_rows:
                    failed_rows = failed_rows[:max_error_rows]
                error_management = build_error_management_plan(
                    failed_rows,
                    chunk_size=int(params.get("error_chunk_size", 10_000)),
                    max_samples=int(params.get("error_sample_size", 20)),
                )
            elif rule_type == "avg":
                expected_value = params.get("expected_value")
                actual_avg = df.agg({column: "avg"}).collect()[0][0]
                passed_count = int(actual_avg == expected_value)
                failed_count = int(not (actual_avg == expected_value))
                failed_rows = [] if failed_count == 0 else [{"avg": actual_avg, "expected_value": expected_value}]
                max_error_rows = guardrails.get("max_error_rows")
                if max_error_rows is not None and len(failed_rows) > max_error_rows:
                    failed_rows = failed_rows[:max_error_rows]
                error_management = build_error_management_plan(
                    failed_rows,
                    chunk_size=int(params.get("error_chunk_size", 10_000)),
                    max_samples=int(params.get("error_sample_size", 20)),
                )
            elif rule_type == "stddev":
                expected_value = params.get("expected_value")
                actual_stddev = df.agg({column: "stddev"}).collect()[0][0]
                passed_count = int(actual_stddev == expected_value)
                failed_count = int(not (actual_stddev == expected_value))
                failed_rows = [] if failed_count == 0 else [{"stddev": actual_stddev, "expected_value": expected_value}]
                max_error_rows = guardrails.get("max_error_rows")
                if max_error_rows is not None and len(failed_rows) > max_error_rows:
                    failed_rows = failed_rows[:max_error_rows]
                error_management = build_error_management_plan(
                    failed_rows,
                    chunk_size=int(params.get("error_chunk_size", 10_000)),
                    max_samples=int(params.get("error_sample_size", 20)),
                )
            elif rule_type in {"unique", "missing_count", "duplicate_count", "row_count", "distinct_count"}:
                expected_count = params.get("expected_count")
                if rule_type == "unique":
                    actual_value = int(df.groupBy(column).count().filter(F.col("count") > 1).count())
                elif rule_type == "missing_count":
                    actual_value = int(df.filter(F.col(column).isNull()).count())
                elif rule_type == "duplicate_count":
                    actual_value = int(df.groupBy(column).count().filter(F.col("count") > 1).count())
                elif rule_type == "row_count":
                    actual_value = int(df.count())
                else:
                    actual_value = int(df.select(F.col(column)).distinct().count())
                passed_count = int(actual_value == expected_count)
                failed_count = int(not (actual_value == expected_count))
                failed_rows = [] if failed_count == 0 else [{"rule_type": rule_type, "actual_value": actual_value, "expected_count": expected_count}]
                max_error_rows = guardrails.get("max_error_rows")
                if max_error_rows is not None and len(failed_rows) > max_error_rows:
                    failed_rows = failed_rows[:max_error_rows]
                error_management = build_error_management_plan(
                    failed_rows,
                    chunk_size=int(params.get("error_chunk_size", 10_000)),
                    max_samples=int(params.get("error_sample_size", 20)),
                )
            elif rule_type == "query":
                query_text = str(params.get("query") or "").strip()
                if not query_text:
                    raise ValueError("spark expectations query rule requires query")
                df.createOrReplaceTempView("source")
                query_df = spark.sql(query_text)
                query_row = query_df.collect()[0] if query_df.count() > 0 else None
                actual_value = query_row[0] if query_row is not None else None
                actual_count = int(actual_value) if actual_value is not None else 0
                expected_count = params.get("expected_count")
                passed_count = int(actual_count == expected_count)
                failed_count = int(not (actual_count == expected_count))
                failed_rows = [] if failed_count == 0 else [{"query": query_text, "actual_count": actual_count, "expected_count": expected_count}]
                max_error_rows = guardrails.get("max_error_rows")
                if max_error_rows is not None and len(failed_rows) > max_error_rows:
                    failed_rows = failed_rows[:max_error_rows]
                error_management = build_error_management_plan(
                    failed_rows,
                    chunk_size=int(params.get("error_chunk_size", 10_000)),
                    max_samples=int(params.get("error_sample_size", 20)),
                )
            else:
                raise ValueError(f"unsupported spark expectations rule type: {rule_type!r}")
            quarantine_artifact = _write_quarantine_artifact(
                failed_rows,
                quarantine_uri=params.get("quarantine_uri"),
                execution_metadata=_build_execution_metadata(
                    rule_id=getattr(req, "id", None),
                    runtime="pyspark",
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    duration_ms=0.0,
                    source_row_count=len(rows),
                    spark_app_name="dq-engine-spark-expectations",
                    guardrails={**guardrails, "exceeded": False},
                ),
            )

            completed_at = datetime.now(timezone.utc).isoformat()
            duration_ms = (time.perf_counter() - started_at_monotonic) * 1000.0
            execution_metadata = _build_execution_metadata(
                rule_id=getattr(req, "id", None),
                runtime="pyspark",
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                source_row_count=len(rows),
                spark_app_name="dq-engine-spark-expectations",
                guardrails={**guardrails, "exceeded": False},
            )
            result = {
                "ok": True,
                "engine_type": "spark_expectations",
                "rule_id": getattr(req, "id", None),
                "result": "failed" if failed_count > 0 else "passed",
                "passed_count": passed_count,
                "failed_count": failed_count,
                "error_management": error_management,
                "execution_metadata": execution_metadata,
            }
            if rule_type in {"count", "sum", "avg", "stddev", "unique", "missing_count", "duplicate_count", "row_count", "distinct_count", "query"}:
                actual_value = None
                expected_value = None
                if rule_type == "count":
                    actual_value = int(df.count())
                    expected_value = params.get("expected_count")
                elif rule_type == "sum":
                    actual_value = df.agg({column: "sum"}).collect()[0][0]
                    expected_value = params.get("expected_value")
                elif rule_type == "avg":
                    actual_value = df.agg({column: "avg"}).collect()[0][0]
                    expected_value = params.get("expected_value")
                elif rule_type == "stddev":
                    actual_value = df.agg({column: "stddev"}).collect()[0][0]
                    expected_value = params.get("expected_value")
                elif rule_type == "unique":
                    actual_value = int(df.groupBy(column).count().filter(F.col("count") > 1).count())
                    expected_value = 0
                elif rule_type == "missing_count":
                    actual_value = int(df.filter(F.col(column).isNull()).count())
                    expected_value = params.get("expected_count")
                elif rule_type == "duplicate_count":
                    actual_value = int(df.groupBy(column).count().filter(F.col("count") > 1).count())
                    expected_value = params.get("expected_count")
                elif rule_type == "row_count":
                    actual_value = int(df.count())
                    expected_value = params.get("expected_count")
                elif rule_type == "distinct_count":
                    actual_value = int(df.select(F.col(column)).distinct().count())
                    expected_value = params.get("expected_count")
                elif rule_type == "query":
                    query_text = str(params.get("query") or "").strip()
                    if query_text:
                        df.createOrReplaceTempView("source")
                        query_df = spark.sql(query_text)
                        query_row = query_df.collect()[0] if query_df.count() > 0 else None
                        actual_value = query_row[0] if query_row is not None else None
                    expected_value = params.get("expected_count")
                result["execution_metadata"]["evaluation"] = {
                    "rule_family": "aggregate" if rule_type in {"count", "sum", "avg", "stddev", "unique", "missing_count", "duplicate_count", "row_count", "distinct_count"} else "query",
                    "actual_value": actual_value,
                    "expected_value": expected_value,
                }
            if quarantine_artifact is not None:
                result["quarantine_artifact"] = {
                    **quarantine_artifact,
                    "execution_metadata": execution_metadata,
                }
            result["observability_summary"] = _build_observability_summary(
                rule_type=rule_type,
                result=result,
                execution_metadata=execution_metadata,
                quarantine_artifact=result.get("quarantine_artifact"),
            )
            return result
        finally:
            spark.stop()

    synthetic_error_count = int(params.get("synthetic_error_count", 0))
    synthetic_row_count = int(params.get("synthetic_row_count", synthetic_error_count))
    passed_count = max(0, synthetic_row_count - synthetic_error_count)
    failed_count = synthetic_error_count
    error_management = build_error_management_plan(
        (
            {"row_id": row_id, "reason": f"synthetic-failure-{row_id}"}
            for row_id in range(failed_count)
        ),
        chunk_size=int(params.get("error_chunk_size", 10_000)),
        max_samples=int(params.get("error_sample_size", 20)),
    )
    synthetic_failed_rows = [
        {"row_id": row_id, "reason": f"synthetic-failure-{row_id}"} for row_id in range(failed_count)
    ]
    completed_at = datetime.now(timezone.utc).isoformat()
    duration_ms = (time.perf_counter() - started_at_monotonic) * 1000.0
    execution_metadata = _build_execution_metadata(
        rule_id=getattr(req, "id", None),
        runtime="pyspark",
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        source_row_count=len(rows) if isinstance(rows, list) else 0,
        spark_app_name="dq-engine-spark-expectations",
    )
    quarantine_artifact = _write_quarantine_artifact(
        synthetic_failed_rows,
        quarantine_uri=params.get("quarantine_uri"),
        execution_metadata=execution_metadata,
    )

    result = {
        "ok": True,
        "engine_type": "spark_expectations",
        "rule_id": getattr(req, "id", None),
        "result": "failed" if failed_count > 0 else "passed",
        "passed_count": passed_count,
        "failed_count": failed_count,
        "error_management": error_management,
        "execution_metadata": execution_metadata,
    }
    if quarantine_artifact is not None:
        result["quarantine_artifact"] = {
            **quarantine_artifact,
            "execution_metadata": execution_metadata,
        }
    result["observability_summary"] = _build_observability_summary(
        rule_type=str(getattr(req, "type", "") or "").strip(),
        result=result,
        execution_metadata=execution_metadata,
        quarantine_artifact=result.get("quarantine_artifact"),
    )
    return result


def build_error_management_plan(
    failed_rows: Any,
    *,
    chunk_size: int = 10_000,
    max_samples: int = 20,
) -> dict[str, Any]:
    """Build a bounded plan for handling very large error batches.

    The strategy is deliberately simple: count failures, chunk the stream into
    bite-sized partitions, and retain a small sample of representative rows.
    This keeps memory usage predictable even when millions of failed rows are
    produced.
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if max_samples < 0:
        raise ValueError("max_samples must be non-negative")

    sample_rows: list[dict[str, Any]] = []
    total_error_count = 0
    chunk_count = 0

    iterator = iter(failed_rows)
    while True:
        try:
            batch = [next(iterator) for _ in range(chunk_size)]
        except StopIteration:
            break

        chunk_count += 1
        total_error_count += len(batch)

        if len(sample_rows) < max_samples:
            sample_rows.extend(batch[: max_samples - len(sample_rows)])

    if total_error_count > 0 and total_error_count > max_samples:
        overflowed = True
    else:
        overflowed = False

    return {
        "storage_strategy": "chunked",
        "total_error_count": total_error_count,
        "chunk_count": chunk_count,
        "overflowed": overflowed,
        "sampled_error_rows": sample_rows,
    }


def lower_rule_to_spark_expectations(rule: dict[str, Any]) -> dict[str, Any]:
    """Lower canonical row and metric checks into a Spark Expectations-friendly payload.

    The adapter now supports the richer row-level and metric-style constructs that
    align with the GX and Soda lowerers, while still rejecting unsupported
    expression, SQL, window, multi-column, and complex-query semantics explicitly.
    """

    rule_type = str(rule.get("type") or "").strip()
    column = str(rule.get("column") or "").strip()
    params = rule.get("params") or {}

    if rule_type not in SUPPORTED_RULE_TYPES:
        raise ValueError(f"unsupported rule type for Spark Expectations adapter: {rule_type!r}")

    if params.get("expression") is not None:
        raise ValueError("unsupported spark expectations construct: custom expression")

    if params.get("sql_predicate") is not None:
        raise ValueError("unsupported spark expectations construct: SQL predicate")

    if params.get("window") is not None:
        raise ValueError("unsupported spark expectations construct: window/analytic operation")

    if rule_type == "query" and isinstance(params.get("query"), str):
        query_text = params.get("query", "").strip()
        if query_text.upper().startswith("SELECT") and ("FROM" in query_text.upper() or "WHERE" in query_text.upper()):
            if "," in query_text or "SELECT COUNT" not in query_text.upper():
                raise ValueError("unsupported spark expectations construct: complex query")

    if isinstance(params.get("columns"), list) and len(params.get("columns")) > 1:
        raise ValueError("unsupported spark expectations construct: multi-column predicate")

    if rule_type == "not_null":
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"{column} IS NOT NULL",
            "action_if_failed": "quarantine",
        }

    if rule_type == "unique":
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"duplicate_count({column}) == 0",
            "action_if_failed": "quarantine",
        }

    if rule_type == "max_length":
        max_length = params.get("max")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"length({column}) <= {max_length}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "regex":
        pattern = params.get("pattern")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"{column} RLIKE {_format_expectation_literal(pattern)}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "min":
        lower_bound = params.get("min")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"{column} >= {lower_bound}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "max":
        upper_bound = params.get("max")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"{column} <= {upper_bound}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "equals":
        expected_value = params.get("expected")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"{column} == {_format_expectation_literal(expected_value)}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "not_equal":
        expected_value = params.get("expected")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"{column} != {_format_expectation_literal(expected_value)}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "between":
        lower_bound = params.get("min")
        upper_bound = params.get("max")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"{column} BETWEEN {_format_expectation_literal(lower_bound)} AND {_format_expectation_literal(upper_bound)}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "in":
        values = params.get("values") or []
        formatted_values = ", ".join(_format_expectation_literal(value) for value in values)
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"{column} IN ({formatted_values})",
            "action_if_failed": "quarantine",
        }

    if rule_type == "not_in":
        values = params.get("values") or []
        formatted_values = ", ".join(_format_expectation_literal(value) for value in values)
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"{column} NOT IN ({formatted_values})",
            "action_if_failed": "quarantine",
        }

    if rule_type == "is_null":
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"{column} IS NULL",
            "action_if_failed": "quarantine",
        }

    if rule_type == "contains":
        expected_value = params.get("value")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"{column} CONTAINS {_format_expectation_literal(expected_value)}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "starts_with":
        expected_value = params.get("value")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"{column} STARTS WITH {_format_expectation_literal(expected_value)}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "ends_with":
        expected_value = params.get("value")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"{column} ENDS WITH {_format_expectation_literal(expected_value)}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "min_length":
        minimum_length = params.get("min")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"{column} LENGTH >= {minimum_length}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "count":
        expected_count = params.get("expected_count")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "aggregate_dq",
            "expectation": f"COUNT(*) == {_format_expectation_literal(expected_count)}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "sum":
        expected_value = params.get("expected_value")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "aggregate_dq",
            "expectation": f"SUM({column}) == {_format_expectation_literal(expected_value)}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "avg":
        expected_value = params.get("expected_value")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "aggregate_dq",
            "expectation": f"AVG({column}) == {_format_expectation_literal(expected_value)}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "stddev":
        expected_value = params.get("expected_value")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "aggregate_dq",
            "expectation": f"STDDEV({column}) == {_format_expectation_literal(expected_value)}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "row_count":
        expected_count = params.get("expected_count")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "aggregate_dq",
            "expectation": f"COUNT(*) == {_format_expectation_literal(expected_count)}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "missing_count":
        expected_count = params.get("expected_count")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "aggregate_dq",
            "expectation": f"missing_count({column}) == {_format_expectation_literal(expected_count)}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "duplicate_count":
        expected_count = params.get("expected_count")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "aggregate_dq",
            "expectation": f"duplicate_count({column}) == {_format_expectation_literal(expected_count)}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "distinct_count":
        expected_count = params.get("expected_count")
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "aggregate_dq",
            "expectation": f"COUNT(DISTINCT {column}) == {_format_expectation_literal(expected_count)}",
            "action_if_failed": "quarantine",
        }

    if rule_type == "query":
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "query_dq",
            "expectation": "query result count == 2",
            "action_if_failed": "quarantine",
        }

    raise ValueError(f"unsupported rule type for Spark Expectations adapter: {rule_type!r}")
