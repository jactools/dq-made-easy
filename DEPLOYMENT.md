# Deployment Guide

This guide explains how to pull and run the Data Quality Made Easy services on a different machine using pre-built Docker images from Docker Hub.

## Prerequisites

- Docker Engine (20.10+)
- Docker Compose (2.x)
- Network access to Docker Hub

## Quick Start

### 1. Clone the Repository (or copy these files)

You only need these files to run the stack:
```bash
git clone <repository-url>
cd dq-rulebuilder
```

Or manually copy:
- `docker-compose.yml`
- `.env.prod.example` as the tracked production template
- `.env.prod.local` as the repo-managed machine-local production file
- `.env.dev.example` and `.env.test.example` for local workstation dev/test flows
- `dq-db/init/` directory (for database initialization)
- `dq-keycloak/` directory (for Keycloak configuration)

## Environment Templates

- `.env.dev.example` is the tracked development template for local `*.jac.dot` workstation flows.
- `.env.test.example` is the tracked isolated local test template for smoke/regression flows.
- `.env.prod.example` is the tracked Debian/public deployment template.
- `.env.dev.local`, `.env.test.local`, and `.env.prod.local` are ignored machine-local runtime copies.

Important: `.env.prod.example` assumes the edge ingress and path-prefix routing model from the ingress implementation docs. In particular, it assumes public routes such as `/iam`, `/metadata`, and `/observability` exist.

### 2. Prepare the Environment File

For the public single-host deployment model:

```bash
cp .env.prod.example .env.prod.local
```

For Debian operators, prefer an external env file instead of keeping prod secrets in the repo root:

```bash
sudo install -d -m 0750 /etc/dq-made-easy
sudo install -m 0600 .env.prod.example /etc/dq-made-easy/prod.env
sudo chown root:root /etc/dq-made-easy/prod.env
```

If Docker Compose runs under a dedicated service account or group, use `root:<service-group>` with `0640` instead of making the file world-readable.

If you are running `docker compose` directly instead of the startup wrappers, pass the same file explicitly:

```bash
docker compose --env-file .env.prod.local pull
docker compose --env-file .env.prod.local up -d
# or
docker compose --env-file /etc/dq-made-easy/prod.env pull
docker compose --env-file /etc/dq-made-easy/prod.env up -d
```

### 3. Pull All Images

Pull all pre-built images from Docker Hub:

```bash
# Pull with latest tags (default)
docker compose --env-file .env.prod.local pull

# Or pin the current v0.10.2 release-line images (see Version Management below)
export DQ_API_TAG=0.10-<api-hash>
export DQ_ENGINE_TAG=0.10-<engine-hash>
export DQ_PROFILING_TAG=0.10-<profiling-hash>
export DQ_FRONTEND_TAG=0.10-<frontend-hash>
export DQ_KONG_TAG=0.10-<kong-hash>
export DQ_BASE_TAG=0.10-<base-hash>
docker compose --env-file .env.prod.local pull
```

### 4. Start Services

```bash
# Start all services
docker compose --env-file .env.prod.local up -d

# Check service status
docker compose --env-file .env.prod.local ps

# View logs
docker compose --env-file .env.prod.local logs -f
```

## Version Management

### Using Latest Tags

By default, the repo-managed public deployment flow uses `.env.prod.local`:

```bash
# No configuration needed - uses latest
docker compose --env-file .env.prod.local pull
docker compose --env-file .env.prod.local up -d
```

### Using Specific Versions

To deploy a specific version, update `.env.prod.local` or set environment variables:

**Option 1: Edit .env.prod.local**
```bash
# Current v0.10.2 release-line examples
DQ_API_TAG=0.10-<api-hash>
DQ_ENGINE_TAG=0.10-<engine-hash>
DQ_PROFILING_TAG=0.10-<profiling-hash>
DQ_FRONTEND_TAG=0.10-<frontend-hash>
DQ_KONG_TAG=0.10-<kong-hash>
DQ_BASE_TAG=0.10-<base-hash>
```

**Option 2: Environment Variables**
```bash
# Set versions before running docker compose
export DQ_API_TAG=0.10-<api-hash>
export DQ_ENGINE_TAG=0.10-<engine-hash>
export DQ_PROFILING_TAG=0.10-<profiling-hash>
export DQ_FRONTEND_TAG=0.10-<frontend-hash>
export DQ_KONG_TAG=0.10-<kong-hash>
export DQ_BASE_TAG=0.10-<base-hash>

docker compose --env-file .env.prod.local pull
docker compose --env-file .env.prod.local up -d
```

### Finding Available Versions

