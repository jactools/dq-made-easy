import pytest
import sys
from types import ModuleType

import app.application.services.gx_expectations as gx_expectations_mod
from app.application.services import compile_rule_to_intermediate_model
from app.application.services import build_gx_expectations_from_intermediate_model
from app.application.services import build_gx_serialized_row_condition_from_intermediate_model
from app.application.services import build_gx_row_condition_meta_from_intermediate_model
from app.application.services import build_gx_row_condition_from_intermediate_model
from app.application.services import GxExpectationBuildError
from app.application.services import lower_gx_row_condition_artifact


def test_build_gx_expectations_from_intermediate_model_builds_expectations_for_simple_and_expression() -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-translate-basic",
        rule_version_id="rv-001",
        filter_expression="email IS NOT NULL AND age BETWEEN 18 AND 65 AND status IN ('ACTIVE', 'PENDING')",
    )

    expectations = build_gx_expectations_from_intermediate_model(
        intermediate,
        rule_id="rule-translate-basic",
        artifact_key=intermediate["artifactKey"],
    )

    assert expectations
    expectation_types = {item.get("expectation_type") for item in expectations}
    assert "expect_column_values_to_not_be_null" in expectation_types
    assert "expect_column_values_to_be_between" in expectation_types
    assert "expect_column_values_to_be_in_set" in expectation_types


def test_build_gx_expectations_from_intermediate_model_attaches_row_condition_for_or_expression() -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-translate-or",
        rule_version_id="rv-002",
        filter_expression="status = 'X' OR status = 'Y'",
    )

    expectations = build_gx_expectations_from_intermediate_model(intermediate)

    assert [item["expectation_type"] for item in expectations] == [
        "expect_column_values_to_be_in_set",
        "expect_column_values_to_be_in_set",
    ]
    assert expectations[0]["kwargs"]["row_condition"]["type"] == "or"
    assert len(expectations[0]["kwargs"]["row_condition"]["conditions"]) == 2


def test_build_gx_expectations_from_intermediate_model_builds_conditional_allowlist_expectations() -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-translate-allowlist",
        rule_version_id="rv-allowlist",
        filter_expression="(currency = 'USD' AND LOWER(payment_method) IN ('card', 'ach')) OR (currency = 'EUR' AND LOWER(payment_method) IN ('card', 'sepa'))",
    )

    expectations = build_gx_expectations_from_intermediate_model(intermediate)

    assert [item["expectation_type"] for item in expectations] == [
        "expect_column_values_to_not_be_null",
        "expect_column_values_to_be_in_set",
        "expect_column_values_to_be_in_set_for_other_column_value",
        "expect_column_values_to_be_in_set_for_other_column_value",
    ]
    assert expectations[1]["kwargs"] == {"column": "currency", "value_set": ["USD", "EUR"]}
    assert expectations[2]["kwargs"] == {
        "column": "payment_method",
        "other_column": "currency",
        "other_value": "USD",
        "value_set": ["card", "ach"],
        "case_sensitive": False,
    }
    assert expectations[3]["kwargs"] == {
        "column": "payment_method",
        "other_column": "currency",
        "other_value": "EUR",
        "value_set": ["card", "sepa"],
        "case_sensitive": False,
    }


def test_build_gx_row_condition_from_intermediate_model_builds_conjunctive_condition_artifact() -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-row-condition-and",
        rule_version_id="rv-003",
        filter_expression="country = 'NL' AND status IN ('ACTIVE', 'PENDING') AND age >= 18",
    )

    row_condition = build_gx_row_condition_from_intermediate_model(intermediate)

    assert row_condition == {
        "kind": "gx_row_condition",
        "prototype": True,
        "syntax": "great_expectations.row_conditions",
        "source": "((Column('country') == 'NL') & (Column('status').is_in(['ACTIVE', 'PENDING'])) & (Column('age') >= 18))",
        "conditionBlocks": [[
            "Column('country') == 'NL'",
            "Column('status').is_in(['ACTIVE', 'PENDING'])",
            "Column('age') >= 18",
        ]],
        "conditionBlockCount": 1,
        "conditionStatementCount": 3,
        "serializedCondition": {
            "type": "and",
            "conditions": [
                {"type": "comparison", "column": {"name": "country"}, "operator": "==", "parameter": "NL"},
                {
                    "type": "comparison",
                    "column": {"name": "status"},
                    "operator": "IN",
                    "parameter": ["ACTIVE", "PENDING"],
                },
                {"type": "comparison", "column": {"name": "age"}, "operator": ">=", "parameter": 18},
            ],
        },
        "representation": "structured",
    }


