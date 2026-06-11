from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

import app.core.dependencies as deps
import app.core.errors as errors_mod


def test_dependencies_select_in_memory_and_postgres(monkeypatch) -> None:
    monkeypatch.setattr(deps, "get_settings", lambda: SimpleNamespace(database_url=None, require_database=False))

    unavailable_getters = [
        (deps.get_data_catalog_repository, "data-catalog-repository"),
        (deps.get_rules_repository, "rules-repository"),
        (deps.get_admin_repository, "admin-repository"),
        (deps.get_app_config_repository, "app-config-repository"),
        (deps.get_approvals_repository, "approvals-repository"),
        (deps.get_workspaces_repository, "workspaces-repository"),
        (deps.get_system_repository, "system-repository"),
        (deps.get_testing_repository, "testing-repository"),
        (deps.get_validation_run_repository, "validation-run-repository"),
        (deps.get_validation_artifact_repository, "validation-artifact-repository"),
        (deps.get_gx_execution_run_repository, "gx-execution-run-repository"),
        (deps.get_gx_run_plan_repository, "gx-run-plan-repository"),
        (deps.get_validation_run_plan_repository, "validation-run-plan-repository"),
        (deps.get_exception_fact_repository, "exception-fact-repository"),
        (deps.get_gx_suite_repository, "gx-suite-repository"),
        (deps.get_profiling_repository, "profiling-repository"),
    ]
    for getter, service in unavailable_getters:
        with pytest.raises(HTTPException) as exc:
            getter()
        assert exc.value.status_code == 503
        assert exc.value.detail["error"] == "repository_unavailable"
        assert exc.value.detail["service"] == service
        assert exc.value.detail["correlation_id"]

    with pytest.raises(HTTPException) as exc:
        deps.get_session_repository()
    assert exc.value.status_code == 503
    assert exc.value.detail["error"] == "session_store_unavailable"

    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: SimpleNamespace(database_url="postgresql://x", require_database=False),
    )
    monkeypatch.setattr(deps, "_get_postgres_catalog_repository", lambda dsn: ("catalog", dsn))
    monkeypatch.setattr(deps, "_get_postgres_rules_repository", lambda dsn: ("rules", dsn))
    monkeypatch.setattr(deps, "_get_postgres_admin_repository", lambda dsn: ("admin", dsn))
    monkeypatch.setattr(deps, "_get_postgres_app_config_repository", lambda dsn: ("appcfg", dsn))
    monkeypatch.setattr(deps, "_get_postgres_session_repository", lambda dsn: ("session", dsn))
    monkeypatch.setattr(deps, "_get_postgres_approvals_repository", lambda dsn: ("approvals", dsn))
    monkeypatch.setattr(deps, "_get_postgres_workspaces_repository", lambda dsn: ("workspaces", dsn))
    monkeypatch.setattr(deps, "_get_postgres_system_repository", lambda dsn: ("system", dsn))
    monkeypatch.setattr(deps, "_get_postgres_testing_repository", lambda dsn: ("testing", dsn))
    monkeypatch.setattr(deps, "_get_postgres_validation_run_repository", lambda dsn: ("validation", dsn))
    monkeypatch.setattr(deps, "_get_postgres_validation_artifact_repository", lambda dsn: ("validation-artifact", dsn))
    monkeypatch.setattr(deps, "_get_postgres_gx_execution_run_repository", lambda dsn: ("gxrun", dsn))
    monkeypatch.setattr(deps, "_get_postgres_gx_run_plan_repository", lambda dsn: ("gxplan", dsn))
    monkeypatch.setattr(deps, "_get_postgres_validation_run_plan_repository", lambda dsn: ("validation-plan", dsn))
    monkeypatch.setattr(deps, "_get_postgres_exception_fact_repository", lambda dsn: ("exceptionfacts", dsn))
    monkeypatch.setattr(deps, "_get_postgres_gx_suite_repository", lambda dsn: ("gxsuite", dsn))
    monkeypatch.setattr(deps, "_get_postgres_profiling_repository", lambda dsn: ("profiling", dsn))

    assert deps.get_data_catalog_repository()[0] == "catalog"
    assert deps.get_rules_repository()[0] == "rules"
    assert deps.get_admin_repository()[0] == "admin"
    assert deps.get_app_config_repository()[0] == "appcfg"
    assert deps.get_session_repository()[0] == "session"
    assert deps.get_approvals_repository()[0] == "approvals"
    assert deps.get_workspaces_repository()[0] == "workspaces"
    assert deps.get_system_repository()[0] == "system"
    assert deps.get_testing_repository()[0] == "testing"
    assert deps.get_validation_run_repository()[0] == "validation"
    assert deps.get_validation_artifact_repository()[0] == "validation-artifact"
    assert deps.get_gx_execution_run_repository()[0] == "gxrun"
    assert deps.get_gx_run_plan_repository()[0] == "gxplan"
    assert deps.get_validation_run_plan_repository()[0] == "validation-plan"
    assert deps.get_exception_fact_repository()[0] == "exceptionfacts"
    assert deps.get_gx_suite_repository()[0] == "gxsuite"
    assert deps.get_profiling_repository()[0] == "profiling"


def test_dependencies_raise_when_database_is_required(monkeypatch) -> None:
    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: SimpleNamespace(database_url=None, require_database=True),
    )

    with pytest.raises(RuntimeError, match="DQ_DB_INTERNAL_URL or DQ_DB_LOCAL_URL is required"):
        deps.get_rules_repository()


@pytest.mark.anyio
async def test_error_problem_details_and_handlers(monkeypatch) -> None:
    monkeypatch.setattr(errors_mod, "get_correlation_id", lambda: "corr-123")

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
        "http_version": "1.1",
    }

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(scope, receive)
    details = errors_mod._problem_details(request, status=418, title="Teapot", detail="brew")
    assert details["status"] == 418
    assert details["correlation_id"] == "corr-123"

    app = FastAPI()
    errors_mod.register_exception_handlers(app)

    http_handler = app.exception_handlers[StarletteHTTPException]
    validation_handler = app.exception_handlers[RequestValidationError]
    unhandled_handler = app.exception_handlers[Exception]

    http_response = await http_handler(request, StarletteHTTPException(status_code=404, detail="missing"))
    assert http_response.status_code == 404

    structured_http_response = await http_handler(
        request,
        StarletteHTTPException(
            status_code=503,
            detail={"error": "downstream_unavailable", "message": "service unavailable"},
        ),
    )
    assert structured_http_response.status_code == 503
    assert structured_http_response.body == (
        b'{"type":"about:blank","title":"HTTP Error","status":503,'
        b'"detail":{"error":"downstream_unavailable","message":"service unavailable"},'
        b'"instance":"/x","correlation_id":"corr-123"}'
    )

    validation_error = RequestValidationError(
        [{"loc": ("body", "field"), "msg": "required", "type": "value_error.missing"}]
    )
    validation_response = await validation_handler(request, validation_error)
    assert validation_response.status_code == 422

    unhandled_response = await unhandled_handler(request, RuntimeError("boom"))
    assert unhandled_response.status_code == 500
