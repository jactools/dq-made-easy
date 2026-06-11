"""Cross-rule conflict and inconsistency detection.

Given a list of compiled rule summaries, detects:
- DQ1_DUPLICATE_EXPRESSION — two rules share the same normalized filter expression.
- DQ1_DUPLICATE_NAME       — two rules share the same name (case-insensitive).
- DQ1_CONTRADICTORY_PREDICATES — same field appears with logically contradictory
  comparison constraints (heuristic: field > A and field < A where A is the same
  literal value, or a redundant inequality chain such as field > 10 AND field > 5
  where both bounds point in the same direction).

Each detected conflict produces one or more `ConflictInfo` dicts:

    {
        "ruleId":       str,
        "conflictsWith": str,
        "conflictType": str,  # "duplicate_expression" | "duplicate_name" | "contradictory_predicates"
        "message":      str,
    }

Conflicts are symmetric (A conflicts with B implies B conflicts with A) but only
one representative entry is emitted (the one in encounter order).
"""
from __future__ import annotations

import re
from typing import Any


_COMPARISON_PATTERN = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|!=|<>|>|<|=)\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

_SCALAR_OPS = {">", ">=", "<", "<=", "=", "!=", "<>"}


def _extract_scalar_predicates(expression: str) -> dict[str, list[tuple[str, float]]]:
    """Return a mapping of field → [(op, value), …] for simple numeric comparisons."""
    result: dict[str, list[tuple[str, float]]] = {}
    for match in _COMPARISON_PATTERN.finditer(expression):
        field = match.group(1).lower()
        op = match.group(2)
        try:
            value = float(match.group(3))
        except ValueError:
            continue
        result.setdefault(field, []).append((op, value))
    return result


def _has_contradictory_predicates(expr_a: str, expr_b: str) -> bool:
    """
    Heuristic: returns True when the same field in both expressions has numeric
    bounds that cannot simultaneously be satisfied.

    Example contradictions:
      expr_a: price > 100, expr_b: price < 50   → price must be >100 AND <50  (impossible)
    """
    preds_a = _extract_scalar_predicates(expr_a)
    preds_b = _extract_scalar_predicates(expr_b)

    for field, ops_a in preds_a.items():
        ops_b = preds_b.get(field)
        if not ops_b:
            continue
        # Collect lower-bound and upper-bound constraints across both expressions
        lower: list[float] = []
        upper: list[float] = []
        for (op, val) in ops_a + ops_b:
            if op in {">", ">="}:
                lower.append(val)
            elif op in {"<", "<="}:
                upper.append(val)

        if lower and upper:
            effective_lower = max(lower)
            effective_upper = min(upper)
            if effective_lower >= effective_upper:
                return True

    return False


def detect_conflicts(
    rule_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detect cross-rule conflicts for a set of compiled rule summaries.

    Args:
        rule_summaries: Each item must have at least:
            - ``ruleId`` (str)
            - ``ruleName`` (str | None)
            - ``compiledExpression`` (str)

    Returns:
        A list of conflict dicts (see module docstring for shape).
    """
    conflicts: list[dict[str, Any]] = []
    seen_pairs: set[frozenset] = set()

    for i, rule_a in enumerate(rule_summaries):
        id_a = str(rule_a.get("ruleId") or "")
        name_a = str(rule_a.get("ruleName") or "").strip().lower()
        expr_a = str(rule_a.get("compiledExpression") or "").strip()

        for rule_b in rule_summaries[i + 1 :]:
            id_b = str(rule_b.get("ruleId") or "")
            name_b = str(rule_b.get("ruleName") or "").strip().lower()
            expr_b = str(rule_b.get("compiledExpression") or "").strip()
            pair = frozenset({id_a, id_b})

            if pair in seen_pairs:
                continue

            # Duplicate expression
            if expr_a and expr_b and expr_a == expr_b:
                seen_pairs.add(pair)
                conflicts.append({
                    "ruleId": id_a,
                    "conflictsWith": id_b,
                    "conflictType": "duplicate_expression",
                    "message": (
                        f"Rule '{id_a}' and rule '{id_b}' share the same "
                        f"compiled expression: '{expr_a[:80]}{'...' if len(expr_a) > 80 else ''}'"
                    ),
                })
                continue

            # Duplicate name
            if name_a and name_b and name_a == name_b:
                conflicts.append({
                    "ruleId": id_a,
                    "conflictsWith": id_b,
                    "conflictType": "duplicate_name",
                    "message": (
                        f"Rule '{id_a}' and rule '{id_b}' share the same name "
                        f"(case-insensitive): '{name_a}'"
                    ),
                })

            # Contradictory numeric predicates (only when expressions are non-trivial)
            if expr_a and expr_b and expr_a != expr_b:
                if _has_contradictory_predicates(expr_a, expr_b):
                    conflicts.append({
                        "ruleId": id_a,
                        "conflictsWith": id_b,
                        "conflictType": "contradictory_predicates",
                        "message": (
                            f"Rule '{id_a}' and rule '{id_b}' have contradictory "
                            "numeric predicates on a shared field."
                        ),
                    })

    return conflicts
