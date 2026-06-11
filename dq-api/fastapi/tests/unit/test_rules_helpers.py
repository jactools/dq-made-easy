from types import SimpleNamespace
import pytest

from fastapi import HTTPException

from app.application.presenters import build_rules_page_payload
from app.domain.entities import rule_policy as rules


def test_normalize_rule_name():
    assert rules.normalize_rule_name("  Name ") == "name"
    assert rules.normalize_rule_name(None) == ""


def test_read_row_field_dict_and_object():
    row_dict = {"name": "n"}
    assert rules.read_row_field(row_dict, "name") == "n"

    class Row:
        pass

    obj = Row()
    obj.foo = "bar"
    # Key with capital letters should fall back to the snake attribute
    assert rules.read_row_field(obj, "Foo") == "bar"


def test_require_workspace():
    with pytest.raises(HTTPException):
        rules.require_workspace(None, "")

    assert rules.require_workspace("", "  workspace1 ") == "workspace1"


def test_derive_rule_status_from_row():
    assert rules.derive_rule_status_from_row({"removed": True}) == "removed"
    assert rules.derive_rule_status_from_row({"active": True}) == "activated"
    assert rules.derive_rule_status_from_row({"last_approval_status": "pending"}) == "pending-approval"


def test_paginate_and_parse_check_params_and_normalize_contract():
    rows = [{"id": i} for i in range(10)]
    page = build_rules_page_payload(rows, page=2, limit=3)
    assert page["pagination"]["page"] == 2
    assert len(page["data"]) == 3
    assert page["data"][0]["id"] == 3

    assert rules.parse_check_type_params(None) is None
    assert rules.parse_check_type_params({"a": 1}) == {"a": 1}
    assert rules.parse_check_type_params('{"a": 2}') == {"a": 2}
    assert rules.parse_check_type_params("invalid") is None
    assert rules.parse_check_type_params(123) is None

    payload = {"check_type_params": '{"x": 1}'}
    normalized = rules.normalize_rule_row_contract(payload)
    assert isinstance(normalized, dict)
    assert normalized["check_type_params"] == {"x": 1}


def test_has_upstream_validation_issue():
    diagnostics = [{"message": "invalid response was received from the upstream server"}]
    assert rules.has_upstream_validation_issue(diagnostics)

    diagnostics2 = [{"message": "some other error"}]
    assert not rules.has_upstream_validation_issue(diagnostics2)
