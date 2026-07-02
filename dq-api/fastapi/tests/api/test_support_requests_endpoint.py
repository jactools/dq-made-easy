from __future__ import annotations

from typing import Any

import pytest

from app.api.v1.endpoints import support as support_endpoints


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, posts: list[tuple[str, Any, dict[str, str]]], response: _FakeResponse) -> None:
        self._posts = posts
        self._response = response

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def post(self, url: str, json: Any, headers: dict[str, str] | None = None) -> _FakeResponse:
        self._posts.append((url, json, headers or {}))
        return self._response


class _FakeSMTP:
    instances: list["_FakeSMTP"] = []

    def __init__(self, host: str, port: int, timeout: float | None = None, context: Any = None) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.ehlo_calls = 0
        self.started_tls = False
        self.login_args: tuple[str, str] | None = None
        self.sent_messages: list[Any] = []
        self.__class__.instances.append(self)

    def __enter__(self) -> "_FakeSMTP":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def ehlo(self) -> None:
        self.ehlo_calls += 1

    def starttls(self, context: Any = None) -> None:
        self.started_tls = True
        self.starttls_context = context

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def send_message(self, message: Any) -> dict[str, Any]:
        self.sent_messages.append(message)
        return {}


@pytest.fixture
def support_config_headers(auth_headers: callable) -> dict[str, str]:
    return auth_headers("dq:config:manage")


@pytest.fixture
def support_request_headers(auth_headers: callable) -> dict[str, str]:
    return auth_headers("dq:rules:read", email="admin@example.com")


def _save_app_config(client, headers: dict[str, str], payload: dict[str, Any]) -> None:
    response = client.put("/api/system/v1/app-config", headers=headers, json=payload)
    assert response.status_code == 200


