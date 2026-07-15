"""Soda rule lowering (Layer 2, per-engine, stub).

Soda lowering is not yet implemented. This module raises a descriptive
error when invoked.
"""

from __future__ import annotations

from typing import Any


def lower_rule_to_soda(rule: dict[str, Any]) -> dict[str, Any]:
    """Lower a rule into a Soda check (not implemented)."""
    raise ValueError(
        f"Soda lowering is not implemented for rule {rule.get('id')!r}"
    )
