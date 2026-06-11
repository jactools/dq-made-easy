from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.core.telemetry import set_span_attributes, traced_span

from .rule_expression import infer_alias_expectations
from .rule_expression import normalize_join_definition
from .rule_expression import validate_filter_expression

_COMPILER_VERSION = "dq-7.3.0"
_INTERMEDIATE_MODEL_SCHEMA_VERSION = "1.1.0"
_SEVERITY_ERROR = "error"
_SEVERITY_WARNING = "warning"
_SEVERITY_INFO = "info"
_DIAG_FILTER_VALIDATION = "DQ7_FILTER_VALIDATION"
_DIAG_RESERVED_KEYWORD = "DQ7_RESERVED_KEYWORD"
_DIAG_UNSUPPORTED_AGGREGATE = "DQ7_UNSUPPORTED_AGGREGATE"
_DIAG_JOIN_VALIDATION = "DQ7_JOIN_VALIDATION"
_DIAG_AST_PARSE = "DQ7_AST_PARSE"
_NON_COMPILABLE_DIAGNOSTIC_CODES = {
    _DIAG_RESERVED_KEYWORD,
    _DIAG_UNSUPPORTED_AGGREGATE,
}
_LITERAL_PATTERN = r"(?:-?\d+(?:\.\d+)?|true|false|'(?:''|[^'])*'|\"(?:\\\"|[^\"])*\")"
_TOKEN_REGEX = re.compile(
    r"""
    (?P<WS>\s+)
    |(?P<LPAREN>\()
    |(?P<RPAREN>\))
    |(?P<COMMA>,)
    |(?P<TYPECAST>::)
    |(?P<DOT>\.)
    |(?P<OP>>=|<=|!=|<>|!~|=|>|<|~)
    |(?P<SSTRING>'(?:''|[^'])*')
    |(?P<DSTRING>\"(?:\\\"|[^\"])*\")
    |(?P<NUMBER>-?\d+(?:\.\d+)?)
    |(?P<ARITH>[+\-*/])
    |(?P<IDENT>[A-Za-z_][A-Za-z0-9_]*)
    """,
    re.VERBOSE,
)
_KEYWORDS = {"AND", "OR", "NOT", "IS", "NULL", "IN", "BETWEEN", "LIKE", "RLIKE", "TRUE", "FALSE"}
_PREDICATE_COMPARISON_REGEX = re.compile(
    rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*(=|!=|>=|<=|>|<)\s*({_LITERAL_PATTERN})",
    re.IGNORECASE,
)
_PREDICATE_BETWEEN_REGEX = re.compile(
    rf"\b([A-Za-z_][A-Za-z0-9_]*)\s+(NOT\s+)?BETWEEN\s+({_LITERAL_PATTERN})\s+AND\s+({_LITERAL_PATTERN})",
    re.IGNORECASE,
)
_PREDICATE_IN_REGEX = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*)\s+(NOT\s+)?IN\s*(\([^\)]*\))",
    re.IGNORECASE,
)
_PREDICATE_LIKE_REGEX = re.compile(
    rf"\b([A-Za-z_][A-Za-z0-9_]*)\s+(NOT\s+)?(LIKE|RLIKE|~|!~)\s*({_LITERAL_PATTERN})",
    re.IGNORECASE,
)
_PREDICATE_IS_NULL_REGEX = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*)\s+IS\s+(NOT\s+)?NULL\b",
    re.IGNORECASE,
)
_REFERENTIAL_INTEGRITY_SUBQUERY_REGEX = re.compile(
    r"^\s*[A-Za-z_][A-Za-z0-9_]*\s+IN\s*\(\s*SELECT\s+[A-Za-z_][A-Za-z0-9_]*\s+FROM\s+[A-Za-z_][A-Za-z0-9_-]*\s*\)\s*$",
    re.IGNORECASE,
)
_UNIQUENESS_WINDOW_REGEX = re.compile(
    r"^\s*COUNT\(\*\)\s+OVER\s*\(\s*PARTITION\s+BY\s+[A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*\s*\)\s*=\s*1\s*$",
    re.IGNORECASE,
)


class _AstParserError(ValueError):
    pass