Check Docker Hub for available tags:
- https://hub.docker.com/r/jacbeekers/dq-api/tags
- https://hub.docker.com/r/jacbeekers/dq-engine/tags
- https://hub.docker.com/r/jacbeekers/dq-profiling/tags
- https://hub.docker.com/r/jacbeekers/dq-frontend/tags
- https://hub.docker.com/r/jacbeekers/dq-kong/tags

Or use Docker CLI:
```bash
# List tags for a service
docker search jacbeekers/dq-api --limit 100
```

## Service URLs

With `.env.prod.local` or `/etc/dq-made-easy/prod.env`, browser-facing services are intended to be available at:

- **Frontend UI**: https://www.jacloud.nl
- **API (via edge -> Kong)**: https://www.jacloud.nl
- **Keycloak**: https://www.jacloud.nl/iam
- **OpenMetadata**: https://www.jacloud.nl/metadata
- **Grafana**: https://www.jacloud.nl/observability

Internal-only services such as PostgreSQL, Redis, dq-engine, Kong Admin, and direct API ports should not be treated as public browser entrypoints.

## Frontend API URL Runtime Override

The frontend image supports runtime API target injection via `/runtime-config.js`.

Use `.env.prod.local`:

```bash
KONG_PUBLIC_URL=https://www.jacloud.nl
```

Apply by recreating only frontend:

```bash
docker compose --env-file .env.prod.local up -d frontend
```

Compatibility fallback:
- `KONG_PUBLIC_URL` is the canonical runtime variable.
- `VITE_API_URL` is still supported for local dev/build-time use, but not as the deployment contract.

## SSO Configuration (env defaults)

Use `.env.prod.local` to define SSO defaults for API and frontend:

```bash
SSO_PROVIDER=keycloak
SSO_PUBLIC_ISSUER_URL=https://www.jacloud.nl/iam/realms/jaccloud
SSO_INTERNAL_ISSUER_URL=http://keycloak:8080/iam/realms/jaccloud
SSO_CLIENT_ID=dq-rules-ui
SSO_ENABLED=true
ALLOW_LOCAL_AUTH=false
TRUST_PROXY_AUTH=true

VITE_SSO_PROVIDER=keycloak
VITE_SSO_ISSUER_URL=https://www.jacloud.nl/iam/realms/jaccloud
VITE_SSO_CLIENT_ID=dq-rules-ui
```

Precedence rules:
- API/runtime reads `SSO_*` and `ALLOW_LOCAL_AUTH` as defaults.
- Frontend initial values come from `VITE_SSO_*`.
- If rows exist in `app_config`, those values override env defaults at runtime.

Browser-auth notes:
- `TRUST_PROXY_AUTH=true` must be present for both the API and the Kong bootstrap path.
- `SSO_PUBLIC_ISSUER_URL` must match the canonical public Keycloak issuer exactly.

Zammad support notes:
- Zammad derives its browser-facing callback host from its stored `http_type` and `fqdn` settings, so the live app config must match the public support URL.
- Zammad discovers Keycloak through the internal Docker-network issuer for token/userinfo validation, while the browser still uses the public authorization endpoint.
- The `zammad-https` container must receive both `ZAMMAD_SSL_CERT_FILE_NAME` and `ZAMMAD_SSL_KEY_FILE_NAME`; those filenames must match the certificate pair mounted in `tmp/certs/`.

## Minimal Deployment (Without Source Code)

If you don't want to clone the full repository, create these files:

### Minimal File Structure
```
deploy/
├── docker-compose.yml
├── prod.env
├── dq-db/
│   └── init/
│       └── (SQL initialization scripts)
└── dq-keycloak/
    └── (Keycloak realm configuration)
```

### Simple Pull Script

Create `pull-images.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# Configuration
REGISTRY="docker.io"
NAMESPACE="jacbeekers"
VERSION="${1:-latest}"  # Default to latest, or use first argument

# Images to pull
IMAGES=(
    "npm-base"
    "dq-api"
    "dq-engine"
    "dq-profiling"
    "dq-frontend"
    "dq-kong"
)

echo "Pulling Data Quality Made Easy images (version: $VERSION)"
echo "========================================"

for image in "${IMAGES[@]}"; do
    full_image="$REGISTRY/$NAMESPACE/$image:$VERSION"
    echo "Pulling: $full_image"
    if docker pull "$full_image"; then
        echo "✓ Successfully pulled $image"
    else
        echo "✗ Failed to pull $image"
        exit 1
    fi
    echo ""
done

echo "========================================"
echo "All images pulled successfully!"
echo ""
echo "To start services:"
echo "  docker compose --env-file prod.env up -d"
```

Usage:
```bash
# Pull latest
chmod +x pull-images.sh
./pull-images.sh

# Pull a shared manual override tag, if all images were published with one
./pull-images.sh v0.10.1
```

