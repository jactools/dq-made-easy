"""Unit tests for apply_validation_policies() — DQ-1.1."""
from __future__ import annotations

import pytest

from app.application.services.validation_policy import apply_validation_policies


pytestmark = pytest.mark.usefixtures("monkeypatch")


def _diag(code: str, severity: str = "error", message: str = "msg") -> dict:
    return {"code": code, "severity": severity, "message": message}


def _policy(check_id: str, enabled: bool = True, severity_override: str | None = None, scope: str = "all") -> dict:
    p: dict = {"checkId": check_id, "enabled": enabled, "scope": scope}
    if severity_override is not None:
        p["severityOverride"] = severity_override
    return p


# ── Pass-through when no policies ─────────────────────────────────────────────

def test_no_policies_returns_diagnostics_unchanged() -> None:
    diags = [_diag("DQ1_EMPTY_EXPRESSION")]
    assert apply_validation_policies(diags, None) == diags


def test_empty_policies_returns_diagnostics_unchanged() -> None:
    diags = [_diag("DQ1_EMPTY_EXPRESSION")]
    assert apply_validation_policies(diags, []) == diags


def test_unknown_check_id_passes_through() -> None:
    diags = [_diag("SOME_UNKNOWN_CODE")]
    policies = [_policy("DQ1_EMPTY_EXPRESSION")]
    result = apply_validation_policies(diags, policies)
    assert result == diags


# ── Disabled policy drops the diagnostic ─────────────────────────────────────

def test_disabled_policy_drops_matching_diagnostic() -> None:
    diags = [_diag("DQ1_MISSING_ALIAS", "warning"), _diag("DQ1_EMPTY_EXPRESSION", "error")]
    policies = [_policy("DQ1_MISSING_ALIAS", enabled=False)]
    result = apply_validation_policies(diags, policies)
    assert len(result) == 1
    assert result[0]["code"] == "DQ1_EMPTY_EXPRESSION"


def test_enabled_policy_keeps_diagnostic() -> None:
    diags = [_diag("DQ1_MISSING_ALIAS", "warning")]
    policies = [_policy("DQ1_MISSING_ALIAS", enabled=True)]
    result = apply_validation_policies(diags, policies)
    assert len(result) == 1


# ── Severity override ─────────────────────────────────────────────────────────

def test_severity_override_replaces_severity() -> None:
    diags = [_diag("DQ1_EXPRESSION_SYNTAX", "error")]
    policies = [_policy("DQ1_EXPRESSION_SYNTAX", severity_override="warning")]
    result = apply_validation_policies(diags, policies)
    assert result[0]["severity"] == "warning"
    assert result[0]["code"] == "DQ1_EXPRESSION_SYNTAX"


def test_no_severity_override_keeps_original_severity() -> None:
    diags = [_diag("DQ1_EXPRESSION_SYNTAX", "error")]
    policies = [_policy("DQ1_EXPRESSION_SYNTAX")]  # no override
    result = apply_validation_policies(diags, policies)
    assert result[0]["severity"] == "error"


# ── Scope filtering ───────────────────────────────────────────────────────────

def test_workspace_scope_matches_workspace() -> None:
    diags = [_diag("DQ1_MISSING_ALIAS", "warning")]
    policies = [_policy("DQ1_MISSING_ALIAS", enabled=False, scope="workspace:finance")]
    result = apply_validation_policies(diags, policies, workspace="finance")
    # policy applies → diagnostic dropped
    assert len(result) == 0


def test_workspace_scope_does_not_apply_to_wrong_workspace() -> None:
    diags = [_diag("DQ1_MISSING_ALIAS", "warning")]
    policies = [_policy("DQ1_MISSING_ALIAS", enabled=False, scope="workspace:finance")]
    result = apply_validation_policies(diags, policies, workspace="marketing")
    # policy does not apply → diagnostic kept
    assert len(result) == 1


def test_workspace_scope_does_not_apply_when_no_workspace() -> None:
    diags = [_diag("DQ1_MISSING_ALIAS", "warning")]
    policies = [_policy("DQ1_MISSING_ALIAS", enabled=False, scope="workspace:finance")]
    result = apply_validation_policies(diags, policies, workspace=None)
    assert len(result) == 1


def test_all_scope_applies_regardless_of_workspace() -> None:
    diags = [_diag("DQ1_MISSING_ALIAS", "warning")]
    policies = [_policy("DQ1_MISSING_ALIAS", enabled=False, scope="all")]
    result = apply_validation_policies(diags, policies, workspace="any-workspace")
    assert len(result) == 0


# ── Multiple diagnostics / policies ──────────────────────────────────────────

def test_multiple_policies_applied_independently() -> None:
    diags = [
        _diag("DQ1_EMPTY_EXPRESSION", "error"),
        _diag("DQ1_MISSING_ALIAS", "warning"),
        _diag("DQ1_DUPLICATE_NAME", "warning"),
    ]
    policies = [
        _policy("DQ1_EMPTY_EXPRESSION", severity_override="warning"),
        _policy("DQ1_MISSING_ALIAS", enabled=False),
    ]
    result = apply_validation_policies(diags, policies)
    # DQ1_EMPTY_EXPRESSION kept with overridden severity
    # DQ1_MISSING_ALIAS dropped
    # DQ1_DUPLICATE_NAME kept unchanged (no policy)
    assert len(result) == 2
    codes = {d["code"] for d in result}
    assert "DQ1_EMPTY_EXPRESSION" in codes
    assert "DQ1_DUPLICATE_NAME" in codes
    expr_diag = next(d for d in result if d["code"] == "DQ1_EMPTY_EXPRESSION")
    assert expr_diag["severity"] == "warning"


def test_blank_policy_ids_are_ignored_and_last_duplicate_policy_wins() -> None:
    diags = [_diag("DQ1_EMPTY_EXPRESSION", "error")]
    policies = [
        {"checkId": "   ", "enabled": False, "scope": "all"},
        _policy("DQ1_EMPTY_EXPRESSION", severity_override="warning"),
        _policy("DQ1_EMPTY_EXPRESSION", severity_override="info"),
    ]

    result = apply_validation_policies(diags, policies)

    assert result == [{"code": "DQ1_EMPTY_EXPRESSION", "severity": "info", "message": "msg"}]