class _ExpressionParser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self._tokens = tokens
        self._index = 0

    def _peek(self) -> tuple[str, str] | None:
        if self._index >= len(self._tokens):
            return None
        return self._tokens[self._index]

    def _advance(self) -> tuple[str, str]:
        token = self._peek()
        if token is None:
            raise _AstParserError("Unexpected end of expression")
        self._index += 1
        return token

    def _match(self, token_type: str, token_value: str | None = None) -> bool:
        token = self._peek()
        if token is None:
            return False
        if token[0] != token_type:
            return False
        if token_value is not None and token[1].upper() != token_value.upper():
            return False
        self._index += 1
        return True

    def _expect(self, token_type: str, token_value: str | None = None) -> tuple[str, str]:
        token = self._peek()
        if token is None:
            expected = token_value or token_type
            raise _AstParserError(f"Expected '{expected}' but reached end of expression")
        if token[0] != token_type:
            expected = token_value or token_type
            raise _AstParserError(f"Expected '{expected}' but found '{token[1]}'")
        if token_value is not None and token[1].upper() != token_value.upper():
            raise _AstParserError(f"Expected '{token_value}' but found '{token[1]}'")
        self._index += 1
        return token

    def _parse_literal(self) -> dict[str, str]:
        token = self._peek()
        if token is None:
            raise _AstParserError("Expected literal but reached end of expression")
        token_type, token_value = token

        if token_type == "NUMBER":
            self._advance()
            return {"value": token_value, "valueType": "number"}
        if token_type == "STRING":
            self._advance()
            return {"value": token_value, "valueType": "string"}
        if token_type == "KEYWORD" and token_value.upper() in {"TRUE", "FALSE"}:
            self._advance()
            return {"value": token_value.lower(), "valueType": "boolean"}
        raise _AstParserError(f"Expected literal but found '{token_value}'")

    def _parse_value_expression(self) -> dict[str, str]:
        return self._parse_value_expression_with_stops(stop_on_comma=False, stop_on_rparen=True)

    def _parse_value_expression_with_stops(self, *, stop_on_comma: bool, stop_on_rparen: bool) -> dict[str, str]:
        parts: list[str] = []
        depth = 0

        while True:
            token = self._peek()
            if token is None:
                break

            token_type, token_value = token

            # Logical connectors terminate the current predicate value expression
            # when we are not nested inside parentheses.
            if depth == 0 and token_type == "KEYWORD" and token_value.upper() in {"AND", "OR"}:
                break
            if depth == 0 and stop_on_rparen and token_type == "RPAREN":
                break
            if depth == 0 and stop_on_comma and token_type == "COMMA":
                break

            self._advance()
            if token_type == "LPAREN":
                depth += 1
            elif token_type == "RPAREN":
                depth -= 1
            parts.append(token_value)

        if not parts:
            raise _AstParserError("Expected predicate value but reached end of expression")

        # Compact the token stream back to a readable SQL-like expression.
        rendered: list[str] = []
        for piece in parts:
            if not rendered:
                rendered.append(piece)
                continue

            prev = rendered[-1]
            if piece in {")", ","}:
                rendered.append(piece)
            elif prev in {"(", "."} or piece == ".":
                rendered.append(piece)
            else:
                rendered.append(f" {piece}")

        return {"value": "".join(rendered).strip(), "valueType": "expression"}

    def _parse_value_operand(self, *, stop_on_comma: bool = False, stop_on_rparen: bool = True) -> dict[str, str]:
        token = self._peek()
        if token is None:
            raise _AstParserError("Expected predicate value but reached end of expression")

        token_type, token_value = token
        if token_type in {"NUMBER", "STRING"}:
            return self._parse_literal()
        if token_type == "KEYWORD" and token_value.upper() in {"TRUE", "FALSE"}:
            return self._parse_literal()
        return self._parse_value_expression_with_stops(
            stop_on_comma=stop_on_comma,
            stop_on_rparen=stop_on_rparen,
        )

    def parse(self) -> dict[str, Any]:
        node = self._parse_or()
        if self._peek() is not None:
            raise _AstParserError(f"Unexpected token '{self._peek()[1]}'")
        return node

    def _parse_or(self) -> dict[str, Any]:
        node = self._parse_and()
        while self._match("KEYWORD", "OR"):
            right = self._parse_and()
            node = {"nodeType": "logical", "operator": "OR", "left": node, "right": right}
        return node

    def _parse_and(self) -> dict[str, Any]:
        node = self._parse_not()
        while self._match("KEYWORD", "AND"):
            right = self._parse_not()
            node = {"nodeType": "logical", "operator": "AND", "left": node, "right": right}
        return node

    def _parse_not(self) -> dict[str, Any]:
        if self._match("KEYWORD", "NOT"):
            operand = self._parse_not()
            return {"nodeType": "unary", "operator": "NOT", "operand": operand}
        return self._parse_factor()

    def _parse_factor(self) -> dict[str, Any]:
        if self._match("LPAREN"):
            nested = self._parse_or()
            self._expect("RPAREN")
            return nested
        return self._parse_predicate()

    def _parse_field_reference(self) -> str:
        # Accept plain identifiers and simple function-call expressions such as
        # TRIM(description) or LOWER(TRIM(name)) on the predicate left-hand side.
        identifier = self._expect("IDENT")[1]
        parts = [identifier]

        # Support dotted references such as a.description or schema.table.column.
        while self._match("DOT"):
            segment = self._expect("IDENT")[1]
            parts.append(".")
            parts.append(segment)

        # Support PostgreSQL-style type casts, e.g. transaction_date::date.
        while self._match("TYPECAST"):
            cast_target = self._advance()
            if cast_target[0] not in {"IDENT", "KEYWORD"}:
                raise _AstParserError(f"Expected type name after '::' but found '{cast_target[1]}'")
            parts.append("::")
            parts.append(cast_target[1])

        while self._match("LPAREN"):
            parts.append("(")
            depth = 1
            while depth > 0:
                token_type, token_value = self._advance()
                if token_type == "LPAREN":
                    depth += 1
                elif token_type == "RPAREN":
                    depth -= 1
                parts.append(token_value)

        return "".join(parts)

    def _parse_predicate(self) -> dict[str, Any]:
        identifier = self._parse_field_reference()

        if self._match("KEYWORD", "IS"):
            is_not = self._match("KEYWORD", "NOT")
            self._expect("KEYWORD", "NULL")
            return {
                "nodeType": "predicate",
                "field": identifier,
                "operator": "IS NOT NULL" if is_not else "IS NULL",
                "value": None,
                "valueType": "null",
            }

        prefixed_not = self._match("KEYWORD", "NOT")

        if self._match("KEYWORD", "IN"):
            self._expect("LPAREN")
            values: list[dict[str, str]] = [
                self._parse_value_operand(stop_on_comma=True, stop_on_rparen=True)
            ]
            while self._match("COMMA"):
                values.append(self._parse_value_operand(stop_on_comma=True, stop_on_rparen=True))
            self._expect("RPAREN")
            return {
                "nodeType": "predicate",
                "field": identifier,
                "operator": "NOT IN" if prefixed_not else "IN",
                "value": values,
                "valueType": "list",
            }

        if self._match("KEYWORD", "BETWEEN"):
            lower = self._parse_value_operand(stop_on_comma=False, stop_on_rparen=True)
            self._expect("KEYWORD", "AND")
            upper = self._parse_value_operand(stop_on_comma=False, stop_on_rparen=True)
            return {
                "nodeType": "predicate",
                "field": identifier,
                "operator": "NOT BETWEEN" if prefixed_not else "BETWEEN",
                "value": {"lower": lower, "upper": upper},
                "valueType": "range",
            }

        if self._match("KEYWORD", "LIKE"):
            literal = self._parse_literal()
            return {
                "nodeType": "predicate",
                "field": identifier,
                "operator": "NOT LIKE" if prefixed_not else "LIKE",
                "value": literal["value"],
                "valueType": literal["valueType"],
            }

        if self._match("KEYWORD", "RLIKE"):
            literal = self._parse_literal()
            return {
                "nodeType": "predicate",
                "field": identifier,
                "operator": "NOT RLIKE" if prefixed_not else "RLIKE",
                "value": literal["value"],
                "valueType": literal["valueType"],
            }

        token = self._peek()
        if token is None:
            if prefixed_not:
                raise _AstParserError(f"Expected IN, BETWEEN, LIKE or RLIKE after NOT for '{identifier}'")
            return {
                "nodeType": "predicate",
                "field": identifier,
                "operator": "IS TRUE",
                "value": "true",
                "valueType": "boolean",
            }

        token_type, token_value = token
        if token_type == "KEYWORD" and token_value in {"AND", "OR"}:
            if prefixed_not:
                raise _AstParserError(f"Expected IN, BETWEEN, LIKE or RLIKE after NOT for '{identifier}'")
            return {
                "nodeType": "predicate",
                "field": identifier,
                "operator": "IS TRUE",
                "value": "true",
                "valueType": "boolean",
            }

        if token_type == "RPAREN":
            if prefixed_not:
                raise _AstParserError(f"Expected IN, BETWEEN, LIKE or RLIKE after NOT for '{identifier}'")
            return {
                "nodeType": "predicate",
                "field": identifier,
                "operator": "IS TRUE",
                "value": "true",
                "valueType": "boolean",
            }

        if token_type == "OP" and token_value in {"~", "!~"}:
            self._advance()
            literal = self._parse_literal()
            base_operator = "RLIKE" if token_value == "~" else "!~"
            if prefixed_not and base_operator == "RLIKE":
                operator = "NOT RLIKE"
            elif prefixed_not and base_operator == "!~":
                operator = "RLIKE"
            else:
                operator = base_operator
            return {
                "nodeType": "predicate",
                "field": identifier,
                "operator": operator,
                "value": literal["value"],
                "valueType": literal["valueType"],
            }

        if token_type == "OP" and token_value in {"=", "!=", "<>", ">", ">=", "<", "<="}:
            self._advance()
            value_operand = self._parse_value_operand()
            operator = "!=" if token_value == "<>" else token_value
            if prefixed_not:
                raise _AstParserError("NOT is not allowed before comparison operators")
            return {
                "nodeType": "predicate",
                "field": identifier,
                "operator": operator,
                "value": value_operand["value"],
                "valueType": value_operand["valueType"],
            }

        if prefixed_not:
            raise _AstParserError(f"Expected IN, BETWEEN, LIKE or RLIKE after NOT for '{identifier}'")
        raise _AstParserError(f"Unsupported predicate operator '{token_value}'")


