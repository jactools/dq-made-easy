from types import SimpleNamespace

from app.api.presenters.catalog_governance import build_catalog_term_payloads
from app.api.presenters.catalog_governance import decode_revalidation_job_id
from app.api.presenters.catalog_governance import encode_revalidation_job_id
from app.domain.entities.catalog_governance import (
    build_catalog_term_entities,
    catalog_term_key_from_name,
    detect_rule_drifts,
    extract_rule_aliases_from_record,
    resolve_rule_aliases,
)


def test_term_key_from_name_and_encode_decode_job_id():
    assert catalog_term_key_from_name("My-Name Example") == "my_name_example"

    job_id = encode_revalidation_job_id(queued=2, triggered_by_term="term", started_at="2020-01-01T00:00:00Z")
    assert job_id.startswith("job-")
    decoded = decode_revalidation_job_id(job_id)
    assert isinstance(decoded, dict)
    assert decoded["queued"] == 2
    assert decoded["triggeredByTerm"] == "term"
    assert "token" in decoded


def test_extract_aliases_and_load_catalog_terms():
    payload = {"alias_mappings": {"a": "1", "b": "2"}}
    assert set(extract_rule_aliases_from_record(payload)) == {"a", "b"}

    repo = SimpleNamespace()
    repo.list_attributes_catalog = lambda _: [
        SimpleNamespace(name="Attr One", type="string", id=1, data_object_id=None),
        SimpleNamespace(name="Attr One", type="string", id=2, data_object_id=None),
        SimpleNamespace(name="Other", type="int", id=3, data_object_id=None),
    ]

    terms = build_catalog_term_payloads(repo.list_attributes_catalog(None))
    assert any(t["termKey"] == "attr_one" for t in terms)
    assert any(t["termKey"] == "other" for t in terms)


def test_catalog_governance_domain_resolves_aliases():
    terms = build_catalog_term_entities(
        [
            SimpleNamespace(name="Email", type="string", id="1", data_object_id=None),
            SimpleNamespace(name="Country Code", type="string", id="2", data_object_id="geo"),
        ]
    )

    resolutions = resolve_rule_aliases(
        ["email", "country", "country code"],
        {"email": "attr-email"},
        terms,
    )
    assert resolutions["email"]["source"] == "manual"
    assert resolutions["country"]["source"] == "unresolved"
    assert resolutions["country code"]["resolvedTermKey"] == "country_code"
    assert resolutions["country code"]["domain"] == "geo"


def test_detect_rule_drifts_reports_attribute_type_changes():
    drift = detect_rule_drifts(
        rule_record={"id": "rule-1", "alias_mappings": {}},
        rule_attributes=[SimpleNamespace(ruleId="rule-1", attributeId="attr-legacy-amount")],
        catalog_attributes=[
            SimpleNamespace(
                id="attr-legacy-amount",
                name="amount",
                type="decimal",
                data_object_id="do-4",
                version_id="dov-9",
            ),
            SimpleNamespace(
                id="attr-latest-amount",
                name="amount",
                type="integer",
                data_object_id="do-4",
                version_id="dov-32",
            ),
        ],
        data_objects_catalog=[SimpleNamespace(id="do-4", latest_version_id="dov-32")],
        detected_at="2026-05-02T12:00:00Z",
    )

    assert drift["affected_aliases"] == ["amount"]
    assert drift["total_drifts"] == 1
    assert drift["needs_revalidation"] is True
    assert drift["drifts"] == [
        {
            "driftType": "data_type_changed",
            "aliasName": "amount",
            "resolvedTermName": "amount",
            "previousValue": "DECIMAL",
            "currentValue": "INTEGER",
            "severity": "critical",
            "detectedAt": "2026-05-02T12:00:00Z",
        }
    ]
