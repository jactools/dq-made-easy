from __future__ import annotations

import json
import os
import re
import sys
import types
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime
from tempfile import TemporaryDirectory
from unittest.mock import patch

TESTS_DIR = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
REPO_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
DQ_UTILS_SRC = os.path.join(REPO_ROOT, "dq-utils", "src")
FASTAPI_SRC = os.path.join(REPO_ROOT, "dq-api", "fastapi")

os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")

sys.path.insert(0, DQ_UTILS_SRC)
sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, FASTAPI_SRC)

from app.application.services import build_gx_expectations_for_rule
from app.application.services import compile_rule_to_intermediate_model
from app.domain.entities import RuleEntity
from gx_dispatch_types import GxWorkerConfig
from gx_dispatch_expectations import _build_row_identifier
from gx_dispatch_expectations import _build_native_gx_alias_map
from gx_dispatch_expectations import _evaluate_expectations_spark
from gx_dispatch_expectations import _rewrite_native_gx_expectation_for_aliases
from gx_dispatch_dispatch import process_dispatch_message


def _parse_timestamp(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


class _Expr:
    def __init__(self, fn):
        self._fn = fn

    def eval(self, row):
        return self._fn(row)

    def isNull(self):
        return _Expr(lambda row: self.eval(row) is None)

    def isNotNull(self):
        return _Expr(lambda row: self.eval(row) is not None)

    def isin(self, values):
        wanted = set(values)
        return _Expr(lambda row: self.eval(row) in wanted)

    def cast(self, kind):
        if kind == "string":
            return _Expr(lambda row: None if self.eval(row) is None else str(self.eval(row)))
        return self

    def rlike(self, pattern):
        compiled = re.compile(pattern)
        return _Expr(lambda row: False if self.cast("string").eval(row) is None else bool(compiled.search(self.cast("string").eval(row))))

    def __and__(self, other):
        return _Expr(lambda row: bool(self.eval(row)) and bool(_coerce_expr(other).eval(row)))

    def __or__(self, other):
        return _Expr(lambda row: bool(self.eval(row)) or bool(_coerce_expr(other).eval(row)))

    def __invert__(self):
        return _Expr(lambda row: not bool(self.eval(row)))

    def __gt__(self, other):
        return _Expr(lambda row: _compare(self.eval(row), _coerce_expr(other).eval(row), lambda left, right: left > right))

    def __ge__(self, other):
        return _Expr(lambda row: _compare(self.eval(row), _coerce_expr(other).eval(row), lambda left, right: left >= right))

    def __lt__(self, other):
        return _Expr(lambda row: _compare(self.eval(row), _coerce_expr(other).eval(row), lambda left, right: left < right))

    def __le__(self, other):
        return _Expr(lambda row: _compare(self.eval(row), _coerce_expr(other).eval(row), lambda left, right: left <= right))

    def __sub__(self, other):
        return _Expr(lambda row: _arithmetic(self.eval(row), _coerce_expr(other).eval(row), lambda left, right: left - right))

    def __truediv__(self, other):
        return _Expr(lambda row: _arithmetic(self.eval(row), _coerce_expr(other).eval(row), lambda left, right: left / right))

    def __eq__(self, other):  # type: ignore[override]
        return _Expr(lambda row: _compare(self.eval(row), _coerce_expr(other).eval(row), lambda left, right: left == right))

    def __ne__(self, other):  # type: ignore[override]
        return _Expr(lambda row: _compare(self.eval(row), _coerce_expr(other).eval(row), lambda left, right: left != right))


def _coerce_expr(value):
    if isinstance(value, _Expr):
        return value
    return _Expr(lambda row: value)


def _compare(left, right, op):
    if left is None or right is None:
        return False
    return op(left, right)


def _arithmetic(left, right, op):
    if left is None or right is None:
        return None
    return op(left, right)


def _parse_sql_literal(value):
    raw = str(value).strip()
    if raw.upper() == "NULL":
        return None
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
        return raw[1:-1]
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    return raw


def _parse_sql_expr(expression):
    text = str(expression).strip()

    between_match = re.match(r"^(?P<column>[A-Za-z_][A-Za-z0-9_\.]*)\s+BETWEEN\s+(?P<lower>.+?)\s+AND\s+(?P<upper>.+)$", text, flags=re.IGNORECASE)
    if between_match:
        column = between_match.group("column")
        lower = _parse_sql_literal(between_match.group("lower"))
        upper = _parse_sql_literal(between_match.group("upper"))
        return (_FakeFunctions(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)).col(column) >= lower) & (
            _FakeFunctions(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)).col(column) <= upper
        )

    rlike_match = re.match(r"^(?P<column>[A-Za-z_][A-Za-z0-9_\.]*)\s+RLIKE\s+(?P<pattern>'.+'|\".+\")$", text, flags=re.IGNORECASE)
    if rlike_match:
        return _FakeFunctions(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)).col(rlike_match.group("column")).rlike(
            _parse_sql_literal(rlike_match.group("pattern"))
        )

    like_match = re.match(r"^(?P<column>[A-Za-z_][A-Za-z0-9_\.]*)\s+LIKE\s+(?P<pattern>'.+'|\".+\")$", text, flags=re.IGNORECASE)
    if like_match:
        pattern = str(_parse_sql_literal(like_match.group("pattern")))
        regex = "^" + re.escape(pattern).replace("%", ".*").replace("_", ".") + "$"
        return _FakeFunctions(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)).col(like_match.group("column")).rlike(regex)

    comparison_match = re.match(
        r"^(?P<column>[A-Za-z_][A-Za-z0-9_\.]*)\s*(?P<operator>>=|<=|!=|=|>|<)\s*(?P<value>.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if comparison_match:
        column_expr = _FakeFunctions(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)).col(comparison_match.group("column"))
        value = _parse_sql_literal(comparison_match.group("value"))
        operator = comparison_match.group("operator")
        if operator == "=":
            return column_expr == value
        if operator == "!=":
            return column_expr != value
        if operator == ">":
            return column_expr > value
        if operator == ">=":
            return column_expr >= value
        if operator == "<":
            return column_expr < value
        if operator == "<=":
            return column_expr <= value

    raise ValueError(f"Unsupported fake SQL expression: {expression}")


