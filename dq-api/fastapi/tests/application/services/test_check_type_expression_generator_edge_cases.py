from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.application.services import check_type_expression_generator as generator_module
from app.application.services.check_type_expression_generator import generate_expression_from_check_type


@dataclass
class _NoModelDumpPayload:
    value: str = "x"


def test_helper_functions_cover_basic_error_paths() -> None:
    with pytest.raises(ValueError, match="mapping-compatible"):
        generator_module._payload_dict(_NoModelDumpPayload())

    assert generator_module._quote_literal(True) == "true"
    assert generator_module._quote_literal(False) == "false"
    assert generator_module._quote_literal(12.5) == "12.5"
    assert generator_module._quote_literal("O'Brien") == "'O''Brien'"

    with pytest.raises(ValueError, match="Unknown operator"):
        generator_module._operator_symbol("bad")

    with pytest.raises(ValueError, match="condition.attribute and condition.value"):
        generator_module._build_simple_condition_clause({"value": "active"})

    with pytest.raises(ValueError, match="support only the 'equals' operator"):
        generator_module._build_simple_condition_clause(
            {"attribute": "status", "operator": "not_equals", "value": "active"}
        )

    with pytest.raises(ValueError, match="leftAttribute"):
        generator_module._build_join_clauses(
            [{"leftAttribute": "", "rightAttribute": "right_key"}],
            context_label="CORRECT",
        )

    with pytest.raises(ValueError, match="numeric_tolerance comparisons require 'tolerance'"):
        generator_module._build_cross_object_comparison_clause(
            {"leftAttribute": "left_value", "rightAttribute": "right_value", "mode": "numeric_tolerance"},
            context_label="CORRECT",
        )

    with pytest.raises(ValueError, match="comparison mode must be one of"):
        generator_module._build_cross_object_comparison_clause(
            {"leftAttribute": "left_value", "rightAttribute": "right_value", "mode": "approx"},
            context_label="CORRECT",
        )


def test_threshold_branch_and_quantile_validation_paths() -> None:
    assert generate_expression_from_check_type(
        "THRESHOLD",
        {
            "checkType": "THRESHOLD",
            "attribute": "status",
            "metric": "null_pct",
            "operator": "gte",
            "threshold": 95,
        },
    ) == "status IS NOT NULL"

    assert generate_expression_from_check_type(
        "THRESHOLD",
        {
            "checkType": "THRESHOLD",
            "attribute": "status",
            "metric": "empty_pct",
            "operator": "gte",
            "threshold": 95,
        },
    ) == "status IS NOT NULL AND TRIM(status) != ''"

    with pytest.raises(ValueError, match="operators gte and lte"):
        generate_expression_from_check_type(
            "THRESHOLD",
            {
                "checkType": "THRESHOLD",
                "attribute": "amount",
                "metric": "quantile",
                "operator": "gt",
                "threshold": 100,
                "quantile": 0.95,
            },
        )

    with pytest.raises(ValueError, match="numeric 'quantile'"):
        generate_expression_from_check_type(
            "THRESHOLD",
            {
                "checkType": "THRESHOLD",
                "attribute": "amount",
                "metric": "quantile",
                "operator": "lte",
                "threshold": 100,
                "quantile": "not-a-number",
            },
        )

    with pytest.raises(ValueError, match="between 0 and 1"):
        generate_expression_from_check_type(
            "THRESHOLD",
            {
                "checkType": "THRESHOLD",
                "attribute": "amount",
                "metric": "quantile",
                "operator": "lte",
                "threshold": 100,
                "quantile": 1.5,
            },
        )


def test_row_count_and_range_missing_values() -> None:
    with pytest.raises(ValueError, match="minValue' and 'maxValue'"):
        generate_expression_from_check_type(
            "ROW_COUNT",
            {
                "checkType": "ROW_COUNT",
                "operator": "between",
                "minValue": 10,
            },
        )

    with pytest.raises(ValueError, match="RANGE check requires 'attribute'"):
        generate_expression_from_check_type(
            "RANGE",
            {
                "checkType": "RANGE",
                "minValue": 0,
                "maxValue": 100,
            },
        )


