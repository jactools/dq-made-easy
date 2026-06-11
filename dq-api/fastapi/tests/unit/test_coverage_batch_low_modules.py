from __future__ import annotations

import asyncio
import importlib
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.presenters.row_access import read_row_field
from app.api.v1.endpoints import app_config as app_config_endpoint
from app.api.v1.endpoints import validation_plan_catalog as validation_plan_catalog_endpoint
from app.api.v1.schemas.validation_plan_catalog_view import ValidationPlanCatalogView
from app.application.resolvers.app_config_resolver import resolve_app_config_view
from app.application.services.exception_fact_validation import ExceptionFactValidationService
from app.application.services.execution_engine_capabilities import ExecutionEngineCapability
from app.application.services.execution_engine_capabilities import ExecutionEngineCapabilityError
from app.application.use_cases.get_rule_details import get_rule_details
from app.application.use_cases.list_rules import ListRulesQuery
from dq_cli import __all__ as cli_exports
from dq_cli import main as cli_main
from dq_cli.run_plan import main as run_plan_main
from app.domain.entities import AppConfigEntity


list_rules_use_case = importlib.import_module("app.application.use_cases.list_rules")


@pytest.fixture
def exception_fact_service() -> ExceptionFactValidationService:
    return ExceptionFactValidationService()


def test_cli_module_reexports_run_plan_main() -> None:
    assert cli_main is run_plan_main
    assert cli_exports == ["main"]


def test_get_rule_details_returns_entity_and_404() -> None:
    class _Repo:
        def __init__(self, rule):
            self._rule = rule

        async def get_rule_by_id(self, rule_id):
            del rule_id
            return self._rule

    found = asyncio.run(get_rule_details("rule-1", _Repo(SimpleNamespace(id="rule-1", name="Rule 1"))))
    assert found.id == "rule-1"
    assert found.name == "Rule 1"

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_rule_details("missing-rule", _Repo(None)))

    assert exc_info.value.status_code == 404
    assert "missing-rule" in str(exc_info.value.detail)


def test_resolve_app_config_view_redacts_encrypted_fields() -> None:
    entity = AppConfigEntity(
        supportEmailSmtpPassword="smtp-secret",
        assistanceRequestItsmAuthToken="itsm-secret",
        maintenanceMode=True,
    )

    view = resolve_app_config_view(entity)
    payload = view.model_dump()

    assert payload["supportEmailSmtpPassword"] == ""
    assert payload["assistanceRequestItsmAuthToken"] == ""
    assert payload["maintenanceMode"] is True


def test_read_row_field_supports_dict_and_attribute_lookup() -> None:
    assert read_row_field({"id": "r1"}, "id") == "r1"

    row = SimpleNamespace(ruleId="exact", rule_id="snake")
    assert read_row_field(row, "ruleId") == "exact"
    assert read_row_field(SimpleNamespace(rule_id="snake"), "ruleId") == "snake"
    assert read_row_field(SimpleNamespace(), "missingField") is None


def test_validation_plan_catalog_endpoint_forwards_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def _list_plan_catalog(**kwargs):
        captured.update(kwargs)
        return ValidationPlanCatalogView()

    monkeypatch.setattr(validation_plan_catalog_endpoint._validation_plan_catalog_api, "list_plan_catalog", _list_plan_catalog)

    repository = object()
    result = asyncio.run(
        validation_plan_catalog_endpoint.list_validation_plan_catalog(
            workspace_id="ws-1",
            business_key="bk-1",
            suite_id="suite-1",
            status="active",
            repository=repository,
        )
    )

    assert isinstance(result, ValidationPlanCatalogView)
    assert captured == {
        "workspace_id": "ws-1",
        "business_key": "bk-1",
        "suite_id": "suite-1",
        "status": "active",
        "repository": repository,
    }


def test_get_app_config_endpoint_uses_policy_loader_and_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    def _set_status_policy(payload: object) -> None:
        calls.append(payload)

    sentinel = {"ok": True}
    monkeypatch.setattr(app_config_endpoint, "set_status_model_policy_from_source", _set_status_policy)
    monkeypatch.setattr(app_config_endpoint, "resolve_app_config_view", lambda payload: sentinel)

    class _Repo:
        def get_app_config(self):
            return {"maintenance_mode": False}

    result = asyncio.run(app_config_endpoint.get_app_config(repository=_Repo()))

    assert result == sentinel
    assert len(calls) == 1
    assert calls[0] == {"maintenance_mode": False}


def test_put_app_config_endpoint_returns_400_on_invalid_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    def _set_status_policy(payload: object) -> None:
        raise ValueError(f"invalid payload: {payload}")

    monkeypatch.setattr(app_config_endpoint, "set_status_model_policy_from_source", _set_status_policy)

    class _Repo:
        def set_app_config(self, payload):
            return payload

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(app_config_endpoint.put_app_config(payload={"bad": True}, repository=_Repo()))

    assert exc_info.value.status_code == 400
    assert "invalid payload" in str(exc_info.value.detail)


def test_put_app_config_endpoint_persists_then_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    def _set_status_policy(payload: object) -> None:
        calls.append(payload)

    sentinel = {"persisted": True}
    monkeypatch.setattr(app_config_endpoint, "set_status_model_policy_from_source", _set_status_policy)
    monkeypatch.setattr(app_config_endpoint, "resolve_app_config_view", lambda payload: {"view": payload})

    class _Repo:
        def set_app_config(self, payload):
            return sentinel

    result = asyncio.run(app_config_endpoint.put_app_config(payload={"maintenance_mode": True}, repository=_Repo()))

    assert result == {"view": sentinel}
    assert calls == [{"maintenance_mode": True}, sentinel]


