# Kong API Gateway for Data Quality Made Easy

Pre-configured Kong 3.4 API Gateway instance for the Data Quality Made Easy platform. Provides API routing, authentication, rate limiting, and CORS handling.

## Features

- Kong 3.4 base
- Pre-configured health checks
- CORS support for frontend integration
- JWT authentication plugin support
- Rate limiting capabilities
- API request/response logging
- Multiple consumer support

## Quick Start

```bash
# Pull image
docker pull jacbeekers/dq-kong:latest

# Requires Kong database (see Docker Compose below)
```

## Required Services

- PostgreSQL 17 (Kong metadata storage)
- DQ API service (upstream)

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `KONG_DATABASE` | Database type | Yes (postgres) |
| `KONG_PG_HOST` | PostgreSQL hostname | Yes |
| `KONG_PG_DATABASE` | Database name | Yes |
| `KONG_PG_USER` | Database user | Yes |
| `KONG_PG_PASSWORD` | Database password | Yes |

## Exposed Ports

- **8000** - HTTP Proxy (client requests)
- **8001** - HTTP Admin API
- **8443** - HTTPS Proxy
- **8444** - HTTPS Admin API

## Tags

- `latest` - Most recent build (Kong 3.4)
- `0.3.0-xxxxxxx` - Semantic version with content hash

## Part of Data Quality Made Easy Platform

Complete deployment: [GitHub Repository](https://github.com/jacbeekers/dq-rulebuilder)
