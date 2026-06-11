from __future__ import annotations

import importlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class GxExpectationBuildError(ValueError):
    pass


@dataclass(frozen=True)
class _FieldRef:
    column: str
    wrapper: str | None = None


@dataclass(frozen=True)
class _RenderedCondition:
    rendered: str
    serialized: dict[str, Any]


_SIMPLE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DOTTED_IDENT_RE = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*\.)+[A-Za-z_][A-Za-z0-9_]*$")
_TYPECAST_RE = re.compile(r"^(?P<base>.+?)(?:::([A-Za-z_][A-Za-z0-9_]*))+$$")
_WRAPPER_RE = re.compile(r"^(?P<wrapper>TRIM|LOWER|UPPER)\((?P<inner>.+)\)$", re.IGNORECASE)
_FUNCTION_CALL_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\((?P<args>.*)\)$", re.IGNORECASE)
_UNIQUENESS_WINDOW_RE = re.compile(
    r"^\s*COUNT\(\*\)\s+OVER\s*\(\s*PARTITION\s+BY\s+(?P<columns>[A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*)\s*\)\s*=\s*1\s*$",
    re.IGNORECASE,
)


def _strip_sql_string_quotes(value: str) -> str:
    raw = value.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
        inner = raw[1:-1]
        if raw[0] == "'":
            return inner.replace("''", "'")
        # Minimal unescape for double-quoted strings.
        return inner.replace('\\"', '"').replace('\\\\', '\\')
    return raw


def _parse_sql_literal(value: str) -> Any:
    raw = value.strip()
    if not raw:
        raise GxExpectationBuildError("Empty literal")

    if re.fullmatch(r"(?i:true|false)", raw):
        return raw.lower() == "true"

    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)

    if raw.upper() == "NULL":
        return None

    if (raw.startswith("'") and raw.endswith("'")) or (raw.startswith('"') and raw.endswith('"')):
        return _strip_sql_string_quotes(raw)

    raise GxExpectationBuildError(f"Unsupported literal: {raw}")


def _parse_in_list(value: str) -> list[Any]:
    raw = value.strip()
    if not (raw.startswith("(") and raw.endswith(")")):
        raise GxExpectationBuildError(f"IN list must be parenthesized, got: {raw}")

    inner = raw[1:-1].strip()
    if not inner:
        raise GxExpectationBuildError("IN list is empty")

    items: list[str] = []
    buf: list[str] = []
    in_quote: str | None = None
    depth = 0
    i = 0
    while i < len(inner):
        ch = inner[i]
        if in_quote:
            buf.append(ch)
            if ch == in_quote:
                if in_quote == "'" and i + 1 < len(inner) and inner[i + 1] == "'":
                    buf.append("'")
                    i += 1
                else:
                    in_quote = None
            i += 1
            continue

        if ch in {"'", '"'}:
            in_quote = ch
            buf.append(ch)
            i += 1
            continue

        if ch == "(":
            depth += 1
            buf.append(ch)
            i += 1
            continue
        if ch == ")":
            depth -= 1
            buf.append(ch)
            i += 1
            continue
        if ch == "," and depth == 0:
            item = "".join(buf).strip()
            if item:
                items.append(item)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        items.append(tail)

    # Reject nested expressions like CAST(...) for now.
    if any("(" in item and not item.strip().startswith(("'", '"')) for item in items):
        raise GxExpectationBuildError(f"IN list contains non-literal expressions: {raw}")

    parsed = [_parse_sql_literal(item) for item in items]
    if any(item is None for item in parsed):
        raise GxExpectationBuildError("IN list must not include NULL")
    return parsed


def _parse_between_bounds(value: str) -> tuple[Any, Any]:
    raw = value.strip()
    match = re.match(r"^(?P<lower>.+?)\s+AND\s+(?P<upper>.+?)$", raw, flags=re.IGNORECASE)
    if not match:
        raise GxExpectationBuildError(f"BETWEEN value must be '<lower> AND <upper>', got: {raw}")
    lower = _parse_sql_literal(match.group("lower").strip())
    upper = _parse_sql_literal(match.group("upper").strip())
    if lower is None or upper is None:
        raise GxExpectationBuildError("BETWEEN bounds must not be NULL")
    return lower, upper


def _split_function_arguments(args: str) -> list[str]:
    inner = str(args or "").strip()
    if not inner:
        return []

    items: list[str] = []
    buffer: list[str] = []
    in_quote: str | None = None
    depth = 0
    index = 0

    while index < len(inner):
        char = inner[index]
        if in_quote:
            buffer.append(char)
            if char == in_quote:
                if in_quote == "'" and index + 1 < len(inner) and inner[index + 1] == "'":
                    buffer.append("'")
                    index += 1
                else:
                    in_quote = None
            index += 1
            continue

        if char in {"'", '"'}:
            in_quote = char
            buffer.append(char)
            index += 1
            continue

        if char == "(":
            depth += 1
            buffer.append(char)
            index += 1
            continue

        if char == ")":
            depth -= 1
            buffer.append(char)
            index += 1
            continue

        if char == "," and depth == 0:
            item = "".join(buffer).strip()
            if item:
                items.append(item)
            buffer = []
            index += 1
            continue

        buffer.append(char)
        index += 1

    tail = "".join(buffer).strip()
    if tail:
        items.append(tail)
    return items


