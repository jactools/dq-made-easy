# Docker Hub Repository Descriptions

⚠️ **DEPRECATED** — This document describes v0.3.0 (legacy). 

**For current v0.11.5+ documentation, see [DOCKER_SERVICES_REFERENCE.md](DOCKER_SERVICES_REFERENCE.md)** which covers all 22+ active services, deployment profiles, observability stack, and TLS security configuration.

---

## Legacy Content (v0.3.0)

The following describes services as they existed in the 0.3.0 release. Most services have been significantly evolved or replaced. This document is retained for historical reference only.



## docker.io/jacbeekers/npm-base

### Repository Overview

**Base Node.js Image for Data Quality Made Easy Services**

This is a foundational image containing Node.js 20 (Bullseye Slim) with build essentials and common dependencies for the Data Quality Made Easy project. It serves as the parent image for `dq-api` and `dq-profiling` services, reducing build times and ensuring consistency across services.

**Key Features:**
- Node.js 20 LTS on Debian Bullseye Slim
- Build essentials (gcc, g++, make)
- curl and ca-certificates pre-installed
- Optimized for production use with minimal attack surface

**Usage:**
```bash
# Pull the image
docker pull docker.io/jacbeekers/npm-base:latest

# Or use specific version
docker pull docker.io/jacbeekers/npm-base:0.3.0-e625985
```

**Tags:**
- `latest` - Most recent build
- `0.3.0-xxxxxxx` - Semantic version with content hash (recommended for production)

**Part of:** Data Quality Made Easy - A data quality rule management platform

**Source:** https://github.com/[your-org]/dq-rulebuilder

---

## docker.io/jacbeekers/dq-api

### Repository Overview

**Data Quality Rules API - Backend Service**

RESTful API service for managing data quality rules, data sources, and profiling results. Built on Node.js/Express with PostgreSQL and Redis, this service provides the backend for the Data Quality Made Easy platform.

**Key Features:**
- RESTful API for CRUD operations on data quality rules
- Data source management and validation
- Rule suggestions based on data profiling
- Integration with Kong API Gateway for multi-consumer access
- JWT authentication support via Keycloak
- OpenAPI/Swagger documentation at `/v1/docs`

**Usage:**
```bash
# Pull the image
docker pull docker.io/jacbeekers/dq-api:latest

# Run with required environment variables
docker run -d \
  -p 4001:4001 \
  -e DATABASE_URL=postgresql://user:pass@host:5432/dq \
  -e REDIS_HOST=redis \
  -e NODE_ENV=production \
  docker.io/jacbeekers/dq-api:latest
```

**Required Services:**
- PostgreSQL 15+ (for data storage)
- Redis 7+ (for caching and job queues)

**Environment Variables:**
- `DATABASE_URL` - PostgreSQL connection string (required)
- `REDIS_HOST` - Redis hostname (required)
- `REDIS_PORT` - Redis port (default: 6379)
- `NODE_ENV` - Environment (production/development)

**Exposed Ports:**
- `4001` - HTTP API

**Health Check:**
- Endpoint: `GET /v1/health`
- Returns: `200 OK` when healthy

**Tags:**
- `latest` - Most recent build
- `0.3.0-xxxxxxx` - Semantic version with content hash (recommended for production)

**Part of:** Data Quality Made Easy Platform

**Documentation:** See full deployment guide at repository

---

## docker.io/jacbeekers/dq-engine

### Repository Overview

**Data Quality Rules Engine - Python-based Rule Executor**

Python-based execution engine that translates and executes data quality rules against target databases. Supports multiple rule types and database platforms.

**Key Features:**
- Rule translation from JSON to SQL
- Multi-database support (PostgreSQL, Oracle, SQL Server, etc.)
- Scheduled rule execution
- Results posting to DQ API
- FastAPI-based management interface

**Usage:**
```bash
# Pull the image
docker pull docker.io/jacbeekers/dq-engine:latest

# Run the engine
docker run -d \
  -p 8000:8000 \
  -e DQ_LOG_LEVEL=INFO \
  docker.io/jacbeekers/dq-engine:latest
```

**Environment Variables:**
- `DQ_LOG_LEVEL` - Python logging level (default: INFO)

**Runtime Model:**
- `POST /compile` validates rule translation only
- Spark execution and run reporting are handled by `dq-engine-gx-worker`

**Exposed Ports:**
- `8000` - HTTP management interface

**Health Check:**
- Endpoint: `GET /docs` (FastAPI documentation)
- Returns: `200 OK` when healthy

**Supported Rule Types:**
- Completeness checks (NULL/NOT NULL validation)
- Uniqueness checks (duplicate detection)
- Value range validation
- Pattern matching (regex)
- Custom SQL expressions

**Tags:**
- `latest` - Most recent build
- `0.3.0-xxxxxxx` - Semantic version with content hash (recommended for production)

**Part of:** Data Quality Made Easy Platform

---

## docker.io/jacbeekers/dq-profiling

### Repository Overview

**Data Profiling Worker - Background Job Processor**

Background worker service that performs data profiling on database tables and generates rule suggestions. Built on Node.js with Bull queue processing.

**Key Features:**
- Automated data profiling for tables and columns
- Statistical analysis (min, max, avg, distinct counts, NULL percentages)
- Pattern detection and data type inference
- Rule suggestion generation based on profiling results
- Redis-based job queue with Bull
- Concurrent job processing

**Usage:**
```bash
# Pull the image
docker pull docker.io/jacbeekers/dq-profiling:latest

# Run the worker
docker run -d \
  -e DATABASE_URL=postgresql://user:pass@host:5432/dq \
  -e REDIS_HOST=redis \
  -e PROFILING_WORKER_CONCURRENCY=2 \
  docker.io/jacbeekers/dq-profiling:latest
```

