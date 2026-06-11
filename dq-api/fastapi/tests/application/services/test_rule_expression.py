from __future__ import annotations

import json

import pytest

from app.application.services.rule_expression import (
    evaluate_expression_on_context,
    evaluate_expression_on_context_with_details,
    infer_alias_expectations,
    normalize_join_definition,
    validate_filter_expression,
)


@pytest.mark.parametrize(
    ("expression", "expected_error"),
    [
        ("", "Filter expression is required"),
        ("name = 1; drop table rules", "Do not use semicolons in filter expressions"),
        ("name = 1 -- comment", "Comments are not allowed in filter expressions"),
        ("name = 1 /* comment */", "Comments are not allowed in filter expressions"),
        ("'unterminated", "Unclosed single quote in filter expression"),
        ('"unterminated', "Unclosed double quote in filter expression"),
        (")name = 1",
        "Unbalanced parentheses: found a closing parenthesis without matching opening parenthesis",
        ),
        ("(name = 1", "Unbalanced parentheses in filter expression"),
        ("AND name = 1", "Expression cannot start with AND/OR"),
        ("name = 1 OR", "Expression cannot end with AND/OR"),
        ("name = 1 AND AND active = true", "Consecutive logical operators detected"),
    ],
)
def test_validate_filter_expression_rejects_invalid_input(expression: str, expected_error: str) -> None:
    assert validate_filter_expression(expression) == expected_error


def test_validate_filter_expression_accepts_balanced_quotes_and_parentheses() -> None:
    expression = "(name = 'OBrien' AND title = \"AB\")"

    assert validate_filter_expression(expression) is None


@pytest.mark.parametrize(
    ("expression", "expected_error"),
    [
        ("name = 'O''Brien'", "Unclosed single quote in filter expression"),
        ('title = "A""B"', "Unclosed double quote in filter expression"),
    ],
)
def test_validate_filter_expression_rejects_escaped_quotes(expression: str, expected_error: str) -> None:
    assert validate_filter_expression(expression) == expected_error


@pytest.mark.parametrize(
    "expression",
    [
        "name = 1 AND OR active = true",
        "name = 1 OR OR active = true",
    ],
)
def test_validate_filter_expression_rejects_mixed_consecutive_logical_operators(expression: str) -> None:
    assert validate_filter_expression(expression) == "Consecutive logical operators detected"


def test_infer_alias_expectations_extracts_types_and_conflict_resolution() -> None:
    expression = (
        "field >= 10 AND tags[ignore] AND active = true AND name = 'Alice' AND "
        "status = 'open' AND status = 1 AND select = 1 AND 1skip = 2 AND regex = /abc/i"
    )

    expectations = {
        item["alias"]: item["expected"]
        for item in infer_alias_expectations(expression)
    }

    assert expectations == {
        "field": "number",
        "tags": "unknown",
        "active": "boolean",
        "name": "string",
        "status": "unknown",
        "regex": "unknown",
    }


def test_infer_alias_expectations_returns_empty_for_blank_input() -> None:
    assert infer_alias_expectations("   ") == []


@pytest.mark.parametrize(
    ("join_definition", "expected_error"),
    [
        (None, "Join definition is required"),
        ("   ", "Join definition is required"),
        ("not-json", "Join definition must be valid JSON"),
        ([], "Join definition must contain at least one condition"),
        ([1], "Join definition entries must be objects"),
        ([{"conditions": [1]}], "Join condition must be an object"),
        ([{"conditions": []}], "Join definition must contain at least one condition"),
        (
            [
                {
                    "conditions": [
                        {
                            "leftDataObjectId": "left-object",
                            "leftAttributeId": "left-attr",
                            "rightDataObjectId": "right-object",
                            "rightAttributeId": "",
                            "operator": "=",
                        }
                    ]
                }
            ],
            "Join condition field 'rightAttributeId' is required",
        ),
        (
            [
                {
                    "conditions": [
                        {
                            "leftDataObjectId": "left-object",
                            "leftAttributeId": "left-attr",
                            "rightDataObjectId": "right-object",
                            "rightAttributeId": "right-attr",
                            "operator": "~~",
                        }
                    ]
                }
            ],
            "Join condition operator must be one of: =, !=, >, >=, <, <=",
        ),
    ],
)
def test_normalize_join_definition_rejects_invalid_input(join_definition: object, expected_error: str) -> None:
    normalized, error = normalize_join_definition(join_definition)

    assert normalized is None
    assert error == expected_error