class _FakeFunctions:
    def __init__(self, now):
        self._now = now

    def col(self, name):
        parts = str(name).split(".")

        def _resolve(row):
            current = row
            for part in parts:
                if not isinstance(current, dict):
                    return None
                current = current.get(part)
            return current

        return _Expr(_resolve)

    def lit(self, value):
        return _Expr(lambda row: value)

    def to_timestamp(self, value):
        expr = _coerce_expr(value)
        return _Expr(lambda row: _parse_timestamp(expr.eval(row)))

    def unix_timestamp(self, value):
        expr = _coerce_expr(value)
        return _Expr(lambda row: None if expr.eval(row) is None else expr.eval(row).timestamp())

    def current_timestamp(self):
        return _Expr(lambda row: self._now)

    def lower(self, value):
        expr = _coerce_expr(value)
        return _Expr(lambda row: None if expr.eval(row) is None else str(expr.eval(row)).lower())

    def abs(self, value):
        expr = _coerce_expr(value)
        return _Expr(lambda row: None if expr.eval(row) is None else abs(expr.eval(row)))

    def expr(self, expression):
        return _parse_sql_expr(expression)


class _FakeDataFrame:
    def __init__(self, rows):
        self._rows = list(rows)
        self.columns = _flatten_columns(rows[0]) if rows else []

    def where(self, condition):
        expr = _coerce_expr(condition)
        return _FakeDataFrame([row for row in self._rows if bool(expr.eval(row))])

    def limit(self, n):
        return _FakeDataFrame(self._rows[:n])

    def take(self, n):
        return self._rows[:n]

    def collect(self):
        return list(self._rows)

    def count(self):
        return len(self._rows)

    def groupBy(self, *columns):
        return _FakeGroupedData(self._rows, list(columns))


class _FakeSparkRow:
    def __init__(self, values):
        self._values = dict(values)

    def asDict(self, recursive=False):
        return dict(self._values)


class _StubTokenProvider:
    def get_token(self, correlation_id: str | None = None) -> str:
        return "token"


class _StubSparkSession:
    def stop(self) -> None:
        return None


def _build_worker_config() -> GxWorkerConfig:
    return GxWorkerConfig(
        redis_url="redis://redis:6379/0",
        queue_key="dq-gx:execution-dispatch",
        processing_queue_key="dq-gx:execution-dispatch:processing",
        heartbeat_key="dq-gx:execution-dispatch:worker-heartbeat",
        heartbeat_ttl_seconds=30,
        heartbeat_interval_seconds=10,
        max_rows=100000,
        poll_timeout_seconds=5,
        api_url="http://kong:8000",
        spark_master="local[*]",
        spark_ui_port=4044,
        s3_endpoint="http://aistor:9000",
        s3_access_key="aistor",
        s3_secret_key="aistorpass",
        s3_region="eu-west-1",
        s3_path_style_access=True,
        s3_ssl_enabled=False,
    )


