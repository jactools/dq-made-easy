from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import Request
from starlette.responses import Response

from app.domain.entities import SessionEntity
from app.middleware import auth_middleware as auth_mw
from app.middleware.require_kong_gateway import RequireKongGatewayMiddleware
from app.core.request_context import get_correlation_id
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.middleware.timing import RequestTimingMiddleware
from app.middleware.api_case_enforcement import ApiCaseEnforcementMiddleware


@pytest.mark.anyio
async def test_correlation_id_middleware_sets_header_and_state():
    middleware = CorrelationIdMiddleware(app=None)
    request = Request({"type": "http", "method": "GET", "path": "/x", "headers": [(b"x-correlation-id", b"cid-1")]})

    async def next_call(req):
        return Response("ok")

    response = await middleware.dispatch(request, next_call)

    assert response.headers["X-Correlation-ID"] == "cid-1"
    assert "X-Trace-ID" not in response.headers or response.headers["X-Trace-ID"]
    assert request.state.correlation_id == "cid-1"
    assert get_correlation_id() == "cid-1"


@pytest.mark.anyio
async def test_correlation_id_middleware_generates_when_header_missing():
    middleware = CorrelationIdMiddleware(app=None)
    request = Request({"type": "http", "method": "GET", "path": "/x", "headers": []})

    async def next_call(req):
        return Response("ok")

    response = await middleware.dispatch(request, next_call)

    generated = response.headers["X-Correlation-ID"]
    # Ensure generated value is a UUID and propagated to state + context.
    UUID(generated)
    assert request.state.correlation_id == generated
    assert get_correlation_id() == generated


@pytest.mark.anyio
async def test_correlation_id_middleware_returns_trace_header_from_scope():
    middleware = CorrelationIdMiddleware(app=None)
    request = Request({"type": "http", "method": "GET", "path": "/x", "headers": [], "otel.trace_id": "ignored"})
    request.scope["otel.trace_id"] = "abc123def456abc123def456abc123de"

    async def next_call(req):
        return Response("ok")

    response = await middleware.dispatch(request, next_call)

    assert response.headers["X-Trace-ID"] == "abc123def456abc123def456abc123de"


@pytest.mark.anyio
async def test_timing_middleware_sets_elapsed_header():
    middleware = RequestTimingMiddleware(app=None)
    request = Request({"type": "http", "method": "GET", "path": "/x", "headers": []})

    async def next_call(req):
        return Response("ok")

    response = await middleware.dispatch(request, next_call)

    assert "X-Process-Time-MS" in response.headers


@pytest.mark.anyio
async def test_timing_middleware_records_low_cardinality_metrics(monkeypatch):
    middleware = RequestTimingMiddleware(app=None)
    request = Request({"type": "http", "method": "GET", "path": "/api/rulebuilder/v1/rules", "headers": []})
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "app.middleware.timing.record_request_metric",
        lambda **kwargs: captured.update(kwargs),
    )

    async def next_call(req):
        return Response("ok", status_code=200)

    response = await middleware.dispatch(request, next_call)

    assert "X-Process-Time-MS" in response.headers
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/rulebuilder/v1/rules"
    assert captured["status_code"] == 200
    assert isinstance(captured["duration_ms"], float)


@pytest.mark.anyio
async def test_auth_middleware_unauthorized_when_scope_required_and_no_token(monkeypatch):
    middleware = auth_mw.AuthMiddleware(app=None)
    request = Request({"type": "http", "method": "GET", "path": "/secure", "headers": []})
    captured: dict[str, object] = {}

    monkeypatch.setattr(auth_mw, "get_settings", lambda: SimpleNamespace(trust_proxy_auth=False))
    monkeypatch.setattr(auth_mw, "get_required_scopes", lambda method, path: ["dq:admin"])
    monkeypatch.setattr(auth_mw, "get_bearer_token", lambda request: (None, None))
    monkeypatch.setattr(auth_mw, "increment_auth_failure", lambda **kwargs: captured.update(kwargs))

    response = await middleware.dispatch(request, lambda req: Response("ok"))

    assert response.status_code == 401
    assert captured["reason"] == "missing_token"


