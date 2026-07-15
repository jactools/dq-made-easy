# Quick Start - Deploy from Docker Hub

This is a simplified guide for quickly deploying Data Quality Made Easy on a new machine using pre-built images.

## Prerequisites
```bash
# Verify Docker is installed
docker --version
docker compose version
```

## Option 1: Quick Deploy (Recommended)

```bash
# 1. Clone repository (or copy deployment files)
git clone <repo-url>
cd dq-made-easy

# 2. Create your production env file
cp .env.prod.example .env.prod.local
# Edit .env.prod.local if needed (passwords, versions, canonical hostnames, etc.)

# 3. Full init (destroy any prior state, start stack, seed database)
./scripts/stack.sh prod init
```

The orchestrator handles secrets generation, TLS certificates, image builds, container startup, and seeding in the correct order.

## Option 2: Pull then Start

```bash
# Pull latest versions
./scripts/pull_images.sh

# Or pull a shared manual override tag
./scripts/pull_images.sh v0.10.5

# Then start with seeding
./scripts/stack.sh prod start --seed
```

## Environment-Specific Quick Commands

```bash
# Dev environment (full reset)
./scripts/stack.sh dev init

# Test environment (start only)
./scripts/stack.sh test start --seed

# Prod environment (stop only)
./scripts/stack.sh prod stop

# Restart any environment (keeps admin passwords, rotates service/user)
./scripts/stack.sh dev restart --seed

# Destroy everything
./scripts/stack.sh dev destroy
```

## Service Access

After starting:
- **Frontend**: https://www.jacloud.nl
- **API (edge -> Kong)**: https://www.jacloud.nl
- **Keycloak**: https://www.jacloud.nl/iam
- **OpenMetadata**: https://www.jacloud.nl/metadata
- **Grafana**: https://www.jacloud.nl/observability

## Frontend API URL (runtime configurable)

The frontend image now supports runtime API URL overrides without rebuilding.

Set in `.env.prod.local`:

```bash
KONG_PUBLIC_URL=https://www.jacloud.nl
```

Then restart only the frontend service:

```bash
docker compose --env-file .env.prod.local up -d frontend
```

Notes:
- `KONG_PUBLIC_URL` is the required runtime variable.
- For browser SSO, `KONG_PUBLIC_URL` should target Kong directly; Kong stays the JWT validation and OAuth2 enforcement layer.

## SSO Configuration (env defaults)

Set in `.env.prod.local` when you want explicit SSO defaults:

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

Notes:
- API/runtime uses `SSO_*` and `ALLOW_LOCAL_AUTH` as defaults.
- Frontend initial settings use `VITE_SSO_*` before app-config is loaded.
- Values in `app_config` override env defaults at runtime when present.
- `TRUST_PROXY_AUTH=true` is required so Kong forwards authenticated browser traffic and the API treats Kong as the trusted JWT gate.
- `SSO_PUBLIC_ISSUER_URL` must match the public Keycloak issuer used by the browser.

## Common Operations

### Full Stack Lifecycle

```bash
# Full clean reset (destroy → start → seed)
./scripts/stack.sh dev init

# Start only (fresh: all new passwords; warm: admin passwords reused)
./scripts/stack.sh dev start --seed

# Restart (keeps admin passwords, rotates service/user passwords)
./scripts/stack.sh dev restart --seed

# Stop only (keeps everything)
./scripts/stack.sh dev stop

# Seed only (reseed running stack)
./scripts/stack.sh dev seed

# Destroy everything (containers, volumes, secrets, credentials)
./scripts/stack.sh dev destroy
```

### Restart Individual Services

```bash
# All services
docker compose --env-file .env.dev.local restart

# Specific service
docker compose --env-file .env.dev.local restart api
```

### Reseed Database While Running

```bash
# Reseed via orchestrator
./scripts/stack.sh dev seed

# Or run the same one-shot service explicitly via Compose
docker compose --profile auth --profile seed run --rm db-seed

# Healthcheck-safe verification only (does not reseed)
docker exec -i <db-container-name> psql -U postgres -d dq -c "SELECT 1" >/dev/null
```

### Keycloak and Kong Setup in Images