def test_cross_object_generators_require_required_fields() -> None:
    with pytest.raises(ValueError, match="refDataObjectId"):
        generate_expression_from_check_type(
            "REFERENTIAL_INTEGRITY",
            {
                "checkType": "REFERENTIAL_INTEGRITY",
                "attribute": "customer_id",
                "refDataObjectVersionId": "customers-v3",
                "refAttribute": "id",
            },
        )

    with pytest.raises(ValueError, match="sourceDataObjectVersionId"):
        generate_expression_from_check_type(
            "CORRECT",
            {
                "checkType": "CORRECT",
                "referenceDataObjectVersionId": "exchange-v2",
                "joinKeys": [{"leftAttribute": "trade_id", "rightAttribute": "trade_id"}],
                "comparison": {"leftAttribute": "closing_price", "rightAttribute": "reference_price", "mode": "exact"},
            },
        )

    with pytest.raises(ValueError, match="comparison"):
        generate_expression_from_check_type(
            "CORRECT",
            {
                "checkType": "CORRECT",
                "sourceDataObjectVersionId": "prices-v1",
                "referenceDataObjectVersionId": "exchange-v2",
                "joinKeys": [{"leftAttribute": "trade_id", "rightAttribute": "trade_id"}],
                "comparison": "bad",
            },
        )

    with pytest.raises(ValueError, match="leftDataObjectVersionId"):
        generate_expression_from_check_type(
            "RECONCILE",
            {
                "checkType": "RECONCILE",
                "rightDataObjectVersionId": "reporting-v4",
                "joinKeys": [{"leftAttribute": "account_id", "rightAttribute": "account_id"}],
                "comparisons": [{"leftAttribute": "balance_amount", "rightAttribute": "reported_balance", "mode": "exact"}],
            },
        )

    with pytest.raises(ValueError, match="at least one entry in 'comparisons'"):
        generate_expression_from_check_type(
            "RECONCILE",
            {
                "checkType": "RECONCILE",
                "leftDataObjectVersionId": "ledger-v1",
                "rightDataObjectVersionId": "reporting-v4",
                "joinKeys": [{"leftAttribute": "account_id", "rightAttribute": "account_id"}],
                "comparisons": [],
            },
        )


def test_plausible_transfer_and_join_consistency_validation_paths() -> None:
    with pytest.raises(ValueError, match="contextAttribute"):
        generate_expression_from_check_type(
            "PLAUSIBLE",
            {
                "checkType": "PLAUSIBLE",
                "mode": "contextual_range",
                "attribute": "customer_age",
                "ranges": [{"contextValue": "youth", "minValue": 18, "maxValue": 25}],
            },
        )

    with pytest.raises(ValueError, match="conditional_allowlist mode requires at least one allowlist entry"):
        generate_expression_from_check_type(
            "PLAUSIBLE",
            {
                "checkType": "PLAUSIBLE",
                "mode": "conditional_allowlist",
                "attribute": "customer_tier",
                "contextAttribute": "product_type",
                "allowlists": [],
            },
        )

    with pytest.raises(ValueError, match="leftHashAttribute"):
        generate_expression_from_check_type(
            "TRANSFER_MATCH",
            {
                "checkType": "TRANSFER_MATCH",
                "mode": "payload_hash_match",
                "leftDataObjectVersionId": "landing-v1",
                "rightDataObjectVersionId": "warehouse-v2",
                "joinKeys": [{"leftAttribute": "file_name", "rightAttribute": "file_name"}],
            },
        )

    with pytest.raises(ValueError, match="mode must be one of"):
        generate_expression_from_check_type(
            "TRANSFER_MATCH",
            {
                "checkType": "TRANSFER_MATCH",
                "mode": "bad-mode",
                "leftDataObjectVersionId": "landing-v1",
                "rightDataObjectVersionId": "warehouse-v2",
                "joinKeys": [{"leftAttribute": "file_name", "rightAttribute": "file_name"}],
            },
        )

    with pytest.raises(ValueError, match="JOIN_CONSISTENCY check requires 'leftDataObjectVersionId'"):
        generate_expression_from_check_type(
            "JOIN_CONSISTENCY",
            {
                "checkType": "JOIN_CONSISTENCY",
                "rightDataObjectVersionId": "billing-v2",
                "joinKeys": [{"leftAttribute": "order_id", "rightAttribute": "order_id"}],
                "comparisons": [{"leftAttribute": "status", "rightAttribute": "status", "mode": "exact"}],
                "actualityDate": {
                    "leftAttribute": "actuality_ts",
                    "rightAttribute": "published_at",
                    "toleranceSource": "DELIVERY_CONTRACT",
                    "contractId": "contract-orders-billing",
                    "resolvedToleranceValue": 2,
                    "resolvedToleranceUnit": "hours",
                },
                "minMatchRate": 99.5,
            },
        )

    with pytest.raises(ValueError, match="resolvedToleranceUnit"):
        generate_expression_from_check_type(
            "JOIN_CONSISTENCY",
            {
                "checkType": "JOIN_CONSISTENCY",
                "leftDataObjectVersionId": "orders-v5",
                "rightDataObjectVersionId": "billing-v2",
                "joinKeys": [{"leftAttribute": "order_id", "rightAttribute": "order_id"}],
                "comparisons": [{"leftAttribute": "status", "rightAttribute": "status", "mode": "exact"}],
                "actualityDate": {
                    "leftAttribute": "actuality_ts",
                    "rightAttribute": "published_at",
                    "toleranceSource": "DELIVERY_CONTRACT",
                    "contractId": "contract-orders-billing",
                    "resolvedToleranceValue": 2,
                    "resolvedToleranceUnit": "weeks",
                },
                "minMatchRate": 99.5,
            },
        )