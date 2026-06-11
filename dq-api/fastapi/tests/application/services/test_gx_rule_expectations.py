from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.application.services as application_services
import app.application.services.gx_rule_expectations as gx_rule_expectations
from app.application.services import compile_rule_to_intermediate_model
from app.application.services import GxExpectationBuildError
from app.application.services import build_gx_expectations_for_rule
from app.domain.entities import RuleEntity


def _rule(*, check_type: str, check_type_params: dict) -> RuleEntity:
    return RuleEntity(
        id="rule-1",
        name="Rule 1",
        description=None,
        expression="TRUE",
        dimension="Validity",
        active=True,
        createdByUserId="user-1",
        tagIds=[],
        checkType=check_type,
        checkTypeParams=check_type_params,
    )


def test_build_gx_expectations_for_rule_builds_regex_expectation_from_check_type() -> None:
    expectations = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="REGEX",
            check_type_params={
                "attribute": "customer_email",
                "pattern": "^[^@]+@[^@]+\\.[^@]+$",
                "flags": "i",
            },
        ),
        rule_id="rule-1",
        artifact_key="ak-1",
    )

    assert expectations == [
        {
            "expectation_type": "expect_column_values_to_match_regex",
            "kwargs": {"column": "customer_email", "regex": "(?i)^[^@]+@[^@]+\\.[^@]+$"},
            "meta": {"dq.rule_id": "rule-1", "dq.artifact_key": "ak-1"},
        }
    ]


def test_build_gx_expectations_for_rule_attaches_structured_row_condition_to_native_expectation() -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-native-row-condition",
        rule_version_id="rv-native-1",
        filter_expression="country = 'NL' AND age BETWEEN 18 AND 65",
    )

    expectations = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="REGEX",
            check_type_params={
                "attribute": "customer_email",
                "pattern": "^[^@]+@[^@]+\\.[^@]+$",
                "flags": "i",
            },
        ),
        intermediate_model=intermediate,
    )

    assert expectations == [
        {
            "expectation_type": "expect_column_values_to_match_regex",
            "kwargs": {
                "column": "customer_email",
                "regex": "(?i)^[^@]+@[^@]+\\.[^@]+$",
                "row_condition": {
                    "type": "and",
                    "conditions": [
                        {"type": "comparison", "column": {"name": "country"}, "operator": "==", "parameter": "NL"},
                        {"type": "comparison", "column": {"name": "age"}, "operator": ">=", "parameter": 18},
                        {"type": "comparison", "column": {"name": "age"}, "operator": "<=", "parameter": 65},
                    ],
                },
            },
            "meta": {},
        }
    ]


def test_build_gx_expectations_for_rule_attaches_pass_through_row_condition_for_regex_filter() -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-native-pass-through",
        rule_version_id="rv-native-2",
        filter_expression="country RLIKE '^N.*'",
    )

    expectations = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="ALLOWLIST",
            check_type_params={
                "attribute": "status",
                "allowedValues": ["ACTIVE", "PENDING"],
                "caseSensitive": True,
            },
        ),
        intermediate_model=intermediate,
    )

    assert expectations == [
        {
            "expectation_type": "expect_column_values_to_be_in_set",
            "kwargs": {
                "column": "status",
                "value_set": ["ACTIVE", "PENDING"],
                "row_condition": {
                    "type": "pass_through",
                    "pass_through_filter": "country RLIKE '^N.*'",
                },
            },
            "meta": {},
        }
    ]


def test_build_gx_expectations_for_rule_builds_dynamic_timeliness_expectations() -> None:
    freshness = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="FRESHNESS",
            check_type_params={"attribute": "published_at", "maxDaysOld": 2, "anchor": "now"},
        )
    )
    lag = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="LAG",
            check_type_params={"startAttribute": "created_at", "endAttribute": "published_at", "maxHours": 6},
        )
    )
    future = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="FUTURE_DATE",
            check_type_params={"attribute": "event_ts", "referenceDate": "2026-04-01T00:00:00Z"},
        )
    )

    assert freshness[0]["expectation_type"] == "expect_column_values_to_be_within_past_days"
    assert freshness[0]["kwargs"] == {"column": "published_at", "max_days_old": 2, "anchor": "now"}
    assert lag[0]["expectation_type"] == "expect_column_pair_values_to_have_max_lag_hours"
    assert lag[0]["kwargs"] == {"column": "published_at", "start_column": "created_at", "max_hours": 6}
    assert future[0]["expectation_type"] == "expect_column_values_to_not_be_in_future"
    assert future[0]["kwargs"] == {"column": "event_ts", "reference_time": "2026-04-01T00:00:00Z"}


def test_build_gx_expectations_for_rule_builds_present_and_uniqueness_expectations() -> None:
    present = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="PRESENT",
            check_type_params={"attribute": "status", "blockedValues": ["N/A", "UNKNOWN"], "caseSensitive": False},
        )
    )
    unique = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="UNIQUENESS",
            check_type_params={"attributes": ["customer_id", "order_id"]},
        )
    )

    assert [item["expectation_type"] for item in present] == [
        "expect_column_values_to_not_be_null",
        "expect_column_values_to_not_match_regex",
        "expect_column_values_to_not_match_regex",
    ]
    assert unique == [
        {
            "expectation_type": "expect_compound_columns_to_be_unique",
            "kwargs": {"column": "customer_id", "columns": ["customer_id", "order_id"]},
            "meta": {},
        }
    ]


