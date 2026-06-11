from typing import Any
from contextlib import contextmanager
import json

import pytest

from app.application.services import compile_rule_to_intermediate_model
from app.application.services import rule_compiler as rule_compiler_module

pytestmark = pytest.mark.usefixtures("clone_payload")


def test_compile_rule_to_intermediate_model_returns_compilable_artifact() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-email-format",
        rule_version_id="rv-001",
        filter_expression="email <> '' and active = true",
    )

    assert artifact["compilable"] is True
    assert artifact["target"] == "dsl"
    assert artifact["schemaVersion"] == "1.1.0"
    assert artifact["executionContract"]["engineTarget"] == "dq-engine"
    assert artifact["executionContract"]["inputFormat"] == "dq.intermediate-model.v1"
    compatibility = artifact["executionContract"]["compatibilityPolicy"]
    assert compatibility["schemaVersioning"] == "semver"
    assert compatibility["compilerVersioning"] == "dq-semver"
    assert compatibility["supportedSchemaSeries"] == "1.x.x"
    assert compatibility["minorVersionBackwardCompatible"] is True
    traceability = artifact["executionContract"]["traceability"]
    assert traceability["ruleId"] == "rule-email-format"
    assert traceability["ruleVersionId"] == "rv-001"
    assert traceability["artifactKey"] == artifact["artifactKey"]
    assert traceability["compilerVersion"] == artifact["compilerVersion"]
    assert traceability["schemaVersion"] == artifact["schemaVersion"]
    assert artifact["filter"]["normalized"] == "email != '' AND active = true"
    assert artifact["filter"]["logicalOperators"] == ["AND"]
    assert artifact["filter"]["ast"] is not None
    assert len(artifact["filter"]["predicates"]) >= 2
    assert artifact["diagnostics"] == []


def test_compile_rule_to_intermediate_model_reports_unsupported_constructs() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-unsupported",
        rule_version_id="rv-001",
        filter_expression="SELECT status FROM source",
    )

    assert artifact["compilable"] is False
    assert artifact["diagnostics"] == [
        {
            "code": "DQ7_RESERVED_KEYWORD",
            "severity": "warning",
            "message": "Reserved keyword SELECT triggers alias warning",
        }
    ]


def test_compile_rule_to_intermediate_model_allows_referential_integrity_subquery_shape() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-ref-integrity",
        rule_version_id="rv-001",
        filter_expression="customer_id IN (SELECT id FROM do-reference-customer)",
    )

    assert artifact["compilable"] is True
    assert artifact["diagnostics"] == []


def test_compile_rule_to_intermediate_model_allows_uniqueness_window_shape() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-uniqueness",
        rule_version_id="rv-001",
        filter_expression="COUNT(*) OVER (PARTITION BY customer_id, order_date) = 1",
    )

    assert artifact["compilable"] is True
    assert artifact["filter"]["normalized"] == "COUNT(*) OVER (PARTITION BY customer_id, order_date) = 1"
    assert artifact["filter"]["ast"] is None
    assert artifact["filter"]["predicates"] == []
    assert artifact["diagnostics"] == [
        {
            "code": "DQ7_AST_PARSE",
            "severity": "warning",
            "message": "AST parse warning: Unsupported predicate operator 'OVER'",
        }
    ]


def test_compile_rule_to_intermediate_model_rejects_aggregate_functions_in_filters() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-aggregate-filter",
        rule_version_id="rv-001",
        filter_expression="COUNT(status) > 1",
    )

    assert artifact["compilable"] is False
    assert any(
        diagnostic["code"] == "DQ7_UNSUPPORTED_AGGREGATE"
        and diagnostic["severity"] == "error"
        and diagnostic["message"] == "COUNT, SUM, AVG, MIN, MAX are reserved; no GROUP BY semantics"
        for diagnostic in artifact["diagnostics"]
    )


def test_compile_rule_to_intermediate_model_keeps_warning_only_ast_fallback_compilable() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-warning-only",
        rule_version_id="rv-001",
        filter_expression="email ILIKE '%@example.com'",
    )

    assert artifact["compilable"] is True
    assert artifact["filter"]["normalized"] == "email ILIKE '%@example.com'"
    assert artifact["filter"]["ast"] is None
    assert artifact["filter"]["predicates"] == []

    diagnostics = artifact["diagnostics"]
    assert len(diagnostics) == 1
    assert diagnostics[0]["code"] == "DQ7_AST_PARSE"
    assert diagnostics[0]["severity"] == "warning"
    assert "Unsupported predicate operator 'ILIKE'" in diagnostics[0]["message"]


