from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml


def _contract_data_source_id(file_path: Path) -> str:
    return file_path.name.removesuffix(".odcs.yaml").removesuffix(".odcs.yml")


def list_contract_files(contracts_dir: Path) -> list[Path]:
    return sorted(
        file_path
        for file_path in contracts_dir.iterdir()
        if file_path.is_file() and file_path.name.endswith((".odcs.yaml", ".odcs.yml"))
    )


def build_data_contract_inventory_payload(files: Sequence[Path]) -> dict[str, object]:
    contracts = [
        {
            "data_source_id": _contract_data_source_id(file_path),
            "contract_url": f"/data-catalog/v1/data-contracts/{_contract_data_source_id(file_path)}",
            "format": "odcs/3.1.0",
        }
        for file_path in files
    ]

    return {
        "success": True,
        "contracts": contracts,
        "count": len(contracts),
    }


def resolve_data_contract_path(contracts_dir: Path, data_source_id: str) -> Path:
    for suffix in (".odcs.yaml", ".odcs.yml"):
        contract_path = contracts_dir / f"{data_source_id}{suffix}"
        if contract_path.exists() and contract_path.is_file():
            return contract_path
    raise FileNotFoundError(f"Data contract not found for data source: {data_source_id}")


def normalize_data_contract_format(response_format: str) -> str:
    normalized = str(response_format or "yaml").strip().lower()
    if normalized in {"yaml", "json"}:
        return normalized
    raise ValueError("Unsupported format. Use 'yaml' or 'json'.")


def parse_data_contract_yaml(yaml_content: str) -> dict[str, Any]:
    parsed = yaml.safe_load(yaml_content)
    if parsed is None:
        return {}
    if not isinstance(parsed, Mapping):
        raise ValueError("Data contract payload has invalid structure")
    return dict(parsed)


def build_quality_rules_payload(data_source_id: str, contract_payload: Mapping[str, Any]) -> dict[str, object]:
    quality = contract_payload.get("quality")
    if not isinstance(quality, Mapping):
        quality = {}

    quality_spec = quality.get("specification")
    slos = quality.get("slos")

    return {
        "success": True,
        "data_source_id": data_source_id,
        "quality_spec": quality_spec if isinstance(quality_spec, str) else "",
        "slos": dict(slos) if isinstance(slos, Mapping) else {},
        "format": "SodaCL",
    }