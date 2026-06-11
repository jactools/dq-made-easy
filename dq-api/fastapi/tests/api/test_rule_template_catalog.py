from fastapi.testclient import TestClient


def test_list_rule_template_packs_returns_pack_metadata(client: TestClient, auth_headers) -> None:
    response = client.get(
        "/api/rulebuilder/v1/rules/template-packs",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert [pack["id"] for pack in payload] == [
        "pack-presence",
        "pack-conformance",
        "pack-consistency",
        "pack-timeliness",
        "pack-validity",
        "pack-uniqueness",
    ]

    presence_pack = payload[0]
    assert presence_pack["default_template_rule_definition"] == {"operator": "percentage_over"}
    assert presence_pack["template_ids"] == [
        "template-completeness-1",
        "template-completeness-2",
        "template-completeness-3",
    ]


def test_list_rule_templates_resolves_pack_defaults_and_inheritance(client: TestClient, auth_headers) -> None:
    response = client.get(
        "/api/rulebuilder/v1/rules/templates?pack_id=pack-conformance",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert [template["id"] for template in payload] == [
        "template-accuracy-1",
        "template-accuracy-2",
        "template-accuracy-3",
    ]
    assert payload[0]["template_rule_definition"]["operator"] == "regex"
    assert payload[1]["inherits_from_template_id"] == "template-accuracy-1"
    assert payload[1]["template_rule_definition"]["expected_values"]["pattern"] == "^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$"


def test_resolve_rule_template_applies_overrides(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/api/rulebuilder/v1/rules/templates/template-completeness-2/resolve",
        headers=auth_headers("dq:rules:write"),
        json={"overrides": {"threshold": 99, "expectedValues": {"placeholder": "UNKNOWN"}}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["inheritance_chain"] == ["template-completeness-1", "template-completeness-2"]
    assert payload["applied_overrides"] == {"threshold": 99, "expected_values": {"placeholder": "UNKNOWN"}}
    assert payload["template"]["template_rule_definition"]["operator"] == "percentage_over"
    assert payload["template"]["template_rule_definition"]["threshold"] == 99
    assert payload["template"]["template_rule_definition"]["expected_values"]["placeholder"] == "UNKNOWN"


def test_list_rule_templates_exposes_advanced_consistency_templates(client: TestClient, auth_headers) -> None:
    response = client.get(
        "/api/rulebuilder/v1/rules/templates?pack_id=pack-consistency",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert [template["id"] for template in payload] == [
        "template-consistency-1",
        "template-consistency-2",
        "template-reconciliation-1",
    ]
    assert payload[1]["template_rule_definition"]["expected_values"]["comparison_columns"][0]["mode"] == "exact"


def test_list_rule_templates_exposes_advanced_validity_templates(client: TestClient, auth_headers) -> None:
    response = client.get(
        "/api/rulebuilder/v1/rules/templates?pack_id=pack-validity",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert [template["id"] for template in payload] == [
        "template-validity-1",
        "template-validity-2",
        "template-validity-3",
        "template-validity-4",
        "template-validity-5",
        "template-validity-6",
        "template-validity-7",
    ]
    assert payload[3]["template_rule_definition"]["expected_values"]["distribution_metric"] == "psi"
    assert payload[6]["inherits_from_template_id"] == "template-validity-6"
