"""Test to print workspace_id from API response."""
import pytest
import json
import base64
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def _jwt(payload: dict[str, object]) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def encode(value: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).decode("utf-8").rstrip("=")

    return f"{encode(header)}.{encode(payload)}.signature"


def _auth_headers(*scopes: str) -> dict[str, str]:
    token = _jwt(
        {
            "sub": "user-123",
            "preferred_username": "admin",
            "iss": "http://keycloak.local:8080/realms/jaccloud",
            "aud": ["dq-rules-ui"],
            "scope": " ".join(scopes),
        }
    )
    return {"Authorization": f"Bearer {token}"}

def test_print_workspace_id_response(monkeypatch) -> None:
    """Print the actual data product response to see workspace_id."""
    response = client.get(
        "/data-catalog/v1/data-products?workspace=retail-banking&page=1&limit=10",
        headers=_auth_headers("dq:rules:read"),
    )
    
    assert response.status_code == 200
    payload = response.json()
    
    # Print full response
    print("\n\n=== FULL RESPONSE ===")
    print(json.dumps(payload, indent=2))
    
    # Check workspace_id in first product
    if payload["data"]:
        first_product = payload["data"][0]
        print(f"\n\nFirst product workspace_id: '{first_product.get('workspace_id')}'")
        print(f"Type: {type(first_product.get('workspace_id'))}")
        print(f"Is empty string: {first_product.get('workspace_id') == ''}")
        print(f"Is None: {first_product.get('workspace_id') is None}")


if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])