@pytest.mark.anyio
async def test_auth_middleware_forbidden_when_scope_missing(monkeypatch):
    middleware = auth_mw.AuthMiddleware(app=None)
    request = Request({"type": "http", "method": "GET", "path": "/secure", "headers": []})
    captured: dict[str, object] = {}

    monkeypatch.setattr(auth_mw, "get_settings", lambda: SimpleNamespace(trust_proxy_auth=False))
    monkeypatch.setattr(auth_mw, "get_required_scopes", lambda method, path: ["dq:admin"])
    monkeypatch.setattr(auth_mw, "get_bearer_token", lambda request: ("token", "authorization"))
    monkeypatch.setattr(
        auth_mw,
        "build_principal",
        lambda token, source, settings, consumer_groups=None: SimpleNamespace(
            user_id="u1",
            scopes=["dq:view"],
            consumer_groups=list(consumer_groups or []),
            claims={"sub": "u1"},
        ),
    )
    monkeypatch.setattr(auth_mw, "has_required_scope", lambda scopes, required: False)
    monkeypatch.setattr(auth_mw, "increment_auth_failure", lambda **kwargs: captured.update(kwargs))

    response = await middleware.dispatch(request, lambda req: Response("ok"))

    assert response.status_code == 403
    assert captured["reason"] == "missing_scope"


@pytest.mark.anyio
async def test_auth_middleware_allows_request_with_valid_scope_and_clears_context(monkeypatch):
    middleware = auth_mw.AuthMiddleware(app=None)
    request = Request({"type": "http", "method": "GET", "path": "/secure", "headers": [(b"x-consumer-groups", b"viewer,analyst")]})
    cleared = {"called": False}
    captured: dict[str, object] = {}

    monkeypatch.setattr(auth_mw, "get_settings", lambda: SimpleNamespace(trust_proxy_auth=False))
    monkeypatch.setattr(auth_mw, "get_required_scopes", lambda method, path: ["dq:view"])
    monkeypatch.setattr(auth_mw, "get_bearer_token", lambda request: ("token", "authorization"))
    monkeypatch.setattr(
        auth_mw,
        "build_principal",
        lambda token, source, settings, consumer_groups=None: SimpleNamespace(
            user_id="u1",
            scopes=["dq:view"],
            consumer_groups=list(consumer_groups or []),
            claims={"sub": "u1"},
        ),
    )
    monkeypatch.setattr(auth_mw, "has_required_scope", lambda scopes, required: True)
    monkeypatch.setattr(auth_mw, "set_user_id", lambda user_id: captured.__setitem__("user_id", user_id))
    monkeypatch.setattr(auth_mw, "set_scopes", lambda scopes: captured.__setitem__("scopes", list(scopes)))
    monkeypatch.setattr(auth_mw, "set_consumer_groups", lambda groups: captured.__setitem__("consumer_groups", list(groups)))
    monkeypatch.setattr(auth_mw, "clear_auth_context", lambda: cleared.__setitem__("called", True))

    async def next_call(req):
        return Response("ok", status_code=200)

    response = await middleware.dispatch(request, next_call)

    assert response.status_code == 200
    assert cleared["called"] is True
    assert captured["consumer_groups"] == ["viewer", "analyst"]


@pytest.mark.anyio
async def test_require_kong_gateway_blocks_api_direct_calls() -> None:
    middleware = RequireKongGatewayMiddleware(app=None)
    request = Request({"type": "http", "method": "GET", "path": "/api/rulebuilder/v1/rules", "headers": []})

    response = await middleware.dispatch(request, lambda req: Response("ok"))

    assert response.status_code == 403
    assert response.body == b'{"detail":"Requests bypassing Kong are not allowed."}'


@pytest.mark.anyio
async def test_require_kong_gateway_allows_health_endpoints() -> None:
    middleware = RequireKongGatewayMiddleware(app=None)
    request = Request({"type": "http", "method": "GET", "path": "/health", "headers": []})

    async def next_call(req: Request) -> Response:
        return Response("ok", status_code=200)

    response = await middleware.dispatch(request, next_call)

    assert response.status_code == 200


@pytest.mark.anyio
async def test_auth_middleware_trusted_proxy_allows_request_with_valid_scope(monkeypatch) -> None:
    middleware = auth_mw.AuthMiddleware(app=None)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/secure",
            "headers": [(b"x-consumer-custom-id", b"proxy-user")],
        }
    )
    cleared = {"called": False}
    captured: dict[str, object] = {}

    monkeypatch.setattr(auth_mw, "get_settings", lambda: SimpleNamespace(trust_proxy_auth=True))
    monkeypatch.setattr(auth_mw, "get_required_scopes", lambda method, path: ["dq:view"])
    monkeypatch.setattr(auth_mw, "get_bearer_token", lambda request: ("token", "authorization"))
    monkeypatch.setattr(
        auth_mw,
        "build_principal_trusted",
        lambda token, source, consumer_groups=None: SimpleNamespace(
            user_id="u1",
            scopes=["dq:view"],
            consumer_groups=list(consumer_groups or []),
            claims={"sub": "u1"},
        ),
    )
    monkeypatch.setattr(auth_mw, "has_required_scope", lambda scopes, required: True)
    monkeypatch.setattr(auth_mw, "set_user_id", lambda user_id: captured.__setitem__("user_id", user_id))
    monkeypatch.setattr(auth_mw, "set_scopes", lambda scopes: captured.__setitem__("scopes", list(scopes)))
    monkeypatch.setattr(auth_mw, "set_consumer_groups", lambda groups: captured.__setitem__("consumer_groups", list(groups)))
    monkeypatch.setattr(auth_mw, "clear_auth_context", lambda: cleared.__setitem__("called", True))

    async def next_call(req):
        return Response("ok", status_code=200)

    response = await middleware.dispatch(request, next_call)

    assert response.status_code == 200
    assert captured["user_id"] == "u1"
    assert cleared["called"] is True