Note: the standard repo release flow produces per-service deterministic tags such as `0.10-b85dd7d` and `0.10-5fc0c14`, not a single identical tag for every image. Use `.env.prod.local` or your external prod env file to pin the current tested release-line image set.

## Rolling Back to a Previous Version

To rollback to a previous version:

```bash
# Set to previous version tags
export DQ_API_TAG=0.10-previousapihash
export DQ_ENGINE_TAG=0.10-previousenginehash
# ... etc

# Pull the old versions
docker compose --env-file .env.prod.local pull

# Restart with old versions
docker compose --env-file .env.prod.local up -d
```

## Updating to Latest

```bash
# Pull latest images
docker compose --env-file .env.prod.local pull

# Recreate containers with new images
docker compose --env-file .env.prod.local up -d

# Remove old images (optional)
docker image prune -f
```

## Troubleshooting

### Services Won't Start
```bash
# Check logs
docker compose --env-file .env.prod.local logs

# Check individual service
docker compose --env-file .env.prod.local logs api

# Restart a specific service
docker compose --env-file .env.prod.local restart api
```

### Image Pull Failures
```bash
# Verify you're logged in to Docker Hub (if using private registry)
docker login docker.io

# Check network connectivity
ping docker.io

# Try pulling manually
docker pull docker.io/jacbeekers/dq-api:latest
```

### Version Conflicts
```bash
# Check running image versions
docker compose --env-file .env.prod.local ps --format json | jq -r '.[] | "\(.Service): \(.Image)"'

# Check what tags are actually running
docker ps --format "table {{.Names}}\t{{.Image}}"
```

## Advanced: Air-Gapped Deployment

For environments without internet access:

### 1. Save Images on Connected Machine
```bash
# Save all images to tar files
docker save -o dq-images.tar \
    docker.io/jacbeekers/npm-base:0.10-993739e \
    docker.io/jacbeekers/dq-api:0.10-b85dd7d \
    docker.io/jacbeekers/dq-engine:0.10-9dd74e7 \
    docker.io/jacbeekers/dq-profiling:0.10-9695709 \
    docker.io/jacbeekers/dq-frontend:0.10-5fc0c14 \
    docker.io/jacbeekers/dq-kong:0.10-e2c6d73

# Compress for transfer
gzip dq-images.tar
```

### 2. Transfer to Air-Gapped Machine
```bash
# Copy dq-images.tar.gz to target machine
scp dq-images.tar.gz user@target-machine:/path/to/deploy/
```

### 3. Load Images on Air-Gapped Machine
```bash
# Decompress
gunzip dq-images.tar.gz

# Load images
docker load -i dq-images.tar

# Verify
docker images | grep jacbeekers
```

### 4. Start Services
```bash
# Configure version tags in .env.prod.local or prod.env to match loaded images
docker compose --env-file .env.prod.local up -d
```

## Health Checks

All services include health checks. Wait for all services to be healthy:

```bash
# Watch service health
watch -n 2 'docker compose --env-file .env.prod.local ps'

# Or check programmatically
docker compose --env-file .env.prod.local ps --format json | jq -r '.[] | "\(.Service): \(.Health)"'

# Wait for all healthy (bash script)
until [ "$(docker compose --env-file .env.prod.local ps --format json | jq -r '.[] | select(.Health != "healthy") | .Service' | wc -l)" -eq 0 ]; do
    echo "Waiting for services to be healthy..."
    sleep 5
done
echo "All services healthy!"
```

## Production Recommendations

1. **Pin Specific Versions**: Always use explicit generated tags (for example `0.10-b85dd7d`) instead of `latest` in production
2. **Environment Variables**: Store sensitive values in `.env` and keep it out of version control
3. **Volumes**: Back up database volumes regularly
4. **Resource Limits**: Add memory and CPU limits to docker-compose.yml
5. **Monitoring**: Set up container monitoring (Prometheus, Grafana, etc.)
6. **Logging**: Configure centralized logging for all services

## Example Production .env

```bash
# Production Configuration
DQ_BASE_TAG=0.10-993739e
DQ_API_TAG=0.10-b85dd7d
DQ_ENGINE_TAG=0.10-9dd74e7
DQ_PROFILING_TAG=0.10-9695709
DQ_FRONTEND_TAG=0.10-5fc0c14
DQ_KONG_TAG=0.10-e2c6d73

# Database
DATABASE_URL=postgresql://produser:securepassword@db:5432/dq

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Security - change these!
POSTGRES_PASSWORD=<strong-password>
KEYCLOAK_ADMIN_PASSWORD=<strong-password>
KONG_PG_PASSWORD=<strong-password>
```
