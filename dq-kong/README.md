# Kong Bootstrap (dq-made-easy)

**Kong image and container lifecycle are managed by `platform-foundation` (`platform-kong`).**

This directory contains only the Kong bootstrap script that deploys
routes, services, consumers, and ACLs to Kong. It is **not** responsible
for building or running the Kong container.

## Directory Structure

```
dq-kong/
├── bootstrap_kong.sh   # Deploys routes, services, consumers, ACLs to Kong
└── README.md           # This file
```

## Bootstrap Script

`scripts/bootstrap_kong.sh` configures Kong by:

1. Creating Kong services (e.g., `dq-api` → `https://api:4010`)
2. Creating routes for each API path (`/auth/v1`, `/admin/v1`, etc.)
3. Enabling CORS and rate-limiting plugins
4. When `TRUST_PROXY_AUTH=true`:
   - Enabling JWT validation on protected routes
   - Syncing Keycloak users → Kong consumers with JWT credentials
   - Setting up ACL groups from Keycloak roles
5. Enabling OpenTelemetry tracing plugin

### Required Environment Variables

| Variable | Description |
|---|---|
| `DQ_API_INTERNAL_URL` | Internal URL of the DQ API service |
| `KEYCLOAK_INTERNAL_URL` | Internal URL of the Keycloak service |
| `KEYCLOAK_ADMIN_REALM` | Keycloak admin realm |
| `KEYCLOAK_SYSTEM_ADMIN_USERNAME` | Keycloak system admin username |
| `KEYCLOAK_SYSTEM_ADMIN_PASSWORD` | Keycloak system admin password |
| `KEYCLOAK_REALM` | Application realm name |
| `DQ_ENGINE_OIDC_CLIENT_ID` | OIDC client ID for the DQ engine |
| `UI_VITE_LOCAL_URL` | Internal URL of the Vite dev server |
| `UI_NGINX_LOCAL_URL` | Internal URL of the Nginx UI |
| `KONG_OTEL_ENDPOINT` | OTLP endpoint for tracing |
| `TRUST_PROXY_AUTH` | When `true`, enables JWT + ACL on routes |

See `docs/technical/PLATFORM_SERVICE_IMAGE_CONTRACT.md` for the full
environment variable reference.

## Platform-Kong (platform-foundation)

The `platform-kong` image in `platform-foundation` provides:

- Kong runtime baseline (`kong:3.9.1`)
- Shared utilities (curl, jq, python3)
- CA trust installation
- Generic start script with bootstrap mount point
- Health check, exposed ports, entrypoint

See `platform-foundation/docker/kong/` for the Dockerfile and start script.