@pytest.mark.anyio
async def test_auth_middleware_accepts_typed_session_entity_from_cookie(monkeypatch) -> None:
    middleware = auth_mw.AuthMiddleware(app=None)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/secure",
            "headers": [(b"cookie", b"dq_session=sid-1")],
            "app": SimpleNamespace(dependency_overrides={}),
        }
    )

    class FakeSessionRepository:
        def get_session(self, session_id: str) -> SessionEntity | None:
            assert session_id == "sid-1"
            return SessionEntity(
                id="sid-1",
                user_id="u1",
                last_activity=datetime.now(),
                access_token="cookie-token",
            )

    monkeypatch.setattr(auth_mw, "get_settings", lambda: SimpleNamespace(trust_proxy_auth=False))
    monkeypatch.setattr(auth_mw, "get_required_scopes", lambda method, path: [])
    monkeypatch.setattr(auth_mw, "get_bearer_token", lambda request: (None, None))
    monkeypatch.setattr(auth_mw, "get_session_repository", lambda: FakeSessionRepository())
    monkeypatch.setattr(
        auth_mw,
        "build_principal",
        lambda token, source, settings, consumer_groups=None: SimpleNamespace(
            user_id="u1",
            scopes=["dq:view"],
            consumer_groups=list(consumer_groups or []),
            claims={"sub": "u1"},
        ),
    )

    async def next_call(req: Request) -> Response:
        return Response("ok", status_code=200)

    response = await middleware.dispatch(request, next_call)

    assert response.status_code == 200


@pytest.mark.anyio
async def test_auth_middleware_accepts_typed_session_entity_for_sid_enforcement(monkeypatch) -> None:
    middleware = auth_mw.AuthMiddleware(app=None)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/secure",
            "headers": [],
            "app": SimpleNamespace(dependency_overrides={}),
        }
    )
    touched: list[str] = []

    class FakeSessionRepository:
        def get_session(self, session_id: str) -> SessionEntity | None:
            assert session_id == "sid-1"
            return SessionEntity(
                id="sid-1",
                user_id="u1",
                last_activity=datetime.now(),
                access_token="token",
            )

        def touch_session(self, session_id: str) -> None:
            touched.append(session_id)

    monkeypatch.setattr(auth_mw, "get_settings", lambda: SimpleNamespace(trust_proxy_auth=False))
    monkeypatch.setattr(auth_mw, "get_required_scopes", lambda method, path: [])
    monkeypatch.setattr(auth_mw, "get_bearer_token", lambda request: ("token", "authorization"))
    monkeypatch.setattr(auth_mw, "get_session_repository", lambda: FakeSessionRepository())
    monkeypatch.setattr(
        auth_mw,
        "get_app_config_repository",
        lambda: SimpleNamespace(get_app_config=lambda: SimpleNamespace(sessionTimeoutMinutes=5)),
    )
    monkeypatch.setattr(
        auth_mw,
        "build_principal",
        lambda token, source, settings, consumer_groups=None: SimpleNamespace(
            user_id="u1",
            scopes=["dq:view"],
            consumer_groups=list(consumer_groups or []),
            claims={"sub": "u1", "sid": "sid-1"},
        ),
    )

    async def next_call(req: Request) -> Response:
        return Response("ok", status_code=200)

    response = await middleware.dispatch(request, next_call)

    assert response.status_code == 200
    assert touched == ["sid-1"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "request_path",
    [
        "/api/rulebuilder/v1/validation-run-plans/plan-1/replay",
        "/rulebuilder/v1/validation-run-plans/plan-1/replay",
    ],
)
async def test_auth_middleware_allows_internal_validation_replay_bearer_without_session(monkeypatch, request_path: str) -> None:
    middleware = auth_mw.AuthMiddleware(app=None)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": request_path,
            "headers": [],
            "app": SimpleNamespace(dependency_overrides={}),
        }
    )
    session_lookup = {"called": False}

    class FakeSessionRepository:
        def get_session(self, session_id: str):
            session_lookup["called"] = True
            raise AssertionError("session lookup should be skipped for internal replay bearer auth")

    monkeypatch.setattr(auth_mw, "get_settings", lambda: SimpleNamespace(trust_proxy_auth=False))
    monkeypatch.setattr(auth_mw, "get_required_scopes", lambda method, path: ["dq:rules:manage"])
    monkeypatch.setattr(auth_mw, "get_bearer_token", lambda request: ("token", "authorization"))
    monkeypatch.setattr(auth_mw, "get_session_repository", lambda: FakeSessionRepository())
    monkeypatch.setattr(
        auth_mw,
        "get_app_config_repository",
        lambda: SimpleNamespace(get_app_config=lambda: SimpleNamespace(sessionTimeoutMinutes=5)),
    )
    monkeypatch.setattr(auth_mw, "get_admin_repository", lambda: None)
    monkeypatch.setattr(
        auth_mw,
        "build_principal",
        lambda token, source, settings, consumer_groups=None: SimpleNamespace(
            user_id="u1",
            scopes=["dq:rules:manage"],
            consumer_groups=list(consumer_groups or []),
            claims={"sub": "u1", "sid": "sid-1"},
        ),
    )
    monkeypatch.setattr(auth_mw, "has_required_scope", lambda scopes, required: True)

    async def next_call(req: Request) -> Response:
        return Response("ok", status_code=200)

    response = await middleware.dispatch(request, next_call)

    assert response.status_code == 200
    assert session_lookup["called"] is False