def test_build_gx_row_condition_from_intermediate_model_distributes_and_over_or() -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-row-condition-dnf",
        rule_version_id="rv-004",
        filter_expression="country = 'NL' AND (status = 'ACTIVE' OR status = 'PENDING')",
    )

    row_condition = build_gx_row_condition_from_intermediate_model(intermediate)

    assert row_condition["conditionBlocks"] == [
        ["Column('country') == 'NL'", "Column('status') == 'ACTIVE'"],
        ["Column('country') == 'NL'", "Column('status') == 'PENDING'"],
    ]
    assert row_condition["source"] == (
        "((Column('country') == 'NL') & (Column('status') == 'ACTIVE')) | "
        "((Column('country') == 'NL') & (Column('status') == 'PENDING'))"
    )


def test_build_gx_row_condition_from_intermediate_model_supports_between_operator() -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-row-condition-between",
        rule_version_id="rv-005",
        filter_expression="age BETWEEN 18 AND 65",
    )

    row_condition = build_gx_row_condition_from_intermediate_model(intermediate)

    assert row_condition["conditionBlocks"] == [["Column('age') >= 18", "Column('age') <= 65"]]
    assert row_condition["serializedCondition"] == {
        "type": "and",
        "conditions": [
            {"type": "comparison", "column": {"name": "age"}, "operator": ">=", "parameter": 18},
            {"type": "comparison", "column": {"name": "age"}, "operator": "<=", "parameter": 65},
        ],
    }


def test_build_gx_row_condition_from_intermediate_model_uses_pass_through_for_regex_family() -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-row-condition-like",
        rule_version_id="rv-005b",
        filter_expression="name RLIKE '^A.*'",
    )

    row_condition = build_gx_row_condition_from_intermediate_model(intermediate)

    assert row_condition["representation"] == "pass_through"
    assert row_condition["source"] == "name RLIKE '^A.*'"
    assert row_condition["serializedCondition"] == {
        "type": "pass_through",
        "pass_through_filter": "name RLIKE '^A.*'",
    }
    assert row_condition["conditionBlocks"] is None


def test_build_gx_row_condition_meta_from_intermediate_model_reports_status() -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-row-condition-meta",
        rule_version_id="rv-006",
        filter_expression="country = 'NL' AND age >= 18",
    )

    meta = build_gx_row_condition_meta_from_intermediate_model(intermediate)

    assert meta["status"] == "available"
    assert meta["prototype"]["kind"] == "gx_row_condition"
    assert meta["liveLowering"]["status"] in {"available", "unavailable"}


def test_build_gx_serialized_row_condition_from_intermediate_model_returns_serialized_payload() -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-row-condition-serialized",
        rule_version_id="rv-006b",
        filter_expression="country = 'NL' AND age >= 18",
    )

    serialized = build_gx_serialized_row_condition_from_intermediate_model(intermediate)

    assert serialized == {
        "type": "and",
        "conditions": [
            {"type": "comparison", "column": {"name": "country"}, "operator": "==", "parameter": "NL"},
            {"type": "comparison", "column": {"name": "age"}, "operator": ">=", "parameter": 18},
        ],
    }