**Required Services:**
- PostgreSQL 15+ (metadata and results storage)
- Redis 7+ (job queue management)
- DQ API (job coordination)

**Environment Variables:**
- `DATABASE_URL` - PostgreSQL connection string (required)
- `REDIS_HOST` - Redis hostname (required)
- `REDIS_PORT` - Redis port (default: 6379)
- `PROFILING_WORKER_CONCURRENCY` - Number of concurrent jobs (default: 2)
- `NODE_ENV` - Environment (production/development)

**Profiling Capabilities:**
- Column-level statistics
- Data type detection
- NULL value analysis
- Uniqueness analysis
- Value distribution patterns
- Suggest completeness rules
- Suggest uniqueness constraints
- Suggest value range rules

**Tags:**
- `latest` - Most recent build
- `0.3.0-xxxxxxx` - Semantic version with content hash (recommended for production)

**Part of:** Data Quality Made Easy Platform

---

## docker.io/jacbeekers/dq-frontend

### Repository Overview

**Data Quality Made Easy - Web User Interface**

React-based single-page application (SPA) for managing data quality rules. Built with Vite, React Components, served via Nginx.

**Key Features:**
- Interactive rule builder interface
- Data source management
- Rule execution monitoring
- Data profiling results viewer
- Rule suggestions from profiling
- Authentication via Keycloak (OIDC)
- Responsive design
- Dark theme support

**Usage:**
```bash
# Pull the image
docker pull docker.io/jacbeekers/dq-frontend:latest

# Run the frontend
docker run -d \
  -p 5173:80 \
  -e KONG_PUBLIC_URL=http://kong:9111 \
  docker.io/jacbeekers/dq-frontend:latest
```

**Environment Variables:**
- `KONG_PUBLIC_URL` - Runtime backend API URL override (preferred)
- `VITE_API_URL` - Backend API URL fallback (compatibility)

**Exposed Ports:**
- `80` - HTTP (mapped to 5173 on host by default)

**Technologies:**
- React 18 with TypeScript
- Vite for build tooling
- React Router for navigation
- Axios for API communication
- Nginx as web server

**Browser Support:**
- Modern browsers (Chrome, Firefox, Safari, Edge)
- ES2020+ JavaScript support required

**Health Check:**
- Endpoint: `GET /`
- Returns: `200 OK` with HTML when healthy

**Tags:**
- `latest` - Most recent build
- `0.3.0-xxxxxxx` - Semantic version with content hash (recommended for production)

**Part of:** Data Quality Made Easy Platform

---

## docker.io/jacbeekers/dq-kong

### Repository Overview

**Kong API Gateway - Configured for Data Quality Made Easy**

Pre-configured Kong API Gateway instance for the Data Quality Made Easy platform. Provides API routing, authentication, rate limiting, and CORS handling for multi-consumer API access.

**Key Features:**
- Kong 3.4 base
- Pre-configured health checks
- CORS support for frontend integration
- JWT authentication plugin support
- Rate limiting capabilities
- API request/response logging
- Multiple consumer support

**Usage:**
```bash
# Pull the image
docker pull docker.io/jacbeekers/dq-kong:latest

# Requires Kong database (PostgreSQL)
# Run with docker-compose for full configuration
docker run -d \
  -p 9111:8000 \
  -p 9001:8001 \
  -e KONG_DATABASE=postgres \
  -e KONG_PG_HOST=kong-db \
  -e KONG_PG_DATABASE=kong \
  -e KONG_PG_USER=kong \
  -e KONG_PG_PASSWORD=kongpass \
  docker.io/jacbeekers/dq-kong:latest
```

**Required Services:**
- PostgreSQL 17 (Kong metadata storage)
- DQ API service (upstream)

**Environment Variables:**
- `KONG_DATABASE` - Database type (postgres)
- `KONG_PG_HOST` - PostgreSQL hostname
- `KONG_PG_DATABASE` - Database name
- `KONG_PG_USER` - Database user
- `KONG_PG_PASSWORD` - Database password

**Exposed Ports:**
- `8000` - HTTP Proxy (client requests)
- `8001` - HTTP Admin API
- `8443` - HTTPS Proxy
- `8444` - HTTPS Admin API

**Configuration:**
See Kong documentation for:
- Service and route configuration
- Plugin management
- Consumer setup
- JWT authentication

**Health Check:**
- Built-in Kong health monitoring
- Status endpoint available on Admin API

**Tags:**
- `latest` - Most recent build
- `0.3.0-xxxxxxx` - Semantic version with content hash (recommended for production)

**Part of:** Data Quality Made Easy Platform

**Kong Version:** 3.4

---

## Usage Recommendations

### For Production:

1. **Always use semantic version tags**, not `latest`:
   ```bash
   docker pull docker.io/jacbeekers/dq-api:0.3.0-6e9ca2e
   ```

2. **Use docker-compose** for orchestration - see repository for complete docker-compose.yml

3. **Set resource limits** in your deployment configuration

4. **Configure health checks** for all services

5. **Use secrets management** for sensitive environment variables

### For Development:

Use `latest` tags for convenience:
```bash
docker compose pull
docker compose up -d
```

### Version Information:

Version tags follow the format: `MAJOR.MINOR-CONTENTHASH`
- Example: `0.3.0-6e9ca2e`
- Content hash ensures reproducible builds
- Same source = same hash = same image

### Getting Started:

See the complete deployment guide:
- Repository: https://github.com/[your-org]/dq-rulebuilder
- Quick Start: See docs/technical/QUICKSTART_DEPLOY.md
- Full Guide: See docs/technical/DEPLOYMENT.md

### Support:

- Documentation: See repository README
- Issues: GitHub Issues
- License: See LICENSE file in repository
