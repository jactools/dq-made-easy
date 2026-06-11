from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from app.application.services.check_type_expression_generator import generate_expression_from_check_type
from app.application.services import check_type_expression_generator as generator_module
from app.domain.entities.rule_check_type import RuleCheckTypeParams


pytestmark = pytest.mark.usefixtures("monkeypatch")


def test_generate_regex_expression_without_flags() -> None:
    expression = generate_expression_from_check_type(
        "REGEX",
        {
            "checkType": "REGEX",
            "attribute": "customer_email",
            "pattern": "^[^@]+@[^@]+\\.[^@]+$",
        },
    )

    assert expression == "REGEXP_MATCHES(customer_email, '^[^@]+@[^@]+\\.[^@]+$')"


def test_generate_regex_expression_with_flags() -> None:
    expression = generate_expression_from_check_type(
        "REGEX",
        {
            "checkType": "REGEX",
            "attribute": "customer_email",
            "pattern": "^[a-z0-9._%+-]+@[a-z0-9.-]+\\.[a-z]{2,}$",
            "flags": "i",
        },
    )

    assert expression == (
        "REGEXP_MATCHES(customer_email, '^[a-z0-9._%+-]+@[a-z0-9.-]+\\.[a-z]{2,}$', 'i')"
    )


def test_generate_regex_expression_requires_attribute() -> None:
    with pytest.raises(ValueError, match="REGEX check requires 'attribute'"):
        generate_expression_from_check_type(
            "REGEX",
            {
                "checkType": "REGEX",
                "pattern": "^X+$",
            },
        )


def test_generate_regex_expression_requires_pattern() -> None:
    with pytest.raises(ValueError, match="REGEX check requires 'pattern'"):
        generate_expression_from_check_type(
            "REGEX",
            {
                "checkType": "REGEX",
                "attribute": "status_code",
            },
        )


def test_generate_range_expression_inclusive_bounds() -> None:
    expression = generate_expression_from_check_type(
        "RANGE",
        {
            "checkType": "RANGE",
            "attribute": "order_amount",
            "minValue": 0,
            "maxValue": 100,
            "inclusive": True,
        },
    )

    assert expression == "order_amount >= 0 AND order_amount <= 100"


def test_generate_range_expression_exclusive_bounds() -> None:
    expression = generate_expression_from_check_type(
        "RANGE",
        {
            "checkType": "RANGE",
            "attribute": "order_amount",
            "minValue": 0,
            "maxValue": 100,
            "inclusive": False,
        },
    )

    assert expression == "order_amount > 0 AND order_amount < 100"


def test_generate_range_expression_with_only_minimum() -> None:
    expression = generate_expression_from_check_type(
        "RANGE",
        {
            "checkType": "RANGE",
            "attribute": "order_amount",
            "minValue": 0,
        },
    )

    assert expression == "order_amount >= 0"


def test_generate_range_expression_with_only_maximum() -> None:
    expression = generate_expression_from_check_type(
        "RANGE",
        {
            "checkType": "RANGE",
            "attribute": "order_amount",
            "maxValue": 100,
        },
    )

    assert expression == "order_amount <= 100"


def test_generate_range_expression_requires_at_least_one_bound() -> None:
    with pytest.raises(ValueError, match="RANGE check requires at least one"):
        generate_expression_from_check_type(
            "RANGE",
            {
                "checkType": "RANGE",
                "attribute": "order_amount",
            },
        )


def test_generate_range_expression_preserves_float_literals() -> None:
    expression = generate_expression_from_check_type(
        "RANGE",
        {
            "checkType": "RANGE",
            "attribute": "order_amount",
            "minValue": 0.0,
            "maxValue": 100.0,
            "inclusive": True,
        },
    )

    assert expression == "order_amount >= 0.0 AND order_amount <= 100.0"


def test_generate_range_expression_supports_lexical_bounds() -> None:
    expression = generate_expression_from_check_type(
        "RANGE",
        {
            "checkType": "RANGE",
            "attribute": "grade_code",
            "minValue": "A",
            "maxValue": "F",
            "inclusive": True,
        },
    )

    assert expression == "grade_code >= 'A' AND grade_code <= 'F'"


def test_generate_allowlist_expression_case_insensitive() -> None:
    expression = generate_expression_from_check_type(
        "ALLOWLIST",
        {
            "checkType": "ALLOWLIST",
            "attribute": "country_code",
            "allowedValues": ["US", "NL"],
            "caseSensitive": False,
        },
    )

    assert expression == "LOWER(country_code) IN ('us', 'nl')"


