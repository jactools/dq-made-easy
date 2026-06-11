# ARCH-EXC-0005: C=3 Observability RBAC Is Documented but Not Yet Enforced

**Status**: Approved
**Category**: compliance
**Owner**: ops-team-observability
**First recorded**: 2026-04-22
**Last reviewed**: 2026-04-22
**Next review date**: 2026-05-31
**Target closure date**: 2026-08-31
**Risk level**: high
**Impact level**: medium
**Governing baseline**: [ADR-029 EU Financial C=3 Security Baseline Mandate](../adr/ADR-029-eu-financial-c3-security-baseline-mandate.md), [DQ-SEC-EU-C3-001](../../docs/technical/EU_FINANCIAL_C3_SECURITY_REQUIREMENTS.md), [DQ-SEC-LOGMON-001](../../docs/technical/LOGGING_AND_MONITORING_POLICY_ISO27001.md)

## Affected Surface

Grafana and related observability access-control enforcement for privileged and read-only roles in repository-managed observability deployments.

## Summary

The repository documents a least-privilege RBAC model for observability access, but the deployment evidence still says RBAC enforcement is pending OIDC integration rather than operationally enforced.

## Rationale

The policy and guidance work was completed ahead of full observability identity integration, leaving a gap between documented role design and enforceable runtime access control.

## Risk Details

In a `C=3` context, documentation-only RBAC is insufficient for privileged observability surfaces because logs, dashboards, and alerting systems can expose sensitive operational data and administrative functions.

## Impact Details

This affects the observability admin path, viewer/editor/admin segregation, and the ability to evidence centrally managed privileged control for monitoring tooling in a `C=3` release.

## Compensating Controls

Role design, access-control policy, CODEOWNERS, and quarterly access-review expectations are documented, and the gap is visible in the implementation checklist instead of being treated as complete.

## Validation and Evidence

- [LOGGING_AND_MONITORING_POLICY_IMPLEMENTATION_CHECKLIST.md](../../docs/technical/LOGGING_AND_MONITORING_POLICY_IMPLEMENTATION_CHECKLIST.md) states `RBAC DEPLOYMENT PENDING`.
- The same checklist states that `RBAC enforcement documented but requires OIDC integration for deployment` and notes `RBAC enforcement (Viewer/Editor/Admin roles) documented but requires OIDC deployment`.
- [GRAFANA_RBAC_DEPLOYMENT_GUIDE.md](../../docs/technical/GRAFANA_RBAC_DEPLOYMENT_GUIDE.md) exists as deployment guidance, which indicates the operational enforcement step is still separate from the documented policy.

## Exit Criteria

Observability RBAC is enforced in the supported deployment path, privileged and non-privileged roles are centrally managed, and runtime evidence exists that the documented access model is operational rather than aspirational.