def test_lower_gx_row_condition_artifact_builds_live_object(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeExpr:
        def __init__(self, rendered: str) -> None:
            self.rendered = rendered

        def __and__(self, other: "_FakeExpr") -> "_FakeExpr":
            return _FakeExpr(f"({self.rendered} & {other.rendered})")

        def __or__(self, other: "_FakeExpr") -> "_FakeExpr":
            return _FakeExpr(f"({self.rendered} | {other.rendered})")

        def __repr__(self) -> str:
            return self.rendered

    class _FakeColumn:
        def __init__(self, column: str) -> None:
            self.column = column

        def __eq__(self, other: object) -> _FakeExpr:  # type: ignore[override]
            return _FakeExpr(f"Column({self.column!r}) == {other!r}")

        def __ge__(self, other: object) -> _FakeExpr:
            return _FakeExpr(f"Column({self.column!r}) >= {other!r}")

        def is_in(self, values: list[object]) -> _FakeExpr:
            return _FakeExpr(f"Column({self.column!r}).is_in({values!r})")

    gx_module = ModuleType("great_expectations")
    expectations_module = ModuleType("great_expectations.expectations")
    row_conditions_module = ModuleType("great_expectations.expectations.row_conditions")
    row_conditions_module.Column = _FakeColumn

    monkeypatch.setitem(sys.modules, "great_expectations", gx_module)
    monkeypatch.setitem(sys.modules, "great_expectations.expectations", expectations_module)
    monkeypatch.setitem(sys.modules, "great_expectations.expectations.row_conditions", row_conditions_module)

    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-row-condition-live",
        rule_version_id="rv-007",
        filter_expression="country = 'NL' AND age >= 18",
    )
    artifact = build_gx_row_condition_from_intermediate_model(intermediate)

    live_condition = lower_gx_row_condition_artifact(artifact)

    rendered = repr(live_condition)
    assert "Column('country') == 'NL'" in rendered
    assert "Column('age') >= 18" in rendered
    assert "&" in rendered


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("''", ""),
        ("'it''s'", "it's"),
        ('"a\\\\b\\\"c"', 'a\\b"c'),
        ("plain", "plain"),
    ],
)
def test_sql_literal_helpers_parse_supported_values(raw: str, expected: object) -> None:
    assert gx_expectations_mod._strip_sql_string_quotes(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("FALSE", False),
        ("42", 42),
        ("-3.5", -3.5),
        ("NULL", None),
        ("'value'", "value"),
    ],
)
def test_parse_sql_literal_supports_scalar_types(raw: str, expected: object) -> None:
    assert gx_expectations_mod._parse_sql_literal(raw) == expected


@pytest.mark.parametrize("raw", ["", "identifier"])
def test_parse_sql_literal_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(GxExpectationBuildError):
        gx_expectations_mod._parse_sql_literal(raw)


def test_parse_in_list_and_between_bounds_cover_validation_edges() -> None:
    assert gx_expectations_mod._parse_in_list("('A','B''C', 3)") == ["A", "B'C", 3]

    with pytest.raises(GxExpectationBuildError, match="parenthesized"):
        gx_expectations_mod._parse_in_list("'A','B'")
    with pytest.raises(GxExpectationBuildError, match="empty"):
        gx_expectations_mod._parse_in_list("()")
    with pytest.raises(GxExpectationBuildError, match="non-literal"):
        gx_expectations_mod._parse_in_list("(CAST(status AS TEXT))")
    with pytest.raises(GxExpectationBuildError, match="must not include NULL"):
        gx_expectations_mod._parse_in_list("('A', NULL)")

    assert gx_expectations_mod._parse_between_bounds("1 AND 2") == (1, 2)
    with pytest.raises(GxExpectationBuildError, match="BETWEEN value"):
        gx_expectations_mod._parse_between_bounds("1,2")
    with pytest.raises(GxExpectationBuildError, match="must not be NULL"):
        gx_expectations_mod._parse_between_bounds("NULL AND 2")