def test_build_gx_expectations_for_rule_builds_row_count_expectation() -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-row-count",
        rule_version_id="rv-row-count",
        filter_expression="country = 'NL'",
    )

    expectations = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="ROW_COUNT",
            check_type_params={"operator": "gte", "threshold": 25},
        ),
        intermediate_model=intermediate,
    )

    assert expectations == [
        {
            "expectation_type": "expect_table_row_count_to_be_between",
            "kwargs": {
                "min_value": 25,
                "row_condition": {
                    "type": "comparison",
                    "column": {"name": "country"},
                    "operator": "==",
                    "parameter": "NL",
                },
            },
            "meta": {},
        }
    ]


def test_build_gx_expectations_for_rule_builds_custom_query_assertion_expectation() -> None:
    rule = SimpleNamespace(
        id="rule-1",
        kind="custom_query_assertion",
        expression="",
        check_type=None,
        check_type_params=None,
        dsl={
            "schema_version": "2.0.0",
            "rule": {
                "kind": "custom_query_assertion",
                "scope": {
                    "dataset": {"data_object_id": "do-1"},
                },
                "measure": {
                    "type": "query",
                    "query_language": "sql",
                    "query": "SELECT transaction_id, amount FROM teller_machine_left_reconcile",
                    "comparison_data_source_name": "Transaction Source",
                    "comparison_query": "SELECT order_id AS transaction_id, total_amount AS amount FROM teller_machine_right_reconcile",
                },
                "expectation": {
                    "type": "threshold",
                    "operator": "gte",
                    "value": 100,
                    "unit": "percent",
                },
                "operations": {
                    "severity": "critical",
                    "preferred_engines": ["gx", "sql"],
                    "fail_if_not_native": False,
                },
                "evidence": {
                    "failed_rows": {
                        "mode": "sample",
                        "limit": 25,
                        "include_row_identifier": True,
                        "include_primary_key": True,
                    },
                    "emit_compiled_artifact": True,
                    "emit_generated_sql": False,
                },
            },
        },
    )

    expectations = build_gx_expectations_for_rule(rule=rule, rule_id="rule-1", artifact_key="ak-1")

    assert expectations == [
        {
            "expectation_type": "expect_query_results_to_match_comparison",
            "kwargs": {
                "base_query": "SELECT transaction_id, amount FROM teller_machine_left_reconcile",
                "comparison_data_source_name": "Transaction Source",
                "comparison_query": "SELECT order_id AS transaction_id, total_amount AS amount FROM teller_machine_right_reconcile",
                "mostly": 1.0,
            },
            "meta": {"dq.rule_id": "rule-1", "dq.artifact_key": "ak-1"},
        }
    ]


def test_build_gx_expectations_for_rule_reads_custom_query_kind_from_dsl_when_kind_is_absent() -> None:
    rule = RuleEntity(
        id="rule-1",
        name="Rule 1",
        description=None,
        expression="",
        dimension="Accuracy",
        active=True,
        createdByUserId="user-1",
        tagIds=[],
        dsl={
            "schema_version": "2.0.0",
            "rule": {
                "kind": "custom_query_assertion",
                "scope": {
                    "dataset": {"data_object_id": "do-1"},
                },
                "measure": {
                    "type": "query",
                    "query_language": "sql",
                    "query": "SELECT transaction_id, amount FROM teller_machine_left_reconcile",
                    "comparison_data_source_name": "Transaction Source",
                    "comparison_query": "SELECT order_id AS transaction_id, total_amount AS amount FROM teller_machine_right_reconcile",
                },
                "expectation": {
                    "type": "threshold",
                    "operator": "gte",
                    "value": 100,
                    "unit": "percent",
                },
                "evidence": {
                    "failed_rows": {
                        "mode": "sample",
                        "limit": 25,
                        "include_row_identifier": True,
                        "include_primary_key": True,
                    },
                    "emit_compiled_artifact": True,
                    "emit_generated_sql": False,
                },
                "operations": {
                    "severity": "critical",
                    "preferred_engines": ["gx", "sql"],
                    "fail_if_not_native": False,
                },
            },
        },
    )

    expectations = build_gx_expectations_for_rule(rule=rule, rule_id="rule-1", artifact_key="ak-1")

    assert expectations == [
        {
            "expectation_type": "expect_query_results_to_match_comparison",
            "kwargs": {
                "base_query": "SELECT transaction_id, amount FROM teller_machine_left_reconcile",
                "comparison_data_source_name": "Transaction Source",
                "comparison_query": "SELECT order_id AS transaction_id, total_amount AS amount FROM teller_machine_right_reconcile",
                "mostly": 1.0,
            },
            "meta": {"dq.rule_id": "rule-1", "dq.artifact_key": "ak-1"},
        }
    ]