def test_generate_allowlist_expression_case_sensitive() -> None:
    expression = generate_expression_from_check_type(
        "ALLOWLIST",
        {
            "checkType": "ALLOWLIST",
            "attribute": "country_code",
            "allowedValues": ["US", "NL"],
            "caseSensitive": True,
        },
    )

    assert expression == "country_code IN ('US', 'NL')"


def test_generate_allowlist_expression_requires_attribute() -> None:
    with pytest.raises(ValueError, match="ALLOWLIST check requires 'attribute'"):
        generate_expression_from_check_type(
            "ALLOWLIST",
            {
                "checkType": "ALLOWLIST",
                "allowedValues": ["US"],
            },
        )


def test_generate_allowlist_expression_requires_values() -> None:
    with pytest.raises(ValueError, match="ALLOWLIST check requires at least one"):
        generate_expression_from_check_type(
            "ALLOWLIST",
            {
                "checkType": "ALLOWLIST",
                "attribute": "country_code",
                "allowedValues": [],
            },
        )


def test_generate_blocklist_expression_case_sensitive() -> None:
    expression = generate_expression_from_check_type(
        "BLOCKLIST",
        {
            "checkType": "BLOCKLIST",
            "attribute": "status",
            "blockedValues": ["DELETED", "ARCHIVED"],
            "caseSensitive": True,
        },
    )

    assert expression == "status NOT IN ('DELETED', 'ARCHIVED')"


def test_generate_blocklist_expression_case_insensitive() -> None:
    expression = generate_expression_from_check_type(
        "BLOCKLIST",
        {
            "checkType": "BLOCKLIST",
            "attribute": "status",
            "blockedValues": ["DELETED", "ARCHIVED"],
            "caseSensitive": False,
        },
    )

    assert expression == "LOWER(status) NOT IN ('deleted', 'archived')"


def test_generate_blocklist_expression_requires_attribute() -> None:
    with pytest.raises(ValueError, match="BLOCKLIST check requires 'attribute'"):
        generate_expression_from_check_type(
            "BLOCKLIST",
            {
                "checkType": "BLOCKLIST",
                "blockedValues": ["DELETED"],
            },
        )


def test_generate_blocklist_expression_requires_values() -> None:
    with pytest.raises(ValueError, match="BLOCKLIST check requires at least one"):
        generate_expression_from_check_type(
            "BLOCKLIST",
            {
                "checkType": "BLOCKLIST",
                "attribute": "status",
                "blockedValues": [],
            },
        )


def test_generate_uniqueness_expression() -> None:
    expression = generate_expression_from_check_type(
        "UNIQUENESS",
        {
            "checkType": "UNIQUENESS",
            "attributes": ["customer_id", "order_date"],
        },
    )

    assert expression == "COUNT(*) OVER (PARTITION BY customer_id, order_date) = 1"


def test_generate_uniqueness_expression_single_attribute() -> None:
    expression = generate_expression_from_check_type(
        "UNIQUENESS",
        {
            "checkType": "UNIQUENESS",
            "attributes": ["email"],
        },
    )

    assert expression == "COUNT(*) OVER (PARTITION BY email) = 1"


def test_generate_row_count_expression() -> None:
    expression = generate_expression_from_check_type(
        "ROW_COUNT",
        {
            "checkType": "ROW_COUNT",
            "operator": "gte",
            "threshold": 25,
        },
    )

    assert expression == "1 = 1"


def test_generate_row_count_expression_requires_threshold() -> None:
    with pytest.raises(ValueError, match="ROW_COUNT check requires 'threshold'"):
        generate_expression_from_check_type(
            "ROW_COUNT",
            {
                "checkType": "ROW_COUNT",
                "operator": "gte",
            },
        )


def test_generate_uniqueness_expression_requires_attributes() -> None:
    with pytest.raises(ValueError, match="UNIQUENESS check requires at least one entry"):
        generate_expression_from_check_type(
            "UNIQUENESS",
            {
                "checkType": "UNIQUENESS",
                "attributes": [],
            },
        )


