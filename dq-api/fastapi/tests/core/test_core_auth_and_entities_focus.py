from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.auth import Settings
import app.core.auth as auth_mod
import app.core.dependencies as deps_mod


def test_core_auth_branch_paths() -> None:
    settings = Settings(sso_enabled=True, sso_issuer="http://issuer", sso_client_id="client")

    assert auth_mod.get_required_scopes("POST", "/rulebuilder/v1/rules")
    assert auth_mod.get_required_scopes("PUT", "/rulebuilder/v1/rules/1")
    assert auth_mod.get_required_scopes("DELETE", "/rulebuilder/v1/rules/1")
    assert auth_mod.get_required_scopes("POST", "/data-catalog/v1/rule-attributes")
    assert auth_mod.get_required_scopes("GET", "/data-catalog/v1/suggestions")
    assert auth_mod.get_required_scopes("POST", "/data-catalog/v1/profiling/requests")
    assert auth_mod.get_required_scopes("PATCH", "/rulebuilder/v1/approvals/1")
    assert auth_mod.get_required_scopes("GET", "/rulebuilder/v1/workspaces")
    assert auth_mod.get_required_scopes("GET", "/system/v1/app-config")
    assert auth_mod.get_required_scopes("GET", "/data-catalog/v1/profiling/requests")
    assert auth_mod.get_required_scopes("POST", "/data-catalog/v1/suggestions")
    assert auth_mod.get_required_scopes("POST", "/v1/other")
    assert auth_mod.get_required_scopes("GET", "/v1/other")

    assert auth_mod.decode_jwt_payload("bad") is None
    payload = {
        "sub": "u1",
        "iss": "http://issuer",
        "aud": ["client"],
        "scope": "dq:rules:read",
    }
    token = "{}.{}.sig".format(
        "e30",
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("="),
    )

    decoded = auth_mod.decode_jwt_payload(token)
    assert decoded and decoded["sub"] == "u1"
    assert auth_mod.is_jwt_payload_valid(decoded, settings)

    list_payload = "{}.{}.sig".format(
        "e30",
        base64.urlsafe_b64encode(json.dumps(["not", "dict"]).encode()).decode().rstrip("="),
    )
    assert auth_mod.decode_jwt_payload(list_payload) is None

    bad_iss = dict(decoded)
    bad_iss["iss"] = "http://other"
    assert not auth_mod.is_jwt_payload_valid(bad_iss, settings)

    bad_aud = dict(decoded)
    bad_aud["aud"] = ["other"]
    assert not auth_mod.is_jwt_payload_valid(bad_aud, settings)

    bad_nbf = dict(decoded)
    bad_nbf["nbf"] = 99999999999
    assert not auth_mod.is_jwt_payload_valid(bad_nbf, settings)

    principal = auth_mod.build_principal(token, "authorization", settings)
    assert principal is not None
    assert principal.user_id == "u1"
    assert "dq:rules:read" in principal.scopes

    assert auth_mod.build_principal("bad", "authorization", settings) is None


def test_dependencies_remaining_branches(monkeypatch) -> None:
    monkeypatch.setattr(deps_mod, "PostgresRulesRepository", lambda dsn: ("r", dsn))
    monkeypatch.setattr(deps_mod, "PostgresAdminRepository", lambda dsn: ("a", dsn))
    monkeypatch.setattr(deps_mod, "PostgresDataCatalogRepository", lambda dsn: ("c", dsn))
    monkeypatch.setattr(deps_mod, "PostgresMasterDataRepository", lambda dsn: ("m", dsn))
    monkeypatch.setattr(deps_mod, "PostgresApprovalsRepository", lambda dsn: ("ap", dsn))
    monkeypatch.setattr(deps_mod, "PostgresWorkspacesRepository", lambda dsn: ("w", dsn))
    monkeypatch.setattr(deps_mod, "PostgresTestingRepository", lambda dsn: ("t", dsn))

    deps_mod._get_postgres_rules_repository.cache_clear()
    deps_mod._get_postgres_admin_repository.cache_clear()
    deps_mod._get_postgres_catalog_repository.cache_clear()
    deps_mod._get_postgres_master_data_repository.cache_clear()
    deps_mod._get_postgres_approvals_repository.cache_clear()
    deps_mod._get_postgres_workspaces_repository.cache_clear()
    deps_mod._get_postgres_testing_repository.cache_clear()

    assert deps_mod._get_postgres_rules_repository("postgresql://x")[0] == "r"
    assert deps_mod._get_postgres_admin_repository("postgresql://x")[0] == "a"
    assert deps_mod._get_postgres_catalog_repository("postgresql://x")[0] == "c"
    assert deps_mod._get_postgres_master_data_repository("postgresql://x")[0] == "m"
    assert deps_mod._get_postgres_approvals_repository("postgresql://x")[0] == "ap"
    assert deps_mod._get_postgres_workspaces_repository("postgresql://x")[0] == "w"
    assert deps_mod._get_postgres_testing_repository("postgresql://x")[0] == "t"

    monkeypatch.setattr(deps_mod, "get_settings", lambda: SimpleNamespace(database_url=None, require_database=False))
    with pytest.raises(HTTPException) as exc:
        deps_mod.get_rules_repository()
    assert exc.value.status_code == 503
    assert exc.value.detail["error"] == "repository_unavailable"
    assert exc.value.detail["service"] == "rules-repository"
