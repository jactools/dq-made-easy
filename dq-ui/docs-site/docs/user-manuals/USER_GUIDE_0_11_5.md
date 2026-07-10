# User Guide — v0.11.5

This guide covers what changed for operators and developers in the v0.11.5 release.

## What changed in 0.11.5

The v0.11.5 release completes the SEC-5 end-to-end TLS enforcement initiative. The stack now routes all local browser traffic to its origin service over a single encrypted path, with no intermediate proxy terminating and re-wrapping TLS.

For end users, the ITSM support portal (Zammad) continues to work at the same browser URL. The difference is invisible at the browser level but removes a security boundary from the internal architecture.

For operators, this release provides:
- Automated validation that prevents new HTTP regressions
- A cutover runbook for migrating remaining services
- A troubleshooting guide for diagnosing TLS failures
- An updated exception registry with retirement dates for each documented deviation

## For operators: what you need to know

### Certificate generation

If you regenerate certificates after this release, the Zammad backend certificates will automatically include the user-facing support hostname (`EDGE_LOCAL_SUPPORT_HOST`) as a Subject Alternative Name. No manual steps required.

```bash
# Regenerate all service certificates
./scripts/create_certs.sh
```

### Validating the TLS posture

Two validation scripts confirm the transport posture is intact:

```bash
# Verify backend direct routing and no intermediate proxy
bash scripts/validate_tls_backend_direct_routing.sh

# Verify all major service and browser paths over TLS
bash scripts/validate_tls_service_paths.sh
```

Run these after any change to compose services, edge configuration, or certificate generation.

### Known exceptions

Two transport deviations are actively tracked with retirement dates:

| Exception | Service | Target closure |
|-----------|---------|----------------|
| ARCH-EXC-0010 | Airflow (HTTP, port 8080) | 2026-12-31 |
| ARCH-EXC-0011 | `zammad-https` TLS-terminating proxy (retained for PUBLIC mode) | 2026-09-30 |

See `architecture/ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md` for the full registry.

### Troubleshooting TLS failures

If a service reports certificate verification failures or connection timeouts after startup, see the [TLS Observability Guide](https://github.com/jactools/dq-rulebuilder/blob/main/implementation-details/SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md) for diagnosis steps, or the [Cutover Runbook](/docs/implementation-details/SEC_5_W7_CUTOVER_RUNBOOK/) for rollback procedures.

Common causes:
- Certificates not yet generated: run `scripts/create_certs.sh`
- CA bundle mount missing: check the service's `volumes:` block in `docker-compose.yml`
- SAN mismatch: verify the edge SNI name matches a SAN in the backend cert

## Related guides

- [TLS Edge Architecture Reference](/docs/implementation-details/TLS_EDGE_ARCHITECTURE_REFERENCE/)
- [TLS Validation Infrastructure](/docs/implementation-details/TLS_VALIDATION_INFRASTRUCTURE/)
- [SEC-5 Cutover Runbook](/docs/implementation-details/SEC_5_W7_CUTOVER_RUNBOOK/)
- [SEC-5 TLS Observability Guide](https://github.com/jactools/dq-rulebuilder/blob/main/implementation-details/SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md)
