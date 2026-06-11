import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.domain.entities import rules_endpoint_support as rules


def test_normalize_rule_name():
    assert rules.normalize_rule_name(None) == ""
    assert rules.normalize_rule_name("  FooBar ") == "foobar"


def test_read_row_field_dict_and_object():
    d = {"name": "Test"}
    assert rules.read_row_field(d, "name") == "Test"

    class Row:
        name = "Obj"

    r = Row()
    assert rules.read_row_field(r, "name") == "Obj"


def test_read_row_field_camel_to_snake():
    class Row:
        data_object_id = "obj-1"

    r = Row()
    assert rules.read_row_field(r, "dataObjectId") == "obj-1"


def test_require_workspace():
    assert rules.require_workspace(None, "  ws ") == "ws"
    with pytest.raises(HTTPException):
        rules.require_workspace(None, "", None)


def test_paginate_basic():
    rows = list(range(1, 8))
    out = rules.build_rules_page_payload(rows, page=1, limit=3)
    assert out["pagination"]["total"] == 7
    assert out["pagination"]["total_pages"] == 3
    assert out["data"] == [1, 2, 3]


def test_parse_check_type_params():
    assert rules.parse_check_type_params(None) is None
    assert rules.parse_check_type_params({"a": 1}) == {"a": 1}
    assert rules.parse_check_type_params("") is None
    assert rules.parse_check_type_params("  {\"x\":1}  ") == {"x": 1}
    # JSON that is not an object -> None
    assert rules.parse_check_type_params("[1,2]") is None
    # invalid JSON -> None
    assert rules.parse_check_type_params("not-json") is None


def test_normalize_rule_row_contract():
    row = {"id": 1, "check_type_params": '{"k": "v"}'}
    out = rules.normalize_rule_row_contract(row)
    assert isinstance(out, dict)
    assert out["check_type_params"] == {"k": "v"}


def test_has_upstream_validation_issue():
    diags = [{"message": "Invalid response was received from the upstream server"}]
    assert rules.has_upstream_validation_issue(diags) is True
    diags = [{"message": "some other error"}]
    assert rules.has_upstream_validation_issue(diags) is False


def test_should_preserve_manual_expression():
    assert rules.should_preserve_manual_expression(generated=False, expression="x") is True
    assert rules.should_preserve_manual_expression(generated=None, expression="x") is False
    assert rules.should_preserve_manual_expression(generated=False, expression=None) is False


def test_is_temporal_attribute_type():
    assert rules.is_temporal_attribute_type("timestamp")
    assert rules.is_temporal_attribute_type("DateTime")
    assert not rules.is_temporal_attribute_type("string")


def test_resolve_openmetadata_contract_cache_ttl_seconds():
    class CfgRepo:
        def __init__(self, val):
            self._val = SimpleNamespace(openMetadataContractCacheTtlSeconds=val)

        def get_app_config(self):
            return self._val

    repo = CfgRepo("60")
    assert rules.resolve_openmetadata_contract_cache_ttl_seconds(repo) == 60

    repo = CfgRepo("-5")
    assert rules.resolve_openmetadata_contract_cache_ttl_seconds(repo) == 0

    repo = CfgRepo("not-int")
    assert rules.resolve_openmetadata_contract_cache_ttl_seconds(repo) == 300


def test_apply_threshold_default_from_config():
    class CfgRepo:
        def __init__(self, val):
            self._val = SimpleNamespace(defaultRuleThresholdPct=val)

        def get_app_config(self):
            return self._val

    # Non-threshold passthrough
    params = {"x": 1}
    assert rules.apply_threshold_default_from_config(check_type=None, check_type_params=params, config_repository=CfgRepo(5)) == params

    # Threshold, with no explicit threshold -> filled from config
    out = rules.apply_threshold_default_from_config(check_type="THRESHOLD", check_type_params=None, config_repository=CfgRepo(12.5))
    assert isinstance(out, dict)
    assert float(out["threshold"]) == 12.5

    # Non-numeric fallback -> 0.0
    out = rules.apply_threshold_default_from_config(check_type="threshold", check_type_params=None, config_repository=CfgRepo("bad"))
    assert float(out["threshold"]) == 0.0
