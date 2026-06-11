from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from app.application.use_cases.sla_slo_management import SlaSloSummaryQuery
from app.application.use_cases.sla_slo_management import approve_sla_slo_definition
from app.application.use_cases.sla_slo_management import create_sla_slo_definition
from app.application.use_cases.sla_slo_management import evaluate_sla_slo_breaches
from app.application.use_cases.sla_slo_management import get_sla_slo_summary
from app.domain.entities.dq_result_event import DqResultEventEntity
from app.infrastructure.repositories.in_memory_app_config_repository import InMemoryAppConfigRepository
from app.infrastructure.repositories.in_memory_dq_result_event_repository import InMemoryDqResultEventRepository
from app.infrastructure.repositories.in_memory_sla_slo_repository import InMemorySlaSloRepository


@dataclass(frozen=True)
class DummyItsmResponse:
    status_code: int
    is_success: bool
    payload: dict[str, object]
    text: str = ""
    reason_phrase: str | None = None


@pytest.fixture()
def sla_slo_repository() -> InMemorySlaSloRepository:
    return InMemorySlaSloRepository()


@pytest.fixture()
def dq_result_event_repository() -> InMemoryDqResultEventRepository:
    return InMemoryDqResultEventRepository()


@pytest.fixture()
def app_config_repository() -> InMemoryAppConfigRepository:
    repository = InMemoryAppConfigRepository()
    repository.set_app_config(
        {
            "assistanceRequestItsmSystem": "HaloITSM",
            "assistanceRequestItsmEndpointUrl": "https://itsm.example.com/api/v1/tickets",
            "assistanceRequestItsmAuthToken": "",
        }
    )
    return repository


@pytest.fixture()
def sample_service_level_payload() -> dict[str, object]:
    return {
        "workspace_id": "workspace-1",
        "name": "Customer dataset availability",
        "description": "Track the quality score for the customer dataset",
        "scope_kind": "dataset",
        "scope_id": "dataset-1",
        "metric_kind": "quality_score",
        "threshold_value": 90,
        "threshold_operator": "gte",
        "lookback_amount": 30,
        "lookback_unit": "day",
    }


@pytest.fixture()
def quality_score_events() -> list[DqResultEventEntity]:
    return [
        DqResultEventEntity.model_validate(
            {
                "emitted_at": "2026-05-27T00:00:00Z",
                "severity": "info",
                "dataset": {
                    "id": "dataset-1",
                    "name": "Customer dataset",
                    "workspace_id": "workspace-1",
                    "data_product_id": "product-1",
                    "data_object_id": "object-1",
                    "data_object_version_id": "object-1-v1",
                },
                "domain": {"id": "domain-1", "name": "Customer"},
                "rule": {"id": "rule-1", "name": "Customer quality"},
                "run_outcome": {
                    "status": "succeeded",
                    "passed": True,
                    "score": 95,
                    "observed_at": "2026-05-27T00:00:00Z",
                },
                "score_dimensions": [
                    {"name": "quality_score", "value": 95, "maximum": 100, "threshold": 90, "passed": True}
                ],
                "correlation": {
                    "correlation_id": "corr-1",
                    "run_id": "run-1",
                    "source_system": "gx",
                },
            }
        ),
        DqResultEventEntity.model_validate(
            {
                "emitted_at": "2026-05-28T00:00:00Z",
                "severity": "critical",
                "dataset": {
                    "id": "dataset-1",
                    "name": "Customer dataset",
                    "workspace_id": "workspace-1",
                    "data_product_id": "product-1",
                    "data_object_id": "object-1",
                    "data_object_version_id": "object-1-v2",
                },
                "domain": {"id": "domain-1", "name": "Customer"},
                "rule": {"id": "rule-1", "name": "Customer quality"},
                "run_outcome": {
                    "status": "failed",
                    "passed": False,
                    "score": 85,
                    "observed_at": "2026-05-28T00:00:00Z",
                },
                "score_dimensions": [
                    {"name": "quality_score", "value": 85, "maximum": 100, "threshold": 90, "passed": False}
                ],
                "correlation": {
                    "correlation_id": "corr-2",
                    "run_id": "run-2",
                    "source_system": "gx",
                },
            }
        ),
    ]