def _parse_function_call(field: str) -> tuple[str, list[str]] | None:
    raw = str(field or "").strip()
    match = _FUNCTION_CALL_RE.match(raw)
    if not match:
        return None
    return match.group("name").upper(), _split_function_arguments(match.group("args"))


def _normalize_regex_flags(flags: str) -> str:
    supported = {"i", "m", "s"}
    normalized = "".join(char for char in str(flags or "") if not char.isspace())
    unsupported = [char for char in normalized if char not in supported]
    if unsupported:
        raise GxExpectationBuildError("REGEXP_MATCHES only supports regex flags 'i', 'm', and 's'")
    return normalized


def _compose_regex_pattern(pattern: str, *, flags: str = "") -> str:
    prefix = f"(?{flags})" if flags else ""
    return f"{prefix}{pattern}"


def _parse_uniqueness_columns(expression: str) -> list[str] | None:
    match = _UNIQUENESS_WINDOW_RE.fullmatch(str(expression or "").strip())
    if not match:
        return None
    columns = [column.strip() for column in match.group("columns").split(",") if column.strip()]
    return columns or None


def _parse_field_ref(field: str) -> _FieldRef:
    raw = str(field or "").strip()
    if not raw:
        raise GxExpectationBuildError("Predicate field is missing")

    wrapper_match = _WRAPPER_RE.match(raw)
    wrapper = None
    if wrapper_match:
        wrapper = wrapper_match.group("wrapper").upper()
        raw = wrapper_match.group("inner").strip()

    typecast_match = _TYPECAST_RE.match(raw)
    if typecast_match:
        raw = typecast_match.group("base").strip()

    if _SIMPLE_IDENT_RE.match(raw):
        return _FieldRef(column=raw, wrapper=wrapper)

    if _DOTTED_IDENT_RE.match(raw):
        return _FieldRef(column=raw.rsplit(".", 1)[-1], wrapper=wrapper)

    raise GxExpectationBuildError(f"Unsupported field reference for GX translation: {field}")


def _build_expression_based_expectation(
    *,
    predicate: Mapping[str, Any],
    meta: Mapping[str, Any],
) -> dict[str, Any] | None:
    field_raw = str(predicate.get("field") or "").strip()
    operator = str(predicate.get("operator") or "").strip().upper()
    value_raw = str(predicate.get("value") or "").strip()
    value_type = str(predicate.get("valueType") or "").strip().lower()

    function_call = _parse_function_call(field_raw)
    if function_call is not None:
        function_name, arguments = function_call

        if function_name == "REGEXP_MATCHES":
            if operator != "IS TRUE":
                raise GxExpectationBuildError(
                    f"REGEXP_MATCHES translation only supports IS TRUE predicates, got: {operator}"
                )
            if len(arguments) not in {2, 3}:
                raise GxExpectationBuildError("REGEXP_MATCHES requires an attribute, a pattern, and optional flags")
            column = _parse_field_ref(arguments[0]).column
            pattern = _strip_sql_string_quotes(arguments[1])
            flags = _normalize_regex_flags(_strip_sql_string_quotes(arguments[2])) if len(arguments) == 3 else ""
            return {
                "expectation_type": "expect_column_values_to_match_regex",
                "kwargs": {"column": column, "regex": _compose_regex_pattern(pattern, flags=flags)},
                "meta": dict(meta),
            }

        if function_name == "DATEDIFF":
            if len(arguments) != 2:
                raise GxExpectationBuildError("DATEDIFF requires a reference and an attribute")
            reference = re.sub(r"\s+", "", arguments[0]).upper()
            if reference not in {"NOW()", "CURRENT_DATE", "CURRENT_DATE()"}:
                raise GxExpectationBuildError(
                    f"DATEDIFF translation only supports NOW() or CURRENT_DATE references, got: {arguments[0]}"
                )
            if operator not in {"<=", "<"}:
                raise GxExpectationBuildError(f"DATEDIFF translation only supports <= or < comparisons, got: {operator}")
            literal = _parse_sql_literal(value_raw)
            if not isinstance(literal, (int, float)):
                raise GxExpectationBuildError(f"DATEDIFF translation requires a numeric literal, got: {value_raw}")
            return {
                "expectation_type": "expect_column_values_to_be_within_past_days",
                "kwargs": {
                    "column": _parse_field_ref(arguments[1]).column,
                    "max_days_old": int(literal),
                    "anchor": "now",
                },
                "meta": dict(meta),
            }

        if function_name == "TIMESTAMPDIFF":
            if len(arguments) != 3:
                raise GxExpectationBuildError("TIMESTAMPDIFF requires a unit, a start attribute, and an end attribute")
            unit = re.sub(r"\s+", "", _strip_sql_string_quotes(arguments[0])).upper()
            if unit != "HOUR":
                raise GxExpectationBuildError(f"TIMESTAMPDIFF translation only supports HOUR units, got: {arguments[0]}")
            if operator not in {"<=", "<"}:
                raise GxExpectationBuildError(
                    f"TIMESTAMPDIFF translation only supports <= or < comparisons, got: {operator}"
                )
            literal = _parse_sql_literal(value_raw)
            if not isinstance(literal, (int, float)):
                raise GxExpectationBuildError(f"TIMESTAMPDIFF translation requires a numeric literal, got: {value_raw}")
            return {
                "expectation_type": "expect_column_pair_values_to_have_max_lag_hours",
                "kwargs": {
                    "column": _parse_field_ref(arguments[2]).column,
                    "start_column": _parse_field_ref(arguments[1]).column,
                    "max_hours": int(literal),
                },
                "meta": dict(meta),
            }

    if operator in {"<=", "<"} and value_type == "expression":
        normalized_rhs = re.sub(r"\s+", "", value_raw).upper()
        if normalized_rhs in {"NOW()", "CURRENT_DATE", "CURRENT_DATE()"}:
            return {
                "expectation_type": "expect_column_values_to_not_be_in_future",
                "kwargs": {"column": _parse_field_ref(field_raw).column},
                "meta": dict(meta),
            }

    return None