def test_exception_fact_validation_service_maps_capability_error_to_http(
    monkeypatch: pytest.MonkeyPatch,
    exception_fact_service: ExceptionFactValidationService,
) -> None:
    def _raise_capability_error(engine_type: str):
        del engine_type
        raise ExecutionEngineCapabilityError(
            "unsupported engine",
            error_code="unsupported_engine_type",
            engine_type="unknown",
            status_code=503,
        )

    monkeypatch.setattr(
        "app.application.services.exception_fact_validation.require_exception_fact_capability",
        _raise_capability_error,
    )

    with pytest.raises(HTTPException) as exc_info:
        exception_fact_service.require_exception_fact_collection_support(
            execution_context=SimpleNamespace(id="run-1", engineType="unknown")
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == "violation_persistence_unavailable"
    assert exc_info.value.detail["run_id"] == "run-1"
    assert exc_info.value.detail["capability_error"] == "unsupported_engine_type"


def test_exception_fact_validation_service_success_and_count_validation(
    monkeypatch: pytest.MonkeyPatch,
    exception_fact_service: ExceptionFactValidationService,
) -> None:
    capability = ExecutionEngineCapability(
        engine_type="gx",
        supported_execution_shapes=frozenset({"single_object"}),
        row_level_exception_facts_supported=True,
        record_identifier_resolution_supported=True,
        normalized_reason_codes_supported=True,
        supported_record_identifier_types=frozenset({"primary_key"}),
    )

    monkeypatch.setattr(
        "app.application.services.exception_fact_validation.require_exception_fact_capability",
        lambda engine_type: capability,
    )

    result = exception_fact_service.require_exception_fact_collection_support(
        execution_context=SimpleNamespace(id="run-1", engineType="gx")
    )
    assert result == capability

    exception_fact_service.validate_exception_fact_persistence_result(
        expected_count=3,
        persisted_count=3,
        run_id="run-1",
    )

    with pytest.raises(HTTPException) as exc_info:
        exception_fact_service.validate_exception_fact_persistence_result(
            expected_count=3,
            persisted_count=1,
            run_id="run-2",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["expected_count"] == 3
    assert exc_info.value.detail["persisted_count"] == 1


def test_list_rules_marks_pending_deactivation_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Row:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def to_payload(self) -> dict[str, object]:
            return dict(self._payload)

    class _RulesRepo:
        def __init__(self) -> None:
            self.kwargs: dict[str, object] | None = None

        async def list_rule_records(self, **kwargs):
            self.kwargs = kwargs
            return [_Row({"id": "r1", "name": "Rule 1"}), _Row({"id": "r2", "name": "Rule 2"})]

    class _Approval:
        def model_dump(self) -> dict[str, object]:
            return {"id": "approval-1"}

    class _ApprovalsRepo:
        def list_approvals(self, status):
            del status
            return [_Approval()]

    monkeypatch.setattr(list_rules_use_case.rule_policy, "build_pending_deactivation_rule_ids", lambda rows: {"r1"})
    monkeypatch.setattr(list_rules_use_case.rule_policy, "normalize_rule_row_contract", lambda row: dict(row))

    rules_repository = _RulesRepo()
    result = asyncio.run(
        list_rules_use_case.list_rules(
            ListRulesQuery(page=1, limit=20, include_deleted=False, workspace="ws-1", is_template=False, query="rule"),
            repository=rules_repository,
            approvals_repository=_ApprovalsRepo(),
        )
    )

    assert rules_repository.kwargs == {
        "workspace": "ws-1",
        "include_deleted": False,
        "is_template": False,
        "query": "rule",
        "limit": 20,
        "offset": 0,
    }
    assert len(result["data"]) == 2
    assert result["data"][0]["pending_deactivation_requested"] is True
    assert result["data"][1]["pending_deactivation_requested"] is False


def test_list_rules_applies_canonical_filters_before_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Row:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def to_payload(self) -> dict[str, object]:
            return dict(self._payload)

    class _RulesRepo:
        async def list_rule_records(self, **kwargs):
            return [
                _Row({"id": "r1", "name": "Rule 1", "active": True, "created_by": "alice@example.com", "version_updated_at": "2026-05-25T10:00:00+00:00"}),
                _Row({"id": "r2", "name": "Rule 2", "active": False, "last_approval_status": "rejected", "created_by": "bob@example.com", "version_updated_at": "2026-05-26T10:00:00+00:00"}),
                _Row({"id": "r3", "name": "Rule 3", "active": True, "created_by": "alice@example.com", "version_updated_at": "2026-05-27T10:00:00+00:00"}),
            ]

    class _ApprovalsRepo:
        def list_approvals(self, status):
            del status
            return []

    monkeypatch.setattr(list_rules_use_case.rule_policy, "build_pending_deactivation_rule_ids", lambda rows: set())
    monkeypatch.setattr(list_rules_use_case.rule_policy, "normalize_rule_row_contract", lambda row: dict(row))

    result = asyncio.run(
        list_rules_use_case.list_rules(
            ListRulesQuery(
                page=1,
                limit=1,
                status="activated",
                owner="alice",
                updated_since=datetime.fromisoformat("2026-05-26T00:00:00+00:00"),
            ),
            repository=_RulesRepo(),
            approvals_repository=_ApprovalsRepo(),
        )
    )

    assert result["pagination"]["total"] == 1
    assert result["data"] == [
        {
            "id": "r3",
            "name": "Rule 3",
            "active": True,
            "created_by": "alice@example.com",
            "version_updated_at": "2026-05-27T10:00:00+00:00",
            "status": "activated",
            "pending_deactivation_requested": False,
        }
    ]