def test_generate_referential_integrity_expression() -> None:
    expression = generate_expression_from_check_type(
        "REFERENTIAL_INTEGRITY",
        {
            "checkType": "REFERENTIAL_INTEGRITY",
            "attribute": "customer_id",
            "refDataObjectId": "customers",
            "refDataObjectVersionId": "customers-v3",
            "refAttribute": "id",
        },
    )

    assert expression == "customer_id IN (SELECT id FROM customers)"


def test_generate_referential_integrity_expression_requires_version_id() -> None:
    with pytest.raises(ValueError, match="REFERENTIAL_INTEGRITY check requires 'refDataObjectVersionId'"):
        generate_expression_from_check_type(
            "REFERENTIAL_INTEGRITY",
            {
                "checkType": "REFERENTIAL_INTEGRITY",
                "attribute": "customer_id",
                "refDataObjectId": "customers",
                "refAttribute": "id",
            },
        )


def test_generate_freshness_expression() -> None:
    expression = generate_expression_from_check_type(
        "FRESHNESS",
        {
            "checkType": "FRESHNESS",
            "attribute": "updated_at",
            "maxDaysOld": 3,
            "anchor": "processing_date",
        },
    )

    assert expression == "DATEDIFF(CURRENT_DATE, updated_at) <= 3"


def test_generate_freshness_expression_requires_attribute() -> None:
    with pytest.raises(ValueError, match="FRESHNESS check requires 'attribute'"):
        generate_expression_from_check_type(
            "FRESHNESS",
            {
                "checkType": "FRESHNESS",
                "maxDaysOld": 3,
                "anchor": "processing_date",
            },
        )


def test_generate_freshness_expression_requires_max_days_old() -> None:
    with pytest.raises(ValueError, match="FRESHNESS check requires 'maxDaysOld'"):
        generate_expression_from_check_type(
            "FRESHNESS",
            {
                "checkType": "FRESHNESS",
                "attribute": "updated_at",
            },
        )


def test_generate_lag_expression() -> None:
    expression = generate_expression_from_check_type(
        "LAG",
        {
            "checkType": "LAG",
            "startAttribute": "created_at",
            "endAttribute": "processed_at",
            "maxHours": 24,
        },
    )

    assert expression == "TIMESTAMPDIFF(HOUR, created_at, processed_at) <= 24"


def test_generate_lag_expression_requires_start_attribute() -> None:
    with pytest.raises(ValueError, match="LAG check requires 'startAttribute'"):
        generate_expression_from_check_type(
            "LAG",
            {
                "checkType": "LAG",
                "endAttribute": "processed_at",
                "maxHours": 24,
            },
        )


def test_generate_lag_expression_requires_end_attribute() -> None:
    with pytest.raises(ValueError, match="LAG check requires 'endAttribute'"):
        generate_expression_from_check_type(
            "LAG",
            {
                "checkType": "LAG",
                "startAttribute": "created_at",
                "maxHours": 24,
            },
        )


def test_generate_lag_expression_requires_max_hours() -> None:
    with pytest.raises(ValueError, match="LAG check requires 'maxHours'"):
        generate_expression_from_check_type(
            "LAG",
            {
                "checkType": "LAG",
                "startAttribute": "created_at",
                "endAttribute": "processed_at",
            },
        )


def test_generate_future_date_expression_with_reference_date() -> None:
    expression = generate_expression_from_check_type(
        "FUTURE_DATE",
        {
            "checkType": "FUTURE_DATE",
            "attribute": "event_date",
            "referenceDate": "2026-03-20",
        },
    )

    assert expression == "event_date <= '2026-03-20'"


def test_generate_future_date_expression_without_reference_date() -> None:
    expression = generate_expression_from_check_type(
        "FUTURE_DATE",
        {
            "checkType": "FUTURE_DATE",
            "attribute": "event_date",
        },
    )

    assert expression == "event_date <= NOW()"


def test_generate_future_date_expression_requires_attribute() -> None:
    with pytest.raises(ValueError, match="FUTURE_DATE check requires 'attribute'"):
        generate_expression_from_check_type(
            "FUTURE_DATE",
            {
                "checkType": "FUTURE_DATE",
            },
        )


def test_present_params_validate_and_generate_expression() -> None:
    adapter = TypeAdapter(RuleCheckTypeParams)

    params = adapter.validate_python(
        {
            "checkType": "PRESENT",
            "attribute": "customer_name",
            "blockedValues": ["UNKNOWN", "N/A"],
            "caseSensitive": False,
        }
    )

    assert params.checkType == "PRESENT"
    expression = generate_expression_from_check_type("PRESENT", params)
    assert expression == (
        "customer_name IS NOT NULL AND TRIM(customer_name) != '' "
        "AND LOWER(TRIM(customer_name)) NOT IN ('unknown', 'n/a')"
    )