def _sql_like_to_regex(pattern: str) -> str:
    raw = _strip_sql_string_quotes(pattern)
    regex_parts: list[str] = ["^"]
    for ch in raw:
        if ch == "%":
            regex_parts.append(".*")
        elif ch == "_":
            regex_parts.append(".")
        else:
            regex_parts.append(re.escape(ch))
    regex_parts.append("$")
    return "".join(regex_parts)


def _python_literal(value: Any) -> str:
    return repr(value)


def _require_filter_ast(intermediate_model: dict[str, Any]) -> dict[str, Any]:
    filter_payload = intermediate_model.get("filter") if isinstance(intermediate_model, dict) else None
    if not isinstance(filter_payload, dict):
        raise GxExpectationBuildError("Intermediate model is missing filter")

    expression_ast = filter_payload.get("ast")
    if not isinstance(expression_ast, dict):
        raise GxExpectationBuildError("Intermediate model is missing filter AST")
    return expression_ast


def _require_filter_payload(intermediate_model: dict[str, Any]) -> dict[str, Any]:
    filter_payload = intermediate_model.get("filter") if isinstance(intermediate_model, dict) else None
    if not isinstance(filter_payload, dict):
        raise GxExpectationBuildError("Intermediate model is missing filter")
    return filter_payload


def _literal_from_ast_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return _parse_sql_literal(str(value.get("value") or "").strip())
    if isinstance(value, (str, int, float, bool)):
        return _parse_sql_literal(str(value).strip()) if isinstance(value, str) else value
    raise GxExpectationBuildError(f"Unsupported literal payload for GX row_condition prototype: {value!r}")


def _list_from_ast_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [_literal_from_ast_value(item) for item in value]
    if isinstance(value, str):
        return _parse_in_list(value)
    raise GxExpectationBuildError(f"Unsupported IN-list payload for GX row_condition prototype: {value!r}")


def _between_bounds_from_ast_value(value: Any) -> tuple[Any, Any]:
    if isinstance(value, dict):
        lower = _literal_from_ast_value(value.get("lower"))
        upper = _literal_from_ast_value(value.get("upper"))
        if lower is None or upper is None:
            raise GxExpectationBuildError("BETWEEN bounds must not be NULL")
        return lower, upper
    if isinstance(value, str):
        return _parse_between_bounds(value)
    raise GxExpectationBuildError(f"Unsupported BETWEEN payload for GX row_condition prototype: {value!r}")


def _rendered_comparison(*, column: str, operator: str, parameter: Any) -> _RenderedCondition:
    return _RenderedCondition(
        rendered=(
            f"Column({_python_literal(column)}).is_in({_python_literal(parameter)})"
            if operator == "IN"
            else f"Column({_python_literal(column)}).is_not_in({_python_literal(parameter)})"
            if operator == "NOT_IN"
            else f"Column({_python_literal(column)}) {operator} {_python_literal(parameter)}"
        ),
        serialized={
            "type": "comparison",
            "column": {"name": column},
            "operator": operator,
            "parameter": parameter,
        },
    )


def _rendered_nullity(*, column: str, is_null: bool) -> _RenderedCondition:
    return _RenderedCondition(
        rendered=f"Column({_python_literal(column)}).{'is_null' if is_null else 'is_not_null'}()",
        serialized={
            "type": "nullity",
            "column": {"name": column},
            "is_null": is_null,
        },
    )


def _requires_pass_through_row_condition(node: dict[str, Any]) -> bool:
    node_type = str(node.get("nodeType") or "")
    if node_type == "predicate":
        field = str(node.get("field") or "").strip()
        if _WRAPPER_RE.match(field):
            return True
        operator = str(node.get("operator") or "").strip().upper()
        return operator in {"LIKE", "NOT LIKE", "RLIKE", "NOT RLIKE"}

    if node_type == "logical":
        left = node.get("left")
        right = node.get("right")
        return (
            isinstance(left, dict)
            and _requires_pass_through_row_condition(left)
        ) or (
            isinstance(right, dict)
            and _requires_pass_through_row_condition(right)
        )

    if node_type == "unary":
        operand = node.get("operand")
        return isinstance(operand, dict) and _requires_pass_through_row_condition(operand)

    return False


