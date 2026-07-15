"""GX rule lowering (Layer 2, per-engine).

Lowers a DQ rule definition into a GX expectation dictionary.
"""

from __future__ import annotations

from typing import Any


def lower_rule_to_gx(rule: dict[str, Any]) -> dict[str, Any]:
    """Lower a rule into a GX expectation."""
    from rule_translator import translate

    expectation = translate(rule)
    return {
        "engine_type": "gx",
        "engine_target": "pyspark",
        "expectation": type(expectation).__name__,
        "kwargs": (
            expectation.to_json_dict()
            if hasattr(expectation, "to_json_dict")
            else {}
        ),
    }