def test_build_gx_expectations_for_rule_builds_quantile_threshold_expectation() -> None:
    expectations = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="THRESHOLD",
            check_type_params={
                "attribute": "amount",
                "metric": "quantile",
                "operator": "lte",
                "threshold": 100,
                "quantile": 0.95,
            },
        )
    )

    assert expectations == [
        {
            "expectation_type": "expect_column_quantile_values_to_be_between",
            "kwargs": {
                "column": "amount",
                "quantile_ranges": {
                    "quantiles": [0.95],
                    "value_ranges": [[None, 100.0]],
                },
                "allow_relative_error": False,
            },
            "meta": {},
        }
    ]


def test_build_gx_expectations_for_rule_rejects_quantile_gt_operator() -> None:
    with pytest.raises(GxExpectationBuildError, match="only supports operators gte and lte"):
        build_gx_expectations_for_rule(
            rule=_rule(
                check_type="THRESHOLD",
                check_type_params={
                    "attribute": "amount",
                    "metric": "quantile",
                    "operator": "gt",
                    "threshold": 100,
                    "quantile": 0.95,
                },
            )
        )


def test_build_gx_expectations_for_rule_builds_referential_integrity_expectation() -> None:
    expectations = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="REFERENTIAL_INTEGRITY",
            check_type_params={
                "attribute": "customer_id",
                "refDataObjectId": "customers",
                "refDataObjectVersionId": "dov-customers",
                "refAttribute": "customer_id",
            },
        )
    )

    assert expectations == [
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "rhs.customer_id"},
            "meta": {},
        }
    ]


def test_build_gx_expectations_for_rule_builds_join_pair_comparison_expectations() -> None:
    expectations = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="JOIN_CONSISTENCY",
            check_type_params={
                "leftDataObjectVersionId": "dov-1",
                "rightDataObjectVersionId": "dov-2",
                "joinKeys": [{"leftAttribute": "order_id", "rightAttribute": "order_id"}],
                "comparisons": [
                    {"leftAttribute": "status", "rightAttribute": "status", "mode": "exact"},
                    {"leftAttribute": "customer_email", "rightAttribute": "email_address", "mode": "case_insensitive"},
                ],
                "actualityDate": {
                    "leftAttribute": "actuality_ts",
                    "rightAttribute": "published_at",
                    "contractId": "contract-1",
                    "resolvedToleranceValue": 2,
                    "resolvedToleranceUnit": "hours",
                },
                "minMatchRate": 99,
            },
        )
    )

    assert [item["expectation_type"] for item in expectations] == [
        "expect_column_pair_values_to_be_equal",
        "expect_column_values_to_equal_other_column_case_insensitive",
        "expect_column_timestamps_to_be_within_tolerance_of_other_column",
    ]
    assert expectations[0]["kwargs"] == {"column_A": "status", "column_B": "rhs.status", "ignore_row_if": "neither"}
    assert expectations[1]["kwargs"] == {"column": "customer_email", "other_column": "rhs.email_address"}
    assert expectations[2]["kwargs"] == {
        "column": "actuality_ts",
        "other_column": "rhs.published_at",
        "max_difference": 2,
        "difference_unit": "hours",
    }


def test_build_gx_expectations_for_rule_builds_contextual_range_plausible_expectations() -> None:
    expectations = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="PLAUSIBLE",
            check_type_params={
                "attribute": "amount",
                "contextAttribute": "country",
                "mode": "contextual_range",
                "ranges": [{"contextValue": "NL", "minValue": 0, "maxValue": 10, "inclusive": True}],
            },
        )
    )

    assert expectations == [
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "country"},
            "meta": {},
        },
        {
            "expectation_type": "expect_column_values_to_be_in_set",
            "kwargs": {"column": "country", "value_set": ["NL"]},
            "meta": {},
        },
        {
            "expectation_type": "expect_column_values_to_be_between",
            "kwargs": {
                "column": "amount",
                "min_value": 0,
                "max_value": 10,
                "row_condition": {
                    "type": "comparison",
                    "column": {"name": "country"},
                    "operator": "==",
                    "parameter": "NL",
                },
            },
            "meta": {},
        },
    ]


def test_build_gx_expectations_for_rule_builds_conditional_allowlist_plausible_expectations() -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-plausible-allowlist",
        rule_version_id="rv-plausible-allowlist",
        filter_expression="segment = 'VIP'",
    )

    expectations = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="PLAUSIBLE",
            check_type_params={
                "attribute": "payment_method",
                "contextAttribute": "currency",
                "mode": "conditional_allowlist",
                "allowlists": [
                    {"contextValue": "USD", "allowedValues": ["card", "ach"], "caseSensitive": False},
                    {"contextValue": "EUR", "allowedValues": ["card", "sepa"], "caseSensitive": False},
                ],
            },
        ),
        intermediate_model=intermediate,
    )

    assert expectations == [
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "currency"},
            "meta": {},
        },
        {
            "expectation_type": "expect_column_values_to_be_in_set",
            "kwargs": {"column": "currency", "value_set": ["USD", "EUR"]},
            "meta": {},
        },
        {
            "expectation_type": "expect_column_values_to_be_in_set_for_other_column_value",
            "kwargs": {
                "column": "payment_method",
                "other_column": "currency",
                "other_value": "USD",
                "value_set": ["card", "ach"],
                "case_sensitive": False,
            },
            "meta": {},
        },
        {
            "expectation_type": "expect_column_values_to_be_in_set_for_other_column_value",
            "kwargs": {
                "column": "payment_method",
                "other_column": "currency",
                "other_value": "EUR",
                "value_set": ["card", "sepa"],
                "case_sensitive": False,
            },
            "meta": {},
        },
    ]