def test_compile_rule_to_intermediate_model_normalizes_join_definition(
    rule_compiler_valid_join_definition: list[dict[str, Any]],
) -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-join",
        rule_version_id="rv-002",
        filter_expression="amount >= 10",
        join_definition=rule_compiler_valid_join_definition,
    )

    assert artifact["compilable"] is True
    assert artifact["join"] is not None
    assert artifact["join"][0]["joinType"] == "inner"


def test_compile_rule_to_intermediate_model_reports_invalid_join_definition() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-bad-join",
        rule_version_id="rv-003",
        filter_expression="amount >= 10",
        join_definition="left.id = right.id",
    )

    assert artifact["compilable"] is False
    messages = [item["message"] for item in artifact["diagnostics"]]
    assert any("Join definition" in message for message in messages)


def test_compile_rule_to_intermediate_model_parses_between_in_and_rlike() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-advanced-predicate",
        rule_version_id="rv-010",
        filter_expression="age BETWEEN 18 AND 65 AND country IN ('NL', 'BE') AND email RLIKE '^[^@]+@'",
    )

    assert artifact["compilable"] is True
    operators = [item["operator"] for item in artifact["filter"]["predicates"]]
    assert "BETWEEN" in operators
    assert "IN" in operators
    assert "RLIKE" in operators
    assert artifact["filter"]["logicalOperators"] == ["AND", "AND"]


def test_compile_rule_to_intermediate_model_parses_not_variants() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-advanced-negation",
        rule_version_id="rv-011",
        filter_expression="status NOT IN ('X', 'Y') OR score NOT BETWEEN 1 AND 9 OR name NOT LIKE 'A%'",
    )

    assert artifact["compilable"] is True
    operators = [item["operator"] for item in artifact["filter"]["predicates"]]
    assert "NOT IN" in operators
    assert "NOT BETWEEN" in operators
    assert "NOT LIKE" in operators
    assert artifact["filter"]["logicalOperators"] == ["OR", "OR"]


def test_compile_rule_to_intermediate_model_parses_function_lhs_predicate_without_ast_warning() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-function-lhs",
        rule_version_id="rv-012",
        filter_expression="description IS NOT NULL AND TRIM(description) != ''",
    )

    assert artifact["compilable"] is True
    assert artifact["filter"]["ast"] is not None

    warnings = [
        item for item in artifact["diagnostics"] if item.get("severity") == "warning"
    ]
    assert not any("AST parse warning" in str(item.get("message")) for item in warnings)

    predicates = artifact["filter"]["predicates"]
    operators = [item["operator"] for item in predicates]
    assert "IS NOT NULL" in operators
    assert "!=" in operators


def test_compile_rule_to_intermediate_model_parses_dotted_identifier_predicate() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-dotted-identifier",
        rule_version_id="rv-013",
        filter_expression="o.description IS NOT NULL AND TRIM(o.description) != ''",
    )

    assert artifact["compilable"] is True
    assert artifact["filter"]["ast"] is not None
    warnings = [
        item for item in artifact["diagnostics"] if item.get("severity") == "warning"
    ]
    assert not any("AST parse warning" in str(item.get("message")) for item in warnings)


def test_compile_rule_to_intermediate_model_parses_interval_expression_without_warning() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-interval-expression",
        rule_version_id="rv-014",
        filter_expression="transaction_date >= NOW() - INTERVAL 30 DAY",
    )

    assert artifact["compilable"] is True
    assert artifact["filter"]["ast"] is not None

    warnings = [item for item in artifact["diagnostics"] if item.get("severity") == "warning"]
    assert not any("AST parse warning" in str(item.get("message")) for item in warnings)

    predicates = artifact["filter"]["predicates"]
    assert any(p.get("field") == "transaction_date" and p.get("operator") == ">=" for p in predicates)


