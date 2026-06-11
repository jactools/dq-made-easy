from __future__ import annotations

from pathlib import Path

import pytest

from app.api.presenters.data_contracts import build_data_contract_inventory_payload
from app.api.presenters.data_contracts import list_contract_files
from app.api.presenters.data_contracts import resolve_data_contract_path


def test_data_contract_inventory_helpers(tmp_path: Path) -> None:
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()
    (contracts_dir / "beta.odcs.yml").write_text("kind: DataContract\n", encoding="utf-8")
    (contracts_dir / "alpha.odcs.yaml").write_text("kind: DataContract\n", encoding="utf-8")
    (contracts_dir / "ignore.txt").write_text("skip", encoding="utf-8")

    files = list_contract_files(contracts_dir)
    assert [file_path.name for file_path in files] == ["alpha.odcs.yaml", "beta.odcs.yml"]

    payload = build_data_contract_inventory_payload(files)
    assert payload == {
        "success": True,
        "contracts": [
            {
                "data_source_id": "alpha",
                "contract_url": "/data-catalog/v1/data-contracts/alpha",
                "format": "odcs/3.1.0",
            },
            {
                "data_source_id": "beta",
                "contract_url": "/data-catalog/v1/data-contracts/beta",
                "format": "odcs/3.1.0",
            },
        ],
        "count": 2,
    }

    assert resolve_data_contract_path(contracts_dir, "alpha").name == "alpha.odcs.yaml"
    assert resolve_data_contract_path(contracts_dir, "beta").name == "beta.odcs.yml"
    with pytest.raises(FileNotFoundError):
        resolve_data_contract_path(contracts_dir, "missing")
