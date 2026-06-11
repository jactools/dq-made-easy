from __future__ import annotations

import pytest

import app.application.services.gx_expectations as gx_mod


def test_literal_and_list_parsers_cover_success_and_failure_paths() -> None:
    assert gx_mod._strip_sql_string_quotes("'a''b'") == "a'b"
    assert gx_mod._strip_sql_string_quotes('"a\\\"b\\\\c"') == 'a"b\\c'
    assert gx_mod._strip_sql_string_quotes("plain") == "plain"

    assert gx_mod._parse_sql_literal("true") is True
    assert gx_mod._parse_sql_literal("FALSE") is False
    assert gx_mod._parse_sql_literal("12") == 12
    assert gx_mod._parse_sql_literal("12.5") == 12.5
    assert gx_mod._parse_sql_literal("NULL") is None
    assert gx_mod._parse_sql_literal("'ok'") == "ok"

    with pytest.raises(gx_mod.GxExpectationBuildError, match="Empty literal"):
        gx_mod._parse_sql_literal("   ")

    with pytest.raises(gx_mod.GxExpectationBuildError, match="Unsupported literal"):
        gx_mod._parse_sql_literal("status")

    assert gx_mod._parse_in_list("('A', 'B''C', 3)") == ["A", "B'C", 3]

    with pytest.raises(gx_mod.GxExpectationBuildError, match="parenthesized"):
        gx_mod._parse_in_list("'A','B'")

    with pytest.raises(gx_mod.GxExpectationBuildError, match="empty"):
        gx_mod._parse_in_list("()")

    with pytest.raises(gx_mod.GxExpectationBuildError, match="non-literal expressions"):
        gx_mod._parse_in_list("(CAST(status AS TEXT))")

    with pytest.raises(gx_mod.GxExpectationBuildError, match="must not include NULL"):
        gx_mod._parse_in_list("('A', NULL)")

    assert gx_mod._parse_between_bounds("1 AND 2") == (1, 2)

    with pytest.raises(gx_mod.GxExpectationBuildError, match="<lower> AND <upper>"):
        gx_mod._parse_between_bounds("1,2")

    with pytest.raises(gx_mod.GxExpectationBuildError, match="must not be NULL"):
        gx_mod._parse_between_bounds("NULL AND 2")


def test_function_and_regex_helpers_cover_validation_paths() -> None:
    assert gx_mod._split_function_arguments("") == []
    assert gx_mod._split_function_arguments("field_one, wrap(inner, arg), 'a,b'") == ["field_one", "wrap(inner, arg)", "'a,b'"]

    assert gx_mod._parse_function_call("TRIM(customer.email)") == ("TRIM", ["customer.email"])
    assert gx_mod._parse_function_call("REGEXP_MATCHES(email, '.*@.*', 'im')") == ("REGEXP_MATCHES", ["email", "'.*@.*'", "'im'"])
    assert gx_mod._parse_function_call("not-a-function") is None

    assert gx_mod._normalize_regex_flags("i m") == "im"
    with pytest.raises(gx_mod.GxExpectationBuildError, match="only supports regex flags"):
        gx_mod._normalize_regex_flags("z")

    assert gx_mod._compose_regex_pattern(".*@.*", flags="im") == "(?im).*@.*"
    assert gx_mod._compose_regex_pattern(".*@.*") == ".*@.*"

    assert gx_mod._parse_uniqueness_columns("COUNT(*) OVER (PARTITION BY a, b) = 1") == ["a", "b"]
    assert gx_mod._parse_uniqueness_columns("something else") is None


def test_field_ref_parser_covers_wrapped_typecast_and_invalid_inputs() -> None:
    assert gx_mod._parse_field_ref("TRIM(customer.email)") == gx_mod._FieldRef(column="email", wrapper="TRIM")
    assert gx_mod._parse_field_ref("customer.email::text") == gx_mod._FieldRef(column="email")
    assert gx_mod._parse_field_ref("customer_email") == gx_mod._FieldRef(column="customer_email")

    with pytest.raises(gx_mod.GxExpectationBuildError, match="Predicate field is missing"):
        gx_mod._parse_field_ref("   ")

    with pytest.raises(gx_mod.GxExpectationBuildError, match="Unsupported field reference"):
        gx_mod._parse_field_ref("customer-email")