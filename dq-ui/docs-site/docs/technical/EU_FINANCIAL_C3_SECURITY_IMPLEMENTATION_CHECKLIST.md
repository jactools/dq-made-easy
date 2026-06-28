# EU Financial C=3 Security Implementation Checklist

Purpose: translate the `C=3` EU financial-sector security baseline into concrete dq-made-easy implementation tasks, ownership checkpoints, evidence outputs, and deviation controls.

Related requirement: [EU_FINANCIAL_C3_SECURITY_REQUIREMENTS.md](/docs/technical/EU_FINANCIAL_C3_SECURITY_REQUIREMENTS/)
Related ADR: [ADR-029](/docs/architecture/adr/ADR-029-eu-financial-c3-security-baseline-mandate/)

## 1. Governance and Risk Control

- [x] Establish the governing requirement and ADR for `C=3` handling.
  - [EU_FINANCIAL_C3_SECURITY_REQUIREMENTS.md](/docs/technical/EU_FINANCIAL_C3_SECURITY_REQUIREMENTS/)
  - [ADR-029](/docs/architecture/adr/ADR-029-eu-financial-c3-security-baseline-mandate/)
- [x] Require architecture deviations for security-significant exceptions.
  - [ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md](/docs/architecture/ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS/)
- [ ] Add a recurring governance review that explicitly includes `DQ-SEC-EU-C3-001` status and open deviations.
- [ ] Define named owners for C=3 baseline evidence, exception approval, and release sign-off.

Evidence:
- [x] Release checklist includes the requirement ID: [RELEASE_READINESS_CHECKLIST.md](/docs/releases/RELEASE_READINESS_CHECKLIST/)

## 2. Identity, Access, and Privileged Control

- [ ] Remove permissive local-auth defaults from `C=3` deployment paths.
- [ ] Eliminate default or placeholder privileged credentials from `C=3` deployment defaults.
- [ ] Enforce centrally managed identity for privileged admin surfaces.
- [ ] Complete deployable RBAC for observability/admin tooling instead of documentation-only role design.
- [ ] Define and document break-glass or emergency access handling if retained.

Evidence / current gaps:
- [ ] [ARCH-EXC-0004](/docs/architecture/deviations/ARCH-EXC-0004-c3-deployments-still-allow-permissive-local-auth-and-default-credentials/)
- [ ] [ARCH-EXC-0005](/docs/architecture/deviations/ARCH-EXC-0005-c3-observability-rbac-is-documented-but-not-yet-enforced/)

## 3. Secure Transport and Cryptography

- [ ] Complete SEC-1 internal TLS execution for `C=3`-relevant internal paths.
- [ ] Remove plaintext transport defaults from `C=3` deployment paths.
- [ ] Record all remaining transport exceptions in the architecture deviation register.
- [ ] Complete SEC-2 inventory and target-state definition for post-quantum readiness.
- [ ] Ensure key, certificate, and trust ownership is documented for all `C=3`-critical surfaces.

Evidence / current gaps:
- [ ] [ARCH-EXC-0001](/docs/architecture/deviations/ARCH-EXC-0001-internal-service-transport-still-defaults-to-plaintext-links/)
- [ ] [ARCH-EXC-0002](/docs/architecture/deviations/ARCH-EXC-0002-adr-028-post-quantum-baseline-is-not-yet-implemented/)
- [ ] [ARCH-EXC-0003](/docs/architecture/deviations/ARCH-EXC-0003-vendor-managed-oidc-and-jwks-surfaces-lack-repository-validated-pq-hybrid-path/)

## 4. Logging, Monitoring, and Audit Evidence

- [x] Apply the ISO 27001-aligned logging and monitoring baseline.
  - [LOGGING_AND_MONITORING_POLICY_ISO27001.md](/docs/technical/LOGGING_AND_MONITORING_POLICY_ISO27001/)
  - [LOGGING_AND_MONITORING_POLICY_IMPLEMENTATION_CHECKLIST.md](/docs/technical/LOGGING_AND_MONITORING_POLICY_IMPLEMENTATION_CHECKLIST/)
- [ ] Ensure privileged observability access is enforced, not just documented.
- [ ] Confirm security-relevant `C=3` events have evidence and retention coverage.
- [ ] Add explicit `C=3` evidence review to quarterly governance cadence.

## 5. Vulnerability, Patch, and Dependency Management

- [ ] Define repository workflow for triaging critical and high vulnerabilities affecting `C=3` surfaces.
- [ ] Define due-date rules for remediation or approved deviation handling.
- [ ] Identify security-critical runtime and container dependencies that require regular review.
- [ ] Add release evidence that open critical/high issues have been reviewed.

## 6. Secure Change and Delivery Controls

- [x] Include `DQ-SEC-EU-C3-001` in release readiness.
  - [RELEASE_READINESS_CHECKLIST.md](/docs/releases/RELEASE_READINESS_CHECKLIST/)
- [ ] Define which change types require explicit security-aware review for `C=3` releases.
- [ ] Ensure secrets, infrastructure, and security-config changes have auditable review paths.
- [ ] Reject releases with open unapproved `C=3` deviations.

## 7. Resilience, Recovery, and Operational Continuity

- [ ] Document backup and restore expectations for `C=3`-critical data and security configuration.
- [ ] Define minimum recovery evidence required for a `C=3` release.
- [ ] Record single points of failure that materially affect a `C=3` deployment.
- [ ] Tie resilience gaps to implementation plans or architecture deviations.

## 8. Third-Party and Supply-Chain Risk

- [ ] Maintain named ownership for critical third-party security and identity dependencies.
- [ ] Track vendor-managed capability gaps as architecture deviations.
- [ ] Verify repository defaults do not assume unvalidated vendor security capabilities.
- [ ] Review third-party risk for auth, crypto, logging, monitoring, and resilience surfaces before release.

## 9. Completion Criteria

Mark the C=3 baseline operationally ready when:

- [ ] all high-impact open deviations against `DQ-SEC-EU-C3-001` are closed or formally approved for release,
- [ ] privileged access paths are centrally managed and enforce least privilege,
- [ ] internal transport and cryptographic baselines for `C=3` surfaces are implemented or explicitly deviated,
- [ ] evidence exists for logging, monitoring, resilience, vulnerability review, and release governance,
- [ ] quarterly governance review includes the C=3 requirement and deviation state.