def test_parse_field_and_ast_value_helpers_cover_supported_and_error_paths() -> None:
    wrapped = gx_expectations_mod._parse_field_ref("TRIM(customer.email)")
    assert wrapped == gx_expectations_mod._FieldRef(column="email", wrapper="TRIM")
    assert gx_expectations_mod._parse_field_ref("customer.email::text") == gx_expectations_mod._FieldRef(column="email")
    assert gx_expectations_mod._parse_field_ref("customer_email") == gx_expectations_mod._FieldRef(column="customer_email")

    with pytest.raises(GxExpectationBuildError, match="Predicate field is missing"):
        gx_expectations_mod._parse_field_ref("   ")
    with pytest.raises(GxExpectationBuildError, match="Unsupported field reference"):
        gx_expectations_mod._parse_field_ref("customer-email")

    assert gx_expectations_mod._literal_from_ast_value({"value": "'ok'"}) == "ok"
    assert gx_expectations_mod._literal_from_ast_value(5) == 5
    assert gx_expectations_mod._list_from_ast_value([{"value": "1"}, "'two'"]) == [1, "two"]
    assert gx_expectations_mod._between_bounds_from_ast_value({"lower": {"value": "1"}, "upper": {"value": "2"}}) == (1, 2)

    with pytest.raises(GxExpectationBuildError, match="Unsupported literal payload"):
        gx_expectations_mod._literal_from_ast_value({"other": "value"})
    with pytest.raises(GxExpectationBuildError, match="Unsupported IN-list payload"):
        gx_expectations_mod._list_from_ast_value(1)
    with pytest.raises(GxExpectationBuildError, match="must not be NULL"):
        gx_expectations_mod._between_bounds_from_ast_value({"lower": {"value": "NULL"}, "upper": {"value": "2"}})
    with pytest.raises(GxExpectationBuildError, match="Unsupported BETWEEN payload"):
        gx_expectations_mod._between_bounds_from_ast_value(1)


def test_ast_condition_helpers_cover_pass_through_and_validation_paths() -> None:
    regex_predicate = {"nodeType": "predicate", "operator": "RLIKE"}
    assert gx_expectations_mod._requires_pass_through_row_condition(regex_predicate) is True
    assert gx_expectations_mod._requires_pass_through_row_condition(
        {"nodeType": "logical", "left": {"nodeType": "predicate", "operator": "="}, "right": regex_predicate}
    ) is True
    assert gx_expectations_mod._requires_pass_through_row_condition(
        {"nodeType": "unary", "operand": regex_predicate}
    ) is True
    assert gx_expectations_mod._requires_pass_through_row_condition({"nodeType": "unknown"}) is False

    with pytest.raises(GxExpectationBuildError, match="missing an operand"):
        gx_expectations_mod._ast_to_rendered_condition_blocks({"nodeType": "logical", "operator": "AND", "left": {}})
    with pytest.raises(GxExpectationBuildError, match="Unsupported logical operator"):
        gx_expectations_mod._ast_to_rendered_condition_blocks(
            {"nodeType": "logical", "operator": "XOR", "left": {"nodeType": "predicate", "operator": "IS NULL", "field": "status"}, "right": {"nodeType": "predicate", "operator": "IS TRUE", "field": "active"}}
        )
    with pytest.raises(GxExpectationBuildError, match="does not support unary operator"):
        gx_expectations_mod._ast_to_rendered_condition_blocks({"nodeType": "unary", "operator": "NOT"})
    with pytest.raises(GxExpectationBuildError, match="Unsupported AST node type"):
        gx_expectations_mod._ast_to_rendered_condition_blocks({"nodeType": "mystery"})

    assert gx_expectations_mod._predicate_to_row_condition_blocks({"field": "status", "operator": "IS NULL"}) == [
        [gx_expectations_mod._RenderedCondition(rendered="Column('status').is_null()", serialized={"type": "nullity", "column": {"name": "status"}, "is_null": True})]
    ]
    assert gx_expectations_mod._predicate_to_row_condition_blocks({"field": "flag", "operator": "IS TRUE"}) == [
        [gx_expectations_mod._RenderedCondition(rendered="Column('flag') == True", serialized={"type": "comparison", "column": {"name": "flag"}, "operator": "==", "parameter": True})]
    ]
    assert gx_expectations_mod._predicate_to_row_condition_blocks({"field": "amount", "operator": "NOT BETWEEN", "value": {"lower": {"value": "1"}, "upper": {"value": "2"}}}) == [
        [gx_expectations_mod._RenderedCondition(rendered="Column('amount') < 1", serialized={"type": "comparison", "column": {"name": "amount"}, "operator": "<", "parameter": 1})],
        [gx_expectations_mod._RenderedCondition(rendered="Column('amount') > 2", serialized={"type": "comparison", "column": {"name": "amount"}, "operator": ">", "parameter": 2})],
    ]

    with pytest.raises(GxExpectationBuildError, match="wrapped field references"):
        gx_expectations_mod._predicate_to_row_condition_blocks({"field": "LOWER(status)", "operator": "=", "value": "'ok'"})
    with pytest.raises(GxExpectationBuildError, match="non-literal expression RHS"):
        gx_expectations_mod._predicate_to_row_condition_blocks({"field": "amount", "operator": "=", "value": "other", "valueType": "expression"})
    with pytest.raises(GxExpectationBuildError, match="Numeric comparison requires numeric literal"):
        gx_expectations_mod._predicate_to_row_condition_blocks({"field": "amount", "operator": ">", "value": "'bad'"})
    with pytest.raises(GxExpectationBuildError, match="does not support predicate operator"):
        gx_expectations_mod._predicate_to_row_condition_blocks({"field": "amount", "operator": "EXISTS", "value": "1"})