```bash
# Keycloak realm import file baked into image
docker exec -it <keycloak-container-name> ls -l /opt/keycloak/data/import

# Kong bootstrap script baked into image
docker exec -it <kong-container-name> ls -l /opt/dq-kong/scripts
```

### View Logs

```bash
# All logs
docker compose logs -f

# Specific service
docker compose logs -f api

# Last 100 lines
docker compose logs --tail=100
```

### Stop Services

```bash
# Stop (keeps data)
docker compose stop

# Stop and remove containers (keeps data)
docker compose down

# Stop and remove everything including volumes (DELETES DATA!)
docker compose down -v

# Or use the orchestrator:
./scripts/stack.sh dev stop   # stop only
./scripts/stack.sh dev destroy  # full teardown
```

### Check Health

```bash
# Service status
docker compose ps

# Detailed inspection
docker inspect <container-name>
```

## Using Specific Versions

Edit `.env.prod.local`:
```bash
# Pin to the current v0.10.2 release-line examples
DQ_API_TAG=0.10-<api-hash>
DQ_ENGINE_TAG=0.10-<engine-hash>
DQ_PROFILING_TAG=0.10-<profiling-hash>
DQ_FRONTEND_TAG=0.10-<frontend-hash>
DQ_KONG_TAG=0.10-<kong-hash>
```

Then:
```bash
docker compose --env-file .env.prod.local pull
./scripts/stack.sh prod start --seed
```

## Password Management

The stack scripts manage passwords automatically:

- **Admin passwords** (DB superuser, Keycloak admin): persisted in stateful volumes. Reused when volumes exist to prevent DB authentication mismatches.
- **Service passwords** (OIDC client secrets, encryption keys): rotated on every start/restart.
- **User passwords** (Keycloak seeded users): rotated on every seed.

A full password reset requires `destroy` followed by `start` (which removes volumes and regenerates everything).

## Troubleshooting

### Ports Already in Use
```bash
# Check what's using the port
lsof -i :5173    # Or whichever port
netstat -an | grep 5173

# Change ports in docker-compose.yml
# Example: "8080:80" means host:8080 -> container:80
```

### Services Won't Start
```bash
# Check logs
docker compose logs

# Check specific service
docker compose logs api

# Check disk space
df -h
```

### Image Pull Fails
```bash
# Login to Docker Hub (if private)
docker login docker.io

# Check network
ping docker.io

# Try manual pull
docker pull docker.io/jacbeekers/dq-api:0.10-7a9c018
```

### Database Issues

```bash
# Reset database (WARNING: deletes data)
docker compose down -v db
docker compose up -d db

# Check database logs
docker compose logs db

# Full reseed
./scripts/stack.sh dev seed
```

### Admin Password Mismatch

If you get authentication errors against the database or Keycloak after starting, the admin password in your secrets file may not match what's inside the volume. Fix:

```bash
# Option A: Full reset (destroys all data)
./scripts/stack.sh dev init

# Option B: Stop → destroy → start (same effect)
./scripts/stack.sh dev destroy
./scripts/stack.sh dev init
```

## Minimal Files Needed

If deploying without the full repository, you only need:

```
deploy/
├── docker-compose.yml          # Service definitions
├── .env                        # Configuration
├── dq-db/
│   └── init/                   # Database init scripts
└── dq-keycloak/
    └── dqprototype-realm.json  # Keycloak config
```

## Production Checklist

- [ ] Pin specific version tags (not `latest`)
- [ ] Change default passwords in `.env`
- [ ] Set up SSL/TLS termination
- [ ] Configure backup strategy for volumes
- [ ] Set up monitoring (health checks)
- [ ] Configure log aggregation
- [ ] Add resource limits to docker-compose.yml
- [ ] Review firewall rules
- [ ] Set up reverse proxy (nginx/traefic)
- [ ] Enable Docker logging driver

## Getting Help

- Full documentation: See [DEPLOYMENT.md](/docs/technical/DEPLOYMENT/)
- Stack script contract: See [STACK_SCRIPT_CONTRACT.md](/docs/implementation-details/STACK_SCRIPT_CONTRACT/)
- Check Docker Hub: https://hub.docker.com/u/jacbeekers
- View available tags: `docker search jacbeekers/dq-api`
- Container logs: `docker compose --env-file .env.prod.local logs -f`
