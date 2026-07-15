# Internal Service Contracts

Use this file for repo-wide env, URL, and trust-bundle conventions that the assistant should preserve when editing code, compose files, or bootstrap scripts.

This guidance is enforced by [env-only-connection.instructions.md](../instructions/env-only-connection.instructions.md).

## Env Re-source and Derived Values

- When `docker compose` is invoked with `--env-file`, interpolation can lock to the file contents. If a script re-sources `ROOT_ENV_FILE`, make sure derived runtime values are injected into the effective env file before running Compose.
- Preserve derived `PIP_INDEX_URL` and `MAVEN_REPOSITORIES` across any re-source of `ROOT_ENV_FILE`.
- `scripts/supporting/setup_env.sh` derives the Maven repository list from `NEXUSCLOUD_MAVEN_GROUP_REPO`, with `NEXUSCLOUD_MPM_GROUP_REPO` as the fallback.

## Env-Only Service Connectivity

- Service connection values must come from the selected `.env.*.local` file or from values that file explicitly exports.
- Do not add hardcoded host, port, URL, realm, username, password, or path fallbacks for service connectivity.
- Do not invent alternate connection paths when a value is missing by guessing defaults such as `db`, `postgres`, `keycloak`, `http://`, `localhost`, or `127.0.0.1`.
- If a required env var is missing, fail immediately with a clear error instead of substituting a fallback.
- If a script needs a derived value, derive it only from env vars that were already provided by the selected env file.
- Do not add a second, script-local connection mechanism alongside the env-file contract.

## Internal API Routing

- `DQ_API_INTERNAL_URL` is reserved for Kong's upstream-to-API wiring and bootstrap path into `dq-api`.
- Non-Kong containers must call repository APIs through `KONG_INTERNAL_URL` or the matching audience-scoped Kong URL, not directly through `DQ_API_INTERNAL_URL` or `dq-api`.

## Internal TLS Material

- The canonical shared trust bundle lives at `tmp/certs/trust/internal-ca-bundle.pem`.
- Per-service leaf certificates live under `tmp/certs/services/<service-name>/tls.crt` and `tmp/certs/services/<service-name>/tls.key`.
- Container mounts and client trust settings should use the canonical trust bundle path and fail fast if required certificates or trust material are missing.