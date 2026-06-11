import asyncio

import pytest
from fastapi import HTTPException

from app.application.use_cases import get_rule_details
from app.infrastructure.repositories import InMemoryRulesRepository

pytestmark = pytest.mark.usefixtures("clone_payload")


def test_get_rule_details_returns_entity_for_known_rule() -> None:
    repository = InMemoryRulesRepository()

    result = asyncio.run(get_rule_details("rule-email-format", repository))

    assert result.id == "rule-email-format"
    assert result.name == "Email format validation"


def test_get_rule_details_raises_404_for_unknown_rule() -> None:
    repository = InMemoryRulesRepository()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_rule_details("missing-rule", repository))

    assert exc_info.value.status_code == 404
    assert "missing-rule" in str(exc_info.value.detail)