def test_correct_params_require_numeric_tolerance_and_generate_expression() -> None:
    adapter = TypeAdapter(RuleCheckTypeParams)

    with pytest.raises(ValueError, match="numeric_tolerance"):
        adapter.validate_python(
            {
                "checkType": "CORRECT",
                "sourceDataObjectVersionId": "prices-v1",
                "referenceDataObjectVersionId": "exchange-v2",
                "joinKeys": [{"leftAttribute": "trade_id", "rightAttribute": "trade_id"}],
                "comparison": {
                    "leftAttribute": "closing_price",
                    "rightAttribute": "reference_price",
                    "mode": "numeric_tolerance",
                },
            }
        )

    params = adapter.validate_python(
        {
            "checkType": "CORRECT",
            "sourceDataObjectVersionId": "prices-v1",
            "referenceDataObjectVersionId": "exchange-v2",
            "joinKeys": [{"leftAttribute": "trade_id", "rightAttribute": "trade_id"}],
            "comparison": {
                "leftAttribute": "closing_price",
                "rightAttribute": "reference_price",
                "mode": "numeric_tolerance",
                "tolerance": 0.01,
            },
        }
    )

    expression = generate_expression_from_check_type("CORRECT", params)
    assert expression == "trade_id = rhs.trade_id AND ABS(closing_price - rhs.reference_price) <= 0.01"


def test_generate_reconcile_expression() -> None:
    expression = generate_expression_from_check_type(
        "RECONCILE",
        {
            "checkType": "RECONCILE",
            "leftDataObjectVersionId": "ledger-v1",
            "rightDataObjectVersionId": "reporting-v4",
            "joinKeys": [{"leftAttribute": "account_id", "rightAttribute": "account_id"}],
            "comparisons": [
                {
                    "leftAttribute": "balance_amount",
                    "rightAttribute": "reported_balance",
                    "mode": "numeric_tolerance",
                    "tolerance": 0.01,
                },
                {
                    "leftAttribute": "currency_code",
                    "rightAttribute": "currency_code",
                    "mode": "exact",
                },
            ],
        },
    )

    assert expression == (
        "account_id = rhs.account_id AND ABS(balance_amount - rhs.reported_balance) <= 0.01 "
        "AND currency_code = rhs.currency_code"
    )


def test_plausible_params_validate_mode_specific_payloads() -> None:
    adapter = TypeAdapter(RuleCheckTypeParams)

    params = adapter.validate_python(
        {
            "checkType": "PLAUSIBLE",
            "mode": "contextual_range",
            "attribute": "customer_age",
            "contextAttribute": "segment",
            "ranges": [
                {"contextValue": "youth", "minValue": 18, "maxValue": 25},
                {"contextValue": "adult", "minValue": 26, "maxValue": 70},
            ],
        }
    )

    expression = generate_expression_from_check_type("PLAUSIBLE", params)
    assert expression == (
        "(segment = 'youth' AND customer_age >= 18.0 AND customer_age <= 25.0) OR "
        "(segment = 'adult' AND customer_age >= 26.0 AND customer_age <= 70.0)"
    )

    with pytest.raises(ValueError, match="conditional_allowlist"):
        adapter.validate_python(
            {
                "checkType": "PLAUSIBLE",
                "mode": "conditional_allowlist",
                "attribute": "customer_tier",
                "contextAttribute": "product_type",
                "ranges": [{"contextValue": "loan", "minValue": 1}],
            }
        )


def test_generate_plausible_conditional_allowlist_expression() -> None:
    expression = generate_expression_from_check_type(
        "PLAUSIBLE",
        {
            "checkType": "PLAUSIBLE",
            "mode": "conditional_allowlist",
            "attribute": "customer_tier",
            "contextAttribute": "product_type",
            "allowlists": [
                {
                    "contextValue": "mortgage",
                    "allowedValues": ["gold", "platinum"],
                    "caseSensitive": False,
                }
            ],
        },
    )

    assert expression == "(product_type = 'mortgage' AND LOWER(customer_tier) IN ('gold', 'platinum'))"


