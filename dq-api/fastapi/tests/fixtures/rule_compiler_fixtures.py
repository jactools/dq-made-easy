from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def rule_compiler_valid_join_definition() -> list[dict[str, Any]]:
    return [
        {
            "joinType": "inner",
            "conditions": [
                {
                    "leftDataObjectId": "orders",
                    "leftAttributeId": "customer_id",
                    "operator": "=",
                    "rightDataObjectId": "customers",
                    "rightAttributeId": "id",
                }
            ],
        }
    ]