def test_compile_rule_to_intermediate_model_parses_timestamp_between_with_interval_bounds() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-timestamp-between",
        rule_version_id="rv-015",
        filter_expression="transaction_date BETWEEN CURRENT_DATE - INTERVAL 30 DAY AND CURRENT_DATE",
    )

    assert artifact["compilable"] is True
    assert artifact["filter"]["ast"] is not None
    warnings = [item for item in artifact["diagnostics"] if item.get("severity") == "warning"]
    assert not any("AST parse warning" in str(item.get("message")) for item in warnings)


def test_compile_rule_to_intermediate_model_parses_in_list_with_type_conversions() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-in-converted-list",
        rule_version_id="rv-016",
        filter_expression="status IN (CAST('OPEN' AS TEXT), CAST('PENDING' AS TEXT), 'CLOSED')",
    )

    assert artifact["compilable"] is True
    assert artifact["filter"]["ast"] is not None
    warnings = [item for item in artifact["diagnostics"] if item.get("severity") == "warning"]
    assert not any("AST parse warning" in str(item.get("message")) for item in warnings)


def test_compile_rule_to_intermediate_model_parses_case_and_postgres_typecast() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-case-typecast",
        rule_version_id="rv-017",
        filter_expression=(
            "event_ts::date >= CURRENT_DATE AND risk_bucket = "
            "CASE WHEN amount > 1000 THEN 'HIGH' ELSE 'LOW' END"
        ),
    )

    assert artifact["compilable"] is True
    assert artifact["filter"]["ast"] is not None
    warnings = [item for item in artifact["diagnostics"] if item.get("severity") == "warning"]
    assert not any("AST parse warning" in str(item.get("message")) for item in warnings)


def test_compile_rule_to_intermediate_model_emits_full_ast_for_grouped_constructs() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-ast-fidelity",
        rule_version_id="rv-030",
        filter_expression="NOT (status IS NULL OR age BETWEEN 18 AND 65) AND country NOT IN ('NL', 'BE')",
    )

    assert artifact["compilable"] is True
    ast = artifact["filter"]["ast"]
    assert ast is not None
    assert ast["nodeType"] == "logical"
    assert ast["operator"] == "AND"

    left_branch = ast["left"]
    assert left_branch["nodeType"] == "unary"
    assert left_branch["operator"] == "NOT"
    assert left_branch["operand"]["nodeType"] == "logical"
    assert left_branch["operand"]["operator"] == "OR"

    operators = [item["operator"] for item in artifact["filter"]["predicates"]]
    assert "IS NULL" in operators
    assert "BETWEEN" in operators
    assert "NOT IN" in operators
    assert artifact["filter"]["logicalOperators"] == ["NOT", "OR", "AND"]


def test_compile_rule_to_intermediate_model_parses_boolean_function_predicate_without_warning() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-regexp-matches",
        rule_version_id="rv-031",
        filter_expression=r"REGEXP_MATCHES(email, '^[^\s@]+@[^\s@]+\.[^\s@]+$')",
    )

    assert artifact["compilable"] is True
    assert artifact["filter"]["ast"] is not None
    warnings = [item for item in artifact["diagnostics"] if item.get("severity") == "warning"]
    assert not any("AST parse warning" in str(item.get("message")) for item in warnings)

    predicates = artifact["filter"]["predicates"]
    assert len(predicates) == 1
    assert predicates[0]["field"].startswith("REGEXP_MATCHES(")
    assert predicates[0]["operator"] == "IS TRUE"
    assert predicates[0]["value"] == "true"


def test_compile_rule_to_intermediate_model_parses_nested_function_lhs_not_in_without_warning() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-present-placeholders",
        rule_version_id="rv-032",
        filter_expression="customer_name IS NOT NULL AND LOWER(TRIM(customer_name)) NOT IN ('unknown', 'n/a')",
    )

    assert artifact["compilable"] is True
    assert artifact["filter"]["ast"] is not None
    warnings = [item for item in artifact["diagnostics"] if item.get("severity") == "warning"]
    assert not any("AST parse warning" in str(item.get("message")) for item in warnings)


