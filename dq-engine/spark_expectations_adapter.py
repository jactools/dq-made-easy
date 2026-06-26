from __future__ import annotations

from typing import Any

SUPPORTED_RULE_TYPES = {"not_null", "min", "max"}


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
    """Lower simple canonical row-level checks into a Spark Expectations-friendly payload.

    The current adapter intentionally stays narrow and fail-fast: it supports the
    row-level checks that are straightforward to compile today and rejects aggregate
    or query-based semantics explicitly so the execution path stays predictable.
    """

    rule_type = str(rule.get("type") or "").strip()
    column = str(rule.get("column") or "").strip()
    params = rule.get("params") or {}

    if rule_type not in SUPPORTED_RULE_TYPES:
        raise ValueError(f"unsupported rule type for Spark Expectations adapter: {rule_type!r}")

    if rule_type == "not_null":
        return {
            "engine_type": "spark_expectations",
            "engine_target": "pyspark",
            "rule_type": "row_dq",
            "expectation": f"{column} IS NOT NULL",
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

    raise ValueError(f"unsupported rule type for Spark Expectations adapter: {rule_type!r}")
