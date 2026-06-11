# Data Quality Rules API

RESTful API service for managing data quality rules, data sources, and profiling results. Built on Node.js/Express with PostgreSQL and Redis.

## Features

- RESTful API for CRUD operations on data quality rules
- Data source management and validation
- Rule suggestions based on data profiling
- Kong API Gateway integration for multi-consumer access
- JWT authentication support via Keycloak
- OpenAPI/Swagger documentation at `/v1/docs`

## Quick Start

```bash
# Pull image
docker pull jacbeekers/dq-api:latest

# Run with required services
docker run -d \
  -p 4001:4001 \
  -e DATABASE_URL=postgresql://user:pass@host:5432/dq \
  -e REDIS_HOST=redis \
  -e NODE_ENV=production \
  jacbeekers/dq-api:latest
```

## Required Services

- PostgreSQL 15+ (data storage)
- Redis 7+ (caching and job queues)

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `REDIS_HOST` | Redis hostname | Yes |
| `REDIS_PORT` | Redis port | No (default: 6379) |
| `NODE_ENV` | Environment mode | No (default: development) |

## Exposed Ports

- **4001** - HTTP API

## Health Check

- Endpoint: `GET /v1/health`
- Returns: `200 OK` when healthy

## Tags

- `latest` - Most recent build
- `0.3.0-xxxxxxx` - Semantic version with content hash (recommended for production)

## Part of Data Quality Made Easy Platform

Complete deployment at: [GitHub Repository](https://github.com/jacbeekers/dq-rulebuilder)