def test_generate_present_expression_with_simple_condition() -> None:
    expression = generate_expression_from_check_type(
        "PRESENT",
        {
            "checkType": "PRESENT",
            "attribute": "email_address",
            "condition": {
                "attribute": "customer_status",
                "operator": "equals",
                "value": "active",
            },
        },
    )

    assert expression == (
        "(customer_status = 'active' AND (email_address IS NOT NULL AND TRIM(email_address) != '')) "
        "OR NOT (customer_status = 'active')"
    )


def test_generate_regex_expression_with_simple_condition_and_required_presence() -> None:
    expression = generate_expression_from_check_type(
        "REGEX",
        {
            "checkType": "REGEX",
            "attribute": "ssn",
            "pattern": r"^\d{3}-\d{2}-\d{4}$",
            "requirePresent": True,
            "condition": {
                "attribute": "customer_segment",
                "operator": "equals",
                "value": "Retail",
            },
        },
    )

    assert expression == (
        "(customer_segment = 'Retail' AND (ssn IS NOT NULL AND TRIM(ssn) != '' AND "
        "REGEXP_MATCHES(ssn, '^\\d{3}-\\d{2}-\\d{4}$'))) OR NOT (customer_segment = 'Retail')"
    )


def test_transfer_match_params_validate_and_generate_payload_hash_expression() -> None:
    adapter = TypeAdapter(RuleCheckTypeParams)

    with pytest.raises(ValueError, match="leftHashAttribute"):
        adapter.validate_python(
            {
                "checkType": "TRANSFER_MATCH",
                "mode": "payload_hash_match",
                "leftDataObjectVersionId": "landing-v1",
                "rightDataObjectVersionId": "warehouse-v2",
                "joinKeys": [{"leftAttribute": "file_name", "rightAttribute": "file_name"}],
            }
        )

    params = adapter.validate_python(
        {
            "checkType": "TRANSFER_MATCH",
            "mode": "payload_hash_match",
            "leftDataObjectVersionId": "landing-v1",
            "rightDataObjectVersionId": "warehouse-v2",
            "joinKeys": [{"leftAttribute": "file_name", "rightAttribute": "file_name"}],
            "leftHashAttribute": "payload_hash",
            "rightHashAttribute": "target_payload_hash",
        }
    )

    expression = generate_expression_from_check_type("TRANSFER_MATCH", params)
    assert expression == "file_name = rhs.file_name AND payload_hash = rhs.target_payload_hash"


def test_join_consistency_params_validate_nested_contract_payload() -> None:
    adapter = TypeAdapter(RuleCheckTypeParams)

    params = adapter.validate_python(
        {
            "checkType": "JOIN_CONSISTENCY",
            "leftDataObjectVersionId": "orders-v5",
            "rightDataObjectVersionId": "billing-v2",
            "joinKeys": [
                {
                    "leftAttribute": "order_id",
                    "rightAttribute": "order_id",
                }
            ],
            "comparisons": [
                {
                    "leftAttribute": "customer_email",
                    "rightAttribute": "email_address",
                    "mode": "case_insensitive",
                }
            ],
            "actualityDate": {
                "leftAttribute": "actuality_ts",
                "rightAttribute": "published_at",
                "toleranceSource": "DELIVERY_CONTRACT",
                "contractId": "contract-orders-billing",
                "resolvedToleranceValue": 2,
                "resolvedToleranceUnit": "hours",
            },
            "minMatchRate": 99.5,
        }
    )

    assert params.checkType == "JOIN_CONSISTENCY"
    assert params.actualityDate.contractId == "contract-orders-billing"
    assert params.comparisons[0].mode == "case_insensitive"


def test_join_consistency_params_require_paired_override_fields() -> None:
    adapter = TypeAdapter(RuleCheckTypeParams)

    with pytest.raises(ValueError, match="overrideToleranceValue"):
        adapter.validate_python(
            {
                "checkType": "JOIN_CONSISTENCY",
                "leftDataObjectVersionId": "orders-v5",
                "rightDataObjectVersionId": "billing-v2",
                "joinKeys": [
                    {
                        "leftAttribute": "order_id",
                        "rightAttribute": "order_id",
                    }
                ],
                "comparisons": [
                    {
                        "leftAttribute": "status",
                        "rightAttribute": "status",
                        "mode": "exact",
                    }
                ],
                "actualityDate": {
                    "leftAttribute": "actuality_ts",
                    "rightAttribute": "published_at",
                    "toleranceSource": "DELIVERY_CONTRACT",
                    "contractId": "contract-orders-billing",
                    "overrideToleranceValue": 2,
                },
                "minMatchRate": 99,
            }
        )


