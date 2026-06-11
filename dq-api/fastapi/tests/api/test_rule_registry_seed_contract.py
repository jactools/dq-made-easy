from __future__ import annotations


def test_seeded_rules_list_includes_owner_and_lifecycle_contract(client, auth_headers) -> None:
    response = client.get("/api/rulebuilder/v1/rules", headers=auth_headers("dq:rules:read"))

    assert response.status_code == 200, response.text

    payload = response.json()
    rows = payload.get("data") or []
    assert rows, "Expected seeded rules to be present"

    for row in rows:
        taxonomy = row.get("taxonomy") or {}
        assert isinstance(taxonomy, dict)
        assert any(
            str(taxonomy.get(field) or "").strip()
            for field in ("owner", "data_steward", "domain_owner", "technical_owner")
        ), row
        assert str(row.get("lifecycle_status") or "").strip(), row