def test_support_request_email_only_sends_smtp_email_and_reference_id(client, support_config_headers, support_request_headers, monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeSMTP.instances.clear()
    _save_app_config(
        client,
        support_config_headers,
        {
            "assistance_request_destinations": ["email"],
            "assistance_request_email_address": "prototype@jaccloud.nl",
            "support_email_smtp_host": "smtp.strato.com",
            "support_email_smtp_port": 465,
            "support_email_smtp_username": "prototype@jaccloud.nl",
            "support_email_smtp_password": "super-secret",
            "support_email_smtp_use_start_tls": True,
            "support_email_from_address": "prototype@jaccloud.nl",
        },
    )

    monkeypatch.setattr(support_endpoints.smtplib, "SMTP_SSL", _FakeSMTP)

    response = client.post(
        "/api/system/v1/support/requests",
        headers=support_request_headers,
        json={
            "title": "GX run plan validation assistance",
            "message": "Validation failed for run plan version gx-run-plan-del-34-v1.",
            "source": "gx-run-plans-admin",
            "workspace_id": "retail-banking",
            "run_plan_id": "gx-run-plan-del-34",
            "run_plan_version_id": "gx-run-plan-del-34-v1",
            "reference_id": "SUP-TEST123456",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reference_id"] == "SUP-TEST123456"
    assert payload["delivery_modes"] == ["email"]
    assert payload["recipient_email"] == "prototype@jaccloud.nl"
    assert payload["mailto_url"] is None
    assert payload["message"] == "Sent email assistance request to prototype@jaccloud.nl. Reference ID: SUP-TEST123456"

    assert len(_FakeSMTP.instances) == 1
    smtp = _FakeSMTP.instances[0]
    assert smtp.host == "smtp.strato.com"
    assert smtp.port == 465
    assert smtp.started_tls is False
    assert smtp.login_args == ("prototype@jaccloud.nl", "super-secret")
    assert len(smtp.sent_messages) == 1
    email_message = smtp.sent_messages[0]
    assert email_message["From"] == "prototype@jaccloud.nl"
    assert email_message["To"] == "prototype@jaccloud.nl"
    assert email_message["Subject"] == "GX run plan validation assistance [SUP-TEST123456]"
    assert "Reference ID: SUP-TEST123456" in email_message.get_content()


def test_support_request_email_falls_back_to_mailto_when_smtp_is_missing(client, support_config_headers, support_request_headers) -> None:
    _save_app_config(
        client,
        support_config_headers,
        {
            "assistance_request_destinations": ["email"],
            "assistance_request_email_address": "prototype@jaccloud.nl",
        },
    )

    response = client.post(
        "/api/system/v1/support/requests",
        headers=support_request_headers,
        json={
            "title": "GX run plan validation assistance",
            "message": "Validation failed for run plan version gx-run-plan-del-34-v1.",
            "source": "gx-run-plans-admin",
            "workspace_id": "retail-banking",
            "run_plan_id": "gx-run-plan-del-34",
            "run_plan_version_id": "gx-run-plan-del-34-v1",
            "reference_id": "SUP-TEST123456",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["delivery_modes"] == ["email"]
    assert payload["recipient_email"] == "prototype@jaccloud.nl"
    assert payload["mailto_url"] is not None
    assert payload["mailto_url"].startswith("mailto:prototype@jaccloud.nl")
    assert payload["message"] == "Prepared email draft for prototype@jaccloud.nl. Reference ID: SUP-TEST123456"


def test_support_request_routes_to_teams_and_itsm(client, support_config_headers, support_request_headers, monkeypatch: pytest.MonkeyPatch) -> None:
    _save_app_config(
        client,
        support_config_headers,
        {
            "assistance_request_destinations": ["teams", "itsm"],
            "assistance_request_itsm_system": "Zammad",
            "assistance_request_itsm_endpoint_url": "https://itsm.example.com/api/v1/tickets",
            "assistance_request_teams_webhook_url": "https://teams.example.com/webhook",
            "assistance_request_itsm_auth_token": "zammad-api-token",
        },
    )

    posts: list[tuple[str, Any, dict[str, str]]] = []
    fake_response = _FakeResponse(200, {"ticket_number": "HAL-4242", "ticket_url": "https://itsm.example.com/tickets/4242"})

    class FakeAsyncClient(_FakeAsyncClient):
        def __init__(self, timeout: float | None = None) -> None:
            super().__init__(posts, fake_response)

    monkeypatch.setattr(support_endpoints.httpx, "AsyncClient", FakeAsyncClient)

    response = client.post(
        "/api/system/v1/support/requests",
        headers=support_request_headers,
        json={
            "title": "GX run plan validation assistance",
            "message": "Validation failed for run plan version gx-run-plan-del-34-v1.",
            "source": "gx-run-plans-admin",
            "workspace_id": "retail-banking",
            "run_plan_id": "gx-run-plan-del-34",
            "run_plan_version_id": "gx-run-plan-del-34-v1",
            "reference_id": "SUP-TEST123456",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["delivery_modes"] == ["teams", "itsm"]
    assert payload["ticket_number"] == "HAL-4242"
    assert payload["ticket_system"] == "Zammad"
    assert payload["ticket_url"] == "https://itsm.example.com/tickets/4242"
    assert len(posts) == 2
    assert posts[0][0] == "https://teams.example.com/webhook"
    assert posts[1][0] == "https://itsm.example.com/api/v1/tickets"
    assert posts[1][2]["Authorization"] == "Token token=zammad-api-token"
    assert posts[1][1]["title"] == "GX run plan validation assistance"
    assert posts[1][1]["group"] == "Users"
    assert isinstance(posts[1][1]["customer"], str)
    assert "@" in posts[1][1]["customer"]

    article = posts[1][1]["article"]
    assert article["sender"] == "Customer"
    assert article["type"] == "note"
    assert article["content_type"] == "text/plain"
    assert "Reference ID: SUP-TEST123456" in article["body"]
    assert "Validation failed for run plan version gx-run-plan-del-34-v1." in article["body"]


def test_support_request_resolves_requester_email_from_claims(client, support_config_headers, auth_headers, monkeypatch: pytest.MonkeyPatch) -> None:
    _save_app_config(
        client,
        support_config_headers,
        {
            "assistance_request_destinations": ["itsm"],
            "assistance_request_itsm_system": "Zammad",
            "assistance_request_itsm_endpoint_url": "https://itsm.example.com/api/v1/tickets",
            "assistance_request_itsm_auth_token": "zammad-api-token",
        },
    )

    posts: list[tuple[str, Any, dict[str, str]]] = []
    fake_response = _FakeResponse(200, {"ticket_number": "HAL-4242", "ticket_url": "https://itsm.example.com/tickets/4242"})

    class FakeAsyncClient(_FakeAsyncClient):
        def __init__(self, timeout: float | None = None) -> None:
            super().__init__(posts, fake_response)

    monkeypatch.setattr(support_endpoints.httpx, "AsyncClient", FakeAsyncClient)

    response = client.post(
        "/api/system/v1/support/requests",
        headers=auth_headers(
            "dq:rules:read",
            sub="oidc-sub-007",
            preferred_username="john.doe",
            email="admin@example.com",
        ),
        json={
            "title": "GX run plan validation assistance",
            "message": "Validation failed for run plan version gx-run-plan-del-34-v1.",
            "source": "gx-run-plans-admin",
            "workspace_id": "retail-banking",
            "run_plan_id": "gx-run-plan-del-34",
            "run_plan_version_id": "gx-run-plan-del-34-v1",
            "reference_id": "SUP-TEST123456",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["delivery_modes"] == ["itsm"]
    assert payload["ticket_number"] == "HAL-4242"
    assert payload["ticket_system"] == "Zammad"
    assert payload["ticket_url"] == "https://itsm.example.com/tickets/4242"
    assert len(posts) == 1
    assert posts[0][0] == "https://itsm.example.com/api/v1/tickets"
    assert posts[0][2]["Authorization"] == "Token token=zammad-api-token"
    assert posts[0][1]["customer"] == "admin@example.com"


def test_support_request_itsm_requires_configured_system(client, support_config_headers, support_request_headers) -> None:
    _save_app_config(
        client,
        support_config_headers,
        {
            "assistance_request_destinations": ["itsm"],
            "assistance_request_itsm_system": "",
            "assistance_request_itsm_endpoint_url": "https://itsm.example.com/api/v1/tickets",
        },
    )

    response = client.post(
        "/api/system/v1/support/requests",
        headers=support_request_headers,
        json={
            "title": "GX run plan validation assistance",
            "message": "Validation failed for run plan version gx-run-plan-del-34-v1.",
            "source": "gx-run-plans-admin",
            "workspace_id": "retail-banking",
            "run_plan_id": "gx-run-plan-del-34",
            "run_plan_version_id": "gx-run-plan-del-34-v1",
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["detail"]["error"] == "itsm_system_missing"


def test_support_request_itsm_requires_zammad_api_token(client, support_config_headers, support_request_headers) -> None:
    _save_app_config(
        client,
        support_config_headers,
        {
            "assistance_request_destinations": ["itsm"],
            "assistance_request_itsm_system": "Zammad",
            "assistance_request_itsm_endpoint_url": "https://itsm.example.com/api/v1/tickets",
            "assistance_request_itsm_auth_token": "",
        },
    )

    response = client.post(
        "/api/system/v1/support/requests",
        headers=support_request_headers,
        json={
            "title": "GX run plan validation assistance",
            "message": "Validation failed for run plan version gx-run-plan-del-34-v1.",
            "source": "gx-run-plans-admin",
            "workspace_id": "retail-banking",
            "run_plan_id": "gx-run-plan-del-34",
            "run_plan_version_id": "gx-run-plan-del-34-v1",
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["detail"]["error"] == "itsm_auth_token_missing"


def test_support_request_itsm_accepts_numeric_ticket_identifiers(client, support_config_headers, support_request_headers, monkeypatch: pytest.MonkeyPatch) -> None:
    _save_app_config(
        client,
        support_config_headers,
        {
            "assistance_request_destinations": ["itsm"],
            "assistance_request_itsm_system": "Zammad",
            "assistance_request_itsm_endpoint_url": "https://itsm.example.com/api/v1/tickets",
            "assistance_request_itsm_auth_token": "zammad-api-token",
        },
    )

    posts: list[tuple[str, Any, dict[str, str]]] = []
    fake_response = _FakeResponse(
        200,
        {
            "id": 4,
            "ticket": {"id": 8, "number": 9},
            "data": {"id": 12, "ticket_id": 16},
        },
    )

    class FakeAsyncClient(_FakeAsyncClient):
        def __init__(self, timeout: float | None = None) -> None:
            super().__init__(posts, fake_response)

    monkeypatch.setattr(support_endpoints.httpx, "AsyncClient", FakeAsyncClient)

    response = client.post(
        "/api/system/v1/support/requests",
        headers=support_request_headers,
        json={
            "title": "GX run plan validation assistance",
            "message": "Validation failed for run plan version gx-run-plan-del-34-v1.",
            "source": "gx-run-plans-admin",
            "workspace_id": "retail-banking",
            "run_plan_id": "gx-run-plan-del-34",
            "run_plan_version_id": "gx-run-plan-del-34-v1",
            "reference_id": "SUP-TEST123456",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticket_number"] == "4"
    assert payload["ticket_system"] == "Zammad"
    assert len(posts) == 1
