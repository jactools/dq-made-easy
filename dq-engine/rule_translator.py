"""Translator that converts a rule (dict) into a Great Expectations Expectation object.

Compatible with great-expectations >= 1.14.0 (GX Core).

Rule shape (example):
{
  "id": 123,
  "table": "customers",
  "column": "email",
  "type": "not_null",
  "params": {}
}

Supported rule types: not_null, unique, max_length, min, max, in_set, regex
"""
from typing import Dict, Any
import great_expectations.expectations as gxe


def translate(rule: Dict[str, Any]) -> gxe.Expectation:
    rtype = rule.get("type")
    col = rule.get("column")
    params = rule.get("params", {}) or {}

    if rtype == "not_null":
        return gxe.ExpectColumnValuesToNotBeNull(column=col)
    if rtype == "unique":
        return gxe.ExpectColumnValuesToBeUnique(column=col)
    if rtype == "max_length":
        return gxe.ExpectColumnValueLengthsToBeBetween(column=col, max_value=params.get("max"))
    if rtype == "min":
        return gxe.ExpectColumnMinToBeBetween(column=col, min_value=params.get("min"))
    if rtype == "max":
        return gxe.ExpectColumnMaxToBeBetween(column=col, max_value=params.get("max"))
    if rtype == "in_set":
        return gxe.ExpectColumnValuesToBeInSet(column=col, value_set=params.get("values", []))
    if rtype == "regex":
        return gxe.ExpectColumnValuesToMatchRegex(column=col, regex=params.get("pattern"))

    raise ValueError(f"unsupported rule type for GX translator: {rtype!r}")