def test_build_row_condition_and_lowering_fail_fast_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(GxExpectationBuildError, match="produced no condition blocks"):
        monkeypatch.setattr(gx_expectations_mod, "_ast_to_rendered_condition_blocks", lambda _node: [])
        gx_expectations_mod.build_gx_row_condition_from_intermediate_model({"filter": {"ast": {}}})

    monkeypatch.setattr(
        gx_expectations_mod,
        "_ast_to_rendered_condition_blocks",
        lambda _node: [[gx_expectations_mod._RenderedCondition(rendered="x", serialized={"type": "comparison", "column": {"name": "x"}, "operator": "==", "parameter": 1})] for _ in range(2)],
    )
    with pytest.raises(GxExpectationBuildError, match="exceeds the limit"):
        gx_expectations_mod.build_gx_row_condition_from_intermediate_model({"filter": {"ast": {}}}, max_condition_blocks=1)

    monkeypatch.setattr(
        gx_expectations_mod,
        "_ast_to_rendered_condition_blocks",
        lambda _node: [[gx_expectations_mod._RenderedCondition(rendered="x", serialized={"type": "comparison", "column": {"name": "x"}, "operator": "==", "parameter": 1})] for _ in range(3)],
    )
    with pytest.raises(GxExpectationBuildError, match="condition statements"):
        gx_expectations_mod.build_gx_row_condition_from_intermediate_model({"filter": {"ast": {}}}, max_condition_statements=2)

    with pytest.raises(GxExpectationBuildError, match="kind must be 'gx_row_condition'"):
        gx_expectations_mod.lower_gx_row_condition_artifact({"kind": "other"})
    with pytest.raises(GxExpectationBuildError, match="source is missing"):
        gx_expectations_mod.lower_gx_row_condition_artifact({"kind": "gx_row_condition", "serializedCondition": None, "source": ""})

    monkeypatch.setattr(gx_expectations_mod.importlib, "import_module", lambda _name: (_ for _ in ()).throw(ModuleNotFoundError("missing")))
    with pytest.raises(GxExpectationBuildError, match="module is unavailable"):
        gx_expectations_mod.lower_gx_row_condition_artifact({"kind": "gx_row_condition", "source": "Column('x') == 1", "serializedCondition": {"type": "comparison"}})

    class _BadDeserializerModule:
        Column = object()

        @staticmethod
        def deserialize_row_condition(_payload):
            raise RuntimeError("boom")

    monkeypatch.setattr(gx_expectations_mod.importlib, "import_module", lambda _name: _BadDeserializerModule)
    with pytest.raises(GxExpectationBuildError, match="Failed to lower GX row-condition artifact: boom"):
        gx_expectations_mod.lower_gx_row_condition_artifact({"kind": "gx_row_condition", "source": "Column('x') == 1", "serializedCondition": {"type": "comparison"}})

    class _NoColumnModule:
        deserialize_row_condition = None

    monkeypatch.setattr(gx_expectations_mod.importlib, "import_module", lambda _name: _NoColumnModule)
    with pytest.raises(GxExpectationBuildError, match="Column is unavailable"):
        gx_expectations_mod.lower_gx_row_condition_artifact({"kind": "gx_row_condition", "source": "Column('x') == 1", "serializedCondition": {}})

    class _EvalModule:
        deserialize_row_condition = None

        @staticmethod
        def Column(name: str) -> object:
            return object()

    monkeypatch.setattr(gx_expectations_mod.importlib, "import_module", lambda _name: _EvalModule)
    with pytest.raises(GxExpectationBuildError, match="Failed to lower GX row-condition artifact"):
        gx_expectations_mod.lower_gx_row_condition_artifact({"kind": "gx_row_condition", "source": "Column('x') == unknown_name", "serializedCondition": {}})