def test_generate_join_consistency_expression() -> None:
    expression = generate_expression_from_check_type(
        "JOIN_CONSISTENCY",
        {
            "checkType": "JOIN_CONSISTENCY",
            "leftDataObjectVersionId": "orders-v5",
            "rightDataObjectVersionId": "billing-v2",
            "joinKeys": [
                {
                    "leftAttribute": "order_id",
                    "rightAttribute": "order_id",
                }
            ],
            "comparisons": [
                {
                    "leftAttribute": "status",
                    "rightAttribute": "status",
                    "mode": "exact",
                },
                {
                    "leftAttribute": "customer_email",
                    "rightAttribute": "email_address",
                    "mode": "case_insensitive",
                },
            ],
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

    assert expression == (
        "order_id = rhs.order_id AND "
        "status = rhs.status AND "
        "LOWER(customer_email) = LOWER(rhs.email_address) AND "
        "ABS(TIMESTAMPDIFF(HOUR, actuality_ts, rhs.published_at)) <= 2"
    )


def test_generate_join_consistency_expression_requires_resolved_tolerance() -> None:
    with pytest.raises(ValueError, match="resolvedToleranceValue"):
        generate_expression_from_check_type(
            "JOIN_CONSISTENCY",
            {
                "checkType": "JOIN_CONSISTENCY",
                "leftDataObjectVersionId": "orders-v5",
                "rightDataObjectVersionId": "billing-v2",
                "joinKeys": [
                    {
                        "leftAttribute": "order_id",
                        "rightAttribute": "order_id",
                    }
                ],
                "comparisons": [
                    {
                        "leftAttribute": "status",
                        "rightAttribute": "status",
                        "mode": "exact",
                    }
                ],
                "actualityDate": {
                    "leftAttribute": "actuality_ts",
                    "rightAttribute": "published_at",
                    "toleranceSource": "DELIVERY_CONTRACT",
                    "contractId": "contract-orders-billing",
                    "resolvedToleranceUnit": "hours",
                },
                "minMatchRate": 99.5,
            },
        )


def test_generate_join_consistency_expression_requires_join_keys() -> None:
    with pytest.raises(ValueError, match="at least one entry in 'joinKeys'"):
        generate_expression_from_check_type(
            "JOIN_CONSISTENCY",
            {
                "checkType": "JOIN_CONSISTENCY",
                "leftDataObjectVersionId": "orders-v5",
                "rightDataObjectVersionId": "billing-v2",
                "joinKeys": [],
                "comparisons": [
                    {
                        "leftAttribute": "status",
                        "rightAttribute": "status",
                        "mode": "exact",
                    }
                ],
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


def test_generate_unknown_check_type_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown checkType"):
        generate_expression_from_check_type("SOMETHING_ELSE", {})


def test_threshold_metric_variants_and_invalid_operator_paths() -> None:
    default_val = generate_expression_from_check_type(
        "THRESHOLD",
        {
            "checkType": "THRESHOLD",
            "attribute": "status",
            "metric": "default_val_pct",
            "operator": "gte",
            "threshold": 95,
            "expectedValue": "UNKNOWN",
        },
    )
    assert default_val == "status IS NOT NULL AND status != 'UNKNOWN'"

    with pytest.raises(ValueError, match="Unknown THRESHOLD metric"):
        generate_expression_from_check_type(
            "THRESHOLD",
            {
                "checkType": "THRESHOLD",
                "attribute": "status",
                "metric": "not-a-metric",
                "operator": "gte",
                "threshold": 95,
            },
        )

    with pytest.raises(ValueError, match="Unknown operator"):
        generate_expression_from_check_type(
            "THRESHOLD",
            {
                "checkType": "THRESHOLD",
                "attribute": "status",
                "metric": "null_pct",
                "operator": "bad-op",
                "threshold": 95,
            },
        )


def test_generate_quantile_threshold_expression() -> None:
    expression = generate_expression_from_check_type(
        "THRESHOLD",
        {
            "checkType": "THRESHOLD",
            "attribute": "amount",
            "metric": "quantile",
            "operator": "lte",
            "threshold": 100,
            "quantile": 0.95,
        },
    )

    assert expression == "1 = 1"


def test_generate_quantile_threshold_expression_requires_quantile() -> None:
    with pytest.raises(ValueError, match="requires 'quantile'"):
        generate_expression_from_check_type(
            "THRESHOLD",
            {
                "checkType": "THRESHOLD",
                "attribute": "amount",
                "metric": "quantile",
                "operator": "lte",
                "threshold": 100,
            },
        )


def test_freshness_anchor_now_and_current_date_paths() -> None:
    now_expr = generate_expression_from_check_type(
        "FRESHNESS",
        {
            "checkType": "FRESHNESS",
            "attribute": "updated_at",
            "maxDaysOld": 3,
            "anchor": "now",
        },
    )
    assert now_expr == "DATEDIFF(NOW(), updated_at) <= 3"

    current_date_expr = generate_expression_from_check_type(
        "FRESHNESS",
        {
            "checkType": "FRESHNESS",
            "attribute": "updated_at",
            "maxDaysOld": 3,
            "anchor": "processing_date",
        },
    )
    assert current_date_expr == "DATEDIFF(CURRENT_DATE, updated_at) <= 3"


def test_join_consistency_requires_valid_unit_and_comparison_mode() -> None:
    base = {
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
            "resolvedToleranceUnit": "hours",
        },
        "minMatchRate": 99.5,
    }

    with pytest.raises(ValueError, match="resolvedToleranceUnit"):
        generate_expression_from_check_type(
            "JOIN_CONSISTENCY",
            {
                **base,
                "actualityDate": {
                    **base["actualityDate"],
                    "resolvedToleranceUnit": "weeks",
                },
            },
        )

    with pytest.raises(ValueError, match="comparison mode"):
        generate_expression_from_check_type(
            "JOIN_CONSISTENCY",
            {
                **base,
                "comparisons": [
                    {
                        "leftAttribute": "status",
                        "rightAttribute": "status",
                        "mode": "approx",
                    }
                ],
            },
        )


def test_join_consistency_requires_actuality_date_dict_and_join_key_attributes() -> None:
    with pytest.raises(ValueError, match="requires 'actualityDate'"):
        generate_expression_from_check_type(
            "JOIN_CONSISTENCY",
            {
                "checkType": "JOIN_CONSISTENCY",
                "leftDataObjectVersionId": "orders-v5",
                "rightDataObjectVersionId": "billing-v2",
                "joinKeys": [{"leftAttribute": "order_id", "rightAttribute": "order_id"}],
                "comparisons": [{"leftAttribute": "status", "rightAttribute": "status", "mode": "exact"}],
                "actualityDate": "bad",
                "minMatchRate": 99,
            },
        )

    with pytest.raises(ValueError, match="joinKeys entries require"):
        generate_expression_from_check_type(
            "JOIN_CONSISTENCY",
            {
                "checkType": "JOIN_CONSISTENCY",
                "leftDataObjectVersionId": "orders-v5",
                "rightDataObjectVersionId": "billing-v2",
                "joinKeys": [{"leftAttribute": "", "rightAttribute": "order_id"}],
                "comparisons": [{"leftAttribute": "status", "rightAttribute": "status", "mode": "exact"}],
                "actualityDate": {
                    "leftAttribute": "actuality_ts",
                    "rightAttribute": "published_at",
                    "toleranceSource": "DELIVERY_CONTRACT",
                    "contractId": "contract-orders-billing",
                    "resolvedToleranceValue": 2,
                    "resolvedToleranceUnit": "hours",
                },
                "minMatchRate": 99,
            },
        )


def test_dispatcher_threshold_override_and_helper_functions() -> None:
    expr = generate_expression_from_check_type(
        "threshold",
        {
            "checkType": "THRESHOLD",
            "attribute": "status",
            "metric": "default_val_pct",
            "operator": "gte",
            "threshold": 95,
            "expectedValue": "N/A",
        },
        threshold_override=91,
    )
    assert expr == "status IS NOT NULL AND status != 'N/A'"

    assert generator_module._quote_values(["A", "B"], case_sensitive=True) == "'A', 'B'"
    assert generator_module._quote_values(["A", "B"], case_sensitive=False) == "'a', 'b'"
    assert generator_module._operator_symbol("gte") == ">="
    assert generator_module._join_consistency_tolerance_unit("days") == "DAY"
