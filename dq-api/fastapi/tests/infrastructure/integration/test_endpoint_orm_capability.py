"""Integration policy guard for ORM-capable API endpoints.

Non-health API routes must depend on repository providers so integration runs
exercise Postgres-backed repositories when DATABASE_URL is configured.
"""
from __future__ import annotations

import sys

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.main import app

pytestmark = pytest.mark.integration

_HEALTH_EXEMPT_PATHS = {
    "/api/system/v1/health",
    "/api/system/v1/live",
    "/api/system/v1/readiness",
    "/api/system/v1/ready",
    "/api/rulebuilder/v1/catalog/health",
    "/api/rulebuilder/v1/governance/status-models/{entity}",
    "/api/system/v1/api-metrics/ping",
}

_NON_REPOSITORY_EXEMPT_PATHS = {
    "/api/data-catalog/v1/materialization-requests/{request_id}",
    "/api/data-catalog/v1/registry/definitions",
    "/api/data-catalog/v1/registry/definitions/{definition_id}",
    "/api/rulebuilder/v1/demo/snake",
    "/api/rulebuilder/v1/test-data/materializations/{request_id}",
    "/api/rulebuilder/v1/test-data/requests/{request_id}",
}

_MUTABLE_STORE_MODULE_ALLOWLIST = {
    "app.api.v1.endpoints.api_metrics",
    "app.api.v1.endpoints.execution_monitoring",
}


def _iter_dependency_calls(dependant: Dependant):
    for dependency in dependant.dependencies:
        if dependency.call is not None:
            yield dependency.call
        yield from _iter_dependency_calls(dependency)


def _is_repository_dependency(callable_obj) -> bool:
    module_name = str(getattr(callable_obj, "__module__", ""))
    func_name = str(getattr(callable_obj, "__name__", ""))
    return module_name == "app.core.dependencies" and func_name.endswith("_repository")


def _is_mutable_module_store(name: str, value: object) -> bool:
    normalized = name.lstrip("_")
    if not normalized or not normalized.isupper():
        return False
    if isinstance(value, (dict, list, set)):
        return True
    return False


def test_non_health_routes_are_repository_backed() -> None:
    violations: list[str] = []

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/"):
            continue
        if route.path in _HEALTH_EXEMPT_PATHS:
            continue
        if route.path in _NON_REPOSITORY_EXEMPT_PATHS:
            continue

        methods = sorted(method for method in route.methods if method not in {"HEAD", "OPTIONS"})
        if not methods:
            continue

        dependency_calls = list(_iter_dependency_calls(route.dependant))
        has_repository_dependency = any(_is_repository_dependency(call_obj) for call_obj in dependency_calls)
        if has_repository_dependency:
            continue

        violations.append(f"{','.join(methods)} {route.path}")

    assert not violations, "Non-health routes missing repository dependency:\n" + "\n".join(violations)


def test_non_health_endpoint_modules_avoid_mutable_runtime_stores() -> None:
    endpoint_modules: set[str] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/"):
            continue
        if route.path in _HEALTH_EXEMPT_PATHS:
            continue
        if route.path in _NON_REPOSITORY_EXEMPT_PATHS:
            continue
        endpoint_modules.add(str(route.endpoint.__module__))

    violations: list[str] = []
    for module_name in sorted(endpoint_modules):
        if module_name in _MUTABLE_STORE_MODULE_ALLOWLIST:
            continue
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for name, value in vars(module).items():
            if not _is_mutable_module_store(name, value):
                continue
            violations.append(f"{module_name}.{name}")

    assert not violations, "Non-health endpoint modules define mutable module stores:\n" + "\n".join(violations)
