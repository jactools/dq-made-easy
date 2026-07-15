"""Trino rule lowering (Layer 2, per-engine).

Lowers a DQ rule definition into a Trino SQL statement.
"""

from __future__ import annotations

from typing import Any

# Import ROW_RULE_TYPES and AGGREGATE_RULE_TYPES from the registry facade
from dq_plan_lowerers import AGGREGATE_RULE_TYPES, ROW_RULE_TYPES


def lower_rule_to_trino(rule: dict[str, Any]) -> dict[str, Any]:
    """Lower a rule into a Trino SQL statement."""
    from trino_adapter import (
        lower_aggregate_rule_to_trino,
        lower_query_rule_to_trino,
        lower_row_rule_to_trino,
    )

    rule_type = str(rule.get("type") or "").strip()

    if rule_type in ROW_RULE_TYPES:
        return lower_row_rule_to_trino(rule)

    if rule_type in AGGREGATE_RULE_TYPES:
        return lower_aggregate_rule_to_trino(rule)

    if rule_type == "query":
        return lower_query_rule_to_trino(rule)

    raise ValueError(f"unsupported rule type for Trino adapter: {rule_type!r}")