def test_compile_rule_to_intermediate_model_parses_cross_object_numeric_tolerance_predicate() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-correct-tolerance",
        rule_version_id="rv-033",
        filter_expression="trade_id = rhs.trade_id AND ABS(closing_price - rhs.reference_price) <= 0.01",
    )

    assert artifact["compilable"] is True
    assert artifact["filter"]["ast"] is not None
    warnings = [item for item in artifact["diagnostics"] if item.get("severity") == "warning"]
    assert not any("AST parse warning" in str(item.get("message")) for item in warnings)


def test_compile_rule_to_intermediate_model_parses_grouped_contextual_plausibility_expression() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-plausible-contextual",
        rule_version_id="rv-034",
        filter_expression=(
            "(segment = 'youth' AND customer_age >= 18 AND customer_age <= 25) "
            "OR (segment = 'adult' AND customer_age >= 26 AND customer_age <= 70)"
        ),
    )

    assert artifact["compilable"] is True
    assert artifact["filter"]["ast"] is not None


def test_compile_rule_to_intermediate_model_artifact_key_is_deterministic_for_equivalent_input() -> None:
    artifact_compact = compile_rule_to_intermediate_model(
        rule_id="rule-contract",
        rule_version_id="rv-020",
        filter_expression="email<>'' and active=true",
    )
    artifact_spaced = compile_rule_to_intermediate_model(
        rule_id="rule-contract",
        rule_version_id="rv-020",
        filter_expression="email != ''   AND   active = true",
    )

    assert artifact_compact["filter"]["normalized"] == artifact_spaced["filter"]["normalized"]
    assert artifact_compact["artifactKey"] == artifact_spaced["artifactKey"]


def test_compile_rule_to_intermediate_model_artifact_key_changes_for_version_change() -> None:
    artifact_v1 = compile_rule_to_intermediate_model(
        rule_id="rule-contract",
        rule_version_id="rv-021",
        filter_expression="email != '' AND active = true",
    )
    artifact_v2 = compile_rule_to_intermediate_model(
        rule_id="rule-contract",
        rule_version_id="rv-022",
        filter_expression="email != '' AND active = true",
    )

    assert artifact_v1["artifactKey"] != artifact_v2["artifactKey"]


def test_compile_rule_to_intermediate_model_serialization_is_stable_for_same_input() -> None:
    artifact_first = compile_rule_to_intermediate_model(
        rule_id="rule-contract",
        rule_version_id="rv-023",
        filter_expression="email != '' AND active = true",
    )
    artifact_second = compile_rule_to_intermediate_model(
        rule_id="rule-contract",
        rule_version_id="rv-023",
        filter_expression="email != '' AND active = true",
    )

    serialized_first = json.dumps(artifact_first, sort_keys=True)
    serialized_second = json.dumps(artifact_second, sort_keys=True)
    assert serialized_first == serialized_second


def test_compile_rule_to_intermediate_model_version_fields_follow_contract() -> None:
    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-contract",
        rule_version_id="rv-024",
        filter_expression="email != '' AND active = true",
    )

    assert artifact["compilerVersion"].startswith("dq-")
    assert artifact["schemaVersion"].count(".") == 2


