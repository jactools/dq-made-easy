# Docker Compose Split - Quick Reference

## Quick Start

### Start Development Environment
```bash
docker compose -f docker-compose/docker-compose.yml \
  --profile base \
  --profile core \
  --profile gateway \
  --profile engine \
  --profile observability \
  up -d
```

### Start Production Environment
```bash
docker compose -f docker-compose/docker-compose.yml \
  --profile base \
  --profile core \
  --profile gateway \
  --profile engine \
  --profile observability \
  --profile support \
  --profile metadata \
  --profile auth \
  --profile llm \
  up -d
```

### Validate Configuration
```bash
docker compose -f docker-compose/docker-compose.yml config
```

## File Structure

```
docker-compose/
├── docker-compose.yml     # Main include file
├── base.yml              # Shared configs & anchors
├── core.yml              # Core services
├── engine.yml            # Engine services
├── observability.yml     # Monitoring
├── support.yml           # Zammad
├── metadata.yml          # OpenMetadata
├── auth.yml              # Keycloak
├── gateway.yml           # Kong
├── llm.yml               # LLM services
├── seed.yml              # Initialization
├── trino.yml             # Trino
└── airflow.yml           # Airflow
```

## Service Directory

| Service | File | Primary Profile |
|---------|------|----------------|
| base, db, redis, kafka, api, frontend | core.yml | core, gateway, observability |
| dq-made-easy-engine, warmup, workers | engine.yml | engine, workers |
| prometheus, grafana, exporters | observability.yml | observability |
| zammad-* | support.yml | support |
| openmetadata-* | metadata.yml | metadata |
| keycloak | auth.yml | auth, gateway |
| kong, edge | gateway.yml | gateway |
| dq-made-easy-llm, ollama-nginx | llm.yml | llm |
| db-seed, delivery-seed | seed.yml | seed |
| trino | trino.yml | trino |
| airflow | airflow.yml | airflow |

## Common Commands

### Start/Stop
```bash
# Start with profile
docker compose -f docker-compose/docker-compose.yml --profile core up -d

# Stop all
docker compose -f docker-compose/docker-compose.yml down

# Stop with volumes
docker compose -f docker-compose/docker-compose.yml down -v
```

### Logs
```bash
# View logs
docker compose -f docker-compose/docker-compose.yml logs <service>

# Follow logs
docker compose -f docker-compose/docker-compose.yml logs -f <service>
```

### Health Checks
```bash
# Check service health
docker compose -f docker-compose/docker-compose.yml ps

# Validate config
docker compose -f docker-compose/docker-compose.yml config
```

## Environment Variables

All environment variables remain in .env.*.local files:
- .env.dev.local - Development
- .env.prod.local - Production
- .env.test.local - Test

Load them with:
```bash
docker compose -f docker-compose/docker-compose.yml --env-file .env.dev.local up
```

## YAML Anchors

Available in base.yml:
- x-defaults - Default restart & networks
- x-engine-base - Engine service config
- x-exporter-base - Exporter config
- x-zammad-service - Zammad template

## Support

- Slack: #devops
- GitHub: Create issue with docker-compose label
- Docs: See migration guide for full details
