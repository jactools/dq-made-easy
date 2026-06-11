import json
import re
from collections.abc import Mapping
from typing import Any

_RESERVED_KEYWORDS = {
    "and",
    "or",
    "not",
    "is",
    "null",
    "in",
    "like",
    "rlike",
    "between",
    "true",
    "false",
    "select",
    "from",
    "where",
    "case",
    "when",
    "then",
    "else",
    "end",
    "now",
    "curdate",
    "count",
    "sum",
    "avg",
    "min",
    "max",
    "length",
    "trim",
    "regexp_replace",
    "interval",
    "day",
}

_JOIN_OPERATORS = {"=", "!=", ">", ">=", "<", "<="}
_JOIN_REQUIRED_KEYS = (
    "leftDataObjectId",
    "leftAttributeId",
    "rightDataObjectId",
    "rightAttributeId",
)


def validate_filter_expression(raw_expression: str) -> str | None:
    expression = str(raw_expression or "").strip()
    if not expression:
        return "Filter expression is required"

    if ";" in expression:
        return "Do not use semicolons in filter expressions"

    if "--" in expression or "/*" in expression or "*/" in expression:
        return "Comments are not allowed in filter expressions"

    paren_depth = 0
    in_single_quote = False
    in_double_quote = False

    for index, current in enumerate(expression):
        next_char = expression[index + 1] if index + 1 < len(expression) else ""

        if in_single_quote:
            if current == "'" and next_char == "'":
                continue
            if current == "'":
                in_single_quote = False
            continue

        if in_double_quote:
            if current == '"' and next_char == '"':
                continue
            if current == '"':
                in_double_quote = False
            continue

        if current == "'":
            in_single_quote = True
            continue

        if current == '"':
            in_double_quote = True
            continue

        if current == "(":
            paren_depth += 1
            continue

        if current == ")":
            paren_depth -= 1
            if paren_depth < 0:
                return "Unbalanced parentheses: found a closing parenthesis without matching opening parenthesis"

    if in_single_quote:
        return "Unclosed single quote in filter expression"
    if in_double_quote:
        return "Unclosed double quote in filter expression"
    if paren_depth != 0:
        return "Unbalanced parentheses in filter expression"

    upper_expression = expression.upper()
    if re.match(r"^(AND|OR)\b", upper_expression):
        return "Expression cannot start with AND/OR"

    if re.search(r"\b(AND|OR)$", upper_expression):
        return "Expression cannot end with AND/OR"

    if "AND AND" in upper_expression or "AND OR" in upper_expression:
        return "Consecutive logical operators detected"
    if "OR OR" in upper_expression or "OR AND" in upper_expression:
        return "Consecutive logical operators detected"

    return None


def infer_alias_expectations(expression: str) -> list[dict[str, str]]:
    source = str(expression or "")
    if not source.strip():
        return []

    source_without_literals = re.sub(r"'(?:''|[^'])*'", " ", source)
    source_without_literals = re.sub(r'"(?:\\"|[^"])*"', " ", source_without_literals)
    source_without_literals = re.sub(r"\[(?:\\.|[^\]])*\]", " ", source_without_literals)
    source_without_literals = re.sub(r"/(?:\\.|[^/\n])+/[gimsuy]*", " ", source_without_literals)

    expectations: dict[str, str] = {}

    def push_expectation(alias_raw: str, expected: str) -> None:
        alias = str(alias_raw or "").strip()
        if not alias or alias.lower() in _RESERVED_KEYWORDS:
            return
        existing = expectations.get(alias)
        if existing is not None and existing != expected:
            expectations[alias] = "unknown"
            return
        expectations[alias] = expected

    comparison_regex = re.compile(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|=|!=|>|<|like|rlike|~|!~)\s*"
        r"(-?\d+(?:\.\d+)?|true|false|'(?:''|[^'])*'|\"(?:\\\"|[^\"])*\")",
        re.IGNORECASE,
    )
    for match in comparison_regex.finditer(source):
        alias = match.group(1)
        literal = str(match.group(3) or "").strip()
        if re.fullmatch(r"-?\d+(?:\.\d+)?", literal):
            push_expectation(alias, "number")
        elif re.fullmatch(r"(?i:true|false)", literal):
            push_expectation(alias, "boolean")
        elif literal.startswith("'") or literal.startswith('"'):
            push_expectation(alias, "string")

    for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", source_without_literals):
        token = match.group(1)
        if token.lower() in _RESERVED_KEYWORDS:
            continue
        expectations.setdefault(token, "unknown")

    return [{"alias": alias, "expected": expected} for alias, expected in expectations.items()]


