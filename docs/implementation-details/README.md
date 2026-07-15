# Docker Compose Split - Implementation Details

This directory contains documentation for the Docker Compose split migration from a monolithic file to modular files.

## Documentation

| Document | Description |
|----------|-------------|
| [DOCKER_COMPOSE_SPLIT_MIGRATION.md](./DOCKER_COMPOSE_SPLIT_MIGRATION.md) | Complete migration guide with step-by-step instructions |
| [DOCKER_COMPOSE_SPLIT_QUICK_REFERENCE.md](./DOCKER_COMPOSE_SPLIT_QUICK_REFERENCE.md) | Quick reference for common commands and usage patterns |
| [DOCKER_COMPOSE_SPLIT_TROUBLESHOOTING.md](./DOCKER_COMPOSE_SPLIT_TROUBLESHOOTING.md) | Troubleshooting guide for common issues |

## Overview

The Docker Compose configuration has been split from:
- **Before**: 1 file, 2,079 lines, 86 services
- **After**: 12 modular files, ~1,587 lines total, 86 services

### Key Benefits

1. **Improved Maintainability**: Each file is 150-300 lines vs 2,000+
2. **Reduced Duplication**: YAML anchors for shared configurations
3. **Better Organization**: Services grouped by function
4. **Enhanced Collaboration**: Teams can work on different files
5. **Faster Operations**: Docker Compose parses smaller files faster

### New File Structure

```
docker-compose/
├── docker-compose.yml     # Main include file
├── base.yml              # Shared configs & anchors
├── core.yml              # Core services (db, redis, kafka, api, frontend)
├── engine.yml            # Engine services
├── observability.yml     # Monitoring (prometheus, grafana, exporters)
├── support.yml           # Zammad support
├── metadata.yml          # OpenMetadata
├── auth.yml              # Keycloak
├── gateway.yml           # Kong
├── llm.yml               # LLM services
├── seed.yml              # Initialization
├── trino.yml             # Trino
└── airflow.yml           # Airflow
```

## Getting Started

1. **Read the Migration Guide** for complete instructions: [DOCKER_COMPOSE_SPLIT_MIGRATION.md](./DOCKER_COMPOSE_SPLIT_MIGRATION.md)

2. **Use the Quick Reference** for common commands: [DOCKER_COMPOSE_SPLIT_QUICK_REFERENCE.md](./DOCKER_COMPOSE_SPLIT_QUICK_REFERENCE.md)

3. **Check Troubleshooting** if you encounter issues: [DOCKER_COMPOSE_SPLIT_TROUBLESHOOTING.md](./DOCKER_COMPOSE_SPLIT_TROUBLESHOOTING.md)

## Support

- Slack: #devops
- GitHub: Create issue with docker-compose label