def _ast_to_rendered_condition_blocks(node: dict[str, Any]) -> list[list[_RenderedCondition]]:
    node_type = str(node.get("nodeType") or "")
    if node_type == "predicate":
        return _predicate_to_row_condition_blocks(node)

    if node_type == "logical":
        operator = str(node.get("operator") or "").upper()
        left = node.get("left")
        right = node.get("right")
        if not isinstance(left, dict) or not isinstance(right, dict):
            raise GxExpectationBuildError("Logical AST node is missing an operand")

        left_blocks = _ast_to_rendered_condition_blocks(left)
        right_blocks = _ast_to_rendered_condition_blocks(right)
        if operator == "AND":
            merged: list[list[_RenderedCondition]] = []
            for left_block in left_blocks:
                for right_block in right_blocks:
                    merged.append([*left_block, *right_block])
            return merged
        if operator == "OR":
            return [*left_blocks, *right_blocks]
        raise GxExpectationBuildError(f"Unsupported logical operator for GX row_condition prototype: {operator}")

    if node_type == "unary":
        operator = str(node.get("operator") or "").upper()
        raise GxExpectationBuildError(
            f"GX row_condition prototype does not support unary operator '{operator or 'UNKNOWN'}'"
        )

    raise GxExpectationBuildError(f"Unsupported AST node type for GX row_condition prototype: {node_type or 'UNKNOWN'}")


def _predicate_to_row_condition_blocks(predicate: dict[str, Any]) -> list[list[_RenderedCondition]]:
    operator = str(predicate.get("operator") or "").strip().upper()
    field = _parse_field_ref(str(predicate.get("field") or ""))
    value = predicate.get("value")
    value_raw = str(value or "").strip()
    value_type = str(predicate.get("valueType") or "").strip().lower()

    if field.wrapper is not None:
        raise GxExpectationBuildError(
            f"GX row_condition prototype does not support wrapped field references like '{predicate.get('field')}'"
        )

    if operator == "IS NOT NULL":
        return [[_rendered_nullity(column=field.column, is_null=False)]]
    if operator == "IS NULL":
        return [[_rendered_nullity(column=field.column, is_null=True)]]
    if operator == "IS TRUE":
        return [[_rendered_comparison(column=field.column, operator="==", parameter=True)]]

    if value_type == "expression":
        raise GxExpectationBuildError(
            f"Predicate '{predicate.get('field')}' uses non-literal expression RHS '{value_raw}'"
        )

    if operator in {"=", "!="}:
        literal = _literal_from_ast_value(value)
        return [[_rendered_comparison(column=field.column, operator="==" if operator == "=" else "!=", parameter=literal)]]

    if operator in {">", ">=", "<", "<="}:
        literal = _literal_from_ast_value(value)
        if not isinstance(literal, (int, float)):
            raise GxExpectationBuildError(f"Numeric comparison requires numeric literal, got: {value_raw}")
        return [[_rendered_comparison(column=field.column, operator=operator, parameter=literal)]]

    if operator in {"BETWEEN", "NOT BETWEEN"}:
        lower, upper = _between_bounds_from_ast_value(value)
        lower_condition = _rendered_comparison(column=field.column, operator=">=", parameter=lower)
        upper_condition = _rendered_comparison(column=field.column, operator="<=", parameter=upper)
        if operator == "BETWEEN":
            return [[lower_condition, upper_condition]]
        return [
            [_rendered_comparison(column=field.column, operator="<", parameter=lower)],
            [_rendered_comparison(column=field.column, operator=">", parameter=upper)],
        ]

    if operator in {"IN", "NOT IN"}:
        values = _list_from_ast_value(value)
        return [[_rendered_comparison(column=field.column, operator="IN" if operator == "IN" else "NOT_IN", parameter=values)]]

    raise GxExpectationBuildError(
        f"GX row_condition prototype does not support predicate operator '{operator}'"
    )


def _combine_serialized_condition_blocks(blocks: list[list[_RenderedCondition]]) -> dict[str, Any]:
    serialized_blocks: list[dict[str, Any]] = []
    for block in blocks:
        block_conditions = [condition.serialized for condition in block]
        if len(block_conditions) == 1:
            serialized_blocks.append(block_conditions[0])
        else:
            serialized_blocks.append({"type": "and", "conditions": block_conditions})

    if len(serialized_blocks) == 1:
        return serialized_blocks[0]
    return {"type": "or", "conditions": serialized_blocks}


