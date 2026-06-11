from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from dq_domain_validation import DomainValidationError
from dq_domain_validation import allowed_value_type
from dq_domain_validation import allowed_values
from dq_domain_validation import validate_allowed_value


def test_allowed_values_are_loaded_from_manifest() -> None:
    assert allowed_values("gx.source_override_format") == ("parquet", "delta")


def test_rule_check_type_metric_values_include_quantile() -> None:
    assert allowed_values("rule_check_type.metric") == ("null_pct", "empty_pct", "default_val_pct", "quantile")


def test_validate_allowed_value_trims_and_returns_canonical_value() -> None:
    assert validate_allowed_value("support.delivery_mode", " email ") == "email"


def test_validate_allowed_value_raises_for_invalid_value() -> None:
    with pytest.raises(DomainValidationError):
        validate_allowed_value("gx.source_override_format", "csv")


def test_allowed_value_type_integrates_with_pydantic() -> None:
    adapter = TypeAdapter(allowed_value_type("gx.source_override_format"))
    assert adapter.validate_python("delta") == "delta"

    with pytest.raises(ValidationError):
        adapter.validate_python("csv")