def test_attach_serialized_row_condition_and_meta_cover_skip_and_merge_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gx_expectations_mod, "build_gx_row_condition_from_intermediate_model", lambda _model: {"serializedCondition": None})
    with pytest.raises(GxExpectationBuildError, match="missing serializedCondition"):
        gx_expectations_mod.build_gx_serialized_row_condition_from_intermediate_model({"filter": {}})

    serialized = {"type": "comparison", "column": {"name": "segment"}, "operator": "==", "parameter": "VIP"}
    monkeypatch.setattr(gx_expectations_mod, "build_gx_serialized_row_condition_from_intermediate_model", lambda _model: serialized)

    expectations = [
        {"expectation_type": "unsupported_expectation", "kwargs": {"column": "status"}, "meta": {}},
        {"expectation_type": "expect_column_values_to_be_in_set", "kwargs": None, "meta": {}},
        {"expectation_type": "expect_column_values_to_be_in_set", "kwargs": {"value_set": ["A"]}, "meta": {}},
        {"expectation_type": "expect_column_values_to_be_in_set", "kwargs": {"column": "status", "value_set": ["A"], "row_condition": "invalid"}, "meta": {}},
        {"expectation_type": "expect_column_values_to_be_in_set", "kwargs": {"column": "status", "value_set": ["A"], "row_condition": {"type": "and", "conditions": [{"type": "comparison", "column": {"name": "country"}, "operator": "==", "parameter": "NL"}]}}, "meta": {}},
    ]

    attached = gx_expectations_mod.attach_gx_row_condition_to_expectations(expectations, intermediate_model={"filter": {}})

    assert attached[:4] == expectations[:4]
    assert attached[4]["kwargs"]["row_condition"] == {
        "type": "and",
        "conditions": [
            {"type": "comparison", "column": {"name": "country"}, "operator": "==", "parameter": "NL"},
            serialized,
        ],
    }

    monkeypatch.setattr(gx_expectations_mod, "build_gx_row_condition_from_intermediate_model", lambda _model: (_ for _ in ()).throw(GxExpectationBuildError("unsupported")))
    assert gx_expectations_mod.build_gx_row_condition_meta_from_intermediate_model({"filter": {}}) == {
        "status": "unsupported",
        "prototype": None,
        "error": "unsupported",
        "liveLowering": {"status": "unavailable", "error": "Row-condition prototype unavailable"},
    }

    prototype = {"kind": "gx_row_condition", "source": "Column('x') == 1", "serializedCondition": {"type": "comparison"}}
    monkeypatch.setattr(gx_expectations_mod, "build_gx_row_condition_from_intermediate_model", lambda _model: prototype)
    monkeypatch.setattr(gx_expectations_mod, "lower_gx_row_condition_artifact", lambda _artifact: (_ for _ in ()).throw(GxExpectationBuildError("gx missing")))
    meta = gx_expectations_mod.build_gx_row_condition_meta_from_intermediate_model({"filter": {}})
    assert meta["status"] == "available"
    assert meta["prototype"] == prototype
    assert meta["liveLowering"] == {"status": "unavailable", "error": "gx missing"}