def test_build_gx_expectations_for_rule_merges_contextual_and_filter_row_conditions() -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-plausible-merge",
        rule_version_id="rv-plausible-merge",
        filter_expression="segment = 'VIP'",
    )

    expectations = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="PLAUSIBLE",
            check_type_params={
                "attribute": "amount",
                "contextAttribute": "country",
                "mode": "contextual_range",
                "ranges": [{"contextValue": "NL", "minValue": 0, "maxValue": 10, "inclusive": True}],
            },
        ),
        intermediate_model=intermediate,
    )

    assert expectations[2]["kwargs"]["row_condition"] == {
        "type": "and",
        "conditions": [
            {
                "type": "comparison",
                "column": {"name": "country"},
                "operator": "==",
                "parameter": "NL",
            },
            {
                "type": "comparison",
                "column": {"name": "segment"},
                "operator": "==",
                "parameter": "VIP",
            },
        ],
    }


def test_build_gx_expectations_for_rule_builds_native_threshold_expectation() -> None:
    expectations = build_gx_expectations_for_rule(
        rule=_rule(
            check_type="THRESHOLD",
            check_type_params={
                "attribute": "customer_email",
                "metric": "null_pct",
                "operator": "gte",
                "threshold": 95,
            },
        )
    )

    assert expectations == [
        {
            "expectation_type": "expect_column_proportion_of_non_null_values_to_be_between",
            "kwargs": {"column": "customer_email", "min_value": 0.95},
            "meta": {},
        }
    ]


def test_build_gx_expectations_for_rule_rejects_non_native_threshold_metric() -> None:
    with pytest.raises(GxExpectationBuildError, match="exact native GX aggregate mapping"):
        build_gx_expectations_for_rule(
            rule=_rule(
                check_type="THRESHOLD",
                check_type_params={
                    "attribute": "status",
                    "metric": "empty_pct",
                    "operator": "gte",
                    "threshold": 95,
                },
            )
        )


def test_build_gx_expectations_for_rule_covers_translator_unsupported_and_fallback_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gx_rule_expectations, "_TRANSLATOR_CHECK_TYPES", {"DERIVED"})
    monkeypatch.setattr(gx_rule_expectations, "_UNSUPPORTED_CHECK_TYPES", {"TRANSFER_ONLY"})
    monkeypatch.setattr(
        gx_rule_expectations,
        "_build_from_intermediate_model",
        lambda *, intermediate_model, rule_id, artifact_key: [
            {
                "expectation_type": "from_intermediate",
                "kwargs": {
                    "intermediate_model": dict(intermediate_model),
                    "rule_id": rule_id,
                    "artifact_key": artifact_key,
                },
                "meta": {},
            }
        ],
    )

    with pytest.raises(GxExpectationBuildError, match="without check_type_params"):
        build_gx_expectations_for_rule(rule=_rule(check_type="REGEX", check_type_params={}))

    with pytest.raises(GxExpectationBuildError, match="requires compiler intermediate model"):
        build_gx_expectations_for_rule(rule=_rule(check_type="DERIVED", check_type_params={"attribute": "status"}))

    built = build_gx_expectations_for_rule(
        rule=_rule(check_type="DERIVED", check_type_params={"attribute": "status"}),
        intermediate_model={"compiled": True},
        rule_id="rule-derived",
        artifact_key="artifact-derived",
    )
    assert built == [
        {
            "expectation_type": "from_intermediate",
            "kwargs": {
                "intermediate_model": {"compiled": True},
                "rule_id": "rule-derived",
                "artifact_key": "artifact-derived",
            },
            "meta": {},
        }
    ]

    with pytest.raises(GxExpectationBuildError, match="does not yet support TRANSFER_ONLY"):
        build_gx_expectations_for_rule(rule=_rule(check_type="TRANSFER_ONLY", check_type_params={"attribute": "status"}))

    with pytest.raises(GxExpectationBuildError, match="without a supported check type or compiler intermediate model"):
        build_gx_expectations_for_rule(rule=_rule(check_type="UNKNOWN", check_type_params={"attribute": "status"}))

    fallback = build_gx_expectations_for_rule(
        rule=_rule(check_type="UNKNOWN", check_type_params={"attribute": "status"}),
        intermediate_model={"fallback": True},
        rule_id="rule-fallback",
        artifact_key="artifact-fallback",
    )
    assert fallback[0]["kwargs"] == {
        "intermediate_model": {"fallback": True},
        "rule_id": "rule-fallback",
        "artifact_key": "artifact-fallback",
    }


