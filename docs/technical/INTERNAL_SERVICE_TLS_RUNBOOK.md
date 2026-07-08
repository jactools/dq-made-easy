# Internal Service TLS Runbook

This runbook covers the repository-managed internal TLS paths that SEC-1 moved to verified transport.

For the broader SEC-5 no-HTTP policy and the current exception boundary, see [SEC-5 No-HTTP Contract and Exception Boundary](../implementation-details/SEC_5_NO_HTTP_CONTRACT_AND_EXCEPTION_BOUNDARY.md).

## What To Run

Generate or refresh certificates and trust artifacts with:

```bash
./scripts/create_certs.sh
```

Validate the active compose/env surfaces with:

```bash
./scripts/validation/validate_internal_tls_migration.sh
```

Validate the certificate inventory with:

```bash
./scripts/validation/validate_tls_certificate_inventory.sh
```

Validate the trust-bundle conventions with:

```bash
./scripts/validation/validate_tls_trust_bundle_conventions.sh
```

Run the representative smoke checks with:

```bash
./scripts/validation/validate_internal_tls_smoke.sh --all
```

## What The Validator Checks

- No active compose or env template keeps `sslmode=disable` for the migrated Postgres paths.
- The DB, Kong DB, and OpenMetadata DB/exporter paths all mount the repository CA bundle.
- Kong Postgres connections require TLS verification.
- The Kong DB certificate is present in the certificate-generation script.
- The full TLS listener inventory has matching leaf cert and key files under `tmp/certs/services/`.
- Browser-facing leaf certs under `tmp/certs/*.pem` contain the expected SAN hostname for the public or local listener.

## Certificate Layout

- Service leaf certificates live under `tmp/certs/services/<service-name>/tls.crt` and `tls.key`.
- Browser-facing host certificates live under `tmp/certs/*.pem` and their matching `-key.pem` files.
- `tmp/certs/mkcert-rootCA.pem` is the host-trusted root CA bundle.
- `tmp/certs/internal-ca-bundle.pem` and `tmp/certs/trust/internal-ca-bundle.pem` are the shared internal trust bundles mounted into callers.
- The standard client-side env hooks for internal TLS callers are `REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE`; OpenMetadata also uses `OPENMETADATA_CA_BUNDLE` as its service-specific alias.

## Common Failures

If Postgres clients fail with certificate errors, check these first:

- The service certificate directory exists under `tmp/certs/services/<service>/`.
- The trust bundle exists at `tmp/certs/trust/internal-ca-bundle.pem`.
- The container mounts the trust bundle at the path expected by the client.
- The hostname in the connection string matches the service name in the certificate SAN.

If Kong fails to start against Postgres, confirm:

- `KONG_PG_SSL=on`
- `KONG_PG_SSL_REQUIRED=on`
- `KONG_PG_SSL_VERIFY=on`
- `KONG_LUA_SSL_TRUSTED_CERTIFICATE` points at the mounted internal CA bundle.

If OpenMetadata cannot connect to its database, confirm:

- `DB_PARAMS` uses `sslmode=verify-full`.
- `sslrootcert` points at `/etc/openmetadata/certs/internal-ca-bundle.pem`.
- The openmetadata-db container is serving TLS on the Postgres port.

## Observability Notes

- TLS handshake failures usually appear first in the affected container logs, not in Grafana.
- For compose-based debugging, start with `docker compose logs db kong-db openmetadata-db kong openmetadata-server`.
- When the stack is healthy but traffic still fails, use the smoke checks above to confirm whether the breakage is in transport, trust, or application wiring.
- For telemetry-related issues, compare the dq-api and OpenMetadata smoke results with the collector logs to separate export failures from service failures.

## Certificate Rotation

Rotation is repo-managed rather than manual:

1. Regenerate certificates with `./scripts/create_certs.sh`.
2. Restart the affected containers so they pick up the new leaf certificates and trust bundle.
3. Re-run the validator and the smoke checks.
4. Investigate hostname/SAN mismatches if verification fails after rotation.

If a listener starts without a certificate, run `./scripts/validation/validate_tls_certificate_inventory.sh` first to pinpoint the missing artifact.