def _build_pass_through_row_condition_artifact(filter_payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized_expression = str(filter_payload.get("normalized") or filter_payload.get("source") or "").strip()
    if not normalized_expression:
        raise GxExpectationBuildError("GX row_condition prototype cannot build a pass-through filter without a normalized expression")

    return {
        "kind": "gx_row_condition",
        "prototype": True,
        "syntax": "great_expectations.row_conditions",
        "source": normalized_expression,
        "conditionBlocks": None,
        "conditionBlockCount": None,
        "conditionStatementCount": None,
        "serializedCondition": {
            "type": "pass_through",
            "pass_through_filter": normalized_expression,
        },
        "representation": "pass_through",
    }


def build_gx_row_condition_from_intermediate_model(
    intermediate_model: dict[str, Any],
    *,
    max_condition_blocks: int = 16,
    max_condition_statements: int = 100,
) -> dict[str, Any]:
    """Compile a DQ-7 filter AST into a serializable GX row_condition prototype artifact.

    The returned object is an intermediate artifact for future GX integration. It is not,
    by itself, a standalone GX expectation or a replacement for the current decomposed
    expectation translation path.
    """

    filter_payload = _require_filter_payload(intermediate_model)
    expression_ast = _require_filter_ast(intermediate_model)
    if _requires_pass_through_row_condition(expression_ast):
        return _build_pass_through_row_condition_artifact(filter_payload)

    blocks = _ast_to_rendered_condition_blocks(expression_ast)
    if not blocks:
        raise GxExpectationBuildError("GX row_condition prototype produced no condition blocks")
    if len(blocks) > max_condition_blocks:
        raise GxExpectationBuildError(
            f"GX row_condition prototype expands to {len(blocks)} blocks which exceeds the limit of {max_condition_blocks}"
        )

    statement_blocks: list[list[str]] = []
    statement_count = 0
    for block in blocks:
        statements = [condition.rendered for condition in block]
        statement_blocks.append(statements)
        statement_count += len(statements)

    if statement_count > max_condition_statements:
        raise GxExpectationBuildError(
            f"GX row_condition prototype requires {statement_count} condition statements which exceeds the limit of {max_condition_statements}"
        )

    rendered_blocks = [" & ".join(f"({statement})" for statement in statements) for statements in statement_blocks]
    source = " | ".join(f"({rendered_block})" for rendered_block in rendered_blocks)

    return {
        "kind": "gx_row_condition",
        "prototype": True,
        "syntax": "great_expectations.row_conditions",
        "source": source,
        "conditionBlocks": statement_blocks,
        "conditionBlockCount": len(statement_blocks),
        "conditionStatementCount": statement_count,
        "serializedCondition": _combine_serialized_condition_blocks(blocks),
        "representation": "structured",
    }


def lower_gx_row_condition_artifact(artifact: Mapping[str, Any]) -> Any:
    """Lower a serialized GX row-condition prototype artifact into a live GX object.

    This requires Great Expectations to be importable at runtime and intentionally
    fails fast if the artifact shape is invalid or GX is unavailable.
    """

    if str(artifact.get("kind") or "") != "gx_row_condition":
        raise GxExpectationBuildError("Row-condition artifact kind must be 'gx_row_condition'")

    serialized_condition = artifact.get("serializedCondition")
    source = str(artifact.get("source") or "").strip()
    if not source and not isinstance(serialized_condition, Mapping):
        raise GxExpectationBuildError("Row-condition artifact source is missing")

    try:
        row_conditions_module = importlib.import_module("great_expectations.expectations.row_conditions")
    except ModuleNotFoundError as exc:
        raise GxExpectationBuildError(
            "Great Expectations row_conditions module is unavailable; install great-expectations to lower the artifact"
        ) from exc

    deserialize_row_condition = getattr(row_conditions_module, "deserialize_row_condition", None)
    if callable(deserialize_row_condition) and isinstance(serialized_condition, Mapping):
        try:
            return deserialize_row_condition(dict(serialized_condition))
        except Exception as exc:  # pragma: no cover - exact GX runtime types vary by version
            raise GxExpectationBuildError(f"Failed to lower GX row-condition artifact: {exc}") from exc

    column_factory = getattr(row_conditions_module, "Column", None)
    if column_factory is None:
        raise GxExpectationBuildError("Great Expectations row_conditions.Column is unavailable")

    try:
        return eval(source, {"__builtins__": {}}, {"Column": column_factory})
    except Exception as exc:  # pragma: no cover - exact GX runtime types vary by version
        raise GxExpectationBuildError(f"Failed to lower GX row-condition artifact: {exc}") from exc


def build_gx_serialized_row_condition_from_intermediate_model(intermediate_model: dict[str, Any]) -> dict[str, Any]:
    artifact = build_gx_row_condition_from_intermediate_model(intermediate_model)
    serialized_condition = artifact.get("serializedCondition")
    if not isinstance(serialized_condition, dict):
        raise GxExpectationBuildError("GX row-condition artifact is missing serializedCondition")
    return dict(serialized_condition)


_ROW_CONDITION_COMPATIBLE_EXPECTATION_TYPES = {
    "expect_column_values_to_not_be_null",
    "expect_column_values_to_be_null",
    "expect_column_values_to_be_in_set",
    "expect_column_values_to_not_be_in_set",
    "expect_column_values_to_be_between",
    "expect_column_values_to_not_be_between",
    "expect_column_proportion_of_non_null_values_to_be_between",
    "expect_column_values_to_be_between_for_other_column_value",
    "expect_column_values_to_be_in_set_for_other_column_value",
    "expect_column_values_to_equal_other_column",
    "expect_column_values_to_equal_other_column_case_insensitive",
    "expect_column_pair_values_to_be_equal",
    "expect_column_values_to_be_within_numeric_tolerance_of_other_column",
    "expect_column_timestamps_to_be_within_tolerance_of_other_column",
    "expect_column_values_to_match_regex",
    "expect_column_values_to_not_match_regex",
    "expect_column_values_to_be_unique",
    "expect_compound_columns_to_be_unique",
    "expect_column_values_to_be_within_past_days",
    "expect_column_pair_values_to_have_max_lag_hours",
    "expect_column_values_to_not_be_in_future",
    "expect_table_row_count_to_be_between",
}


def _merge_serialized_row_conditions(
    existing_row_condition: Mapping[str, Any] | None,
    attached_row_condition: Mapping[str, Any],
) -> dict[str, Any]:
    if existing_row_condition is None:
        return dict(attached_row_condition)

    existing_conditions: list[dict[str, Any]] = []
    if str(existing_row_condition.get("type") or "").strip().lower() == "and":
        raw_conditions = existing_row_condition.get("conditions")
        if isinstance(raw_conditions, list):
            existing_conditions.extend(
                dict(condition) for condition in raw_conditions if isinstance(condition, Mapping)
            )
    if not existing_conditions:
        existing_conditions.append(dict(existing_row_condition))

    attached_conditions: list[dict[str, Any]] = []
    if str(attached_row_condition.get("type") or "").strip().lower() == "and":
        raw_conditions = attached_row_condition.get("conditions")
        if isinstance(raw_conditions, list):
            attached_conditions.extend(
                dict(condition) for condition in raw_conditions if isinstance(condition, Mapping)
            )
    if not attached_conditions:
        attached_conditions.append(dict(attached_row_condition))

    merged_conditions = existing_conditions + attached_conditions
    if len(merged_conditions) == 1:
        return merged_conditions[0]
    return {
        "type": "and",
        "conditions": merged_conditions,
    }


def attach_gx_row_condition_to_expectations(
    expectations: list[dict[str, Any]],
    *,
    intermediate_model: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if intermediate_model is None:
        return expectations

    serialized_row_condition = build_gx_serialized_row_condition_from_intermediate_model(dict(intermediate_model))
    attached: list[dict[str, Any]] = []
    for expectation in expectations:
        expectation_type = str(expectation.get("expectation_type") or "").strip()
        if expectation_type not in _ROW_CONDITION_COMPATIBLE_EXPECTATION_TYPES:
            attached.append(expectation)
            continue

        kwargs = expectation.get("kwargs") if isinstance(expectation.get("kwargs"), dict) else None
        primary_column = ""
        if kwargs is not None:
            primary_column = str(kwargs.get("column") or kwargs.get("column_A") or "").strip()
        if kwargs is None or (not primary_column and expectation_type != "expect_table_row_count_to_be_between"):
            attached.append(expectation)
            continue

        existing_row_condition = kwargs.get("row_condition")
        if existing_row_condition is not None and not isinstance(existing_row_condition, Mapping):
            attached.append(expectation)
            continue

        merged_row_condition = _merge_serialized_row_conditions(
            existing_row_condition=existing_row_condition,
            attached_row_condition=serialized_row_condition,
        )

        attached.append(
            {
                **expectation,
                "kwargs": {
                    **kwargs,
                    "row_condition": merged_row_condition,
                },
            }
        )

    return attached


def build_gx_row_condition_meta_from_intermediate_model(intermediate_model: dict[str, Any]) -> dict[str, Any]:
    try:
        prototype = build_gx_row_condition_from_intermediate_model(intermediate_model)
    except GxExpectationBuildError as exc:
        return {
            "status": "unsupported",
            "prototype": None,
            "error": str(exc),
            "liveLowering": {
                "status": "unavailable",
                "error": "Row-condition prototype unavailable",
            },
        }

    try:
        live_condition = lower_gx_row_condition_artifact(prototype)
    except GxExpectationBuildError as exc:
        live_lowering = {
            "status": "unavailable",
            "error": str(exc),
        }
    else:
        live_lowering = {
            "status": "available",
            "pythonType": type(live_condition).__name__,
            "repr": repr(live_condition),
        }

    return {
        "status": "available",
        "prototype": prototype,
        "error": None,
        "liveLowering": live_lowering,
    }


def _flatten_ast_branches(node: dict[str, Any], *, operator: str) -> list[dict[str, Any]]:
    node_type = str(node.get("nodeType") or "").strip().lower()
    if node_type != "logical":
        return [node]

    current_operator = str(node.get("operator") or "").strip().upper()
    left = node.get("left")
    right = node.get("right")
    if not isinstance(left, dict) or not isinstance(right, dict):
        raise GxExpectationBuildError("Logical AST node is missing an operand")

    if current_operator == operator:
        return [*_flatten_ast_branches(left, operator=operator), *_flatten_ast_branches(right, operator=operator)]
    return [node]


def _merge_literal_values(values: list[Any]) -> list[Any]:
    merged: list[Any] = []
    for value in values:
        if value not in merged:
            merged.append(value)
    return merged


def _build_conditional_allowlist_expectations_from_intermediate_model(
    intermediate_model: dict[str, Any],
    *,
    meta: Mapping[str, Any],
) -> list[dict[str, Any]] | None:
    filter_payload = intermediate_model.get("filter") if isinstance(intermediate_model, dict) else None
    if not isinstance(filter_payload, dict):
        return None

    ast = filter_payload.get("ast")
    if not isinstance(ast, dict):
        return None

    try:
        branch_nodes = _flatten_ast_branches(ast, operator="OR")
    except GxExpectationBuildError:
        return None

    if len(branch_nodes) < 2:
        return None

    context_column: str | None = None
    attribute_column: str | None = None
    case_sensitive: bool | None = None
    grouped_allowlists: dict[Any, list[Any]] = {}

    for branch in branch_nodes:
        try:
            conjunct_nodes = _flatten_ast_branches(branch, operator="AND")
        except GxExpectationBuildError:
            return None

        if len(conjunct_nodes) != 2:
            return None

        context_predicate: dict[str, Any] | None = None
        allowlist_predicate: dict[str, Any] | None = None

        for predicate in conjunct_nodes:
            if not isinstance(predicate, dict):
                return None
            operator = str(predicate.get("operator") or "").strip().upper()
            field = _parse_field_ref(str(predicate.get("field") or ""))
            if operator == "=" and context_predicate is None:
                context_predicate = predicate
                if field.wrapper is not None:
                    return None
                continue
            if operator == "IN" and allowlist_predicate is None:
                allowlist_predicate = predicate
                if field.wrapper not in {None, "LOWER"}:
                    return None
                continue

        if context_predicate is None or allowlist_predicate is None:
            return None

        context_field = _parse_field_ref(str(context_predicate.get("field") or ""))
        allowlist_field = _parse_field_ref(str(allowlist_predicate.get("field") or ""))
        if context_field.wrapper is not None or allowlist_field.column == context_field.column:
            return None

        current_case_sensitive = allowlist_field.wrapper is None
        if allowlist_field.wrapper not in {None, "LOWER"}:
            return None

        context_value = _literal_from_ast_value(context_predicate.get("value"))
        allowed_values = _list_from_ast_value(allowlist_predicate.get("value"))

        if context_column is None:
            context_column = context_field.column
        elif context_column != context_field.column:
            return None

        if attribute_column is None:
            attribute_column = allowlist_field.column
        elif attribute_column != allowlist_field.column:
            return None

        if case_sensitive is None:
            case_sensitive = current_case_sensitive
        elif case_sensitive != current_case_sensitive:
            return None

        grouped_allowlists.setdefault(context_value, [])
        grouped_allowlists[context_value].extend(allowed_values)

    if context_column is None or attribute_column is None or case_sensitive is None:
        return None

    expectations: list[dict[str, Any]] = [
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": context_column},
            "meta": dict(meta),
        },
        {
            "expectation_type": "expect_column_values_to_be_in_set",
            "kwargs": {"column": context_column, "value_set": list(grouped_allowlists.keys())},
            "meta": dict(meta),
        },
    ]

    for context_value, allowed_values in grouped_allowlists.items():
        expectations.append(
            {
                "expectation_type": "expect_column_values_to_be_in_set_for_other_column_value",
                "kwargs": {
                    "column": attribute_column,
                    "other_column": context_column,
                    "other_value": context_value,
                    "value_set": _merge_literal_values(allowed_values),
                    "case_sensitive": case_sensitive,
                },
                "meta": dict(meta),
            }
        )

    return expectations


def build_gx_expectations_from_intermediate_model(
    intermediate_model: dict[str, Any],
    *,
    rule_id: str | None = None,
    artifact_key: str | None = None,
) -> list[dict[str, Any]]:
    """Translate a rule compiler intermediate model into Great Expectations expectations.

    This is intentionally strict and fail-fast:
    - OR / unary NOT expressions are rejected (cannot be represented safely as independent expectations).
    - Predicates with non-literal RHS expressions are rejected.
    """

    filter_payload = intermediate_model.get("filter") if isinstance(intermediate_model, dict) else None
    if not isinstance(filter_payload, dict):
        raise GxExpectationBuildError("Intermediate model is missing filter")

    meta: dict[str, Any] = {}
    if rule_id:
        meta["dq.rule_id"] = rule_id
    if artifact_key:
        meta["dq.artifact_key"] = artifact_key

    normalized_expression = str(filter_payload.get("normalized") or filter_payload.get("source") or "").strip()
    uniqueness_columns = _parse_uniqueness_columns(normalized_expression)
    if uniqueness_columns is not None:
        if len(uniqueness_columns) == 1:
            return [
                {
                    "expectation_type": "expect_column_values_to_be_unique",
                    "kwargs": {"column": uniqueness_columns[0]},
                    "meta": dict(meta),
                }
            ]
        return [
            {
                "expectation_type": "expect_compound_columns_to_be_unique",
                "kwargs": {"column": uniqueness_columns[0], "columns": uniqueness_columns},
                "meta": dict(meta),
            }
        ]

    contextual_allowlist_expectations = _build_conditional_allowlist_expectations_from_intermediate_model(
        dict(intermediate_model),
        meta=meta,
    )
    if contextual_allowlist_expectations is not None:
        return contextual_allowlist_expectations

    logical_ops = filter_payload.get("logicalOperators") or []
    if not isinstance(logical_ops, list):
        logical_ops = []
    upper_ops = {str(op).upper() for op in logical_ops}
    has_ast = isinstance(filter_payload.get("ast"), dict)
    if "NOT" in upper_ops:
        raise GxExpectationBuildError("GX translation does not support unary NOT expressions")
    use_row_condition = "OR" in upper_ops and has_ast
    if "OR" in upper_ops and not has_ast:
        raise GxExpectationBuildError("GX translation does not support OR / unary NOT expressions")

    predicates = filter_payload.get("predicates") or []
    if not isinstance(predicates, list) or not predicates:
        raise GxExpectationBuildError("No predicates available for GX translation")

    expectations: list[dict[str, Any]] = []

    for predicate in predicates:
        if not isinstance(predicate, dict):
            raise GxExpectationBuildError("Predicate payload is invalid")

        expression_expectation = _build_expression_based_expectation(predicate=predicate, meta=meta)
        if expression_expectation is not None:
            expectations.append(expression_expectation)
            continue

        operator = str(predicate.get("operator") or "").strip().upper()
        field = _parse_field_ref(str(predicate.get("field") or ""))
        value_raw = str(predicate.get("value") or "").strip()
        value_type = str(predicate.get("valueType") or "").strip().lower()

        # Special-case TRIM(col) = '' / != '' as whitespace-only handling.
        if field.wrapper == "TRIM" and operator in {"=", "!="} and value_type == "string":
            literal = _parse_sql_literal(value_raw)
            if literal == "":
                expectations.append(
                    {
                        "expectation_type": (
                            "expect_column_values_to_not_match_regex" if operator == "!=" else "expect_column_values_to_match_regex"
                        ),
                        "kwargs": {"column": field.column, "regex": r"^\\s*$"},
                        "meta": dict(meta),
                    }
                )
                continue

        if operator == "IS NOT NULL":
            expectations.append(
                {
                    "expectation_type": "expect_column_values_to_not_be_null",
                    "kwargs": {"column": field.column},
                    "meta": dict(meta),
                }
            )
            continue

        if operator == "IS NULL":
            expectations.append(
                {
                    "expectation_type": "expect_column_values_to_be_null",
                    "kwargs": {"column": field.column},
                    "meta": dict(meta),
                }
            )
            continue

        if operator == "IS TRUE":
            expectations.append(
                {
                    "expectation_type": "expect_column_values_to_be_in_set",
                    "kwargs": {"column": field.column, "value_set": [True]},
                    "meta": dict(meta),
                }
            )
            continue

        if value_type == "expression":
            raise GxExpectationBuildError(
                f"Predicate '{predicate.get('field')}' uses non-literal expression RHS '{value_raw}'"
            )

        if operator in {"=", "!="}:
            literal = _parse_sql_literal(value_raw)
            expectation_type = (
                "expect_column_values_to_be_in_set" if operator == "=" else "expect_column_values_to_not_be_in_set"
            )
            expectations.append(
                {
                    "expectation_type": expectation_type,
                    "kwargs": {"column": field.column, "value_set": [literal]},
                    "meta": dict(meta),
                }
            )
            continue

        if operator in {">", ">=", "<", "<="}:
            literal = _parse_sql_literal(value_raw)
            if not isinstance(literal, (int, float)):
                raise GxExpectationBuildError(f"Numeric comparison requires numeric literal, got: {value_raw}")
            kwargs: dict[str, Any] = {"column": field.column}
            if operator in {">", ">="}:
                kwargs["min_value"] = literal
                if operator == ">":
                    kwargs["strict_min"] = True
            else:
                kwargs["max_value"] = literal
                if operator == "<":
                    kwargs["strict_max"] = True
            expectations.append(
                {
                    "expectation_type": "expect_column_values_to_be_between",
                    "kwargs": kwargs,
                    "meta": dict(meta),
                }
            )
            continue

        if operator in {"BETWEEN", "NOT BETWEEN"}:
            lower, upper = _parse_between_bounds(value_raw)
            expectations.append(
                {
                    "expectation_type": (
                        "expect_column_values_to_be_between"
                        if operator == "BETWEEN"
                        else "expect_column_values_to_not_be_between"
                    ),
                    "kwargs": {"column": field.column, "min_value": lower, "max_value": upper},
                    "meta": dict(meta),
                }
            )
            continue

        if operator in {"IN", "NOT IN"}:
            values = _parse_in_list(value_raw)
            expectations.append(
                {
                    "expectation_type": (
                        "expect_column_values_to_be_in_set" if operator == "IN" else "expect_column_values_to_not_be_in_set"
                    ),
                    "kwargs": {"column": field.column, "value_set": values},
                    "meta": dict(meta),
                }
            )
            continue

        if operator in {"LIKE", "NOT LIKE"}:
            regex = _sql_like_to_regex(value_raw)
            expectations.append(
                {
                    "expectation_type": (
                        "expect_column_values_to_match_regex" if operator == "LIKE" else "expect_column_values_to_not_match_regex"
                    ),
                    "kwargs": {"column": field.column, "regex": regex},
                    "meta": dict(meta),
                }
            )
            continue

        if operator in {"RLIKE", "NOT RLIKE"}:
            regex = _strip_sql_string_quotes(value_raw)
            if not regex:
                raise GxExpectationBuildError("RLIKE regex literal is empty")
            expectations.append(
                {
                    "expectation_type": (
                        "expect_column_values_to_match_regex" if operator == "RLIKE" else "expect_column_values_to_not_match_regex"
                    ),
                    "kwargs": {"column": field.column, "regex": regex},
                    "meta": dict(meta),
                }
            )
            continue

        raise GxExpectationBuildError(f"Unsupported predicate operator for GX translation: {operator}")

    if use_row_condition:
        return attach_gx_row_condition_to_expectations(expectations, intermediate_model=intermediate_model)

    return expectations

    if not expectations:
        raise GxExpectationBuildError("GX translation produced no expectations")

    return expectations