def test_direct_helper_validation_branches_cover_threshold_regex_and_builder_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert gx_rule_expectations._build_meta(rule_id="rule-1", artifact_key="artifact-1") == {
        "dq.rule_id": "rule-1",
        "dq.artifact_key": "artifact-1",
    }
    assert gx_rule_expectations._build_meta(rule_id=None, artifact_key="artifact-1") == {"dq.artifact_key": "artifact-1"}
    assert gx_rule_expectations._unsupported_check_type_message("JOINED").startswith(
        "GX auto-publish does not yet support JOINED"
    )

    with pytest.raises(GxExpectationBuildError, match="No GX expectation builder"):
        gx_rule_expectations._build_direct_expectations(check_type="UNKNOWN", params={}, meta={})

    monkeypatch.setattr(gx_rule_expectations, "_build_regex_expectations", lambda *, params, meta: [])
    with pytest.raises(GxExpectationBuildError, match="produced no expectations"):
        gx_rule_expectations._build_direct_expectations(
            check_type="REGEX",
            params={"attribute": "customer_email", "pattern": ".+"},
            meta={},
        )

    assert gx_rule_expectations._threshold_ratio_bounds(operator="gt", ratio=0.95, metric="null_pct") == {
        "min_value": 0.95,
        "strict_min": True,
    }
    assert gx_rule_expectations._threshold_ratio_bounds(operator="lte", ratio=0.25, metric="null_pct") == {
        "max_value": 0.25
    }
    assert gx_rule_expectations._threshold_ratio_bounds(operator="lt", ratio=0.25, metric="null_pct") == {
        "max_value": 0.25,
        "strict_max": True,
    }
    with pytest.raises(GxExpectationBuildError, match="operator must be one of"):
        gx_rule_expectations._threshold_ratio_bounds(operator="eq", ratio=0.25, metric="null_pct")

    with pytest.raises(GxExpectationBuildError, match="requires 'threshold'"):
        gx_rule_expectations._require_threshold_ratio(params={}, metric="null_pct")
    with pytest.raises(GxExpectationBuildError, match="requires numeric 'threshold'"):
        gx_rule_expectations._require_threshold_ratio(params={"threshold": "abc"}, metric="null_pct")
    with pytest.raises(GxExpectationBuildError, match="between 0 and 100"):
        gx_rule_expectations._require_threshold_ratio(params={"threshold": 101}, metric="null_pct")

    assert gx_rule_expectations._normalize_regex_flags(" i m ", check_type="REGEX") == "im"
    with pytest.raises(GxExpectationBuildError, match="only supports regex flags"):
        gx_rule_expectations._normalize_regex_flags("ix", check_type="REGEX")
    assert gx_rule_expectations._compose_regex("abc", flags="im", exact=True) == "(?im)^(?:abc)$"
    assert gx_rule_expectations._compose_literal_set_regex(["A+B", "C"], case_sensitive=False) == "(?i)^(?:A\\+B|C)$"


def test_native_builder_variants_cover_range_allowlist_blocklist_and_present_paths() -> None:
    assert gx_rule_expectations._build_range_expectations(
        params={"attribute": "amount", "minValue": 1, "maxValue": 10, "inclusive": False},
        meta={"dq.rule_id": "rule-1"},
    ) == [
        {
            "expectation_type": "expect_column_values_to_be_between",
            "kwargs": {"column": "amount", "min_value": 1, "max_value": 10, "strict_min": True, "strict_max": True},
            "meta": {"dq.rule_id": "rule-1"},
        }
    ]
    with pytest.raises(GxExpectationBuildError, match="at least one of 'minValue' or 'maxValue'"):
        gx_rule_expectations._build_range_expectations(params={"attribute": "amount"}, meta={})

    assert gx_rule_expectations._build_allowlist_expectations(
        params={"attribute": "status", "allowedValues": ["ACTIVE", "PENDING"], "caseSensitive": True},
        meta={},
    ) == [
        {
            "expectation_type": "expect_column_values_to_be_in_set",
            "kwargs": {"column": "status", "value_set": ["ACTIVE", "PENDING"]},
            "meta": {},
        }
    ]
    assert gx_rule_expectations._build_blocklist_expectations(
        params={"attribute": "status", "blockedValues": ["UNKNOWN"], "caseSensitive": True},
        meta={},
    ) == [
        {
            "expectation_type": "expect_column_values_to_not_be_in_set",
            "kwargs": {"column": "status", "value_set": ["UNKNOWN"]},
            "meta": {},
        }
    ]

    assert gx_rule_expectations._build_present_expectations(params={"attribute": "status"}, meta={}) == [
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "status"},
            "meta": {},
        },
        {
            "expectation_type": "expect_column_values_to_not_match_regex",
            "kwargs": {"column": "status", "regex": r"^\s*$"},
            "meta": {},
        },
    ]
    assert gx_rule_expectations._build_present_expectations(
        params={"attribute": "status", "blockedValues": ["N/A"], "caseSensitive": True},
        meta={},
    )[2] == {
        "expectation_type": "expect_column_values_to_not_match_regex",
        "kwargs": {"column": "status", "regex": r"^(?:\s*(?:N/A)\s*)$"},
        "meta": {},
    }


