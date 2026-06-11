from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "dq-metadata" / "scripts" / "seed_openmetadata_product_specs.py"
MANIFEST_PATH = Path(__file__).resolve().parents[2] / "dq-metadata" / "demo" / "openmetadata_product_specs.retail_banking.json"


def _load_module():
    script_dir = str(MODULE_PATH.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location("seed_openmetadata_product_specs", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_load_manifest_enforces_demo_shape() -> None:
    loader = _load_module()

    manifest = loader.load_manifest(MANIFEST_PATH)

    assert manifest["glossary"]["name"] == "retail_banking_product_specs"
    assert len(manifest["product_specs"]) == 1
    product_spec = manifest["product_specs"][0]
    assert product_spec["product_spec_id"] == "ps.retail_banking_customer_360"
    assert product_spec["registry_definition_ids"] == [
        "def.data_product.retail_banking",
        "def.data_object.customer",
        "def.attribute.customer_id",
    ]
    assert product_spec["odcs_contract_refs"][0]["odcs_contract_id"] == "urn:dq:contract:retail-banking-customer-360-delivery"


def test_build_term_payload_serializes_complex_fields_as_json_strings() -> None:
    loader = _load_module()
    manifest = loader.load_manifest(MANIFEST_PATH)

    payload = loader.build_term_payload(manifest["product_specs"][0], manifest["glossary"]["name"])

    assert payload["name"] == "ps.retail_banking_customer_360"
    assert payload["extension"]["product_spec_id"] == "ps.retail_banking_customer_360"
    assert json.loads(payload["extension"]["product_scope"])["domains"] == ["retail_banking"]
    assert json.loads(payload["extension"]["registry_definition_ids"])[0] == "def.data_product.retail_banking"
    assert json.loads(payload["extension"]["odcs_contract_refs"])[0]["odcs_contract_name"] == "retail_banking_customer_360_delivery"


def test_seed_product_specs_dry_run_writes_report(tmp_path: Path) -> None:
    loader = _load_module()
    manifest = loader.load_manifest(MANIFEST_PATH)
    report_path = tmp_path / "seed-report.json"

    report = loader.seed_product_specs(
        client=None,
        manifest=manifest,
        output_path=report_path,
        dry_run=True,
    )

    assert report["dry_run"] is True
    assert report["product_spec_count"] == 1
    assert report_path.is_file() is True
    rendered = json.loads(report_path.read_text(encoding="utf-8"))
    assert rendered["product_specs"][0]["product_spec_id"] == "ps.retail_banking_customer_360"
    assert rendered["product_specs"][0]["payload"]["extension"]["product_name"] == "Retail Banking Customer 360"