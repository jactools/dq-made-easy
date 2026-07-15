from __future__ import annotations

from typing import Any

from dq_plan_execution_types import GxWorkerExecutionError


class _NativeGxBatchRunner:
    def __init__(self, df: Any) -> None:
        self._df = df
        self._context = None
        self._batches: dict[tuple[str, ...], Any] = {}

    def _get_context(self) -> Any:
        if self._context is not None:
            return self._context
        try:
            import great_expectations as gx
        except ModuleNotFoundError as exc:
            raise GxWorkerExecutionError(
                "great_expectations is not installed in dq-engine",
                failure_code="GX_WORKER_EXECUTION_ERROR",
            ) from exc

        self._context = gx.get_context(mode="ephemeral")
        return self._context

    def _get_batch(self, *, batch_key: tuple[str, ...], df: Any) -> Any:
        cached = self._batches.get(batch_key)
        if cached is not None:
            return cached

        try:
            context = self._get_context()
            datasource = context.data_sources.add_or_update_spark("dq_worker_runtime")
            asset = datasource.add_dataframe_asset(f"execution_data_{len(self._batches)}")
            batch_definition = asset.add_batch_definition_whole_dataframe("batch")
            batch = batch_definition.get_batch(batch_parameters={"dataframe": df})
        except Exception as exc:
            raise GxWorkerExecutionError(
                f"Failed to initialize native GX Spark batch: {exc}",
                failure_code="GX_WORKER_EXECUTION_ERROR",
            ) from exc
        self._batches[batch_key] = batch
        return batch

    def validate(self, expectation: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
        from great_expectations.expectations import registry
        from pyspark.sql import functions as F

        expectation_type = str(expectation.get("expectation_type") or "").strip()
        expectation_class = registry.get_expectation_impl(expectation_type)
        if expectation_class is None:
            raise GxWorkerExecutionError(
                f"Native GX expectation '{expectation_type}' is not registered",
                failure_code="GX_WORKER_UNSUPPORTED_EXPECTATION",
            )

        prepared_expectation = expectation
        batch_key: tuple[str, ...] = tuple()
        batch_df = self._df
        kwargs = dict(prepared_expectation.get("kwargs") or {})
        row_condition = kwargs.get("row_condition")
        if _native_gx_requires_column_projection(expectation_type, kwargs) and not isinstance(row_condition, str):
            required_columns = _required_columns_for_expectation(expectation_type, kwargs)
            alias_map = _build_native_gx_alias_map(required_columns)
            batch_key = tuple(required_columns)
            batch_df = self._df.select(*[F.col(column_name).alias(alias_map[column_name]) for column_name in required_columns])
            prepared_expectation = _rewrite_native_gx_expectation_for_aliases(expectation, alias_map)
            kwargs = dict(prepared_expectation.get("kwargs") or {})

        if "row_condition" in kwargs:
            kwargs["row_condition"] = _lower_native_gx_row_condition(kwargs.get("row_condition"))
        meta = prepared_expectation.get("meta") if isinstance(prepared_expectation.get("meta"), dict) else None

        try:
            gx_expectation = expectation_class(meta=dict(meta) if meta else None, **kwargs)
            result = self._get_batch(batch_key=batch_key, df=batch_df).validate(gx_expectation)
        except Exception as exc:
            raise GxWorkerExecutionError(
                f"Native GX validation failed for '{expectation_type}': {exc}",
                failure_code="GX_WORKER_EXECUTION_ERROR",
            ) from exc

        if bool(result.success):
            return True, None

        payload = result.result if isinstance(result.result, dict) else None
        return False, {
            "reason": "expectation_failed",
            "expectation_type": expectation_type,
            "message": "Expectation failed",
            "gx_result": payload,
        }


def _column_is_available(df_columns: set[str], column_name: str) -> bool:
    return column_name in df_columns


def _supports_native_gx_execution(expectation_type: str) -> bool:
    return expectation_type in {
        "expect_query_results_to_match_comparison",
    }


def _collect_row_condition_columns(row_condition: Any) -> list[str]:
    """Collect all column names referenced in a row condition tree."""
    if isinstance(row_condition, str) or row_condition is None:
        return []
    if not isinstance(row_condition, dict):
        return []

    condition_type = str(row_condition.get("type") or "").strip().lower()
    if condition_type in {"and", "or"}:
        raw_conditions = row_condition.get("conditions")
        if not isinstance(raw_conditions, list):
            return []
        columns: list[str] = []
        for item in raw_conditions:
            columns.extend(_collect_row_condition_columns(item))
        return columns

    raw_column = row_condition.get("column")
    if isinstance(raw_column, dict):
        column_name = str(raw_column.get("name") or "").strip()
        return [column_name] if column_name else []
    return []


def _required_columns_for_expectation(expectation_type: str, kwargs: dict[str, Any]) -> list[str]:
    if expectation_type == "expect_query_results_to_match_comparison":
        return []
    columns: list[str] = []
    if expectation_type == "expect_compound_columns_to_be_unique":
        raw_columns = kwargs.get("columns")
        if isinstance(raw_columns, list):
            columns.extend(str(value).strip() for value in raw_columns if str(value).strip())
    elif expectation_type == "expect_column_pair_values_to_be_equal":
        for key in ("column_A", "column_B"):
            value = str(kwargs.get(key) or "").strip()
            if value:
                columns.append(value)
    else:
        column = str(kwargs.get("column") or "").strip()
        if column:
            columns.append(column)
    columns.extend(_collect_row_condition_columns(kwargs.get("row_condition")))
    deduplicated: list[str] = []
    for column_name in columns:
        if column_name and column_name not in deduplicated:
            deduplicated.append(column_name)
    return deduplicated


def _native_gx_requires_column_projection(expectation_type: str, kwargs: dict[str, Any]) -> bool:
    return False


def _build_native_gx_alias_map(columns: list[str]) -> dict[str, str]:
    return {column_name: f"__dq_alias_{idx}" for idx, column_name in enumerate(columns)}


def _rewrite_native_gx_expectation_for_aliases(expectation: dict[str, Any], alias_map: dict[str, str]) -> dict[str, Any]:
    rewritten = dict(expectation)
    kwargs = dict(expectation.get("kwargs") or {})
    rewritten["kwargs"] = kwargs
    return rewritten


def _lower_native_gx_row_condition(row_condition: Any) -> Any:
    return row_condition


def _row_to_mapping(row: Any) -> dict[str, Any] | None:
    if isinstance(row, dict):
        return row

    as_dict = getattr(row, "asDict", None)
    if callable(as_dict):
        try:
            mapped = as_dict(recursive=True)
        except TypeError:
            mapped = as_dict()
        if isinstance(mapped, dict):
            return mapped

    as_dict = getattr(row, "_asdict", None)
    if callable(as_dict):
        mapped = as_dict()
        if isinstance(mapped, dict):
            return mapped

    return None


def _resolve_row_value(row: Any, field_name: str) -> Any:
    current: Any = row
    for part in str(field_name).split("."):
        current_mapping = _row_to_mapping(current)
        if current_mapping is None:
            return None
        current = current_mapping.get(part)
    return current


def _build_row_identifier(row: Any, primary_key_fields: list[str]) -> str | None:
    if _row_to_mapping(row) is None or not primary_key_fields:
        return None

    parts: list[str] = []
    for field_name in primary_key_fields:
        value = _resolve_row_value(row, field_name)
        if value is None:
            return None
        parts.append(f"{field_name}={value}")
    return "|".join(parts) if parts else None


def _first_row_identifier(df: Any, failure_condition: Any, primary_key_fields: list[str]) -> str | None:
    if not primary_key_fields or failure_condition is None:
        return None

    failing_rows = df.where(failure_condition).limit(1).take(1)
    if not failing_rows:
        return None
    return _build_row_identifier(failing_rows[0], primary_key_fields)


def _build_row_failure_diagnostics(
    df: Any,
    failure_condition: Any,
    *,
    primary_key_fields: list[str],
    expectation_index: int,
    expectation_type: str,
    column: str,
    message: str,
) -> list[dict[str, Any]]:
    failing_rows = df.where(failure_condition).collect()
    diagnostics: list[dict[str, Any]] = []
    for row in failing_rows:
        row_identifier = _build_row_identifier(row, primary_key_fields)
        if not row_identifier:
            continue
        diagnostics.append(
            {
                "reason": "expectation_failed",
                "expectation_index": expectation_index,
                "expectation_type": expectation_type,
                "column": column,
                "message": message,
                "row_identifier": row_identifier,
                "data_primary_key": row_identifier,
            }
        )
    return diagnostics


def evaluate_expectations_spark(
    df: Any, expectations: list[dict[str, Any]], *, primary_key_fields: list[str] | None = None
) -> tuple[bool, dict[str, Any], list[dict[str, Any]]]:
    from pyspark.sql import functions as F

    diagnostics: list[dict[str, Any]] = []
    passed = 0
    failed = 0
    started_at = ""

    computed_row_counts: dict[int, int] = {}
    normalized_primary_key_fields = [str(value).strip() for value in (primary_key_fields or []) if str(value).strip()]

    def _get_row_count(frame: Any) -> int:
        frame_key = id(frame)
        if frame_key not in computed_row_counts:
            computed_row_counts[frame_key] = int(frame.count())
        return computed_row_counts[frame_key]

    df_columns = set(getattr(df, "columns", []) or [])
    native_gx_runner = _NativeGxBatchRunner(df) if _supports_native_gx_execution("expect_query_results_to_match_comparison") and not normalized_primary_key_fields else None

    for idx, exp in enumerate(expectations):
        expectation_type = str(exp.get("expectation_type") or "").strip()
        kwargs = exp.get("kwargs") if isinstance(exp.get("kwargs"), dict) else {}

        if native_gx_runner is not None and _supports_native_gx_execution(expectation_type):
            missing_columns = [
                column_name
                for column_name in _required_columns_for_expectation(expectation_type, kwargs)
                if not _column_is_available(df_columns, column_name)
            ]
            if missing_columns:
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "columns": missing_columns,
                        "message": f"Column(s) missing: {', '.join(missing_columns)}",
                    }
                )
                continue

            ok, native_failure = native_gx_runner.validate(exp)
            if ok:
                passed += 1
            else:
                failed += 1
                diagnostics.append(
                    {
                        "expectation_index": idx,
                        **(native_failure or {
                            "reason": "expectation_failed",
                            "expectation_type": expectation_type,
                            "message": "Expectation failed",
                        }),
                    }
                )
            continue

        row_condition = kwargs.get("row_condition")
        scoped_df = df
        if row_condition is not None:
            scoped_df = df.where(
                _build_spark_row_condition_expression(
                    row_condition=row_condition,
                    functions_module=F,
                    df_columns=df_columns,
                )
            )

        if expectation_type == "expect_table_row_count_to_be_between":
            min_value = kwargs.get("min_value")
            max_value = kwargs.get("max_value")
            if min_value is None or max_value is None:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires min_value and max_value",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            row_count = _get_row_count(scoped_df)
            ok = int(min_value) <= row_count <= int(max_value)
            if ok:
                passed += 1
            else:
                failed += 1
                diagnostics.append(
                    {
                        "reason": "expectation_failed",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "row_count": row_count,
                        "min_value": min_value,
                        "max_value": max_value,
                        "message": "Row count expectation failed",
                    }
                )
            continue

        if expectation_type == "expect_compound_columns_to_be_unique":
            columns = kwargs.get("columns")
            if not isinstance(columns, list) or not columns:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires columns list",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            missing_columns = [str(value).strip() for value in columns if str(value).strip() and str(value).strip() not in df_columns]
            if missing_columns:
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "columns": missing_columns,
                        "message": f"Column(s) missing: {', '.join(missing_columns)}",
                    }
                )
                continue
            has_failure = bool(scoped_df.groupBy(*columns).count().where(F.col("count") > 1).limit(1).take(1))
            if not has_failure:
                passed += 1
            else:
                failed += 1
                diagnostics.append(
                    {
                        "reason": "expectation_failed",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "columns": list(columns),
                        "message": "Expectation failed",
                    }
                )
            continue

        if expectation_type == "expect_query_results_to_match_comparison":
            try:
                ok, native_failure = _NativeGxBatchRunner(df).validate(exp)
            except GxWorkerExecutionError:
                raise
            except Exception as exc:
                raise GxWorkerExecutionError(
                    f"Native GX validation failed for '{expectation_type}': {exc}",
                    failure_code="GX_WORKER_EXECUTION_ERROR",
                ) from exc
            if ok:
                passed += 1
            else:
                failed += 1
                diagnostics.append(
                    {
                        "expectation_index": idx,
                        **(native_failure or {
                            "reason": "expectation_failed",
                            "expectation_type": expectation_type,
                            "message": "Expectation failed",
                        }),
                    }
                )
            continue

        column = str(kwargs.get("column") or kwargs.get("column_A") or "").strip()
        if not column:
            raise GxWorkerExecutionError(
                f"Expectation '{expectation_type}' missing column",
                failure_code="GX_WORKER_INVALID_EXPECTATION",
            )

        if not _column_is_available(df_columns, column):
            failed += 1
            row_identifier = _first_row_identifier(scoped_df, F.lit(True), normalized_primary_key_fields)
            diagnostics.append(
                {
                    "reason": "missing_column",
                    "expectation_index": idx,
                    "expectation_type": expectation_type,
                    "column": column,
                    "message": f"Column '{column}' not found",
                    **(
                        {
                            "row_identifier": row_identifier,
                            "data_primary_key": row_identifier,
                        }
                        if row_identifier
                        else {}
                    ),
                }
            )
            continue

        col = F.col(column)
        has_failure = False
        failure_condition = None

        if expectation_type == "expect_column_values_to_not_be_null":
            failure_condition = col.isNull()
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_values_to_be_unique":
            has_failure = bool(scoped_df.groupBy(column).count().where(F.col("count") > 1).limit(1).take(1))
        elif expectation_type == "expect_column_pair_values_to_be_equal":
            other_column = str(kwargs.get("column_B") or "").strip()
            left_column = str(kwargs.get("column_A") or column).strip()
            ignore_row_if = str(kwargs.get("ignore_row_if") or "both_values_are_missing").strip().lower()
            if not left_column or not other_column:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires column_A and column_B",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if not _column_is_available(df_columns, left_column):
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "column": left_column,
                        "message": f"Column '{left_column}' not found",
                    }
                )
                continue
            if not _column_is_available(df_columns, other_column):
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "column": other_column,
                        "message": f"Column '{other_column}' not found",
                    }
                )
                continue

            left_col = F.col(left_column)
            right_col = F.col(other_column)
            if ignore_row_if == "both_values_are_missing":
                evaluated_rows = ~(left_col.isNull() & right_col.isNull())
            elif ignore_row_if == "either_value_is_missing":
                evaluated_rows = left_col.isNotNull() & right_col.isNotNull()
            elif ignore_row_if == "neither":
                evaluated_rows = F.lit(True)
            else:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' has unsupported ignore_row_if '{ignore_row_if}'",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            failure_condition = evaluated_rows & (left_col.isNull() | right_col.isNull() | (left_col != right_col))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_values_to_be_between_for_other_column_value":
            other_column = str(kwargs.get("other_column") or "").strip()
            other_value = kwargs.get("other_value")
            min_value = kwargs.get("min_value")
            max_value = kwargs.get("max_value")
            strict_min = bool(kwargs.get("strict_min"))
            strict_max = bool(kwargs.get("strict_max"))
            if not other_column:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires other_column",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if other_value is None:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires other_value",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if min_value is None and max_value is None:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires at least one of min_value or max_value",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if not _column_is_available(df_columns, other_column):
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "column": other_column,
                        "message": f"Column '{other_column}' not found",
                    }
                )
                continue

            other_col = F.col(other_column)
            context_matches = other_col == F.lit(other_value)
            in_range = F.lit(True)
            if min_value is not None:
                min_lit = F.lit(min_value)
                in_range = in_range & ((col > min_lit) if strict_min else (col >= min_lit))
            if max_value is not None:
                max_lit = F.lit(max_value)
                in_range = in_range & ((col < max_lit) if strict_max else (col <= max_lit))

            failure_condition = context_matches & (col.isNull() | (~in_range))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_values_to_be_in_set_for_other_column_value":
            other_column = str(kwargs.get("other_column") or "").strip()
            other_value = kwargs.get("other_value")
            value_set = kwargs.get("value_set")
            case_sensitive = bool(kwargs.get("case_sensitive", True))
            if not other_column:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires other_column",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if other_value is None:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires other_value",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if not isinstance(value_set, list):
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires value_set list",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if not _column_is_available(df_columns, other_column):
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "column": other_column,
                        "message": f"Column '{other_column}' not found",
                    }
                )
                continue

            other_col = F.col(other_column)
            context_matches = other_col == F.lit(other_value)
            if case_sensitive:
                allowed = col.isin(value_set)
            else:
                normalized_values = [str(item).lower() for item in value_set]
                allowed = F.lower(col.cast("string")).isin(normalized_values)
            failure_condition = context_matches & (col.isNull() | (~allowed))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type in {
            "expect_column_values_to_equal_other_column",
            "expect_column_values_to_equal_other_column_case_insensitive",
            "expect_column_values_to_be_within_numeric_tolerance_of_other_column",
            "expect_column_timestamps_to_be_within_tolerance_of_other_column",
        }:
            other_column = str(kwargs.get("other_column") or "").strip()
            if not other_column:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires other_column",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if not _column_is_available(df_columns, other_column):
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "column": other_column,
                        "message": f"Column '{other_column}' not found",
                    }
                )
                continue

            other_col = F.col(other_column)
            if expectation_type == "expect_column_values_to_equal_other_column":
                failure_condition = col.isNull() | other_col.isNull() | (col != other_col)
            elif expectation_type == "expect_column_values_to_equal_other_column_case_insensitive":
                failure_condition = col.isNull() | other_col.isNull() | (F.lower(col.cast("string")) != F.lower(other_col.cast("string")))
            elif expectation_type == "expect_column_values_to_be_within_numeric_tolerance_of_other_column":
                tolerance = kwargs.get("tolerance")
                if tolerance is None:
                    raise GxWorkerExecutionError(
                        f"Expectation '{expectation_type}' requires tolerance",
                        failure_code="GX_WORKER_INVALID_EXPECTATION",
                    )
                failure_condition = col.isNull() | other_col.isNull() | (F.abs(col - other_col) > F.lit(float(tolerance)))
            else:
                max_difference = kwargs.get("max_difference")
                difference_unit = str(kwargs.get("difference_unit") or "").strip().lower()
                if max_difference is None:
                    raise GxWorkerExecutionError(
                        f"Expectation '{expectation_type}' requires max_difference",
                        failure_code="GX_WORKER_INVALID_EXPECTATION",
                    )
                if difference_unit not in {"minute", "minutes", "hour", "hours", "day", "days"}:
                    raise GxWorkerExecutionError(
                        f"Expectation '{expectation_type}' has unsupported difference_unit '{difference_unit}'",
                        failure_code="GX_WORKER_INVALID_EXPECTATION",
                    )
                divisor = 60.0 if difference_unit.startswith("minute") else 3600.0 if difference_unit.startswith("hour") else 86400.0
                left_ts = F.to_timestamp(col)
                right_ts = F.to_timestamp(other_col)
                difference = F.abs(F.unix_timestamp(left_ts) - F.unix_timestamp(right_ts)) / F.lit(divisor)
                failure_condition = left_ts.isNull() | right_ts.isNull() | (difference > F.lit(float(max_difference)))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_values_to_be_null":
            failure_condition = col.isNotNull()
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_proportion_of_non_null_values_to_be_between":
            min_value = kwargs.get("min_value")
            max_value = kwargs.get("max_value")
            strict_min = bool(kwargs.get("strict_min"))
            strict_max = bool(kwargs.get("strict_max"))
            row_count = int(scoped_df.count())
            if row_count <= 0:
                proportion = 0.0
            else:
                non_null_count = int(scoped_df.where(col.isNotNull()).count())
                proportion = float(non_null_count) / float(row_count)
            lower_ok = True if min_value is None else proportion > float(min_value) if strict_min else proportion >= float(min_value)
            upper_ok = True if max_value is None else proportion < float(max_value) if strict_max else proportion <= float(max_value)
            has_failure = not (lower_ok and upper_ok)
        elif expectation_type == "expect_column_values_to_be_in_set":
            value_set = kwargs.get("value_set")
            if not isinstance(value_set, list):
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires value_set list",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            failure_condition = col.isNotNull() & (~col.isin(value_set))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_values_to_not_be_in_set":
            value_set = kwargs.get("value_set")
            if not isinstance(value_set, list):
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires value_set list",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            failure_condition = col.isNotNull() & (col.isin(value_set))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type in {"expect_column_values_to_be_between", "expect_column_values_to_not_be_between"}:
            min_value = kwargs.get("min_value")
            max_value = kwargs.get("max_value")
            strict_min = bool(kwargs.get("strict_min"))
            strict_max = bool(kwargs.get("strict_max"))
            if min_value is None and max_value is None:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires at least one of min_value or max_value",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            in_range = F.lit(True)
            if min_value is not None:
                min_lit = F.lit(min_value)
                in_range = in_range & ((col > min_lit) if strict_min else (col >= min_lit))
            if max_value is not None:
                max_lit = F.lit(max_value)
                in_range = in_range & ((col < max_lit) if strict_max else (col <= max_lit))

            if expectation_type == "expect_column_values_to_be_between":
                failure_condition = col.isNotNull() & (~in_range)
            else:
                failure_condition = col.isNotNull() & (in_range)
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type in {"expect_column_values_to_match_regex", "expect_column_values_to_not_match_regex"}:
            regex = str(kwargs.get("regex") or "")
            if not regex:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires regex",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            matches = col.cast("string").rlike(regex)
            if expectation_type == "expect_column_values_to_match_regex":
                failure_condition = col.isNull() | (~matches)
            else:
                failure_condition = col.isNotNull() & matches
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_values_to_be_within_past_days":
            max_days_old = kwargs.get("max_days_old")
            anchor = str(kwargs.get("anchor") or "now").strip().lower()
            if max_days_old is None:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires max_days_old",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if anchor != "now":
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' supports only anchor='now'",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            column_ts = F.to_timestamp(col)
            age_days = (F.unix_timestamp(F.current_timestamp()) - F.unix_timestamp(column_ts)) / F.lit(86400.0)
            failure_condition = column_ts.isNull() | (age_days > F.lit(float(max_days_old)))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_pair_values_to_have_max_lag_hours":
            start_column = str(kwargs.get("start_column") or "").strip()
            max_hours = kwargs.get("max_hours")
            if not start_column:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires start_column",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if max_hours is None:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires max_hours",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if start_column not in df_columns:
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "column": start_column,
                        "message": f"Column '{start_column}' not found",
                    }
                )
                continue
            start_ts = F.to_timestamp(F.col(start_column))
            end_ts = F.to_timestamp(col)
            lag_hours = (F.unix_timestamp(end_ts) - F.unix_timestamp(start_ts)) / F.lit(3600.0)
            failure_condition = start_ts.isNull() | end_ts.isNull() | (lag_hours > F.lit(float(max_hours)))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_values_to_not_be_in_future":
            reference_time = kwargs.get("reference_time")
            column_ts = F.to_timestamp(col)
            reference_ts = F.to_timestamp(F.lit(reference_time)) if reference_time is not None else F.current_timestamp()
            failure_condition = column_ts.isNull() | (column_ts > reference_ts)
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        else:
            raise GxWorkerExecutionError(
                f"Unsupported expectation_type '{expectation_type}'",
                failure_code="GX_WORKER_UNSUPPORTED_EXPECTATION",
            )

        ok = not has_failure
        if ok:
            passed += 1
        else:
            failed += 1
            if normalized_primary_key_fields and failure_condition is not None:
                row_diagnostics = _build_row_failure_diagnostics(
                    scoped_df,
                    failure_condition,
                    primary_key_fields=normalized_primary_key_fields,
                    expectation_index=idx,
                    expectation_type=expectation_type,
                    column=column,
                    message="Expectation failed",
                )
                if row_diagnostics:
                    diagnostics.extend(row_diagnostics)
                    continue

            row_identifier = _first_row_identifier(scoped_df, failure_condition, normalized_primary_key_fields)
            diagnostic = {
                "reason": "expectation_failed",
                "expectation_index": idx,
                "expectation_type": expectation_type,
                "column": column,
                "message": "Expectation failed",
            }
            if row_identifier:
                diagnostic["row_identifier"] = row_identifier
                diagnostic["data_primary_key"] = row_identifier
            diagnostics.append(diagnostic)

    completed_at = ""
    summary = {
        "started_at": started_at,
        "completed_at": completed_at,
        "row_count": computed_row_counts.get(id(df)),
        "expectation_count": int(len(expectations)),
        "passed_expectation_count": int(passed),
        "failed_expectation_count": int(failed),
    }
    return failed == 0, summary, diagnostics


def _build_spark_row_condition_expression(row_condition: Any, *, functions_module: Any, df_columns: set[str]) -> Any:
    return row_condition