def test_plausible_builders_cover_case_sensitive_and_validation_error_paths() -> None:
    conditional = gx_rule_expectations._build_plausible_expectations(
        params={
            "attribute": "payment_method",
            "contextAttribute": "currency",
            "mode": "conditional_allowlist",
            "allowlists": [{"contextValue": "USD", "allowedValues": ["CARD"], "caseSensitive": True}],
        },
        meta={},
    )
    assert conditional[2] == {
        "expectation_type": "expect_column_values_to_be_in_set_for_other_column_value",
        "kwargs": {
            "column": "payment_method",
            "other_column": "currency",
            "other_value": "USD",
            "value_set": ["CARD"],
            "case_sensitive": True,
        },
        "meta": {},
    }

    with pytest.raises(GxExpectationBuildError, match="contextual_range entries must be objects"):
        gx_rule_expectations._build_plausible_expectations(
            params={
                "attribute": "amount",
                "contextAttribute": "country",
                "mode": "contextual_range",
                "ranges": ["bad"],
            },
            meta={},
        )
    with pytest.raises(GxExpectationBuildError, match="at least one of 'minValue' or 'maxValue'"):
        gx_rule_expectations._build_plausible_expectations(
            params={
                "attribute": "amount",
                "contextAttribute": "country",
                "mode": "contextual_range",
                "ranges": [{"contextValue": "NL"}],
            },
            meta={},
        )
    with pytest.raises(GxExpectationBuildError, match="conditional_allowlist entries must be objects"):
        gx_rule_expectations._build_plausible_expectations(
            params={
                "attribute": "payment_method",
                "contextAttribute": "currency",
                "mode": "conditional_allowlist",
                "allowlists": ["bad"],
            },
            meta={},
        )
    with pytest.raises(GxExpectationBuildError, match="mode must be one of"):
        gx_rule_expectations._build_plausible_expectations(
            params={"attribute": "amount", "contextAttribute": "country", "mode": "mystery"},
            meta={},
        )


def test_uniqueness_and_comparison_helpers_cover_remaining_modes_and_errors() -> None:
    assert gx_rule_expectations._build_uniqueness_expectations(
        params={"attributes": ["customer_id"]},
        meta={},
    ) == [
        {
            "expectation_type": "expect_column_values_to_be_unique",
            "kwargs": {"column": "customer_id"},
            "meta": {},
        }
    ]
    with pytest.raises(GxExpectationBuildError, match="at least one non-empty attribute"):
        gx_rule_expectations._build_uniqueness_expectations(params={"attributes": [" ", ""]}, meta={})

    with pytest.raises(GxExpectationBuildError, match="non-empty right-side attribute"):
        gx_rule_expectations._rhs_column("   ")

    assert gx_rule_expectations._comparison_expectation(
        left_column="amount",
        right_column="rhs.amount",
        mode="numeric_tolerance",
        tolerance="0.5",
        meta={},
        check_type="CORRECT",
    ) == {
        "expectation_type": "expect_column_values_to_be_within_numeric_tolerance_of_other_column",
        "kwargs": {"column": "amount", "other_column": "rhs.amount", "tolerance": 0.5},
        "meta": {},
    }
    with pytest.raises(GxExpectationBuildError, match="require 'tolerance'"):
        gx_rule_expectations._comparison_expectation(
            left_column="amount",
            right_column="rhs.amount",
            mode="numeric_tolerance",
            tolerance=None,
            meta={},
            check_type="CORRECT",
        )
    with pytest.raises(GxExpectationBuildError, match="does not support comparison mode"):
        gx_rule_expectations._comparison_expectation(
            left_column="amount",
            right_column="rhs.amount",
            mode="approximate",
            tolerance=None,
            meta={},
            check_type="CORRECT",
        )


