# Docker Hub Publishing Guide

This guide explains how to publish the repository descriptions to Docker Hub.

## 🚀 Quick Start - Automated Script (Recommended)

Use the automated script to update all repositories at once:

```bash
# 1. Create a Docker Hub access token
# Go to: https://hub.docker.com/settings/security
# Click "New Access Token"
# Name it (e.g., "dq-rulebuilder-updates")
# Select permissions: Read, Write, Delete
# Copy the token (starts with dckr_pat_...)

# 2. Set your token
export DOCKER_HUB_TOKEN="dckr_pat_your_token_here"

# 3. Run the script
./scripts/update_docker_hub.sh

# Or with explicit username
./scripts/update_docker_hub.sh --username jacbeekers --token "dckr_pat_..."

# Dry run to preview changes
./scripts/update_docker_hub.sh --dry-run
```

The script will:
- ✅ Authenticate with Docker Hub
- ✅ Update all repository descriptions in `docker-hub-descriptions/` automatically
- ✅ Update both short and full descriptions
- ✅ Show success/failure for each repository
- ✅ Provide a summary at the end

When you publish a specific image through `scripts/build_and_push_one.sh` or
`scripts/build_and_push_all.sh --image <name>`, the matching Docker Hub
description is refreshed automatically after a successful push.

**That's it!** All repositories will be updated in under a minute.

---

## Manual Publishing Process

### Method 1: Via Docker Hub Web Interface (Recommended)

1. **Login to Docker Hub**
   - Go to https://hub.docker.com/
   - Sign in with your credentials

2. **Navigate to Each Repository**
   - Go to https://hub.docker.com/r/jacbeekers/[image-name]
   - Click the repository name

3. **Edit Repository Details**
   - Click "Manage Repository" or the settings icon
   - Look for the "Description" section

4. **Add Short Description**
   - Limited to **100 characters**
   - Should be a concise one-liner
   - See "Short Descriptions" section below

5. **Add Full Description**
   - Supports Markdown formatting
   - Copy from "Full Descriptions for Docker Hub" section below
   - Preview before saving

6. **Add Categories/Topics**
   - Add relevant topics (like tags)
   - Examples: `data-quality`, `nodejs`, `react`, `api`, `kong`

7. **Save Changes**

### Method 2: Via Docker Hub API (Automation)

You can use the Docker Hub API to update descriptions programmatically:

```bash
# Set your credentials
DOCKER_HUB_USERNAME="jacbeekers"
DOCKER_HUB_PASSWORD="your-token"

# Login and get token
TOKEN=$(curl -s -H "Content-Type: application/json" \
  -X POST \
  -d "{\"username\": \"$DOCKER_HUB_USERNAME\", \"password\": \"$DOCKER_HUB_PASSWORD\"}" \
  https://hub.docker.com/v2/users/login/ | jq -r .token)

# Update repository description
REPO_NAME="npm-base"
FULL_DESCRIPTION="Your full markdown description here..."

curl -X PATCH \
  -H "Authorization: JWT ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"full_description\": \"${FULL_DESCRIPTION}\"}" \
  "https://hub.docker.com/v2/repositories/${DOCKER_HUB_USERNAME}/${REPO_NAME}/"
```

---

## Short Descriptions (100 character limit)

Copy these for the "Short Description" field:

### jacbeekers/npm-base
```
Base Node.js 20 image with build essentials for Data Quality Made Easy services
```
(79 characters)

### jacbeekers/dq-api
```
RESTful API for data quality rule management with PostgreSQL and Redis
```
(74 characters)

### jacbeekers/dq-engine
```
Python-based data quality rule execution engine with multi-database support
```
(78 characters)

### jacbeekers/dq-profiling
```
Background worker for data profiling and rule suggestion generation
```
(68 characters)

### jacbeekers/dq-frontend
```
React-based web UI for managing data quality rules with app-owned components
```
(73 characters)

### jacbeekers/dq-kong
```
Kong 3.4 API Gateway pre-configured for Data Quality Made Easy platform
```
(70 characters)

---

## Full Descriptions for Docker Hub

Copy these for the "Full Description" field (supports Markdown):

### jacbeekers/npm-base