def test_build_gx_expectations_from_intermediate_model_covers_translation_edges() -> None:
    with pytest.raises(GxExpectationBuildError, match="missing filter"):
        build_gx_expectations_from_intermediate_model({})
    with pytest.raises(GxExpectationBuildError, match="does not support OR / unary NOT"):
        build_gx_expectations_from_intermediate_model({"filter": {"logicalOperators": ["OR"], "predicates": [{}]}})
    with pytest.raises(GxExpectationBuildError, match="No predicates"):
        build_gx_expectations_from_intermediate_model({"filter": {"logicalOperators": [], "predicates": []}})
    with pytest.raises(GxExpectationBuildError, match="Predicate payload is invalid"):
        build_gx_expectations_from_intermediate_model({"filter": {"logicalOperators": [], "predicates": [1]}})

    expectations = build_gx_expectations_from_intermediate_model(
        {
            "filter": {
                "logicalOperators": [],
                "predicates": [
                    {"field": "TRIM(status)", "operator": "=", "value": "''", "valueType": "string"},
                    {"field": "TRIM(comment)", "operator": "!=", "value": "''", "valueType": "string"},
                    {"field": "deleted_at", "operator": "IS NULL"},
                    {"field": "active", "operator": "IS TRUE"},
                    {"field": "score", "operator": "<", "value": "10", "valueType": "number"},
                    {"field": "age", "operator": "NOT BETWEEN", "value": "18 AND 65", "valueType": "number"},
                    {"field": "status", "operator": "NOT IN", "value": "('A','B')", "valueType": "string"},
                    {"field": "email", "operator": "LIKE", "value": "'a_%'", "valueType": "string"},
                    {"field": "name", "operator": "NOT LIKE", "value": "'B%'", "valueType": "string"},
                    {"field": "code", "operator": "RLIKE", "value": "'^A.*'", "valueType": "string"},
                ],
            }
        },
        rule_id="rule-edges",
        artifact_key="ak-edges",
    )

    assert [item["expectation_type"] for item in expectations] == [
        "expect_column_values_to_match_regex",
        "expect_column_values_to_not_match_regex",
        "expect_column_values_to_be_null",
        "expect_column_values_to_be_in_set",
        "expect_column_values_to_be_between",
        "expect_column_values_to_not_be_between",
        "expect_column_values_to_not_be_in_set",
        "expect_column_values_to_match_regex",
        "expect_column_values_to_not_match_regex",
        "expect_column_values_to_match_regex",
    ]
    assert expectations[4]["kwargs"] == {"column": "score", "max_value": 10, "strict_max": True}
    assert expectations[5]["kwargs"] == {"column": "age", "min_value": 18, "max_value": 65}
    assert expectations[6]["kwargs"] == {"column": "status", "value_set": ["A", "B"]}
    assert expectations[0]["meta"] == {"dq.rule_id": "rule-edges", "dq.artifact_key": "ak-edges"}

    with pytest.raises(GxExpectationBuildError, match="non-literal expression RHS"):
        build_gx_expectations_from_intermediate_model({"filter": {"logicalOperators": [], "predicates": [{"field": "score", "operator": "=", "value": "other", "valueType": "expression"}]}})
    with pytest.raises(GxExpectationBuildError, match="Numeric comparison requires numeric literal"):
        build_gx_expectations_from_intermediate_model({"filter": {"logicalOperators": [], "predicates": [{"field": "score", "operator": ">=", "value": "'bad'", "valueType": "string"}]}})
    with pytest.raises(GxExpectationBuildError, match="RLIKE regex literal is empty"):
        build_gx_expectations_from_intermediate_model({"filter": {"logicalOperators": [], "predicates": [{"field": "code", "operator": "RLIKE", "value": "''", "valueType": "string"}]}})
    with pytest.raises(GxExpectationBuildError, match="Unsupported predicate operator"):
        build_gx_expectations_from_intermediate_model({"filter": {"logicalOperators": [], "predicates": [{"field": "code", "operator": "EXISTS", "value": "1", "valueType": "number"}]}})


