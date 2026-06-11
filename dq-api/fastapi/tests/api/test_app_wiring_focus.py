from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.main as main_mod
from app.api.v1.router import api_router
from app.main import create_app


def test_api_router_contains_expected_routes():
    paths = {route.path for route in api_router.routes}

    assert "/rulebuilder/v1/rules" in paths
    assert "/rulebuilder/v1/rules/{rule_id}" in paths
    assert "/system/v1/system-info" in paths
    assert "/rulebuilder/v1/workspaces" in paths


def test_create_app_registers_middlewares_and_prefixes():
    app = create_app()

    middleware_names = [entry.cls.__name__ for entry in app.user_middleware]
    assert "AuthMiddleware" in middleware_names
    assert "CorrelationIdMiddleware" in middleware_names
    assert "RequestTimingMiddleware" in middleware_names

    paths = {route.path for route in app.routes}
    assert "/api/system/v1/system-info" in paths
    assert "/system/v1/system-info" in paths


def test_create_app_instruments_fastapi(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(main_mod, "instrument_app", lambda app, settings: captured.update({"app": app, "settings": settings}))

    app = create_app()

    assert captured["app"] is app


def test_create_app_requires_database_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(
        main_mod,
        "get_settings",
        lambda: SimpleNamespace(
            app_name="DQ API",
            api_v1_prefix="/api/v1",
            gateway_api_prefix="/v1",
            log_level="INFO",
            cors_origins_list=["http://localhost:5173"],
            require_database=True,
            database_url=None,
            validate_runtime_requirements=lambda: (_ for _ in ()).throw(
                RuntimeError("DQ_DB_INTERNAL_URL or DQ_DB_LOCAL_URL is required when REQUIRE_DATABASE=true")
            ),
        ),
    )
    monkeypatch.setattr(main_mod, "instrument_app", lambda app, settings: None)

    with pytest.raises(RuntimeError, match="DQ_DB_INTERNAL_URL or DQ_DB_LOCAL_URL is required"):
        create_app()
