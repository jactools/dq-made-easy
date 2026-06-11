from __future__ import annotations

import pytest

from app.api.presenters.data_contracts import build_quality_rules_payload
from app.api.presenters.data_contracts import normalize_data_contract_format
from app.api.presenters.data_contracts import parse_data_contract_yaml


def test_data_contract_format_yaml_parse_and_quality_payload() -> None:
    assert normalize_data_contract_format(" JSON ") == "json"
    assert normalize_data_contract_format("") == "yaml"
    with pytest.raises(ValueError):
        normalize_data_contract_format("xml")

    assert parse_data_contract_yaml("") == {}
    parsed = parse_data_contract_yaml(
        "\n".join(
            [
                "kind: DataContract",
                "quality:",
                "  specification: checks",
                "  slos:",
                "    freshness: daily",
            ]
        )
    )
    assert parsed["kind"] == "DataContract"
    assert build_quality_rules_payload("source-1", parsed) == {
        "success": True,
        "data_source_id": "source-1",
        "quality_spec": "checks",
        "slos": {"freshness": "daily"},
        "format": "SodaCL",
    }

    assert build_quality_rules_payload("source-2", {"quality": []}) == {
        "success": True,
        "data_source_id": "source-2",
        "quality_spec": "",
        "slos": {},
        "format": "SodaCL",
    }

    with pytest.raises(ValueError):
        parse_data_contract_yaml("- invalid\n- shape\n")