```markdown
# Base Node.js Image for Data Quality Made Easy

Foundational image containing Node.js 20 (Bullseye Slim) with build essentials and common dependencies. Serves as the parent image for `dq-api` and `dq-profiling` services.

## Features

- Node.js 20 LTS on Debian Bullseye Slim
- Build essentials (gcc, g++, make)
- curl and ca-certificates pre-installed
- Optimized for production with minimal attack surface

## Quick Start

```bash
docker pull jacbeekers/npm-base:latest
```

## Tags

- `latest` - Most recent build
- `0.3.0-xxxxxxx` - Semantic version with content hash (recommended for production)

## Usage

This is a base image meant to be used in `FROM` statements:

```dockerfile
FROM jacbeekers/npm-base:0.3.0-e625985
WORKDIR /app
COPY package*.json ./
RUN npm ci --production
```

## Part of Data Quality Made Easy

This image is part of the Data Quality Made Easy platform - a comprehensive data quality rule management system.

**Other Services:**
- `jacbeekers/dq-api` - REST API backend
- `jacbeekers/dq-engine` - Rule execution engine
- `jacbeekers/dq-profiling` - Profiling worker
- `jacbeekers/dq-frontend` - Web UI
- `jacbeekers/dq-kong` - API Gateway

## Documentation

Full documentation: [GitHub Repository](https://github.com/[your-org]/dq-rulebuilder)

## Support

- Issues: GitHub Issues
- License: See repository
```

---

### jacbeekers/dq-api

```markdown
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

## Docker Compose Example

```yaml
services:
  api:
    image: jacbeekers/dq-api:0.3.0-6e9ca2e
    ports:
      - "4001:4001"
    environment:
      DATABASE_URL: postgresql://postgres:postgres@db:5432/dq
      REDIS_HOST: redis
      NODE_ENV: production
    depends_on:
      - db
      - redis
```

## Part of Data Quality Made Easy Platform

Complete deployment at: [GitHub Repository](https://github.com/[your-org]/dq-rulebuilder)
```

---

### jacbeekers/dq-engine

```markdown
# Data Quality Rules Engine

Python-based execution engine that translates and executes data quality rules against target databases. Supports multiple rule types and database platforms.

## Features

- Rule translation from JSON to SQL
- Multi-database support (PostgreSQL, Oracle, SQL Server, etc.)
- Scheduled rule execution
- Results posting to DQ API
- FastAPI-based management interface

## Quick Start

```bash
# Pull image
docker pull jacbeekers/dq-engine:latest

# Run engine
docker run -d \
  -p 8000:8000 \
  -e DQ_LOG_LEVEL=INFO \
  jacbeekers/dq-engine:latest
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DQ_LOG_LEVEL` | Python logging level | No (default: INFO) |

## Exposed Ports

- **8000** - HTTP management interface

## Supported Rule Types

- ✅ Completeness checks (NULL/NOT NULL)
- ✅ Uniqueness checks (duplicate detection)
- ✅ Value range validation
- ✅ Pattern matching (regex)
- ✅ Custom SQL expressions

## Runtime Model

- `POST /compile` validates rule translation only.
- Spark execution and run reporting are handled by the `dq-engine-gx-worker` service.

## Health Check

- Endpoint: `GET /docs` (FastAPI documentation)
- Returns: `200 OK` when healthy

## Tags

- `latest` - Most recent build
- `0.3.0-xxxxxxx` - Semantic version with content hash

## Docker Compose Example

```yaml
services:
  dq-engine:
    image: jacbeekers/dq-engine:0.3.0-14aefcc
    ports:
      - "8000:8000"
    environment:
      DQ_LOG_LEVEL: INFO
```

## Part of Data Quality Made Easy Platform

Complete deployment: [GitHub Repository](https://github.com/[your-org]/dq-rulebuilder)
```

---

### jacbeekers/dq-profiling

```markdown
# Data Profiling Worker

Background worker service that performs data profiling on database tables and generates rule suggestions. Built on Node.js with Bull queue processing.

## Features

- Automated data profiling for tables and columns
- Statistical analysis (min, max, avg, distinct counts, NULL %)
- Pattern detection and data type inference
- Rule suggestion generation
- Redis-based job queue with Bull
- Concurrent job processing

## Quick Start

```bash
# Pull image
docker pull jacbeekers/dq-profiling:latest