def test_build_gx_expectations_from_intermediate_model_attaches_or_row_condition() -> None:
    expectations = build_gx_expectations_from_intermediate_model(
        {
            "filter": {
                "logicalOperators": ["OR"],
                "predicates": [
                    {"field": "currency", "operator": "=", "value": "'USD'", "valueType": "string"},
                    {"field": "currency", "operator": "=", "value": "'EUR'", "valueType": "string"},
                ],
                "ast": {
                    "nodeType": "logical",
                    "operator": "OR",
                    "left": {
                        "nodeType": "predicate",
                        "field": "currency",
                        "operator": "=",
                        "value": "'USD'",
                        "valueType": "string",
                    },
                    "right": {
                        "nodeType": "predicate",
                        "field": "currency",
                        "operator": "=",
                        "value": "'EUR'",
                        "valueType": "string",
                    },
                },
            }
        },
        rule_id="rule-or",
        artifact_key="ak-or",
    )

    assert [item["expectation_type"] for item in expectations] == [
        "expect_column_values_to_be_in_set",
        "expect_column_values_to_be_in_set",
    ]
    assert expectations[0]["kwargs"]["row_condition"]["type"] == "or"
    assert len(expectations[0]["kwargs"]["row_condition"]["conditions"]) == 2


@pytest.mark.parametrize(
    ("expression", "expected_type", "expected_kwargs"),
    [
        (
            "REGEXP_MATCHES(email, '^[^@]+@[^@]+\\.[^@]+$')",
            "expect_column_values_to_match_regex",
            {"column": "email", "regex": "^[^@]+@[^@]+\\.[^@]+$"},
        ),
        (
            "DATEDIFF(NOW(), created_at) <= 1",
            "expect_column_values_to_be_within_past_days",
            {"column": "created_at", "max_days_old": 1, "anchor": "now"},
        ),
        (
            "TIMESTAMPDIFF(HOUR, start_date, end_date) <= 24",
            "expect_column_pair_values_to_have_max_lag_hours",
            {"column": "end_date", "start_column": "start_date", "max_hours": 24},
        ),
        (
            "created_at <= NOW()",
            "expect_column_values_to_not_be_in_future",
            {"column": "created_at"},
        ),
    ],
)
def test_build_gx_expectations_from_intermediate_model_translates_function_expressions(
    expression: str,
    expected_type: str,
    expected_kwargs: dict[str, object],
) -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-function-translation",
        rule_version_id="rv-function-translation",
        filter_expression=expression,
    )

    expectations = build_gx_expectations_from_intermediate_model(intermediate)

    assert len(expectations) == 1
    assert expectations[0]["expectation_type"] == expected_type
    assert expectations[0]["kwargs"] == expected_kwargs


def test_build_gx_expectations_from_intermediate_model_translates_compound_uniqueness_window() -> None:
    intermediate = compile_rule_to_intermediate_model(
        rule_id="rule-uniqueness-window",
        rule_version_id="rv-uniqueness-window",
        filter_expression="COUNT(*) OVER (PARTITION BY customer_id, email) = 1",
    )

    expectations = build_gx_expectations_from_intermediate_model(intermediate)

    assert expectations == [
        {
            "expectation_type": "expect_compound_columns_to_be_unique",
            "kwargs": {"column": "customer_id", "columns": ["customer_id", "email"]},
            "meta": {},
        }
    ]