def test_cross_object_builders_cover_remaining_positive_and_fail_fast_paths() -> None:
    assert gx_rule_expectations._build_correct_expectations(
        params={
            "comparison": {
                "leftAttribute": "amount",
                "rightAttribute": "amount_rhs",
                "mode": "numeric_tolerance",
                "tolerance": 1,
            }
        },
        meta={},
    ) == [
        {
            "expectation_type": "expect_column_values_to_be_within_numeric_tolerance_of_other_column",
            "kwargs": {"column": "amount", "other_column": "rhs.amount_rhs", "tolerance": 1.0},
            "meta": {},
        }
    ]
    with pytest.raises(GxExpectationBuildError, match="requires 'comparison'"):
        gx_rule_expectations._build_correct_expectations(params={}, meta={})

    with pytest.raises(GxExpectationBuildError, match="comparisons entries must be objects"):
        gx_rule_expectations._build_reconcile_expectations(params={"comparisons": ["bad"]}, meta={})

    assert gx_rule_expectations._build_transfer_match_expectations(
        params={
            "mode": "payload_hash_match",
            "leftHashAttribute": "payload_hash",
            "rightHashAttribute": "payload_hash_rhs",
        },
        meta={},
    ) == [
        {
            "expectation_type": "expect_column_pair_values_to_be_equal",
            "kwargs": {"column_A": "payload_hash", "column_B": "rhs.payload_hash_rhs", "ignore_row_if": "neither"},
            "meta": {},
        }
    ]
    with pytest.raises(GxExpectationBuildError, match="comparisons entries must be objects"):
        gx_rule_expectations._build_transfer_match_expectations(
            params={"mode": "row_value_match", "comparisons": ["bad"]},
            meta={},
        )
    with pytest.raises(GxExpectationBuildError, match="does not support mode 'other'"):
        gx_rule_expectations._build_transfer_match_expectations(params={"mode": "other"}, meta={})

    with pytest.raises(GxExpectationBuildError, match="requires 'actualityDate'"):
        gx_rule_expectations._build_join_consistency_expectations(
            params={"comparisons": [{"leftAttribute": "a", "rightAttribute": "b"}]},
            meta={},
        )
    with pytest.raises(GxExpectationBuildError, match="comparisons entries must be objects"):
        gx_rule_expectations._build_join_consistency_expectations(
            params={"comparisons": ["bad"], "actualityDate": {}},
            meta={},
        )
    with pytest.raises(GxExpectationBuildError, match="requires resolvedToleranceValue and resolvedToleranceUnit"):
        gx_rule_expectations._build_join_consistency_expectations(
            params={
                "comparisons": [{"leftAttribute": "status", "rightAttribute": "status"}],
                "actualityDate": {"leftAttribute": "actuality_ts", "rightAttribute": "published_at"},
            },
            meta={},
        )

    with pytest.raises(GxExpectationBuildError, match="requires 'maxDaysOld'"):
        gx_rule_expectations._build_freshness_expectations(params={"attribute": "published_at"}, meta={})
    with pytest.raises(GxExpectationBuildError, match="only supports anchor='now'"):
        gx_rule_expectations._build_freshness_expectations(
            params={"attribute": "published_at", "maxDaysOld": 2, "anchor": "event"},
            meta={},
        )

    with pytest.raises(GxExpectationBuildError, match="requires 'maxHours'"):
        gx_rule_expectations._build_lag_expectations(
            params={"startAttribute": "created_at", "endAttribute": "published_at"},
            meta={},
        )

    assert gx_rule_expectations._build_future_date_expectations(
        params={"attribute": "event_ts"},
        meta={},
    ) == [
        {
            "expectation_type": "expect_column_values_to_not_be_in_future",
            "kwargs": {"column": "event_ts"},
            "meta": {},
        }
    ]


def test_build_gx_expectations_for_rule_reads_check_type_params_fallback_attribute() -> None:
    rule = SimpleNamespace(
        id="rule-fallback-params",
        checkType="REGEX",
        check_type_params=None,
        checkTypeParams={
            "attribute": "customer_email",
            "pattern": ".+@example.com",
            "flags": "i",
        },
    )

    expectations = build_gx_expectations_for_rule(rule=rule)

    assert expectations == [
        {
            "expectation_type": "expect_column_values_to_match_regex",
            "kwargs": {"column": "customer_email", "regex": "(?i).+@example.com"},
            "meta": {},
        }
    ]


def test_build_from_intermediate_model_uses_services_package_function(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[dict[str, object], str | None, str | None]] = []

    def fake_build(intermediate_model: dict[str, object], *, rule_id: str | None, artifact_key: str | None):
        calls.append((intermediate_model, rule_id, artifact_key))
        return [{"expectation_type": "from-service", "kwargs": {}, "meta": {}}]

    monkeypatch.setattr(application_services, "build_gx_expectations_from_intermediate_model", fake_build)

    built = gx_rule_expectations._build_from_intermediate_model(
        intermediate_model={"compiled": True},
        rule_id="rule-123",
        artifact_key="artifact-123",
    )

    assert built == [{"expectation_type": "from-service", "kwargs": {}, "meta": {}}]
    assert calls == [({"compiled": True}, "rule-123", "artifact-123")]


def test_direct_helpers_cover_missing_text_and_list_failures() -> None:
    with pytest.raises(GxExpectationBuildError, match="REGEX check type requires 'attribute'"):
        gx_rule_expectations._require_text({}, "attribute", check_type="REGEX")

    with pytest.raises(GxExpectationBuildError, match="ALLOWLIST check type requires a non-empty 'allowedValues' list"):
        gx_rule_expectations._require_list({}, "allowedValues", check_type="ALLOWLIST")