def test_normalize_join_definition_rejects_non_object_and_non_array() -> None:
    normalized, error = normalize_join_definition(123)

    assert normalized is None
    assert error == "Join definition must be an object or array"


@pytest.mark.parametrize(
    "join_definition",
    [
        {
            "conditions": [
                {
                    "leftDataObjectId": "left-object",
                    "leftAttributeId": "left-attr",
                    "rightDataObjectId": "right-object",
                    "rightAttributeId": "right-attr",
                    "operator": "=",
                }
            ]
        },
        [
            {
                "conditions": [
                    {
                        "leftDataObjectId": "left-object",
                        "leftAttributeId": "left-attr",
                        "rightDataObjectId": "right-object",
                        "rightAttributeId": "right-attr",
                        "operator": "!=",
                    }
                ]
            }
        ],
    ],
)
def test_normalize_join_definition_accepts_valid_object_and_list(join_definition: object) -> None:
    normalized, error = normalize_join_definition(join_definition)

    assert error is None
    assert json.loads(str(normalized)) == join_definition


@pytest.mark.parametrize(
    "join_definition",
    [
        json.dumps(
            {
                "conditions": [
                    {
                        "leftDataObjectId": "left-object",
                        "leftAttributeId": "left-attr",
                        "rightDataObjectId": "right-object",
                        "rightAttributeId": "right-attr",
                        "operator": "=",
                    }
                ]
            }
        ),
        json.dumps(
            [
                {
                    "conditions": [
                        {
                            "leftDataObjectId": "left-object",
                            "leftAttributeId": "left-attr",
                            "rightDataObjectId": "right-object",
                            "rightAttributeId": "right-attr",
                            "operator": "!=",
                        }
                    ]
                }
            ]
        ),
    ],
)
def test_normalize_join_definition_accepts_string_input(join_definition: str) -> None:
    normalized, error = normalize_join_definition(join_definition)

    assert error is None
    assert json.loads(str(normalized)) == json.loads(join_definition)


@pytest.mark.parametrize(
    ("expression", "context", "expected_result"),
    [
        (
            "deleted = NULL AND active = true AND NOT suspended",
            {"deleted": None, "active": True, "suspended": False},
            True,
        ),
        ("age = 19 OR age = 20", {"age": 18}, False),
    ],
)
def test_evaluate_expression_on_context_with_details(expression: str, context: dict[str, object], expected_result: bool) -> None:
    result, error = evaluate_expression_on_context_with_details(expression, context)

    assert result is expected_result
    assert error is None


def test_evaluate_expression_on_context_returns_false_and_error_for_invalid_expression() -> None:
    result, error = evaluate_expression_on_context_with_details("age =", {"age": 18})

    assert result is False
    assert error is not None
    assert evaluate_expression_on_context("age =", {"age": 18}) is False


def test_evaluate_expression_on_context_handles_not_equal_operator() -> None:
    result, error = evaluate_expression_on_context_with_details("age <> 19", {"age": 18})

    assert result is True
    assert error is None


@pytest.mark.parametrize(
    ("expression", "context"),
    [
        ("deleted IS None", {"deleted": None}),
        ("deleted IS NOT None", {"deleted": "2026-01-01"}),
    ],
)
def test_evaluate_expression_on_context_reports_null_shorthand_parse_failure(expression: str, context: dict[str, object]) -> None:
    result, error = evaluate_expression_on_context_with_details(expression, context)

    assert result is False
    assert error is not None