def _tokenize_expression(normalized_expression: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    position = 0
    while position < len(normalized_expression):
        match = _TOKEN_REGEX.match(normalized_expression, position)
        if not match:
            snippet = normalized_expression[position : position + 16]
            raise _AstParserError(f"Unrecognized token near '{snippet}'")

        token_type = match.lastgroup
        token_value = match.group()
        position = match.end()

        if token_type == "WS":
            continue
        if token_type in {"SSTRING", "DSTRING"}:
            tokens.append(("STRING", token_value))
            continue
        if token_type == "IDENT":
            upper = token_value.upper()
            if upper in _KEYWORDS:
                tokens.append(("KEYWORD", upper))
            else:
                tokens.append(("IDENT", token_value))
            continue
        if token_type in {"LPAREN", "RPAREN", "COMMA", "TYPECAST", "DOT", "OP", "NUMBER", "ARITH"}:
            tokens.append((token_type, token_value))
            continue

    return tokens


def _compile_expression_ast(normalized_expression: str) -> tuple[dict[str, Any] | None, str | None]:
    if not normalized_expression:
        return None, None
    try:
        tokens = _tokenize_expression(normalized_expression)
        parser = _ExpressionParser(tokens)
        return parser.parse(), None
    except _AstParserError as exc:
        return None, str(exc)


def _literal_value_to_string(literal: dict[str, str]) -> str:
    return str(literal.get("value") or "")


def _ast_predicate_to_flat(node: dict[str, Any]) -> dict[str, str]:
    operator = str(node.get("operator") or "")
    value = node.get("value")

    if operator in {"BETWEEN", "NOT BETWEEN"} and isinstance(value, dict):
        lower = _literal_value_to_string(value.get("lower", {}))
        upper = _literal_value_to_string(value.get("upper", {}))
        return {
            "field": str(node.get("field") or ""),
            "operator": operator,
            "value": f"{lower} AND {upper}",
            "valueType": "range",
        }

    if operator in {"IN", "NOT IN"} and isinstance(value, list):
        rendered = ", ".join(_literal_value_to_string(item) for item in value if isinstance(item, dict))
        return {
            "field": str(node.get("field") or ""),
            "operator": operator,
            "value": f"({rendered})",
            "valueType": "list",
        }

    if operator in {"IS NULL", "IS NOT NULL"}:
        return {
            "field": str(node.get("field") or ""),
            "operator": operator,
            "value": "NULL",
            "valueType": "null",
        }

    return {
        "field": str(node.get("field") or ""),
        "operator": operator,
        "value": "" if value is None else str(value),
        "valueType": str(node.get("valueType") or "unknown"),
    }


def _collect_predicates_from_ast(ast: dict[str, Any] | None) -> list[dict[str, str]]:
    if ast is None:
        return []

    predicates: list[dict[str, str]] = []

    def walk(node: dict[str, Any]) -> None:
        node_type = str(node.get("nodeType") or "")
        if node_type == "predicate":
            predicates.append(_ast_predicate_to_flat(node))
            return
        if node_type == "logical":
            left = node.get("left")
            right = node.get("right")
            if isinstance(left, dict):
                walk(left)
            if isinstance(right, dict):
                walk(right)
            return
        if node_type == "unary":
            operand = node.get("operand")
            if isinstance(operand, dict):
                walk(operand)

    walk(ast)
    return predicates


def _collect_logical_operators_from_ast(ast: dict[str, Any] | None) -> list[str]:
    if ast is None:
        return []

    operators: list[str] = []

    def walk(node: dict[str, Any]) -> None:
        node_type = str(node.get("nodeType") or "")
        if node_type == "logical":
            left = node.get("left")
            right = node.get("right")
            if isinstance(left, dict):
                walk(left)
            operator = str(node.get("operator") or "").upper()
            if operator in {"AND", "OR"}:
                operators.append(operator)
            if isinstance(right, dict):
                walk(right)
            return
        if node_type == "unary":
            operator = str(node.get("operator") or "").upper()
            if operator == "NOT":
                operators.append("NOT")
            operand = node.get("operand")
            if isinstance(operand, dict):
                walk(operand)

    walk(ast)
    return operators


def _normalize_expression(expression: str) -> str:
    normalized = str(expression or "").strip()
    normalized = re.sub(r"\s*<>\s*", " != ", normalized)
    normalized = re.sub(r"\s*(>=|<=|!=|=|>|<)\s*", r" \1 ", normalized)
    normalized = re.sub(r"\bAND\b", " AND ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bOR\b", " OR ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bNOT\b", " NOT ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _infer_literal_type(raw_literal: str) -> str:
    literal = str(raw_literal or "").strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", literal):
        return "number"
    if re.fullmatch(r"(?i:true|false)", literal):
        return "boolean"
    if literal.startswith("'") or literal.startswith('"'):
        return "string"
    if literal.startswith("(") and literal.endswith(")"):
        return "list"
    return "unknown"


def _compile_predicates(normalized_expression: str) -> list[dict[str, str]]:
    indexed: list[tuple[int, dict[str, str]]] = []

    for match in _PREDICATE_BETWEEN_REGEX.finditer(normalized_expression):
        not_prefix = "NOT " if match.group(2) else ""
        lower = str(match.group(3)).strip()
        upper = str(match.group(4)).strip()
        indexed.append(
            (
                match.start(),
                {
                    "field": str(match.group(1)),
                    "operator": f"{not_prefix}BETWEEN".strip().upper(),
                    "value": f"{lower} AND {upper}",
                    "valueType": "range",
                },
            )
        )

    for match in _PREDICATE_IN_REGEX.finditer(normalized_expression):
        not_prefix = "NOT " if match.group(2) else ""
        value = str(match.group(3)).strip()
        indexed.append(
            (
                match.start(),
                {
                    "field": str(match.group(1)),
                    "operator": f"{not_prefix}IN".strip().upper(),
                    "value": value,
                    "valueType": "list",
                },
            )
        )

    for match in _PREDICATE_LIKE_REGEX.finditer(normalized_expression):
        not_prefix = "NOT " if match.group(2) else ""
        operator = str(match.group(3)).upper()
        value = str(match.group(4)).strip()
        indexed.append(
            (
                match.start(),
                {
                    "field": str(match.group(1)),
                    "operator": f"{not_prefix}{operator}".strip().upper(),
                    "value": value,
                    "valueType": _infer_literal_type(value),
                },
            )
        )

    for match in _PREDICATE_IS_NULL_REGEX.finditer(normalized_expression):
        not_prefix = "NOT " if match.group(2) else ""
        indexed.append(
            (
                match.start(),
                {
                    "field": str(match.group(1)),
                    "operator": f"IS {not_prefix}NULL".strip().upper(),
                    "value": "NULL",
                    "valueType": "null",
                },
            )
        )

    for match in _PREDICATE_COMPARISON_REGEX.finditer(normalized_expression):
        indexed.append(
            (
                match.start(),
                {
                    "field": str(match.group(1)),
                    "operator": str(match.group(2)).upper(),
                    "value": str(match.group(3)).strip(),
                    "valueType": _infer_literal_type(str(match.group(3))),
                },
            )
        )

    indexed.sort(key=lambda row: row[0])

    predicates: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for _, predicate in indexed:
        key = (predicate["field"], predicate["operator"], predicate["value"])
        if key in seen:
            continue
        seen.add(key)
        predicates.append(predicate)

    return predicates


def _extract_logical_operators(normalized_expression: str) -> list[str]:
    tokens = re.findall(r"\b(?:AND|OR|NOT|IN|BETWEEN|LIKE|RLIKE)\b", normalized_expression, flags=re.IGNORECASE)
    operators: list[str] = []
    consume_between_and = False
    for index, token in enumerate(tokens):
        upper = token.upper()
        if upper == "BETWEEN":
            consume_between_and = True
            continue
        if upper == "AND" and consume_between_and:
            consume_between_and = False
            continue
        if upper == "NOT":
            next_token = tokens[index + 1].upper() if index + 1 < len(tokens) else ""
            if next_token in {"IN", "BETWEEN", "LIKE", "RLIKE"}:
                continue
        if upper in {"AND", "OR", "NOT"}:
            operators.append(upper)
    return operators


def _compile_diagnostics(normalized_expression: str, validation_error: str | None) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    if validation_error:
        diagnostics.append(
            {
                "code": _DIAG_FILTER_VALIDATION,
                "severity": _SEVERITY_ERROR,
                "message": validation_error,
            }
        )

    scrubbed_expression = re.sub(r"'(?:''|[^'])*'", " ", normalized_expression)
    scrubbed_expression = re.sub(r'"(?:\\"|[^"])*"', " ", scrubbed_expression)

    if (
        re.search(r"\bSELECT\b", scrubbed_expression, flags=re.IGNORECASE)
        and _REFERENTIAL_INTEGRITY_SUBQUERY_REGEX.fullmatch(scrubbed_expression) is None
    ):
        diagnostics.append(
            {
                "code": _DIAG_RESERVED_KEYWORD,
                "severity": _SEVERITY_WARNING,
                "message": "Reserved keyword SELECT triggers alias warning",
            }
        )

    if (
        re.search(r"\b(?:COUNT|SUM|AVG|MIN|MAX)\s*\(", scrubbed_expression, flags=re.IGNORECASE)
        and _UNIQUENESS_WINDOW_REGEX.fullmatch(scrubbed_expression) is None
    ):
        diagnostics.append(
            {
                "code": _DIAG_UNSUPPORTED_AGGREGATE,
                "severity": _SEVERITY_ERROR,
                "message": "COUNT, SUM, AVG, MIN, MAX are reserved; no GROUP BY semantics",
            }
        )

    return diagnostics


def _build_artifact_key(rule_id: str, rule_version_id: str, normalized_expression: str) -> str:
    source = f"{rule_id}:{rule_version_id}:{normalized_expression}".encode("utf-8")
    digest = hashlib.sha256(source).hexdigest()[:16]
    return f"rule::{rule_id}::version::{rule_version_id}::{digest}"


def compile_rule_to_intermediate_model(
    *,
    rule_id: str,
    rule_version_id: str,
    filter_expression: str,
    join_definition: str | list[dict[str, Any]] | dict[str, Any] | None = None,
) -> dict[str, Any]:
    with traced_span(
        "rules.compile",
        endpoint_group="rules",
        operation="compile_rule",
        rule_id=rule_id,
        rule_version_id=rule_version_id,
        compiler_join_supplied=join_definition is not None,
    ) as span:
        normalized_expression = _normalize_expression(filter_expression)
        validation_error = validate_filter_expression(normalized_expression)
        diagnostics = _compile_diagnostics(normalized_expression, validation_error)

        serialized_joins: str | None = None
        if join_definition is not None:
            serialized_joins, join_error = normalize_join_definition(join_definition)
            if join_error:
                diagnostics.append(
                    {
                        "code": _DIAG_JOIN_VALIDATION,
                        "severity": _SEVERITY_ERROR,
                        "message": join_error,
                    }
                )

        predicates = _compile_predicates(normalized_expression)
        expression_ast, ast_error = _compile_expression_ast(normalized_expression)
        if ast_error and not any(item.get("code") in _NON_COMPILABLE_DIAGNOSTIC_CODES for item in diagnostics):
            diagnostics.append(
                {
                    "code": _DIAG_AST_PARSE,
                    "severity": _SEVERITY_WARNING,
                    "message": f"AST parse warning: {ast_error}",
                }
            )
        else:
            predicates = _collect_predicates_from_ast(expression_ast)

        alias_expectations = infer_alias_expectations(normalized_expression)
        artifact_key = _build_artifact_key(rule_id, rule_version_id, normalized_expression)
        has_errors = any(item.get("severity") == _SEVERITY_ERROR for item in diagnostics)
        has_non_compilable_warning = any(item.get("code") in _NON_COMPILABLE_DIAGNOSTIC_CODES for item in diagnostics)
        set_span_attributes(
            span,
            compiler_predicate_count=len(predicates),
            compiler_alias_expectation_count=len(alias_expectations),
            compiler_diagnostics_count=len(diagnostics),
            compiler_compilable=not has_errors and not has_non_compilable_warning,
        )

        return {
            "artifactKey": artifact_key,
            "compilerVersion": _COMPILER_VERSION,
            "schemaVersion": _INTERMEDIATE_MODEL_SCHEMA_VERSION,
            "target": "dsl",
            "rule": {
                "id": rule_id,
                "versionId": rule_version_id,
            },
            "filter": {
                "source": str(filter_expression or "").strip(),
                "normalized": normalized_expression,
                "predicates": predicates,
                "logicalOperators": _collect_logical_operators_from_ast(expression_ast)
                if expression_ast is not None
                else _extract_logical_operators(normalized_expression),
                "aliasExpectations": alias_expectations,
                "ast": expression_ast,
            },
            "join": json.loads(serialized_joins) if serialized_joins else None,
            "executionContract": {
                "engineTarget": "dq-engine",
                "inputFormat": "dq.intermediate-model.v1",
                "compatibilityPolicy": {
                    "schemaVersioning": "semver",
                    "compilerVersioning": "dq-semver",
                    "supportedSchemaSeries": "1.x.x",
                    "minorVersionBackwardCompatible": True,
                },
                "traceability": {
                    "ruleId": rule_id,
                    "ruleVersionId": rule_version_id,
                    "artifactKey": artifact_key,
                    "compilerVersion": _COMPILER_VERSION,
                    "schemaVersion": _INTERMEDIATE_MODEL_SCHEMA_VERSION,
                },
                "requiredExecutionResultFields": [
                    "artifactKey",
                    "ruleId",
                    "ruleVersionId",
                    "executionId",
                    "executedAt",
                    "resultStatus",
                ],
            },
            "diagnostics": diagnostics,
            "compilable": not has_errors and not has_non_compilable_warning,
        }