# Run worker
docker run -d \
  -e DATABASE_URL=postgresql://user:pass@host:5432/dq \
  -e REDIS_HOST=redis \
  -e PROFILING_WORKER_CONCURRENCY=2 \
  jacbeekers/dq-profiling:latest
```

## Required Services

- PostgreSQL 15+ (metadata storage)
- Redis 7+ (job queue)
- DQ API (job coordination)

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection | Yes |
| `REDIS_HOST` | Redis hostname | Yes |
| `REDIS_PORT` | Redis port | No (default: 6379) |
| `PROFILING_WORKER_CONCURRENCY` | Concurrent jobs | No (default: 2) |
| `NODE_ENV` | Environment mode | No |

## Profiling Capabilities

- Column-level statistics
- Data type detection
- NULL value analysis
- Uniqueness analysis
- Value distribution patterns

## Generated Rule Suggestions

- Completeness rules
- Uniqueness constraints
- Value range rules

## Tags

- `latest` - Most recent build
- `0.3.0-xxxxxxx` - Semantic version with content hash

## Docker Compose Example

```yaml
services:
  profiling-worker:
    image: jacbeekers/dq-profiling:0.3.0-5a2a995
    environment:
      DATABASE_URL: postgresql://postgres:postgres@db:5432/dq
      REDIS_HOST: redis
      PROFILING_WORKER_CONCURRENCY: 2
    depends_on:
      - db
      - redis
      - api
```

## Part of Data Quality Made Easy Platform

Complete deployment: [GitHub Repository](https://github.com/[your-org]/dq-rulebuilder)
```

---

### jacbeekers/dq-frontend

```markdown
# Data Quality Made Easy - Web UI

React-based single-page application (SPA) for managing data quality rules. Built with Vite, React, and app-owned components, served via Nginx.

## Features

- Interactive rule builder interface
- Data source management
- Rule execution monitoring
- Data profiling results viewer
- Rule suggestions from profiling
- Authentication via Keycloak (OIDC)
- Responsive design with app-owned styling
- Dark theme support

## Quick Start

```bash
# Pull image
docker pull jacbeekers/dq-frontend:latest

# Run frontend
docker run -d \
  -p 5173:80 \
  -e KONG_PUBLIC_URL=http://kong:9111 \
  jacbeekers/dq-frontend:latest
```

Access at: http://localhost:5173

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `KONG_PUBLIC_URL` | Runtime backend API URL override (preferred) | http://localhost:9111 |
| `VITE_API_URL` | Backend API URL fallback (compatibility) | http://localhost:9111 |

## Exposed Ports

- **80** - HTTP (map to 5173 on host)

## Technology Stack

- React 18 with TypeScript
- Vite for build tooling
- React Router for navigation
- Axios for API communication
- App-owned components
- Nginx as web server

## Browser Support

Modern browsers with ES2020+ JavaScript support:
- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)

## Health Check

- Endpoint: `GET /`
- Returns: `200 OK` with HTML

## Tags

- `latest` - Most recent build
- `0.3.0-xxxxxxx` - Semantic version with content hash

## Docker Compose Example

```yaml
services:
  frontend:
    image: jacbeekers/dq-frontend:0.3.0-6725b17
    ports:
      - "5173:80"
    environment:
      KONG_PUBLIC_URL: http://kong:9111
    depends_on:
      - api
```

## Part of Data Quality Made Easy Platform

Complete deployment: [GitHub Repository](https://github.com/[your-org]/dq-rulebuilder)
```

---

### jacbeekers/dq-kong

