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
cd dq-rulebuilder

# 2. Create your production env file
cp .env.prod.example .env.prod.local
# Edit .env.prod.local if needed (passwords, versions, canonical hostnames, etc.)

# 3. Pull all images (uses versions from .env.prod.local)
docker compose --env-file .env.prod.local pull

# 4. Start services
docker compose --env-file .env.prod.local up -d

# 5. Check status
docker compose --env-file .env.prod.local ps

# 6. View logs
docker compose --env-file .env.prod.local logs -f
```

Important: `.env.prod.example` is the tracked public single-host template, and `.env.prod.local` is your ignored machine-local runtime copy. For Debian operators, prefer an external file such as `/etc/dq-made-easy/prod.env` with `root:root` ownership and `0600` permissions instead of storing production secrets in the repo root. For local workstation flows, use `.env.dev.example` or `.env.test.example` instead.

## Option 2: Use Pull Script

```bash
# Pull latest versions
./scripts/pull_images.sh

# Or pull a shared manual override tag
./scripts/pull_images.sh v0.10.2

# Then start
docker compose --env-file .env.prod.local up -d
```

## Option 3: Manual Pull

```bash
# Pull individual images
docker pull docker.io/jacbeekers/npm-base:latest
docker pull docker.io/jacbeekers/dq-api:latest
docker pull docker.io/jacbeekers/dq-engine:latest
docker pull docker.io/jacbeekers/dq-profiling:latest
docker pull docker.io/jacbeekers/dq-frontend:latest
docker pull docker.io/jacbeekers/dq-kong:latest

# Or with specific versions
docker pull docker.io/jacbeekers/dq-api:0.10-b85dd7d
# ... etc
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
- API/runtime uses `SSO_*`, `ALLOW_LOCAL_AUTH`, and `TRUST_PROXY_AUTH` as defaults.
- Frontend initial settings use `VITE_SSO_*` before app-config is loaded.
- Values in `app_config` override env defaults at runtime when present.

## Common Operations

### Update to Latest
```bash
docker compose --env-file .env.prod.local pull
docker compose --env-file .env.prod.local up -d
```

### Restart Services
```bash
# All services
docker compose --env-file .env.prod.local restart

# Specific service
docker compose --env-file .env.prod.local restart api
```

### Reseed Database While Running
```bash
# Re-apply schema + seed data through the dedicated db-seed one-shot service
bash ./scripts/reseed_running_db.sh

# Or run the same one-shot service explicitly via Compose
docker compose --env-file .env.prod.local --profile auth --profile seed run --rm db-seed

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
docker compose --env-file .env.prod.local logs -f

# Specific service
docker compose --env-file .env.prod.local logs -f api

# Last 100 lines
docker compose --env-file .env.prod.local logs --tail=100
```

### Stop Services
```bash
# Stop (keeps data)
docker compose --env-file .env.prod.local stop

# Stop and remove containers (keeps data)
docker compose --env-file .env.prod.local down

# Stop and remove everything including volumes (DELETES DATA!)
docker compose --env-file .env.prod.local down -v
```

### Check Health
```bash
# Service status
docker compose --env-file .env.prod.local ps

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
docker compose --env-file .env.prod.local up -d
```

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
docker compose --env-file .env.prod.local logs

# Check specific service
docker compose --env-file .env.prod.local logs api

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
docker pull docker.io/jacbeekers/dq-api:latest
```

### Database Issues
```bash
# Reset database (WARNING: deletes data)
docker compose --env-file .env.prod.local down -v db
docker compose --env-file .env.prod.local up -d db

# Check database logs
docker compose --env-file .env.prod.local logs db
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
- [ ] Set up reverse proxy (nginx/traefik)
- [ ] Enable Docker logging driver

## Getting Help

- Full documentation: See [DEPLOYMENT.md](./DEPLOYMENT.md)
- Check Docker Hub: https://hub.docker.com/u/jacbeekers
- View available tags: `docker search jacbeekers/dq-api`
- Container logs: `docker compose --env-file .env.prod.local logs -f`
