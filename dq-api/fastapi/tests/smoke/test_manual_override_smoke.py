from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.smoke.smoke_auth import smoke_auth_headers


pytestmark = pytest.mark.usefixtures("monkeypatch")

client = TestClient(app)


def _manual_override_payload(name: str) -> dict:
    return {
        "name": name,
        "description": "manual override smoke",
        "dimension": "Validity",
        "workspace": "default",
        "dsl": {
            "schemaVersion": "1.0.0",
            "source": {
                "kind": "check_type",
                "checkType": "RANGE",
                "checkTypeParams": {
                    "checkType": "RANGE",
                    "attribute": "order_amount",
                    "minValue": 0,
                    "maxValue": 100,
                    "inclusive": True,
                },
                "manualExpressionOverride": {
                    "expression": "amount_value > 10",
                    "confirmed": False,
                },
            },
        },
    }


def test_smoke_manual_override_create_requires_confirmation() -> None:
    response = client.post(
        "/api/rulebuilder/v1/rules",
        headers=smoke_auth_headers("dq:rules:write"),
        json=_manual_override_payload(f"Smoke Manual Override Missing Confirm {uuid4().hex[:8]}"),
    )

    assert response.status_code == 400
    assert "confirmation" in str(response.json().get("detail", "")).lower()


def test_smoke_manual_override_create_with_confirmation_persists_audit_fields() -> None:
    payload = _manual_override_payload(f"Smoke Manual Override Confirmed {uuid4().hex[:8]}")
    payload["dsl"]["source"]["manualExpressionOverride"]["confirmed"] = True

    response = client.post(
        "/api/rulebuilder/v1/rules",
        headers=smoke_auth_headers("dq:rules:write"),
        json=payload,
    )

    assert response.status_code == 200
    body = response.json()

    manual_by = body.get("manual_override_by") or body.get("manualOverrideBy")
    manual_at = body.get("manual_override_at") or body.get("manualOverrideAt")

    assert isinstance(manual_by, str)
    assert manual_by.strip() != ""
    assert isinstance(manual_at, str)
    assert manual_at.strip() != ""
