from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.catalog_governance import RevalidationJobRequest
from app.api.presenters.catalog_governance import build_catalog_term_payloads
from app.api.presenters.catalog_governance import decode_revalidation_job_id
from app.api.presenters.catalog_governance import encode_revalidation_job_id
from app.api.presenters.catalog_governance import filter_catalog_term_payloads
from app.api.v1.endpoints.catalog_governance import check_rule_drift
from app.api.v1.endpoints.catalog_governance import create_revalidation_job
from app.api.v1.endpoints.catalog_governance import get_drift_summary
from app.api.v1.endpoints.catalog_governance import get_catalog_terms
from app.api.v1.endpoints.catalog_governance import get_revalidation_job_status
from app.domain.entities.catalog_governance import catalog_term_key_from_name
from app.domain.entities.catalog_governance import extract_rule_aliases_from_record

pytestmark = pytest.mark.usefixtures("clone_payload")


class _FakeDataCatalogRepository:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def list_attributes_catalog(self, _workspace):
        return self._rows

    def list_rule_attributes(self):
        return [SimpleNamespace(ruleId="rule-1", attributeId="attr-legacy-amount")]

    def list_data_objects_catalog(self, _workspace):
        return [SimpleNamespace(id="do-4", latest_version_id="dov-32")]


class _FakeRulesRepository:
    async def list_rule_records(self, *, limit: int, offset: int):
        return [{"id": "rule-1", "name": "Rule 1", "current_version_id": "rv-1", "aliasMappings": {"Amount": "amount"}}]

    async def list_rule_versions(self, rule_id: str, limit: int = 20, offset: int = 0):
        assert rule_id == "rule-1"
        return {
            "versions": [
                {
                    "id": "rv-1",
                    "versionNumber": 1,
                    "isCurrentVersion": True,
                    "expression": "amount <= 50000",
                }
            ]
        }


class _FakeAppConfigRepository:
    def __init__(self, *, default_catalog_term_match_threshold_pct: float = 70.0) -> None:
        self._threshold = default_catalog_term_match_threshold_pct

    def get_app_config(self):
        return SimpleNamespace(defaultCatalogTermMatchThresholdPct=self._threshold)


def test_term_key_normalizes_spaces_and_dashes() -> None:
    assert catalog_term_key_from_name("  Total-Amount   USD ") == "total_amount_usd"


def test_extract_aliases_returns_keys_only_for_dict_values() -> None:
    payload = {"alias_mappings": {" Amount ": "amount", "": "ignored"}}
    assert extract_rule_aliases_from_record(payload) == ["Amount"]
    assert extract_rule_aliases_from_record({"alias_mappings": []}) == []


def test_load_catalog_terms_skips_blank_and_duplicate_names() -> None:
    repository = _FakeDataCatalogRepository(
        [
            SimpleNamespace(id="1", name="Amount", type="NUMBER", data_object_id="orders"),
            SimpleNamespace(id="2", name=" ", type="NUMBER", data_object_id="orders"),
            SimpleNamespace(id="3", name="amount", type="INT", data_object_id="billing"),
            SimpleNamespace(id="4", name="Tax-Rate", type="DECIMAL", data_object_id=None),
        ]
    )

    terms = build_catalog_term_payloads(repository.list_attributes_catalog(None))

    assert [term["termKey"] for term in terms] == ["amount", "tax_rate"]
    assert terms[0]["domain"] == "orders"
    assert terms[1]["domain"] == "catalog"


def test_decode_revalidation_job_id_rejects_invalid_values() -> None:
    assert decode_revalidation_job_id("abc") is None
    assert decode_revalidation_job_id("job-") is None
    assert decode_revalidation_job_id("job-###") is None


def test_decode_revalidation_job_id_rejects_non_dict_payload() -> None:
    # Encoded JSON array should be rejected because metadata must be a dict.
    encoded = "job-WzEsMiwzXQ"
    assert decode_revalidation_job_id(encoded) is None


@pytest.mark.anyio
async def test_catalog_terms_filters_by_domain_and_search() -> None:
    repository = _FakeDataCatalogRepository(
        [
            SimpleNamespace(id="1", name="Amount", type="NUMBER", data_object_id="orders"),
            SimpleNamespace(id="2", name="Tax Rate", type="NUMBER", data_object_id="billing"),
        ]
    )

    payload = await get_catalog_terms(
        domain="orders",
        search="amo",
        repository=repository,
        app_config_repository=_FakeAppConfigRepository(),
    )

    assert [term["termKey"] for term in payload["terms"]] == ["amount"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("search", "expected_score"),
    [
        ("a percentage must be lower than 10%", 92.35),
        ("a percentage must be less than 10%", 92.35),
        ("a percentage must be under 10%", 92.35),
        ("a percentage must be below 10%", 92.35),
        ("a percentage between 1 and 2", 87.78),
        ("a percentage equal to 10", 92.35),
        ("a percentage max 10", 92.35),
        ("a percentage at least 10", 92.35),
    ],
)
async def test_catalog_terms_apply_match_threshold_pct(search: str, expected_score: float) -> None:
    rows = [
        {"termName": "Discount Percent", "termKey": "discount_percent", "description": "Catalog attribute Discount Percent"},
        {"termName": "Phone Number", "termKey": "phone_number", "description": "Catalog attribute Phone Number"},
    ]

    low_threshold_matches = filter_catalog_term_payloads(
        rows,
        search=search,
        match_threshold_pct=60,
    )
    high_threshold_matches = filter_catalog_term_payloads(
        rows,
        search=search,
        match_threshold_pct=93,
    )

    assert [term["termKey"] for term in low_threshold_matches] == ["discount_percent"]
    assert low_threshold_matches[0]["matchScorePct"] == expected_score
    assert high_threshold_matches == []


