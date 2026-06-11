import math
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.application.presenters import build_rules_page_payload
from app.domain.entities import rule_policy as rules_mod


def test_normalize_rule_name():
    assert rules_mod.normalize_rule_name(None) == ""
    assert rules_mod.normalize_rule_name("  MyRule  ") == "myrule"


def test_read_row_field_dict_and_object_attributes():
    row = {"keyOne": "v1"}
    assert rules_mod.read_row_field(row, "keyOne") == "v1"

    obj = SimpleNamespace()
    obj.MyKey = "exact"
    assert rules_mod.read_row_field(obj, "MyKey") == "exact"

    obj2 = SimpleNamespace(my_key="snake")
    assert rules_mod.read_row_field(obj2, "MyKey") == "snake"

    obj3 = SimpleNamespace()
    assert rules_mod.read_row_field(obj3, "Missing") is None


def test_require_workspace_ok_and_missing():
    assert rules_mod.require_workspace(None, " ", "ws-a") == "ws-a"
    with pytest.raises(HTTPException):
        rules_mod.require_workspace(None, "", "  ")


def test_paginate_basic():
    rows = [{"id": i} for i in range(1, 6)]
    out = build_rules_page_payload(rows, page=1, limit=2)
    assert out["pagination"]["total"] == 5
    assert out["pagination"]["total_pages"] == math.ceil(5 / 2)
    assert len(out["data"]) == 2

    out2 = build_rules_page_payload(rows, page=100, limit=100)
    assert out2["data"] == []
    assert out2["pagination"]["total_pages"] == 1


def test_parse_check_type_params_variants():
    assert rules_mod.parse_check_type_params(None) is None
    assert rules_mod.parse_check_type_params({"a": 1}) == {"a": 1}
    assert rules_mod.parse_check_type_params("") is None
    payload = json.dumps({"x": "y"})
    assert rules_mod.parse_check_type_params(payload) == {"x": "y"}
    assert rules_mod.parse_check_type_params("not-json") is None


def test_normalize_rule_row_contract_parses_params():
    row = {"id": 1, "check_type_params": json.dumps({"k": "v"})}
    normalized = rules_mod.normalize_rule_row_contract(row)
    assert isinstance(normalized["check_type_params"], dict)
    assert normalized["check_type_params"]["k"] == "v"


def test_has_upstream_validation_issue_detects_messages():
    diags = [{"message": "Upstream server timed out"}]
    assert rules_mod.has_upstream_validation_issue(diags)

    diags2 = [{"message": "All good"}]
    assert not rules_mod.has_upstream_validation_issue(diags2)


def test_should_preserve_manual_expression():
    assert rules_mod.should_preserve_manual_expression(generated=False, expression="x")
    assert not rules_mod.should_preserve_manual_expression(generated=True, expression="x")
    assert not rules_mod.should_preserve_manual_expression(generated=False, expression=" ")


class _FakeConfigRepo:
    def __init__(self, defaultRuleThresholdPct=None, openMetadataContractCacheTtlSeconds=None):
        self._app = SimpleNamespace(
            defaultRuleThresholdPct=defaultRuleThresholdPct,
            openMetadataContractCacheTtlSeconds=openMetadataContractCacheTtlSeconds,
        )

    def get_app_config(self):
        return self._app


def test_apply_threshold_default_from_config():
    repo = _FakeConfigRepo(defaultRuleThresholdPct=12.5)
    # Non-threshold leaves params untouched
    assert rules_mod.apply_threshold_default_from_config(check_type="OTHER", check_type_params=None, config_repository=repo) is None

    # Threshold without provided threshold gets default
    out = rules_mod.apply_threshold_default_from_config(check_type="THRESHOLD", check_type_params=None, config_repository=repo)
    assert isinstance(out, dict) and float(out["threshold"]) == 12.5

    # Provided threshold preserved
    params = {"threshold": 5}
    out2 = rules_mod.apply_threshold_default_from_config(check_type="THRESHOLD", check_type_params=params, config_repository=repo)
    assert out2["threshold"] == 5

    # Non-numeric config fails fast.
    repo2 = _FakeConfigRepo(defaultRuleThresholdPct="not-float")
    with pytest.raises(HTTPException) as threshold_error:
        rules_mod.apply_threshold_default_from_config(check_type="THRESHOLD", check_type_params=None, config_repository=repo2)
    assert threshold_error.value.status_code == 503


def test_validate_rule_check_type_params_rejects_invalid_quantile_operator():
    with pytest.raises(HTTPException) as exc_info:
        rules_mod.validate_rule_check_type_params(
            check_type="THRESHOLD",
            check_type_params={
                "checkType": "THRESHOLD",
                "attribute": "fee_amount",
                "metric": "quantile",
                "operator": "gt",
                "threshold": 0.5,
                "quantile": 0.95,
            },
        )

    assert exc_info.value.status_code == 400
    assert "only supports operators gte and lte" in str(exc_info.value.detail)


def test_validate_rule_check_type_params_accepts_valid_quantile_threshold():
    out = rules_mod.validate_rule_check_type_params(
        check_type="THRESHOLD",
        check_type_params={
            "checkType": "THRESHOLD",
            "attribute": "fee_amount",
            "metric": "quantile",
            "operator": "gte",
            "threshold": 0.5,
            "quantile": 0.95,
        },
    )

    assert out == {
        "checkType": "THRESHOLD",
        "attribute": "fee_amount",
        "metric": "quantile",
        "operator": "gte",
        "threshold": 0.5,
        "quantile": 0.95,
    }


def test_resolve_openmetadata_contract_cache_ttl_seconds():
    repo = _FakeConfigRepo(openMetadataContractCacheTtlSeconds="60")
    assert rules_mod.resolve_openmetadata_contract_cache_ttl_seconds(repo) == 60

    repo2 = _FakeConfigRepo(openMetadataContractCacheTtlSeconds="-5")
    assert rules_mod.resolve_openmetadata_contract_cache_ttl_seconds(repo2) == 0

    repo3 = _FakeConfigRepo(openMetadataContractCacheTtlSeconds="bad")
    with pytest.raises(HTTPException) as ttl_error:
        rules_mod.resolve_openmetadata_contract_cache_ttl_seconds(repo3)
    assert ttl_error.value.status_code == 503


def test_is_temporal_attribute_type():
    assert rules_mod.is_temporal_attribute_type("timestamp")
    assert rules_mod.is_temporal_attribute_type("Date")
    assert not rules_mod.is_temporal_attribute_type("varchar")
