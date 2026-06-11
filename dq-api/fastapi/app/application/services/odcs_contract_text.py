from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import yaml


def _normalized_format(contract_format: str | None) -> str:
    normalized = str(contract_format or "").strip().lower()
    if normalized in {"json", "yaml", "yml"}:
        return "json" if normalized == "json" else "yaml"
    raise ValueError("contract_format must be 'yaml' or 'json'")


def dump_contract_text(payload: Mapping[str, Any], *, contract_format: str = "yaml") -> str:
    normalized_format = _normalized_format(contract_format)
    if normalized_format == "json":
        return json.dumps(payload, indent=2, sort_keys=False) + "\n"
    return yaml.safe_dump(dict(payload), sort_keys=False, allow_unicode=False)


def load_contract_payload(contract_text: str) -> dict[str, Any]:
    normalized_text = str(contract_text or "").strip()
    if not normalized_text:
        raise ValueError("contract_text is required")

    parsed: Any
    try:
        parsed = json.loads(normalized_text)
    except ValueError:
        parsed = yaml.safe_load(normalized_text)

    if not isinstance(parsed, dict):
        raise ValueError("contract_text must decode to an object")
    return dict(parsed)