def test_native_builder_variants_cover_case_insensitive_allow_block_and_one_sided_ranges() -> None:
    assert gx_rule_expectations._build_range_expectations(
        params={"attribute": "amount", "minValue": 1},
        meta={},
    ) == [
        {
            "expectation_type": "expect_column_values_to_be_between",
            "kwargs": {"column": "amount", "min_value": 1},
            "meta": {},
        }
    ]
    assert gx_rule_expectations._build_range_expectations(
        params={"attribute": "amount", "maxValue": 10, "inclusive": False},
        meta={},
    ) == [
        {
            "expectation_type": "expect_column_values_to_be_between",
            "kwargs": {"column": "amount", "max_value": 10, "strict_max": True},
            "meta": {},
        }
    ]
    assert gx_rule_expectations._build_range_expectations(
        params={"attribute": "amount", "maxValue": 11, "inclusive": True},
        meta={},
    ) == [
        {
            "expectation_type": "expect_column_values_to_be_between",
            "kwargs": {"column": "amount", "max_value": 11},
            "meta": {},
        }
    ]

    assert gx_rule_expectations._build_allowlist_expectations(
        params={"attribute": "status", "allowedValues": ["ACTIVE", "PENDING"], "caseSensitive": False},
        meta={},
    ) == [
        {
            "expectation_type": "expect_column_values_to_match_regex",
            "kwargs": {"column": "status", "regex": "(?i)^(?:ACTIVE|PENDING)$"},
            "meta": {},
        }
    ]
    assert gx_rule_expectations._build_blocklist_expectations(
        params={"attribute": "status", "blockedValues": ["UNKNOWN"], "caseSensitive": False},
        meta={},
    ) == [
        {
            "expectation_type": "expect_column_values_to_not_match_regex",
            "kwargs": {"column": "status", "regex": "(?i)^(?:UNKNOWN)$"},
            "meta": {},
        }
    ]


def test_plausible_builders_cover_duplicate_context_and_one_sided_bounds() -> None:
    contextual = gx_rule_expectations._build_plausible_expectations(
        params={
            "attribute": "amount",
            "contextAttribute": "country",
            "mode": "contextual_range",
            "ranges": [
                {"contextValue": "NL", "minValue": 0, "inclusive": False},
                {"contextValue": "NL", "maxValue": 10, "inclusive": False},
            ],
        },
        meta={},
    )
    assert contextual[1] == {
        "expectation_type": "expect_column_values_to_be_in_set",
        "kwargs": {"column": "country", "value_set": ["NL"]},
        "meta": {},
    }
    assert contextual[2]["kwargs"] == {
        "column": "amount",
        "row_condition": {
            "type": "comparison",
            "column": {"name": "country"},
            "operator": "==",
            "parameter": "NL",
        },
        "min_value": 0,
        "strict_min": True,
    }
    assert contextual[3]["kwargs"] == {
        "column": "amount",
        "row_condition": {
            "type": "comparison",
            "column": {"name": "country"},
            "operator": "==",
            "parameter": "NL",
        },
        "max_value": 10,
        "strict_max": True,
    }

    conditional = gx_rule_expectations._build_plausible_expectations(
        params={
            "attribute": "payment_method",
            "contextAttribute": "currency",
            "mode": "conditional_allowlist",
            "allowlists": [
                {"contextValue": "USD", "allowedValues": ["card"], "caseSensitive": False},
                {"contextValue": "USD", "allowedValues": ["ach"], "caseSensitive": False},
            ],
        },
        meta={},
    )
    assert conditional[1] == {
        "expectation_type": "expect_column_values_to_be_in_set",
        "kwargs": {"column": "currency", "value_set": ["USD"]},
        "meta": {},
    }


def test_cross_object_builders_cover_positive_reconcile_and_transfer_row_value_paths() -> None:
    assert gx_rule_expectations._build_reconcile_expectations(
        params={
            "comparisons": [
                {"leftAttribute": "status", "rightAttribute": "status", "mode": "exact"},
                {"leftAttribute": "amount", "rightAttribute": "amount", "mode": "numeric_tolerance", "tolerance": 2},
            ]
        },
        meta={"dq.rule_id": "rule-1"},
    ) == [
        {
            "expectation_type": "expect_column_pair_values_to_be_equal",
            "kwargs": {"column_A": "status", "column_B": "rhs.status", "ignore_row_if": "neither"},
            "meta": {"dq.rule_id": "rule-1"},
        },
        {
            "expectation_type": "expect_column_values_to_be_within_numeric_tolerance_of_other_column",
            "kwargs": {"column": "amount", "other_column": "rhs.amount", "tolerance": 2.0},
            "meta": {"dq.rule_id": "rule-1"},
        },
    ]

    assert gx_rule_expectations._build_transfer_match_expectations(
        params={
            "mode": "row_value_match",
            "comparisons": [
                {"leftAttribute": "status", "rightAttribute": "status", "mode": "exact"},
                {"leftAttribute": "email", "rightAttribute": "email_rhs", "mode": "case_insensitive"},
            ],
        },
        meta={},
    ) == [
        {
            "expectation_type": "expect_column_pair_values_to_be_equal",
            "kwargs": {"column_A": "status", "column_B": "rhs.status", "ignore_row_if": "neither"},
            "meta": {},
        },
        {
            "expectation_type": "expect_column_values_to_equal_other_column_case_insensitive",
            "kwargs": {"column": "email", "other_column": "rhs.email_rhs"},
            "meta": {},
        },
    ]