"""Applies configurable validation policies to compiler diagnostics.

Policies are loaded from app_config.validationPolicies. For each diagnostic
the policy engine:

  1. Looks up the matching policy by checkId.
  2. If the policy is disabled, the diagnostic is dropped.
  3. If the policy has a severityOverride, the diagnostic severity is replaced.
  4. Policies with scope "workspace:<name>" are only applied when the workspace
     matches; otherwise the policy is ignored for that diagnostic.

Diagnostics whose checkId does not match any policy pass through unchanged.
"""
from __future__ import annotations

from typing import Any

_DEFAULT_SEVERITY_FOR_CHECK: dict[str, str] = {
    "DQ1_EMPTY_EXPRESSION": "error",
    "DQ1_EXPRESSION_SYNTAX": "error",
    "DQ1_UNSUPPORTED_KEYWORD": "error",
    "DQ1_MISSING_ALIAS": "warning",
    "DQ1_JOIN_VALIDATION": "warning",
    "DQ1_DUPLICATE_EXPRESSION": "warning",
    "DQ1_DUPLICATE_NAME": "warning",
    "DQ1_CONTRADICTORY_PREDICATES": "warning",
    # compiler-native codes also mapped so policies can override them
    "DQ7_FILTER_VALIDATION": "error",
    "DQ7_RESERVED_KEYWORD": "warning",
    "DQ7_UNSUPPORTED_AGGREGATE": "error",
    "DQ7_JOIN_VALIDATION": "warning",
    "DQ7_AST_PARSE": "error",
}


def _policy_applies(policy: dict[str, Any], workspace: str | None) -> bool:
    scope = str(policy.get("scope") or "all").strip()
    if scope == "all":
        return True
    if scope.startswith("workspace:") and workspace:
        return scope[len("workspace:"):] == workspace
    return False


def apply_validation_policies(
    diagnostics: list[dict[str, Any]],
    policies: list[dict[str, Any]] | None,
    workspace: str | None = None,
) -> list[dict[str, Any]]:
    """Return filtered/re-severity-mapped diagnostics after applying policies.

    Args:
        diagnostics: Raw diagnostics from the compiler (list of dicts with
                     at least ``code`` and ``severity`` fields).
        policies: List of policy dicts from app_config (may be None/empty).
        workspace: Current workspace name for scope-filtered policies.

    Returns:
        A new list of diagnostics after policy application.
    """
    if not policies:
        return list(diagnostics)

    # Build a lookup: checkId -> policy dict (last one wins on duplicate checkId)
    policy_index: dict[str, dict[str, Any]] = {}
    for policy in policies:
        check_id = str(policy.get("checkId") or "").strip()
        if check_id:
            policy_index[check_id] = policy

    result: list[dict[str, Any]] = []
    for diag in diagnostics:
        code = str(diag.get("code") or "").strip()
        policy = policy_index.get(code)

        if policy is None:
            result.append(diag)
            continue

        if not _policy_applies(policy, workspace):
            result.append(diag)
            continue

        enabled = bool(policy.get("enabled", True))
        if not enabled:
            continue  # suppressed by policy

        severity_override = policy.get("severityOverride")
        if severity_override is not None:
            diag = dict(diag, severity=str(severity_override))

        result.append(diag)

    return result
