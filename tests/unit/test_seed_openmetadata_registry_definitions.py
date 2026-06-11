from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "dq-metadata" / "scripts" / "seed_openmetadata_registry_definitions.py"
MANIFEST_PATH = Path(__file__).resolve().parents[2] / "dq-metadata" / "demo" / "openmetadata_registry_definitions.retail_banking.json"


def _load_module():
    script_dir = str(MODULE_PATH.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location("seed_openmetadata_registry_definitions", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_load_manifest_enforces_demo_shape() -> None:
    loader = _load_module()

    manifest = loader.load_manifest(MANIFEST_PATH)

    assert manifest["glossary"]["name"] == "retail_banking_registry"
    assert len(manifest["definitions"]) == 5
    assert sum(1 for item in manifest["definitions"] if item["definition_type"] == "data_product") == 1
    assert sum(1 for item in manifest["definitions"] if item["definition_type"] == "data_object") == 1
    assert sum(1 for item in manifest["definitions"] if item["definition_type"] == "attribute") == 3


def test_build_term_payload_serializes_complex_fields_as_json_strings() -> None:
    loader = _load_module()
    manifest = loader.load_manifest(MANIFEST_PATH)

    payload = loader.build_term_payload(manifest["definitions"][2], manifest["glossary"]["name"])

    assert payload["name"] == "customer_id_attribute"
    assert payload["extension"]["definition_id"] == "def.attribute.customer_id"
    assert json.loads(payload["extension"]["value_domain"])["format"] == "uuid"
    assert json.loads(payload["extension"]["provenance"])["approved_by"] == "data-governance"
    assert json.loads(payload["extension"]["applies_to"]) == ["data_object:customer"]


def test_seed_registry_definitions_dry_run_writes_report(tmp_path: Path) -> None:
    loader = _load_module()
    manifest = loader.load_manifest(MANIFEST_PATH)
    report_path = tmp_path / "seed-report.json"

    report = loader.seed_registry_definitions(
        client=None,
        manifest=manifest,
        output_path=report_path,
        dry_run=True,
    )

    assert report["dry_run"] is True
    assert report["definition_count"] == 5
    assert report_path.is_file() is True
    rendered = json.loads(report_path.read_text(encoding="utf-8"))
    assert rendered["definitions"][0]["definition_id"] == "def.data_product.retail_banking"
    assert rendered["definitions"][2]["payload"]["extension"]["definition_type"] == "attribute"


def test_has_named_property_detects_existing_property() -> None:
    loader = _load_module()

    payload = {
        "id": "type-1",
        "customProperties": [
            {
                "name": "definition_id",
                "propertyType": {"id": "string-type", "type": "type"},
            }
        ],
    }

    assert loader._has_named_property(payload, "definition_id") is True
    assert loader._has_named_property(payload, "definition_type") is False