```markdown
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

## Configuration

Kong can be configured via:
- Admin API (port 8001)
- Environment variables
- kong.conf file

See [Kong Documentation](https://docs.konghq.com/) for details.

## Tags

- `latest` - Most recent build (Kong 3.4)
- `0.3.0-xxxxxxx` - Semantic version with content hash

## Docker Compose Example

```yaml
services:
  kong-db:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: kong
      POSTGRES_USER: kong
      POSTGRES_PASSWORD: kongpass
    volumes:
      - kong-db-data-v17:/var/lib/postgresql/data

  kong-migrations:
    image: kong:3.9.1
    command: kong migrations bootstrap
    depends_on:
      - kong-db
    environment:
      KONG_DATABASE: postgres
      KONG_PG_HOST: kong-db
      KONG_PG_DATABASE: kong
      KONG_PG_USER: kong
      KONG_PG_PASSWORD: kongpass

  kong:
    image: jacbeekers/dq-kong:0.3.0-0aaabb2
    depends_on:
      - kong-db
      - kong-migrations
    ports:
      - "9111:8000"
      - "9001:8001"
    environment:
      KONG_DATABASE: postgres
      KONG_PG_HOST: kong-db
      KONG_PG_DATABASE: kong
      KONG_PG_USER: kong
      KONG_PG_PASSWORD: kongpass
      KONG_PROXY_ACCESS_LOG: /dev/stdout
      KONG_ADMIN_ACCESS_LOG: /dev/stdout
      KONG_PROXY_ERROR_LOG: /dev/stderr
      KONG_ADMIN_ERROR_LOG: /dev/stderr
```

## Part of Data Quality Made Easy Platform

Complete deployment: [GitHub Repository](https://github.com/[your-org]/dq-rulebuilder)
```

---

## Categories/Topics to Add

Add these topics/tags to each repository for better discoverability:

### Common tags for all images:
- `data-quality`
- `docker`
- `dq-rulebuilder`

### Image-specific additional tags:

**npm-base:**
- `nodejs`
- `node20`
- `base-image`
- `build-tools`

**dq-api:**
- `nodejs`
- `api`
- `rest-api`
- `express`
- `postgresql`
- `redis`

**dq-engine:**
- `python`
- `fastapi`
- `data-validation`
- `rule-engine`
- `sql`

**dq-profiling:**
- `nodejs`
- `worker`
- `background-job`
- `bull`
- `data-profiling`
- `redis`

**dq-frontend:**
- `react`
- `vite`
- `spa`
- `ui`
- `nginx`
- `typescript`

**dq-kong:**
- `kong`
- `api-gateway`
- `authentication`
- `rate-limiting`
- `cors`

---

## Automation Script

Here's a script to update all repositories at once:

```bash
#!/usr/bin/env bash
# update_docker_hub.sh

DOCKER_HUB_USERNAME="jacbeekers"
DOCKER_HUB_TOKEN="your-token-here"

# Login and get JWT token
TOKEN=$(curl -s -H "Content-Type: application/json" \
  -X POST \
  -d "{\"username\": \"$DOCKER_HUB_USERNAME\", \"password\": \"$DOCKER_HUB_TOKEN\"}" \
  https://hub.docker.com/v2/users/login/ | jq -r .token)

# Function to update repository
update_repo() {
    local repo_name="$1"
    local full_desc="$2"
    
    echo "Updating $repo_name..."
    
    curl -s -X PATCH \
      -H "Authorization: JWT ${TOKEN}" \
      -H "Content-Type: application/json" \
      -d "{\"full_description\": $(jq -Rs . <<< "$full_desc")}" \
      "https://hub.docker.com/v2/repositories/${DOCKER_HUB_USERNAME}/${repo_name}/" \
      > /dev/null
    
    echo "✓ Updated $repo_name"
}

# Update each repository (copy full descriptions from above)
update_repo "npm-base" "$(cat npm-base-description.md)"
update_repo "dq-api" "$(cat dq-api-description.md)"
# ... etc
```

---

## Notes

1. **Character Limits:**
   - Short description: 100 characters max
   - Full description: No practical limit, but keep it concise

2. **Markdown Support:**
   - Full description supports Markdown
   - Use tables, code blocks, lists for better formatting

3. **Images/Badges:**
   - You can add badges (shields.io)
   - Example: `![Docker Pulls](https://img.shields.io/docker/pulls/jacbeekers/dq-api)`

4. **Links:**
   - Add links to documentation, GitHub, issues
   - Use relative links within Docker Hub

5. **Updates:**
   - Update descriptions when features change
   - Keep version information current
   - Add migration notes for breaking changes