@pytest.mark.anyio
async def test_catalog_terms_use_app_config_threshold_when_not_supplied() -> None:
    repository = _FakeDataCatalogRepository(
        [
            SimpleNamespace(id="1", name="Discount Percent", type="NUMBER", data_object_id="pricing"),
            SimpleNamespace(id="2", name="Phone Number", type="NUMBER", data_object_id="pricing"),
        ]
    )

    payload = await get_catalog_terms(
        search="a percentage must be less than 10%",
        repository=repository,
        app_config_repository=_FakeAppConfigRepository(default_catalog_term_match_threshold_pct=60),
    )

    assert [term["termKey"] for term in payload["terms"]] == ["discount_percent"]


@pytest.mark.anyio
async def test_check_rule_drift_reports_attribute_type_change() -> None:
    repository = _FakeDataCatalogRepository(
        [
            SimpleNamespace(id="attr-legacy-amount", name="amount", type="decimal", data_object_id="do-4", version_id="dov-9"),
            SimpleNamespace(id="attr-current-amount", name="amount", type="integer", data_object_id="do-4", version_id="dov-32"),
        ]
    )

    payload = await check_rule_drift(
        rule_id="rule-1",
        version_id="rv-1",
        rules_repository=_FakeRulesRepository(),
        catalog_repository=repository,
    )

    assert payload["ruleId"] == "rule-1"
    assert payload["ruleVersionId"] == "rv-1"
    assert payload["versionNumber"] == 1
    assert payload["affectedAliases"] == ["amount"]
    assert payload["totalDrifts"] == 1
    assert payload["drifts"] == [
        {
            "driftType": "data_type_changed",
            "aliasName": "amount",
            "resolvedTermName": "amount",
            "previousValue": "DECIMAL",
            "currentValue": "INTEGER",
            "severity": "critical",
            "detectedAt": payload["detectedAt"],
        }
    ]


@pytest.mark.anyio
async def test_get_drift_summary_aggregates_attribute_type_change() -> None:
    repository = _FakeDataCatalogRepository(
        [
            SimpleNamespace(id="attr-legacy-amount", name="amount", type="decimal", data_object_id="do-4", version_id="dov-9"),
            SimpleNamespace(id="attr-current-amount", name="amount", type="integer", data_object_id="do-4", version_id="dov-32"),
        ]
    )

    payload = await get_drift_summary(
        rules_repository=_FakeRulesRepository(),
        catalog_repository=repository,
    )

    assert payload["rulesWithDrift"] == 1
    assert payload["totalDriftsDetected"] == 1
    assert payload["criticalDrifts"] == 1
    assert payload["warningDrifts"] == 0
    assert payload["byDriftType"] == {"data_type_changed": 1}
    assert payload["affectedRules"] == [
        {
            "ruleId": "rule-1",
            "ruleName": "Rule 1",
            "ruleVersionId": "rv-1",
            "versionNumber": 1,
            "affectedAliases": ["amount"],
            "totalDrifts": 1,
            "needsRevalidation": True,
        }
    ]


@pytest.mark.anyio
async def test_create_revalidation_job_requires_rule_versions() -> None:
    with pytest.raises(HTTPException) as error:
        await create_revalidation_job(
            body=RevalidationJobRequest(ruleVersionIds=[]),
            rules_repository=_FakeRulesRepository(),
        )

    assert error.value.status_code == 400
    assert error.value.detail == "ruleVersionIds required"


@pytest.mark.anyio
async def test_create_revalidation_job_defaults_triggered_by_term_name() -> None:
    result = await create_revalidation_job(
        body=RevalidationJobRequest(ruleVersionIds=["v1"]),
        rules_repository=_FakeRulesRepository(),
    )

    assert result["status"] == "completed"
    assert result["ruleVersionsQueued"] == 1
    assert result["triggeredByTerm"] == "N/A"


@pytest.mark.anyio
async def test_get_revalidation_job_status_rejects_unknown_job() -> None:
    with pytest.raises(HTTPException) as error:
        await get_revalidation_job_status(job_id="invalid", rules_repository=_FakeRulesRepository())

    assert error.value.status_code == 404


@pytest.mark.anyio
async def test_get_revalidation_job_status_uses_encoded_metadata_defaults() -> None:
    job_id = encode_revalidation_job_id(queued=2, triggered_by_term="", started_at="")

    payload = await get_revalidation_job_status(job_id=job_id, rules_repository=_FakeRulesRepository())

    assert payload["queued"] == 2
    assert payload["completed"] == 2
    assert payload["triggered_by_term"] == "N/A"
    assert isinstance(payload["started_at"], str)
