# Release Readiness Checklist

Use this checklist before every production release.

## Governance

- [ ] Logging and Monitoring Policy compliance reviewed (DQ-SEC-LOGMON-001).
- [ ] EU Financial C=3 Security Requirements compliance reviewed (DQ-SEC-EU-C3-001) when the release is intended for a C=3 financial-sector context.
- [ ] CRR and EMIR Reporting Evidence Requirements reviewed (DQ-REG-CRR-EMIR-001) when the release is intended to support CRR- or EMIR-relevant reporting use cases.
- [ ] Governance gates workflow succeeded for the release commit/PR.
- [ ] Security-impacting exceptions documented with owner and expiry.

## Functional and Operational

- [ ] Regression tests passed.
- [ ] Observability baseline checks passed.
- [ ] Correlation propagation checks passed.
- [ ] Rollback plan reviewed and verified.

## Release Metadata

- [ ] User-facing release notes updated.
- [ ] Version updated according to release policy.
- [ ] Deployment/runbook references validated.