async def _run_http_middleware(middleware, scope: dict, body: bytes = b"") -> tuple[int, dict[str, str], bytes]:
    sent_messages: list[dict] = []
    body_sent = False

    async def receive() -> dict:
        nonlocal body_sent
        if body_sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        body_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict) -> None:
        sent_messages.append(message)

    await middleware(scope, receive, send)

    response_start = next(message for message in sent_messages if message.get("type") == "http.response.start")
    response_body = b"".join(
        message.get("body", b"")
        for message in sent_messages
        if message.get("type") == "http.response.body"
    )
    headers = {
        key.decode("latin-1"): value.decode("latin-1")
        for key, value in response_start.get("headers", [])
    }
    return int(response_start["status"]), headers, response_body


@pytest.mark.anyio
async def test_api_case_enforcement_preserves_snake_case_request_bodies():
    captured: dict[str, object] = {}

    async def app(scope: dict, receive, send) -> None:
        req = Request(scope, receive)
        captured.update(await req.json())
        response = Response(json.dumps({"ok": True}), media_type="application/json")
        await response(scope, receive, send)

    middleware = ApiCaseEnforcementMiddleware(app)
    status_code, _, response_body = await _run_http_middleware(
        middleware,
        {
            "type": "http",
            "method": "POST",
            "path": "/api/rulebuilder/v1/rules",
            "headers": [(b"content-type", b"application/json")],
        },
        json.dumps(
            {
                "workspace_id": "ws-a",
                "manual_alias_mappings": {"source_column": "target_column"},
            }
        ).encode("utf-8"),
    )

    assert status_code == 200
    assert captured["workspace_id"] == "ws-a"
    assert captured["manual_alias_mappings"] == {"source_column": "target_column"}
    assert json.loads(response_body) == {"ok": True}


@pytest.mark.anyio
async def test_api_case_enforcement_normalizes_response_to_snake_case():
    async def app(scope: dict, receive, send) -> None:
        response = Response(
            json.dumps(
                {
                    "buildDate": "2026-03-28",
                    "apiInfo": {"schemaVersion": "v1"},
                    "listRows": [{"ruleId": "rule-1"}],
                }
            ),
            media_type="application/json",
        )
        await response(scope, receive, send)

    middleware = ApiCaseEnforcementMiddleware(app)
    status_code, _, response_body = await _run_http_middleware(
        middleware,
        {"type": "http", "method": "GET", "path": "/api/system/v1/system-info", "headers": []},
    )
    payload = json.loads(response_body)

    assert status_code == 200
    assert payload["build_date"] == "2026-03-28"
    assert payload["api_info"]["schema_version"] == "v1"
    assert payload["list_rows"][0]["rule_id"] == "rule-1"


@pytest.mark.anyio
async def test_api_case_enforcement_skips_non_api_paths():
    async def app(scope: dict, receive, send) -> None:
        response = Response(json.dumps({"buildDate": "same"}), media_type="application/json")
        await response(scope, receive, send)

    middleware = ApiCaseEnforcementMiddleware(app)
    status_code, _, response_body = await _run_http_middleware(
        middleware,
        {"type": "http", "method": "GET", "path": "/health", "headers": []},
    )

    assert status_code == 200
    assert json.loads(response_body) == {"buildDate": "same"}
