import base64
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.v1.endpoints import data_contracts as data_contracts_endpoints
from app.core.config import get_settings
from app.main import app

client = TestClient(app)


def _jwt(payload: dict[str, object]) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def encode(value: dict[str, object]) -> str:
        encoded = base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).decode("utf-8")
        return encoded.rstrip("=")

    return f"{encode(header)}.{encode(payload)}.signature"


def _auth_headers(claims: dict[str, object], *scopes: str) -> dict[str, str]:
    merged_claims = dict(claims)
    merged_claims["scope"] = " ".join(scopes)
    token = _jwt(merged_claims)
    return {"Authorization": f"Bearer {token}"}


def _configure_sso(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()


def teardown_function() -> None:
    get_settings.cache_clear()


def test_list_data_contracts_returns_contract_inventory(monkeypatch, suggestions_auth_claims: dict[str, object]) -> None:
    _configure_sso(monkeypatch)

    response = client.get(
        "/api/data-catalog/v1/data-contracts",
        headers=_auth_headers(suggestions_auth_claims, "dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["count"] >= 1
    first_contract = payload["contracts"][0]
    assert "data_source_id" in first_contract
    assert "contract_url" in first_contract
    assert first_contract["format"] == "odcs/3.1.0"


def test_get_data_contract_supports_yaml_and_json(monkeypatch, suggestions_auth_claims: dict[str, object]) -> None:
    _configure_sso(monkeypatch)

    data_source_id = "demo-azure-payments-sql"

    yaml_response = client.get(
        f"/api/data-catalog/v1/data-contracts/{data_source_id}",
        headers=_auth_headers(suggestions_auth_claims, "dq:rules:read"),
    )
    assert yaml_response.status_code == 200
    assert yaml_response.headers["content-type"].startswith("application/x-yaml")
    assert yaml_response.text

    json_response = client.get(
        f"/api/data-catalog/v1/data-contracts/{data_source_id}?format=json",
        headers=_auth_headers(suggestions_auth_claims, "dq:rules:read"),
    )
    assert json_response.status_code == 200
    payload = json_response.json()
    contract_api_version = payload.get("api_version") or payload.get("apiVersion")
    assert contract_api_version == "v3.1.0"
    assert payload["kind"] == "DataContract"


def test_get_quality_rules_extracts_quality_section(monkeypatch, suggestions_auth_claims: dict[str, object]) -> None:
    _configure_sso(monkeypatch)

    response = client.get(
        "/api/data-catalog/v1/data-contracts/demo-azure-payments-sql/quality-rules",
        headers=_auth_headers(suggestions_auth_claims, "dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data_source_id"] == "demo-azure-payments-sql"
    assert isinstance(payload["quality_spec"], str)
    assert isinstance(payload["slos"], dict)
    assert payload["format"] == "SodaCL"


def test_analyze_data_contract_reports_canonical_snapshot_and_comparison(monkeypatch, suggestions_auth_claims: dict[str, object]) -> None:
    _configure_sso(monkeypatch)

    response = client.get(
        "/api/data-catalog/v1/data-contracts/demo-azure-payments-sql/analysis?baseline_data_source_id=demo-azure-payments-sql",
        headers=_auth_headers(suggestions_auth_claims, "dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data_source_id"] == "demo-azure-payments-sql"
    assert payload["contract"]["source_kind"] == "source_dataset"
    assert payload["comparison"]["change_classification"] == "identical"


def test_data_contracts_fail_fast_when_contracts_dir_missing(monkeypatch, suggestions_auth_claims: dict[str, object]) -> None:
    _configure_sso(monkeypatch)

    missing_dir = Path(__file__).resolve().parent / "missing-contracts-dir"
    monkeypatch.setattr(data_contracts_endpoints, "_contracts_dir", lambda: missing_dir)

    response = client.get(
        "/api/data-catalog/v1/data-contracts",
        headers=_auth_headers(suggestions_auth_claims, "dq:rules:read"),
    )

    assert response.status_code == 503
    payload = response.json()
    assert "directory" in payload["detail"].lower()