class _FakeGroupedData:
    def __init__(self, rows, columns):
        self._rows = rows
        self._columns = columns

    def count(self):
        counts = {}
        for row in self._rows:
            key = tuple(row.get(column) for column in self._columns)
            counts[key] = counts.get(key, 0) + 1
        return _FakeDataFrame(
            [
                {**{column: key[idx] for idx, column in enumerate(self._columns)}, "count": count}
                for key, count in counts.items()
            ]
        )


def _flatten_columns(row, prefix=""):
    columns = []
    for key, value in row.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        columns.append(name)
        if isinstance(value, dict):
            columns.extend(_flatten_columns(value, prefix=name))
    return columns


@contextmanager
def _fake_pyspark(now: datetime):
    functions_module = _FakeFunctions(now)
    pyspark_sql_module = types.ModuleType("pyspark.sql")
    pyspark_sql_module.functions = functions_module
    pyspark_module = types.ModuleType("pyspark")
    pyspark_module.sql = pyspark_sql_module
    with patch.dict(sys.modules, {"pyspark": pyspark_module, "pyspark.sql": pyspark_sql_module}):
        yield


class GxDispatchWorkerCustomExpectationTests(unittest.TestCase):
    def test_process_dispatch_message_executes_generated_suite_with_row_condition_scoping(self) -> None:
        intermediate = compile_rule_to_intermediate_model(
            rule_id="rule-worker-row-condition",
            rule_version_id="rv-worker-row-condition",
            filter_expression="country = 'NL'",
        )
        rule = RuleEntity(
            id="rule-worker-row-condition",
            name="Rule Worker Row Condition",
            description=None,
            expression="country = 'NL'",
            dimension="Timeliness",
            active=True,
            createdByUserId="user-1",
            tagIds=[],
            checkType="FRESHNESS",
            checkTypeParams={"attribute": "published_at", "maxDaysOld": 2, "anchor": "now"},
        )
        expectations = build_gx_expectations_for_rule(
            rule=rule,
            intermediate_model=intermediate,
            rule_id="rule-worker-row-condition",
            artifact_key=intermediate["artifactKey"],
        )
        envelope = {
            "suite_id": "gx_rule-worker-row-condition",
            "suite_version": 1,
            "gx_suite": {"expectations": expectations},
            "resolved_execution_scope": {"data_object_version_ids": ["dov-1"]},
        }
        payload = {
            "run_id": "run-row-condition-e2e-1",
            "queue_message_id": "run-row-condition-e2e-1",
            "correlation_id": "corr-row-condition-e2e-1",
            "requested_by": "user-1",
            "engine_target": "pyspark",
            "suite_id": "gx_rule-worker-row-condition",
            "suite_version": 1,
            "source_overrides_by_data_object_version_id": {
                "dov-1": {"uri": "s3://dq-tests/rules/row-condition.parquet", "format": "parquet"}
            },
        }
        rows = [
            {"country": "NL", "published_at": "2026-04-17T12:00:00Z"},
            {"country": "BE", "published_at": "2026-04-01T00:00:00Z"},
        ]
        reports: list[dict[str, object]] = []

        with TemporaryDirectory() as tmpdir:
            with _fake_pyspark(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)):
                with patch("gx_dispatch_worker._build_token_provider", return_value=_StubTokenProvider()), patch(
                    "execution_dispatch.report_run",
                    side_effect=lambda *args, **kwargs: reports.append(kwargs),
                ), patch(
                    "gx_dispatch_worker._api_report_execution_progress",
                    side_effect=lambda *args, **kwargs: None,
                ), patch(
                    "gx_dispatch_worker._api_get_suite_envelope",
                    return_value=envelope,
                ), patch(
                    "gx_dispatch_worker._create_spark_session",
                    return_value=_StubSparkSession(),
                ), patch(
                    "gx_dispatch_worker._download_s3a_prefix_to_tempdir",
                    return_value=(TemporaryDirectory(), tmpdir),
                ), patch(
                    "gx_dispatch_worker._spark_read_dataset",
                    return_value=_FakeDataFrame(rows),
                ), patch(
                    "gx_dispatch_worker.record_worker_duration",
                    side_effect=lambda *args, **kwargs: None,
                ), patch(
                    "gx_dispatch_worker.record_worker_expectation_results",
                    side_effect=lambda *args, **kwargs: None,
                ):
                    process_dispatch_message(_build_worker_config(), raw_message=json.dumps(payload))

        self.assertGreaterEqual(len(reports), 2)
        self.assertEqual(reports[0]["new_status"], "running")
        self.assertEqual(reports[-1]["new_status"], "succeeded")
        result = reports[-1]["result_summary"]["results"][0]
        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["failed_expectation_count"], 0)

    def test_process_dispatch_message_reports_row_identifier_for_failed_expectation(self) -> None:
        envelope = {
            "suite_id": "gx_rule-worker-row-identifier",
            "suite_version": 1,
            "gx_suite": {
                "expectations": [
                    {
                        "expectation_type": "expect_column_values_to_not_be_null",
                        "kwargs": {"column": "email"},
                    }
                ]
            },
            "executionHints": {"recommendedEngine": "pyspark", "primaryKeyFields": ["order_id"]},
            "resolved_execution_scope": {"data_object_version_ids": ["dov-1"]},
        }
        payload = {
            "run_id": "run-row-identifier-1",
            "queue_message_id": "run-row-identifier-1",
            "correlation_id": "corr-row-identifier-1",
            "requested_by": "user-1",
            "engine_target": "pyspark",
            "suite_id": "gx_rule-worker-row-identifier",
            "suite_version": 1,
            "source_overrides_by_data_object_version_id": {
                "dov-1": {"uri": "s3://dq-tests/rules/row-identifier.parquet", "format": "parquet"}
            },
        }
        rows = [
            {"order_id": 1, "email": "a@example.com"},
            {"order_id": 42, "email": None},
        ]
        reports: list[dict[str, object]] = []

        with TemporaryDirectory() as tmpdir:
            with _fake_pyspark(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)):
                with patch("gx_dispatch_worker._build_token_provider", return_value=_StubTokenProvider()), patch(
                    "execution_dispatch.report_run",
                    side_effect=lambda *args, **kwargs: reports.append(kwargs),
                ), patch(
                    "gx_dispatch_worker._api_report_execution_progress",
                    side_effect=lambda *args, **kwargs: None,
                ), patch(
                    "gx_dispatch_worker._api_get_suite_envelope",
                    return_value=envelope,
                ), patch(
                    "gx_dispatch_worker._create_spark_session",
                    return_value=_StubSparkSession(),
                ), patch(
                    "gx_dispatch_worker._download_s3a_prefix_to_tempdir",
                    return_value=(TemporaryDirectory(), tmpdir),
                ), patch(
                    "gx_dispatch_worker._spark_read_dataset",
                    return_value=_FakeDataFrame(rows),
                ), patch(
                    "gx_dispatch_worker.record_worker_duration",
                    side_effect=lambda *args, **kwargs: None,
                ), patch(
                    "gx_dispatch_worker.record_worker_expectation_results",
                    side_effect=lambda *args, **kwargs: None,
                ):
                    process_dispatch_message(_build_worker_config(), raw_message=json.dumps(payload))

        self.assertGreaterEqual(len(reports), 2)
        self.assertEqual(reports[-1]["new_status"], "failed")
        self.assertEqual(reports[-1]["failure_code"], "GX_VALIDATION_FAILED")
        self.assertEqual(reports[-1]["diagnostics"][0]["row_identifier"], "order_id=42")
        self.assertEqual(reports[-1]["diagnostics"][0]["data_object_version_id"], "dov-1")

    def test_evaluate_expectations_applies_structured_row_condition(self) -> None:
        rows = [
            {"country": "NL", "status": "ACTIVE"},
            {"country": "BE", "status": "BLOCKED"},
        ]

        with _fake_pyspark(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)):
            ok, summary, diagnostics = _evaluate_expectations_spark(
                _FakeDataFrame(rows),
                [
                    {
                        "expectation_type": "expect_column_values_to_be_in_set",
                        "kwargs": {
                            "column": "status",
                            "value_set": ["ACTIVE"],
                            "row_condition": {
                                "type": "comparison",
                                "column": {"name": "country"},
                                "operator": "==",
                                "parameter": "NL",
                            },
                        },
                    }
                ],
            )

        self.assertTrue(ok)
        self.assertEqual(summary["passed_expectation_count"], 1)
        self.assertEqual(diagnostics, [])

    def test_evaluate_expectations_includes_row_identifier_when_primary_keys_exist(self) -> None:
        rows = [
            {"order_id": 1, "email": "a@example.com"},
            {"order_id": 42, "email": None},
        ]

        with _fake_pyspark(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)):
            ok, summary, diagnostics = _evaluate_expectations_spark(
                _FakeDataFrame(rows),
                [
                    {
                        "expectation_type": "expect_column_values_to_not_be_null",
                        "kwargs": {"column": "email"},
                    }
                ],
                primary_key_fields=["order_id"],
            )

        self.assertFalse(ok)
        self.assertEqual(summary["failed_expectation_count"], 1)
        self.assertEqual(diagnostics[0]["row_identifier"], "order_id=42")

    def test_evaluate_expectations_emits_row_level_diagnostics_for_high_cardinality_failures(self) -> None:
        rows = [
            {
                "customer_id": f"cust-invalid-{index:03d}",
                "email": f"invalid-{index:03d}@example",
                "created_at": "2026-04-18T12:00:00Z",
            }
            for index in range(1, 206)
        ]
        rows.extend(
            [
                {
                    "customer_id": f"cust-valid-{index:03d}",
                    "email": f"valid-{index:03d}@example.com",
                    "created_at": "2026-04-18T12:00:00Z",
                }
                for index in range(1, 6)
            ]
        )

        with _fake_pyspark(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)):
            ok, summary, diagnostics = _evaluate_expectations_spark(
                _FakeDataFrame(rows),
                [
                    {
                        "expectation_type": "expect_column_values_to_match_regex",
                        "kwargs": {
                            "column": "email",
                            "regex": "^[^@]+@[^@]+\\.[^@]+$",
                        },
                    }
                ],
                primary_key_fields=["customer_id"],
            )

        self.assertFalse(ok)
        self.assertEqual(summary["failed_expectation_count"], 1)
        self.assertEqual(len(diagnostics), 205)
        self.assertEqual(diagnostics[0]["row_identifier"], "customer_id=cust-invalid-001")
        self.assertEqual(diagnostics[0]["data_primary_key"], "customer_id=cust-invalid-001")
        self.assertEqual(diagnostics[-1]["row_identifier"], "customer_id=cust-invalid-205")
        self.assertTrue(all(item["expectation_type"] == "expect_column_values_to_match_regex" for item in diagnostics))

    def test_evaluate_expectations_includes_data_primary_key_for_missing_columns(self) -> None:
        rows = [
            {"order_id": 1, "email": "a@example.com"},
            {"order_id": 42, "email": None},
        ]

        with _fake_pyspark(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)):
            ok, summary, diagnostics = _evaluate_expectations_spark(
                _FakeDataFrame(rows),
                [
                    {
                        "expectation_type": "expect_column_values_to_not_be_null",
                        "kwargs": {"column": "phone"},
                    }
                ],
                primary_key_fields=["order_id"],
            )

        self.assertFalse(ok)
        self.assertEqual(summary["failed_expectation_count"], 1)
        self.assertEqual(diagnostics[0]["row_identifier"], "order_id=1")
        self.assertEqual(diagnostics[0]["data_primary_key"], "order_id=1")

    def test_build_row_identifier_handles_row_like_objects(self) -> None:
        row = _FakeSparkRow({"order_id": 42, "email": None})

        self.assertEqual(_build_row_identifier(row, ["order_id"]), "order_id=42")

    def test_evaluate_expectations_applies_pass_through_row_condition(self) -> None:
        rows = [
            {"country": "NL", "status": "ACTIVE"},
            {"country": "BE", "status": "BLOCKED"},
        ]

        with _fake_pyspark(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)):
            ok, summary, diagnostics = _evaluate_expectations_spark(
                _FakeDataFrame(rows),
                [
                    {
                        "expectation_type": "expect_column_values_to_be_in_set",
                        "kwargs": {
                            "column": "status",
                            "value_set": ["ACTIVE"],
                            "row_condition": {
                                "type": "pass_through",
                                "pass_through_filter": "country RLIKE '^N.*'",
                            },
                        },
                    }
                ],
            )

        self.assertTrue(ok)
        self.assertEqual(summary["passed_expectation_count"], 1)
        self.assertEqual(diagnostics, [])

    def test_evaluate_expectations_applies_row_condition_to_row_count(self) -> None:
        rows = [
            {"country": "NL", "status": "ACTIVE"},
            {"country": "BE", "status": "BLOCKED"},
        ]

        with _fake_pyspark(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)):
            ok, summary, diagnostics = _evaluate_expectations_spark(
                _FakeDataFrame(rows),
                [
                    {
                        "expectation_type": "expect_table_row_count_to_be_between",
                        "kwargs": {
                            "min_value": 2,
                            "max_value": 10,
                            "row_condition": {
                                "type": "comparison",
                                "column": {"name": "country"},
                                "operator": "==",
                                "parameter": "NL",
                            },
                        },
                    }
                ],
            )

        self.assertFalse(ok)
        self.assertEqual(summary["failed_expectation_count"], 1)
        self.assertEqual(diagnostics[0]["expectation_type"], "expect_table_row_count_to_be_between")
        self.assertEqual(diagnostics[0]["row_count"], 1)

    def test_evaluate_expectations_supports_uniqueness_and_open_ended_range(self) -> None:
        rows = [
            {"order_id": "o-1", "amount": 10},
            {"order_id": "o-2", "amount": 12},
        ]

        with _fake_pyspark(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)):
            ok, summary, diagnostics = _evaluate_expectations_spark(
                _FakeDataFrame(rows),
                [
                    {"expectation_type": "expect_column_values_to_be_unique", "kwargs": {"column": "order_id"}},
                    {"expectation_type": "expect_column_values_to_be_between", "kwargs": {"column": "amount", "min_value": 0}},
                ],
            )

        self.assertTrue(ok)
        self.assertEqual(summary["passed_expectation_count"], 2)
        self.assertEqual(diagnostics, [])

    def test_evaluate_expectations_detects_compound_duplicate_keys(self) -> None:
        rows = [
            {"customer_id": "c-1", "order_id": "o-1"},
            {"customer_id": "c-1", "order_id": "o-1"},
        ]

        with _fake_pyspark(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)):
            ok, summary, diagnostics = _evaluate_expectations_spark(
                _FakeDataFrame(rows),
                [
                    {
                        "expectation_type": "expect_compound_columns_to_be_unique",
                        "kwargs": {"column": "customer_id", "columns": ["customer_id", "order_id"]},
                    }
                ],
            )

        self.assertFalse(ok)
        self.assertEqual(summary["failed_expectation_count"], 1)
        self.assertEqual(diagnostics[0]["expectation_type"], "expect_compound_columns_to_be_unique")

    def test_evaluate_expectations_supports_dynamic_timeliness_checks(self) -> None:
        now = datetime(2026, 4, 18, 12, 0, tzinfo=UTC)
        rows = [
            {
                "published_at": "2026-04-17T12:00:00Z",
                "created_at": "2026-04-17T09:00:00Z",
                "event_ts": "2026-04-18T11:00:00Z",
            },
            {
                "published_at": "2026-04-10T00:00:00Z",
                "created_at": "2026-04-17T00:00:00Z",
                "event_ts": "2026-04-19T00:00:00Z",
            },
        ]

        with _fake_pyspark(now):
            ok, summary, diagnostics = _evaluate_expectations_spark(
                _FakeDataFrame(rows),
                [
                    {
                        "expectation_type": "expect_column_values_to_be_within_past_days",
                        "kwargs": {"column": "published_at", "max_days_old": 2, "anchor": "now"},
                    },
                    {
                        "expectation_type": "expect_column_pair_values_to_have_max_lag_hours",
                        "kwargs": {"column": "published_at", "start_column": "created_at", "max_hours": 48},
                    },
                    {
                        "expectation_type": "expect_column_values_to_not_be_in_future",
                        "kwargs": {"column": "event_ts", "reference_time": "2026-04-18T12:00:00Z"},
                    },
                ],
            )

        self.assertFalse(ok)
        self.assertEqual(summary["failed_expectation_count"], 2)
        self.assertEqual(
            [item["expectation_type"] for item in diagnostics],
            [
                "expect_column_values_to_be_within_past_days",
                "expect_column_values_to_not_be_in_future",
            ],
        )

    def test_evaluate_expectations_supports_join_pair_custom_comparisons(self) -> None:
        rows = [
            {"status": "ACTIVE", "amount": 100.0, "actuality_ts": "2026-04-18T10:00:00Z", "rhs": {"status": "active", "amount": 100.005, "published_at": "2026-04-18T10:30:00Z", "ref_id": "A-1"}},
            {"status": "PENDING", "amount": 50.0, "actuality_ts": "2026-04-18T08:00:00Z", "rhs": {"status": "FAILED", "amount": 55.0, "published_at": "2026-04-19T10:00:00Z", "ref_id": None}},
        ]

        with _fake_pyspark(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)):
            ok, summary, diagnostics = _evaluate_expectations_spark(
                _FakeDataFrame(rows),
                [
                    {
                        "expectation_type": "expect_column_values_to_equal_other_column_case_insensitive",
                        "kwargs": {"column": "status", "other_column": "rhs.status"},
                    },
                    {
                        "expectation_type": "expect_column_values_to_be_within_numeric_tolerance_of_other_column",
                        "kwargs": {"column": "amount", "other_column": "rhs.amount", "tolerance": 0.01},
                    },
                    {
                        "expectation_type": "expect_column_timestamps_to_be_within_tolerance_of_other_column",
                        "kwargs": {
                            "column": "actuality_ts",
                            "other_column": "rhs.published_at",
                            "max_difference": 2,
                            "difference_unit": "hours",
                        },
                    },
                    {
                        "expectation_type": "expect_column_values_to_not_be_null",
                        "kwargs": {"column": "rhs.ref_id"},
                    },
                ],
            )

        self.assertFalse(ok)
        self.assertEqual(summary["failed_expectation_count"], 4)
        self.assertEqual(
            [item["expectation_type"] for item in diagnostics],
            [
                "expect_column_values_to_equal_other_column_case_insensitive",
                "expect_column_values_to_be_within_numeric_tolerance_of_other_column",
                "expect_column_timestamps_to_be_within_tolerance_of_other_column",
                "expect_column_values_to_not_be_null",
            ],
        )

    def test_evaluate_expectations_supports_plausible_conditional_expectations(self) -> None:
        rows = [
            {"amount": 50, "currency": "USD", "payment_method": "Card"},
            {"amount": 125000, "currency": "USD", "payment_method": "ACH"},
            {"amount": 200, "currency": "JPY", "payment_method": "wire"},
            {"amount": 10, "currency": "EUR", "payment_method": None},
        ]

        with _fake_pyspark(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)):
            ok, summary, diagnostics = _evaluate_expectations_spark(
                _FakeDataFrame(rows),
                [
                    {
                        "expectation_type": "expect_column_values_to_not_be_null",
                        "kwargs": {"column": "currency"},
                    },
                    {
                        "expectation_type": "expect_column_values_to_be_in_set",
                        "kwargs": {"column": "currency", "value_set": ["USD", "EUR"]},
                    },
                    {
                        "expectation_type": "expect_column_values_to_be_between",
                        "kwargs": {
                            "column": "amount",
                            "min_value": 0,
                            "max_value": 100000,
                            "row_condition": {
                                "type": "comparison",
                                "column": {"name": "currency"},
                                "operator": "==",
                                "parameter": "USD",
                            },
                        },
                    },
                    {
                        "expectation_type": "expect_column_values_to_be_between",
                        "kwargs": {
                            "column": "amount",
                            "min_value": 0,
                            "max_value": 90000,
                            "row_condition": {
                                "type": "comparison",
                                "column": {"name": "currency"},
                                "operator": "==",
                                "parameter": "EUR",
                            },
                        },
                    },
                    {
                        "expectation_type": "expect_column_values_to_match_regex",
                        "kwargs": {
                            "column": "payment_method",
                            "regex": "(?i)^(?:card|ach)$",
                            "row_condition": {
                                "type": "comparison",
                                "column": {"name": "currency"},
                                "operator": "==",
                                "parameter": "USD",
                            },
                        },
                    },
                    {
                        "expectation_type": "expect_column_values_to_match_regex",
                        "kwargs": {
                            "column": "payment_method",
                            "regex": "(?i)^(?:card|sepa)$",
                            "row_condition": {
                                "type": "comparison",
                                "column": {"name": "currency"},
                                "operator": "==",
                                "parameter": "EUR",
                            },
                        },
                    },
                ],
            )

        self.assertFalse(ok)
        self.assertEqual(summary["failed_expectation_count"], 3)
        self.assertEqual(
            [item["expectation_type"] for item in diagnostics],
            [
                "expect_column_values_to_be_in_set",
                "expect_column_values_to_be_between",
                "expect_column_values_to_match_regex",
            ],
        )

    def test_evaluate_expectations_supports_native_pair_equality_in_fallback(self) -> None:
        rows = [
            {"status": "ACTIVE", "rhs": {"status": "ACTIVE"}},
            {"status": "PENDING", "rhs": {"status": None}},
        ]

        with _fake_pyspark(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)):
            ok, summary, diagnostics = _evaluate_expectations_spark(
                _FakeDataFrame(rows),
                [
                    {
                        "expectation_type": "expect_column_pair_values_to_be_equal",
                        "kwargs": {"column_A": "status", "column_B": "rhs.status", "ignore_row_if": "neither"},
                    }
                ],
            )

        self.assertFalse(ok)
        self.assertEqual(summary["failed_expectation_count"], 1)
        self.assertEqual(diagnostics[0]["expectation_type"], "expect_column_pair_values_to_be_equal")

    def test_evaluate_expectations_supports_native_threshold_aggregate_in_fallback(self) -> None:
        rows = [{"email": "a@example.com"} for _ in range(9)] + [{"email": None}]

        with _fake_pyspark(datetime(2026, 4, 18, 12, 0, tzinfo=UTC)):
            ok, summary, diagnostics = _evaluate_expectations_spark(
                _FakeDataFrame(rows),
                [
                    {
                        "expectation_type": "expect_column_proportion_of_non_null_values_to_be_between",
                        "kwargs": {"column": "email", "min_value": 0.95},
                    }
                ],
            )

        self.assertFalse(ok)
        self.assertEqual(summary["failed_expectation_count"], 1)
        self.assertEqual(diagnostics[0]["expectation_type"], "expect_column_proportion_of_non_null_values_to_be_between")

    def test_rewrite_native_gx_expectation_for_aliases_rewrites_nested_pair_columns(self) -> None:
        alias_map = _build_native_gx_alias_map(["status", "rhs.status", "rhs.country"])
        rewritten = _rewrite_native_gx_expectation_for_aliases(
            {
                "expectation_type": "expect_column_pair_values_to_be_equal",
                "kwargs": {
                    "column_A": "status",
                    "column_B": "rhs.status",
                    "ignore_row_if": "neither",
                    "row_condition": {
                        "type": "comparison",
                        "column": {"name": "rhs.country"},
                        "operator": "==",
                        "parameter": "NL",
                    },
                },
            },
            alias_map,
        )

        self.assertEqual(rewritten["kwargs"]["column_A"], alias_map["status"])
        self.assertEqual(rewritten["kwargs"]["column_B"], alias_map["rhs.status"])
        self.assertEqual(
            rewritten["kwargs"]["row_condition"]["column"]["name"],
            alias_map["rhs.country"],
        )

    def test_rewrite_native_gx_expectation_for_aliases_rewrites_compound_column_lists(self) -> None:
        alias_map = _build_native_gx_alias_map(["order_id", "rhs.order_id"])
        rewritten = _rewrite_native_gx_expectation_for_aliases(
            {
                "expectation_type": "expect_compound_columns_to_be_unique",
                "kwargs": {
                    "columns": ["order_id", "rhs.order_id"],
                },
            },
            alias_map,
        )

        self.assertEqual(
            rewritten["kwargs"]["columns"],
            [alias_map["order_id"], alias_map["rhs.order_id"]],
        )

    def test_evaluate_expectations_prefers_native_gx_for_real_spark_dataframes(self) -> None:
        class _PseudoSparkDataFrame(_FakeDataFrame):
            pass

        _PseudoSparkDataFrame.__module__ = "pyspark.sql.dataframe"

        with patch("gx_dispatch_worker._NativeGxBatchRunner.validate", return_value=(True, None)) as native_validate:
            ok, summary, diagnostics = _evaluate_expectations_spark(
                _PseudoSparkDataFrame([{"status": "ACTIVE", "rhs": {"status": "ACTIVE"}}]),
                [
                    {
                        "expectation_type": "expect_column_pair_values_to_be_equal",
                        "kwargs": {"column_A": "status", "column_B": "rhs.status", "ignore_row_if": "neither"},
                    }
                ],
            )

        self.assertTrue(ok)
        self.assertEqual(summary["passed_expectation_count"], 1)
        self.assertEqual(diagnostics, [])
        native_validate.assert_called_once()


if __name__ == "__main__":
    unittest.main()