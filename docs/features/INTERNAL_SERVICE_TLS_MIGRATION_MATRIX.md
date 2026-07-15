# Internal Service TLS Migration Matrix

Status: Done

This matrix summarizes the secure internal transport surfaces covered by SEC-1.

| Surface | Status | Validation entrypoint | Notes |
|---|---|---|---|
| API service HTTPS | Complete | `scripts/validation/validate_internal_tls_smoke.sh --http` | Kong routes to the API over HTTPS with repo CA trust. |
| Postgres family | Complete | `scripts/validation/validate_internal_tls_migration.sh` | DB, Kong DB, and OpenMetadata DB/exporter paths use verified TLS. |
| Redis family | Complete | `scripts/validation/validate_internal_tls_migration.sh` | Redis is TLS-only and clients use `rediss://`. |
| AIStor / S3-compatible clients | Complete | Existing engine smoke checks | HTTPS S3 endpoints require the repository CA bundle. |
| Telemetry export | Complete | `scripts/validation/validate_internal_tls_smoke.sh --telemetry --metadata-telemetry` | OTLP HTTP uses the HTTPS collector endpoint with repo trust. |
| Contract cache / data path | Complete | `scripts/validation/validate_internal_tls_smoke.sh --data-cache` | OpenMetadata cache hit/miss behavior is exercised through Grafana. |
| Validation coverage | In place | `scripts/validation/validate_internal_tls_migration.sh` | Flags plaintext Postgres leftovers and missing trust wiring. |
| Smoke coverage | In place | `scripts/validation/validate_internal_tls_smoke.sh --all` | Runs representative HTTP, data/cache, and telemetry checks. |

## Reading The Matrix

- Complete means the active repo defaults now use TLS with verification enabled.
- In place means the repo has the validation or smoke entrypoint needed to keep the surface honest.
- Pending items should only appear here if a new internal transport surface is introduced later.
