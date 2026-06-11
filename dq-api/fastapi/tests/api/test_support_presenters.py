from __future__ import annotations

from types import SimpleNamespace

import app.api.presenters.support as support_presenters_mod
from app.api.presenters.gx import extract_itsm_response_message
from app.api.presenters.gx import build_itsm_response_entity
from app.api.presenters.gx import extract_itsm_ticket_number
from app.api.presenters.gx import extract_itsm_ticket_url
from app.api.presenters.support import build_support_delivery_message
from app.api.presenters.support import build_support_email_message
from app.api.presenters.support import build_support_request_payload
from app.api.presenters.support import build_support_teams_payload
from app.api.presenters.support import build_zammad_ticket_payload
from app.api.presenters.support import normalize_support_destinations
from app.api.presenters.support import resolve_support_requester_email


def test_extract_itsm_response_fields_from_nested_and_snake_case_payloads() -> None:
    payload = {
        "ticket": {"number": "HAL-4242"},
        "ticket_url": "https://itsm.example.com/tickets/4242",
        "message": "Zammad rejected the request",
    }

    assert extract_itsm_ticket_number(payload) == "HAL-4242"
    assert extract_itsm_ticket_url(payload) == "https://itsm.example.com/tickets/4242"
    assert extract_itsm_response_message(payload) == "Zammad rejected the request"


def test_extract_itsm_response_fields_from_data_aliases() -> None:
    payload = {
        "data": {"ticket_id": "internal-42"},
        "url": "https://itsm.example.com/tickets/internal-42",
        "detail": "downstream rejected request",
    }

    assert extract_itsm_ticket_number(payload) == "internal-42"
    assert extract_itsm_ticket_url(payload) == "https://itsm.example.com/tickets/internal-42"
    assert extract_itsm_response_message(payload) == "downstream rejected request"


def test_build_itsm_response_entity_normalizes_numeric_identifier_fields() -> None:
    response = build_itsm_response_entity(
        {
            "id": 4,
            "ticket": {"id": 8, "number": 9},
            "data": {"id": 12, "ticket_id": 16, "ticket_number": 20},
        }
    )

    assert response is not None
    assert response.id == "4"
    assert response.ticket is not None
    assert response.ticket.id == "8"
    assert response.ticket.number == "9"
    assert response.data is not None
    assert response.data.id == "12"
    assert response.data.ticketId == "16"
    assert response.data.ticketNumber == "20"


def test_support_presenters_build_payloads_and_messages() -> None:
    request_payload = SimpleNamespace(
        title="GX assistance",
        message="Validation failed.",
        source="gx-run-plans-admin",
        workspaceId="retail-banking",
        runPlanId="plan-1",
        runPlanVersionId="plan-1-v1",
        details={"code": "ERR"},
        diagnostics=[{"message": "boom"}],
        metadata={"severity": "high"},
    )

    assert normalize_support_destinations(["EMAIL", "itsm", "email", "unknown"]) == ["email", "itsm"]
    assert normalize_support_destinations(None) == []

    payload = build_support_request_payload(request_payload, "SUP-1", "corr-1", "user-1")
    assert payload["request_type"] == "application_support"
    assert payload["workspace_id"] == "retail-banking"
    assert payload["metadata"] == {"severity": "high"}

    teams_payload = build_support_teams_payload(request_payload, "corr-1", "SUP-1")
    assert "[SUP-1] GX assistance" in teams_payload["text"]
    assert "Run plan version: plan-1-v1" in teams_payload["text"]

    email_message = build_support_email_message(
        recipient_email="support@example.com",
        sender_email="noreply@example.com",
        request_payload=request_payload,
        correlation_id="corr-1",
        reference_id="SUP-1",
    )
    assert email_message["Subject"] == "GX assistance [SUP-1]"
    assert email_message["X-Workspace-ID"] == "retail-banking"
    assert "Details:" in email_message.get_content()

    zammad_payload = build_zammad_ticket_payload(request_payload, "SUP-1", "corr-1", "owner@example.com")
    assert zammad_payload["customer"] == "owner@example.com"
    assert zammad_payload["article"]["sender"] == "Customer"
    assert "Reference ID: SUP-1" in zammad_payload["article"]["body"]

    class _AdminRepo:
        def get_current_user(self, user_id, claims):
            assert user_id == "user-1"
            assert claims == {"email": "claim@example.com"}
            return SimpleNamespace(email="")

    assert resolve_support_requester_email(_AdminRepo(), "user-1", {"email": "claim@example.com"}) == "claim@example.com"
    assert build_support_delivery_message(["itsm"], "SUP-1", ticket_system="Zammad", ticket_number="HAL-42") == "Created Zammad ticket HAL-42. Reference ID: SUP-1"
    assert build_support_delivery_message(["email", "teams"], "SUP-1") == "Routed the support request to email, teams. Reference ID: SUP-1"


def test_support_presenter_helpers_cover_alternate_and_fallback_paths() -> None:
    class _AttributePayload:
        workspace_id = "workspace-1"
        title = "Fallback title"

    assert normalize_support_destinations("EMAIL, teams, email, unknown, itsm, teams") == ["email", "teams", "itsm"]
    assert normalize_support_destinations(("EMAIL", "EMAIL", "TEAMS")) == ["email", "teams"]

    assert build_support_delivery_message(["email"], "SUP-2", recipient_email="help@example.com") == "Sent email assistance request to help@example.com. Reference ID: SUP-2"
    assert build_support_delivery_message(["itsm"], "SUP-3", ticket_system="Jira", ticket_number="123") == "Created Jira ticket 123. Reference ID: SUP-3"

    assert build_support_request_payload(_AttributePayload(), "SUP-2", "corr-2", None)["workspace_id"] == "workspace-1"
    assert build_support_request_payload({"title": "Only title"}, "SUP-3", "corr-3", "user-3")["requested_by"] == "user-3"

    assert support_presenters_mod._field({"workspaceId": "workspace-a", "workspace_id": "workspace-b"}, "workspaceId", "workspace_id") == "workspace-a"
    assert support_presenters_mod._field(_AttributePayload(), "workspaceId", "workspace_id") == "workspace-1"
    assert support_presenters_mod._field({}, "missing") is None

    class _CurrentUserRepo:
        def get_current_user(self, user_id, claims):
            assert user_id == "user-4"
            assert claims is None
            return SimpleNamespace(email="staff@example.com")

    assert resolve_support_requester_email(_CurrentUserRepo(), "user-4", None) == "staff@example.com"

    class _NoEmailRepo:
        def get_current_user(self, user_id, claims):
            assert user_id == "user-5"
            assert claims == {"preferred_username": "not-an-email"}
            return SimpleNamespace(email="")

    assert resolve_support_requester_email(_NoEmailRepo(), "user-5", {"preferred_username": "not-an-email"}) is None

    assert build_support_delivery_message(["teams"], "SUP-4") == "Sent the support request to Teams. Reference ID: SUP-4"