def test_compile_rule_to_intermediate_model_emits_custom_span(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class _Span:
        def __init__(self, attrs: dict[str, object]) -> None:
            self.attrs = attrs

        def is_recording(self) -> bool:
            return True

        def set_attribute(self, key: str, value: object) -> None:
            self.attrs[key] = value

        def record_exception(self, exc: Exception) -> None:
            return None

        def set_status(self, status) -> None:
            return None

    @contextmanager
    def _fake_traced_span(name: str, **attrs: object):
        calls.append((name, dict(attrs)))
        yield _Span(calls[-1][1])

    monkeypatch.setattr(rule_compiler_module, "traced_span", _fake_traced_span)

    artifact = compile_rule_to_intermediate_model(
        rule_id="rule-span",
        rule_version_id="rv-span-1",
        filter_expression="email != '' AND active = true",
    )

    assert artifact["compilable"] is True
    assert calls[0][0] == "rules.compile"
    assert calls[0][1]["rule_id"] == "rule-span"
    assert calls[0][1]["rule_version_id"] == "rv-span-1"
    assert calls[0][1]["compiler_compilable"] is True


def test_compile_predicates_deduplicates_equivalent_predicates() -> None:
    predicates = rule_compiler_module._compile_predicates(
        "status = 'A' OR status = 'A' OR status = 'B'"
    )
    rendered = [(item["field"], item["operator"], item["value"]) for item in predicates]
    assert rendered.count(("status", "=", "'A'")) == 1
    assert ("status", "=", "'B'") in rendered


def test_extract_logical_operators_skips_between_and_and_prefixed_not_tokens() -> None:
    operators = rule_compiler_module._extract_logical_operators(
        "age BETWEEN 18 AND 65 AND status NOT IN ('X') OR NOT active"
    )
    assert operators == ["AND", "OR", "NOT"]


def test_compile_expression_ast_handles_invalid_and_unary_not_paths() -> None:
    ast, error = rule_compiler_module._compile_expression_ast("status = 'A' AND")
    assert ast is None
    assert error is not None

    ast_ok, error_ok = rule_compiler_module._compile_expression_ast("NOT status IS NULL")
    assert error_ok is None
    assert ast_ok is not None
    assert ast_ok["nodeType"] == "unary"
    assert ast_ok["operator"] == "NOT"


def test_parse_predicate_not_before_comparison_raises_ast_error() -> None:
    parser = rule_compiler_module._ExpressionParser(
        rule_compiler_module._tokenize_expression("status NOT = 'A'")
    )
    with pytest.raises(rule_compiler_module._AstParserError, match="NOT is not allowed"):
        parser.parse()


def test_parse_predicate_handles_tilde_and_bang_tilde_variants() -> None:
    parser_not_rlike = rule_compiler_module._ExpressionParser(
        rule_compiler_module._tokenize_expression("status !~ 'x'")
    )
    result_not_rlike = parser_not_rlike.parse()
    assert result_not_rlike["operator"] == "!~"

    parser_not_prefix_tilde = rule_compiler_module._ExpressionParser(
        rule_compiler_module._tokenize_expression("status NOT ~ 'x'")
    )
    result_not_prefix_tilde = parser_not_prefix_tilde.parse()
    assert result_not_prefix_tilde["operator"] == "NOT RLIKE"

    parser_not_prefix_bang = rule_compiler_module._ExpressionParser(
        rule_compiler_module._tokenize_expression("status NOT !~ 'x'")
    )
    result_not_prefix_bang = parser_not_prefix_bang.parse()
    assert result_not_prefix_bang["operator"] == "RLIKE"


def test_parse_value_expression_renders_commas_parentheses_and_dots() -> None:
    parser = rule_compiler_module._ExpressionParser(
        rule_compiler_module._tokenize_expression("status IN (func(a.b), 'x')")
    )
    parsed = parser.parse()
    values = parsed["value"]
    assert isinstance(values, list)
    assert values[0]["value"].replace(" ", "") == "func(a.b)"
    assert values[1]["value"] == "'x'"


def test_compile_diagnostics_includes_validation_and_unsupported_keywords() -> None:
    diagnostics = rule_compiler_module._compile_diagnostics(
        "SELECT x FROM y WHERE z = 1",
        validation_error="invalid filter",
    )
    codes = {item["code"] for item in diagnostics}
    assert "DQ7_FILTER_VALIDATION" in codes
    assert "DQ7_RESERVED_KEYWORD" in codes


def test_collect_predicates_and_logical_operators_from_ast_helpers() -> None:
    ast = {
        "nodeType": "logical",
        "operator": "AND",
        "left": {
            "nodeType": "predicate",
            "field": "status",
            "operator": "IN",
            "value": [{"value": "'A'", "valueType": "string"}],
            "valueType": "list",
        },
        "right": {
            "nodeType": "unary",
            "operator": "NOT",
            "operand": {
                "nodeType": "predicate",
                "field": "age",
                "operator": "BETWEEN",
                "value": {
                    "lower": {"value": "1", "valueType": "number"},
                    "upper": {"value": "9", "valueType": "number"},
                },
                "valueType": "range",
            },
        },
    }

    predicates = rule_compiler_module._collect_predicates_from_ast(ast)
    assert any(item["operator"] == "IN" and item["value"] == "('A')" for item in predicates)
    assert any(item["operator"] == "BETWEEN" and item["value"] == "1 AND 9" for item in predicates)

    operators = rule_compiler_module._collect_logical_operators_from_ast(ast)
    assert operators == ["AND", "NOT"]