def test_approve_sla_slo_definition_syncs_to_itsm_and_marks_active(
    sla_slo_repository: InMemorySlaSloRepository,
    app_config_repository: InMemoryAppConfigRepository,
    sample_service_level_payload: dict[str, object],
):
    created = asyncio.run(
        create_sla_slo_definition(
            payload=sample_service_level_payload,
            repository=sla_slo_repository,
            actor_id="creator-1",
        )
    )

    async def fake_send_itsm_request(endpoint_url: str, request_payload: dict[str, object], request_headers: dict[str, str]) -> DummyItsmResponse:
        assert endpoint_url == "https://itsm.example.com/api/v1/tickets"
        assert request_payload["request_type"] == "sla_slo_definition"
        assert request_payload["body"]["workspace_id"] == "workspace-1"
        assert request_headers == {}
        return DummyItsmResponse(
            status_code=201,
            is_success=True,
            payload={
                "ticketNumber": "HAL-4321",
                "ticketUrl": "https://itsm.example.com/tickets/HAL-4321",
                "ticketId": "ticket-4321",
            },
        )

    approved = asyncio.run(
        approve_sla_slo_definition(
            definition_id=created.id,
            payload={"comments": "Approved for rollout"},
            repository=sla_slo_repository,
            app_config_repository=app_config_repository,
            send_itsm_request=fake_send_itsm_request,
            correlation_id="corr-approval-1",
            actor_id="approver-1",
        )
    )

    assert approved.lifecycleStatus == "active"
    assert approved.approvalStatus == "approved"
    assert approved.itsmSystem == "HaloITSM"
    assert approved.itsmTicketNumber == "HAL-4321"
    assert approved.itsmTicketUrl == "https://itsm.example.com/tickets/HAL-4321"

def test_get_sla_slo_summary_computes_adherence_from_result_history(
    sla_slo_repository: InMemorySlaSloRepository,
    dq_result_event_repository: InMemoryDqResultEventRepository,
    sample_service_level_payload: dict[str, object],
    quality_score_events: list[DqResultEventEntity],
):
    created = asyncio.run(
        create_sla_slo_definition(
            payload=sample_service_level_payload,
            repository=sla_slo_repository,
            actor_id="creator-1",
        )
    )
    asyncio.run(
        sla_slo_repository.approve_sla_slo_definition(
            created.id,
            {
                "approval_status": "approved",
                "lifecycle_status": "active",
                "reviewed_by": "approver-1",
                "reviewed_at": "2026-05-27T00:00:00Z",
                "itsm_system": "HaloITSM",
                "itsm_ticket_number": "HAL-4321",
                "itsm_ticket_url": "https://itsm.example.com/tickets/HAL-4321",
            },
            actor_id="approver-1",
        )
    )

    for event in quality_score_events:
        asyncio.run(dq_result_event_repository.record_result_event(event))

    summary = asyncio.run(
        get_sla_slo_summary(
            query=SlaSloSummaryQuery(workspace_id="workspace-1"),
            repository=sla_slo_repository,
            dq_result_event_repository=dq_result_event_repository,
        )
    )

    assert summary["total_definitions"] == 1
    assert summary["active_definitions"] == 1
    assert summary["at_risk_definitions"] == 1
    assert summary["compliant_definitions"] == 0

    definition = summary["definitions"][0]
    assert definition["id"] == created.id
    assert definition["adherence"]["observed_event_count"] == 2
    assert definition["adherence"]["compliance_rate_pct"] == 50
    assert definition["adherence"]["current_value"] == 85
    assert definition["adherence"]["meets_target"] is False


def test_evaluate_sla_slo_breaches_records_explicit_breach_events(
    sla_slo_repository: InMemorySlaSloRepository,
    dq_result_event_repository: InMemoryDqResultEventRepository,
    sample_service_level_payload: dict[str, object],
    quality_score_events: list[DqResultEventEntity],
):
    created = asyncio.run(
        create_sla_slo_definition(
            payload=sample_service_level_payload,
            repository=sla_slo_repository,
            actor_id="creator-1",
        )
    )
    asyncio.run(
        sla_slo_repository.approve_sla_slo_definition(
            created.id,
            {
                "approval_status": "approved",
                "lifecycle_status": "active",
                "reviewed_by": "approver-1",
                "reviewed_at": "2026-05-27T00:00:00Z",
                "itsm_system": "HaloITSM",
                "itsm_ticket_number": "HAL-4321",
                "itsm_ticket_url": "https://itsm.example.com/tickets/HAL-4321",
            },
            actor_id="approver-1",
        )
    )

    for event in quality_score_events:
        asyncio.run(dq_result_event_repository.record_result_event(event))

    result = asyncio.run(
        evaluate_sla_slo_breaches(
            workspace_id="workspace-1",
            repository=sla_slo_repository,
            dq_result_event_repository=dq_result_event_repository,
        )
    )

    assert result["evaluated_definitions"] == 1
    assert result["breached_definitions"] == 1
    assert result["breach_events_recorded"] == 1
    assert result["breaches"][0]["definition_id"] == created.id
    assert result["breaches"][0]["severity"] == "warning"

    recorded_breaches = asyncio.run(
        dq_result_event_repository.list_result_events(
            status="failed",
            severity="warning",
        )
    )
    assert len(recorded_breaches) == 1
    assert recorded_breaches[0].rule.id == created.id