def normalize_join_definition(join_definition: str | list[dict] | dict | None) -> tuple[str | None, str | None]:
    if join_definition is None:
        return None, "Join definition is required"

    if isinstance(join_definition, str):
        normalized = join_definition.strip()
        if not normalized:
            return None, "Join definition is required"
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            return None, "Join definition must be valid JSON"
    else:
        parsed = join_definition

    if isinstance(parsed, list):
        if len(parsed) == 0:
            return None, "Join definition must contain at least one condition"
        definitions = parsed
    elif isinstance(parsed, Mapping):
        definitions = [parsed]
    else:
        return None, "Join definition must be an object or array"

    for definition in definitions:
        if not isinstance(definition, Mapping):
            return None, "Join definition entries must be objects"

        conditions = definition.get("conditions")
        if not isinstance(conditions, list) or len(conditions) == 0:
            return None, "Join definition must contain at least one condition"

        for condition in conditions:
            if not isinstance(condition, Mapping):
                return None, "Join condition must be an object"

            for key in _JOIN_REQUIRED_KEYS:
                value = str(condition.get(key) or "").strip()
                if not value:
                    return None, f"Join condition field '{key}' is required"

            operator = str(condition.get("operator") or "").strip()
            if operator not in _JOIN_OPERATORS:
                return None, "Join condition operator must be one of: =, !=, >, >=, <, <="

    return json.dumps(parsed), None


def evaluate_expression_on_context_with_details(expression: str, context: dict[str, Any]) -> tuple[bool, str | None]:
    py_expression = str(expression or "")
    py_expression = re.sub(r"\s*<>\s*", " != ", py_expression)
    py_expression = re.sub(r"\bAND\b", " and ", py_expression, flags=re.IGNORECASE)
    py_expression = re.sub(r"\bOR\b", " or ", py_expression, flags=re.IGNORECASE)
    py_expression = re.sub(r"\bNOT\b", " not ", py_expression, flags=re.IGNORECASE)
    py_expression = re.sub(r"\bNULL\b", "None", py_expression, flags=re.IGNORECASE)
    py_expression = re.sub(r"\btrue\b", "True", py_expression, flags=re.IGNORECASE)
    py_expression = re.sub(r"\bfalse\b", "False", py_expression, flags=re.IGNORECASE)

    py_expression = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s+IS\s+NOT\s+None\b",
        r"(ctx.get('\1') is not None)",
        py_expression,
        flags=re.IGNORECASE,
    )
    py_expression = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s+IS\s+None\b",
        r"(ctx.get('\1') is None)",
        py_expression,
        flags=re.IGNORECASE,
    )

    py_expression = re.sub(r"(?<![<>=!])=(?!=)", "==", py_expression)

    fields = sorted((name for name in context.keys() if "." not in name), key=len, reverse=True)
    for field in fields:
        py_expression = re.sub(rf"\b{re.escape(field)}\b", f"ctx.get('{field}')", py_expression)

    try:
        result = eval(py_expression, {"__builtins__": {}}, {"ctx": context})
    except Exception as exc:
        return False, str(exc)
    return bool(result), None


def evaluate_expression_on_context(expression: str, context: dict[str, Any]) -> bool:
    result, _ = evaluate_expression_on_context_with_details(expression, context)
    return result
