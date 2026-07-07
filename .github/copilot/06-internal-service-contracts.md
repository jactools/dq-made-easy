# Internal Service Contracts

Use this file for repo-wide env, URL, and trust-bundle conventions that the assistant should preserve when editing code, compose files, or bootstrap scripts.

## Env Re-source and Derived Values

- When `docker compose` is invoked with `--env-file`, interpolation can lock to the file contents. If a script re-sources `ROOT_ENV_FILE`, make sure derived runtime values are injected into the effective env file before running Compose.
- Preserve derived `PIP_INDEX_URL` and `MAVEN_REPOSITORIES` across any re-source of `ROOT_ENV_FILE`.
- `scripts/supporting/setup_env.sh` derives the Maven repository list from `NEXUSCLOUD_MAVEN_GROUP_REPO`, with `NEXUSCLOUD_MPM_GROUP_REPO` as the fallback.

## Internal API Routing

- `DQ_API_INTERNAL_URL` is reserved for Kong's upstream-to-API wiring and bootstrap path into `dq-api`.
- Non-Kong containers must call repository APIs through `KONG_INTERNAL_URL` or the matching audience-scoped Kong URL, not directly through `DQ_API_INTERNAL_URL` or `dq-api`.

## Internal TLS Material

- The canonical shared trust bundle lives at `tmp/certs/trust/internal-ca-bundle.pem`.
- Per-service leaf certificates live under `tmp/certs/services/<service-name>/tls.crt` and `tmp/certs/services/<service-name>/tls.key`.
- Container mounts and client trust settings should use the canonical trust bundle path and fail fast if required certificates or trust material are missing.