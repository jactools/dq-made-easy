# Docker Services Reference (v0.11.5+)

**Last Updated**: 2026-07-09  
**Platform Version**: v0.11.5+  
**Architecture**: Multi-service with 22+ service profiles for flexible deployments

This document describes all Docker services in the dq-made-easy platform. For older versions (0.3.0 and earlier), see [DOCKER_HUB_DESCRIPTIONS.md](DOCKER_HUB_DESCRIPTIONS.md).

---

## Quick Navigation

- [Core Platform](#core-platform-services)
- [Infrastructure & Routing](#infrastructure--routing)
- [Data Discovery](#data-discovery)
- [Observability Stack](#observability-stack)
- [Background Workers](#background-workers)
- [Optional Services](#optional-services)
- [Deployment Profiles](#deployment-profiles)
- [Environment Setup](#environment-setup)
- [Certificate & Security](#certificate--security)

---

## Core Platform Services

### dq-api (FastAPI Backend)

**Purpose**: RESTful API backend for rule management, data source administration, and profiling coordination

**Image**: `jacbeekers/dq-api:v0.11.5-<hash>`  
**Base**: Python 3.14-slim  
**Port**: 8000 (default) / 4001 (gateway-exposed)

**Key Features**:
- Rule CRUD operations (stored in PostgreSQL)
- Data source registration and validation
- Profiling request orchestration
- Result persistence
- OpenAPI/Swagger at `/docs`
- CORS-enabled for frontend integration

**Environment Variables** (required):
- `DATABASE_URL` - PostgreSQL connection (e.g., `postgresql://dq:pass@db:5432/dq`)
- `REDIS_HOST` - Redis for caching (default: `redis`)
- `REDIS_PORT` - Redis port (default: `6379`)
- `LOG_LEVEL` - Python logging level (default: `INFO`)

**Health Check**:
- Endpoint: `GET /health`
- Returns: `200 OK` with service status

**Docker Compose Profile**: `core`

---

### dq-frontend (React/Vite UI)

**Purpose**: Single-page web application for interactive rule building and management

**Image**: `jacbeekers/dq-frontend:v0.11.5-<hash>`  
**Base**: Node 22-bullseye-slim + Nginx  
**Port**: 5173 (dev) / 80 (production via Kong)

**Key Features**:
- React 18 + TypeScript
- Vite build tooling (fast HMR)
- Interactive rule builder
- Data source explorer
- Rule execution monitoring
- Profiling results viewer
- Keycloak OIDC authentication
- Dark/light theme support
- Responsive design

**Environment Variables** (runtime):
- `VITE_API_URL` - Backend API URL (default: `/api` for gateway routing)
- `VITE_KEYCLOAK_REALM` - Keycloak realm (default: `master`)
- `VITE_KEYCLOAK_CLIENT_ID` - OIDC client (default: `dq-frontend`)

**Health Check**:
- Endpoint: `GET /`
- Returns: `200 OK` with HTML

**Docker Compose Profile**: `core`

---

### PostgreSQL 18 (Main Database)

**Purpose**: Primary data store for rules, data sources, results, and metadata

**Image**: `postgres:18-alpine`  
**Port**: 5432  
**Volume**: `postgres-data` (persistent)

**Key Features**:
- Full ACID compliance
- JSON support for complex rule definitions
- Materialized views for reporting
- Row-level security for multi-tenant isolation
- High-availability ready (replication support)

**Environment Variables**:
- `POSTGRES_DB` - Database name (default: `dq`)
- `POSTGRES_USER` - Admin user (default: `dq`)
- `POSTGRES_PASSWORD` - Admin password (required)

**Seeding**:
- Initial schema loaded from `/db/init/` on first run
- CSV data sources in `data_sources/` directory
- Custom SQL patches in `/db/patches/`

**Health Check**:
- Built-in: `pg_isready` on port 5432

**Docker Compose Profile**: `core`

---

### Apache Spark 4.1 (Execution Engine)

**Purpose**: Distributed rule execution engine for data quality checks against target databases

**Image**: `jacbeekers/spark-base:v0.11.5-<hash>`  
**Base**: Python 3.13 + Spark 4.1 + Great Expectations  
**Ports**: 7077 (master), 8080 (UI), 4040 (driver)

**Key Features**:
- Spark SQL for rule translation and execution
- PySpark for complex rule logic
- Great Expectations integration for validation
- Horizontal scaling (worker nodes)
- Results streaming to Kafka
- Exception fact storage

**Environment Variables**:
- `SPARK_MASTER` - Master node URL (e.g., `spark://spark-master:7077`)
- `SPARK_DRIVER_MEMORY` - Driver heap (default: `2g`)
- `SPARK_EXECUTOR_MEMORY` - Executor heap (default: `2g`)
- `EXECUTOR_CORES` - CPU per executor (default: `2`)

**Deployment Model**:
- **Master**: Cluster manager
- **Worker(s)**: Distributed execution (scales horizontally)
- **Driver**: Rule compilation and coordination

**Docker Compose Profile**: `core`

---

### Redis 6.0

**Purpose**: Distributed cache, session store, and job queue management

**Image**: `redis:6-alpine`  
**Port**: 6379  
**Volume**: `redis-data` (persistent)

**Key Features**:
- Fast in-memory caching (rule metadata, query results)
- Distributed job queues (Bull for profiling/execution)
- Session state for API
- Pub/Sub for event notifications

**Commands**:
```bash
# Monitor queue jobs
redis-cli -h redis BLPOP dq:jobs 0

# Check memory usage
redis-cli -h redis INFO memory
```

**Docker Compose Profile**: `core`

---

## Infrastructure & Routing

### Kong 3.9.1 (API Gateway)

**Purpose**: Central API gateway providing routing, authentication, rate limiting, and request transformation

**Image**: `kong:3.9.1-alpine`  
**Ports**: 8000 (proxy), 8001 (admin), 8443 (HTTPS proxy), 8444 (HTTPS admin)  
**Database**: Kong PostgreSQL (separate from main DB)

**Key Features**:
- JWT authentication plugin (Keycloak integration)
- Rate limiting per consumer
- CORS headers management
- Request/response transformation
- Load balancing upstream services
- Multiple consumer support
- API versioning (e.g., `/v1/`, `/v2/`)

**Routes Configured**:
- `/api/v1/*` → `dq-api:8000`
- `/docs/*` → API documentation
- `/health` → Kong health check

**Environment Variables**:
- `KONG_DATABASE` - `postgres`
- `KONG_PG_HOST` - Kong DB hostname (default: `kong-db`)
- `KONG_PG_DATABASE` - Database name (default: `kong`)
- `KONG_PG_USER` - User (default: `kong`)
- `KONG_PG_PASSWORD` - Password (required)
- `KONG_LOG_LEVEL` - Logging level (default: `notice`)

**Admin Console**:
- URL: `http://localhost:8001`
- Manage routes, services, plugins, consumers

**Docker Compose Profile**: `gateway`

---

### Kong PostgreSQL 17

**Purpose**: Metadata store for Kong configuration (separate from application DB)

**Image**: `postgres:17-alpine`  
**Port**: 5433 (separate port to avoid conflicts)

**Docker Compose Profile**: `gateway`

---

### Keycloak 26.6.2 (OIDC/SSO Provider)

**Purpose**: Centralized authentication and authorization via OpenID Connect

**Image**: `keycloak:26.6.2`  
**Port**: 8080  
**Database**: PostgreSQL (or H2 in dev)

**Key Features**:
- OIDC/OAuth2 provider
- User and role management
- Multi-realm support
- Social login integration
- JWT token generation
- SAML support

**Default Credentials**:
- Username: `admin`
- Password: `admin` (change in production)

**Realms**:
- `master` - Admin realm
- `dq-made-easy` - Application realm

**Clients**:
- `dq-frontend` - SPA client
- `dq-api` - Backend service client

**Environment Variables**:
- `KC_DB` - Database type (default: `dev` mode uses H2)
- `KC_DB_URL` - Database connection
- `KEYCLOAK_ADMIN` - Admin user (default: `admin`)
- `KEYCLOAK_ADMIN_PASSWORD` - Admin password (required)

**Docker Compose Profile**: `gateway` or `authentication`

---

## Data Discovery

### OpenMetadata 1.x

**Purpose**: Data catalog and lineage tracking for discovered data assets

**Image**: `openmetadata/openmetadata:1.x-<hash>`  
**Port**: 8585  
**Database**: MySQL 8.0 (embedded or external)

**Key Features**:
- Data asset registration and discovery
- Lineage tracking (rule → data source → metrics)
- Metadata versioning
- Search and tagging
- Access control

**Docker Compose Profile**: `metadata`

---

### Elasticsearch 8.11.4 (Search Backend)

**Purpose**: Full-text search index for metadata and asset discovery

**Image**: `docker.elastic.co/elasticsearch/elasticsearch:8.11.4`  
**Port**: 9200  
**Volume**: `elasticsearch-data`

**Environment Variables**:
- `discovery.type` - `single-node` for single-instance
- `xpack.security.enabled` - Enable X-Pack security (default: `true`)

**Docker Compose Profile**: `metadata`

---

### Apache Kafka 3.9.1

**Purpose**: Event streaming for violation notifications and metrics publishing

**Image**: `confluentinc/cp-kafka:7.9.1`  
**Port**: 9092 (broker), 29092 (external)  
**Volume**: `kafka-data`

**Topics**:
- `dq-violations` - Rule violation events
- `dq-metrics` - Execution metrics
- `dq-events` - Platform events

**Environment Variables**:
- `KAFKA_BROKER_ID` - Broker ID (default: `1`)
- `KAFKA_ZOOKEEPER_CONNECT` - ZooKeeper address
- `KAFKA_ADVERTISED_LISTENERS` - Advertised listener addresses

**Docker Compose Profile**: `events` or `core-extended`

---

## Observability Stack

### Prometheus v3

**Purpose**: Metrics collection and time-series database

**Image**: `prom/prometheus:v3-<hash>`  
**Port**: 9090  
**Volume**: `prometheus-data` (persistent)

**Scrape Targets**:
- `dq-api:8000/metrics`
- `kong:8001/metrics`
- `spark-master:8080/metrics`
- `postgres-exporter:9187`
- `redis-exporter:9121`

**Retention**:
- Default: 15 days (configurable)

**Docker Compose Profile**: `observability`

---

### Grafana 12.3

**Purpose**: Metrics visualization and alerting dashboards

**Image**: `grafana/grafana:12.3-<hash>`  
**Port**: 3000  
**Volume**: `grafana-data` (persistent for dashboards)

**Default Credentials**:
- Username: `admin`
- Password: `admin` (change in production)

**Data Sources**:
- Prometheus (metrics)
- Loki (logs)
- Tempo (traces)

**Pre-configured Dashboards**:
- Rule execution metrics
- API performance
- Database connections
- Worker queue health

**Docker Compose Profile**: `observability`

---

### Loki 3.6.4

**Purpose**: Log aggregation and querying

**Image**: `grafana/loki:3.6.4-<hash>`  
**Port**: 3100  
**Volume**: `loki-data`

**Log Sources**:
- `dq-api` (application logs)
- `dq-workers` (execution logs)
- `postgres` (database logs)
- `kong` (gateway logs)

**Query Language**: LogQL (similar to PromQL)

**Docker Compose Profile**: `observability`

---

### Tempo 2.6.1

**Purpose**: Distributed tracing backend

**Image**: `grafana/tempo:2.6.1-<hash>`  
**Port**: 3200 (query), 4317 (OTLP receiver)  
**Volume**: `tempo-data`

**Trace Collection**:
- OpenTelemetry Collector → Tempo
- Correlation IDs tracked across services

**Docker Compose Profile**: `observability`

---

### OpenTelemetry Collector 0.148.0

**Purpose**: Unified telemetry collection (metrics, logs, traces)

**Image**: `otel/opentelemetry-collector:0.148.0`  
**Ports**: 4317 (OTLP gRPC), 4318 (OTLP HTTP), 14250 (Jaeger)

**Receivers**:
- OTLP (OpenTelemetry Protocol)
- Prometheus (metrics scrape)
- Jaeger (trace ingestion)

**Exporters**:
- Prometheus (metrics)
- Loki (logs)
- Tempo (traces)

**Docker Compose Profile**: `observability`

---

### Prometheus Pushgateway

**Purpose**: Accept metrics from batch/short-lived jobs

**Image**: `prom/pushgateway:v2-<hash>`  
**Port**: 9091

**Use Case**: Profiling workers push job completion metrics

**Docker Compose Profile**: `observability`

---

### Container Metrics Exporter

**Purpose**: Export Docker container-level metrics to Prometheus

**Image**: `jacbeekers/container-metrics-exporter:v0.11.5-<hash>`  
**Port**: 9100

**Metrics**:
- Container CPU, memory, network I/O
- Per-service resource utilization

**Docker Compose Profile**: `observability`

---

## Background Workers

### Profiling Worker

**Purpose**: Background service for data profiling and rule suggestion generation

**Image**: `jacbeekers/dq-profiling-worker:v0.11.5-<hash>`  
**Base**: Python 3.13

**Key Features**:
- Bull queue consumption (Redis-backed)
- Statistical analysis (min, max, mean, stddev)
- Data type inference
- Pattern detection
- Rule suggestion generation
- Concurrent job processing

**Environment Variables**:
- `REDIS_HOST` - Redis hostname (default: `redis`)
- `REDIS_PORT` - Redis port (default: `6379`)
- `DATABASE_URL` - PostgreSQL connection
- `WORKER_CONCURRENCY` - Parallel jobs (default: `2`)
- `LOG_LEVEL` - Logging level (default: `INFO`)

**Scaling**: Horizontal - add multiple worker replicas

**Docker Compose Profile**: `workers`

---

### Rule Execution Worker (GX Validator)

**Purpose**: Distributed rule execution using Great Expectations

**Image**: `jacbeekers/gx-worker:v0.11.5-<hash>`  
**Base**: Python 3.13 + Spark 4.1

**Key Features**:
- Great Expectations rule execution
- Spark DataFrame validation
- Exception fact generation
- Result persistence
- Distributed execution (scales with Spark cluster)

**Environment Variables**:
- `SPARK_MASTER` - Spark cluster URL
- `REDIS_HOST` - Redis for job coordination
- `DATABASE_URL` - Result storage

**Docker Compose Profile**: `workers` or `core-extended`

---

### Test Data Generator Worker

**Purpose**: Generate synthetic test data for rule validation

**Image**: `jacbeekers/test-data-generator:v0.11.5-<hash>`  
**Base**: Python 3.13

**Features**:
- Faker-based synthetic data
- Data distribution control
- Volume scaling
- CSV/Parquet output

**Docker Compose Profile**: `workers` or `development`

---

## Optional Services

### LLM Service (Huggingface Models)

**Purpose**: Natural language rule drafting and AI-assisted rule generation

**Image**: `jacbeekers/dq-llm:v0.11.5-<hash>`  
**Base**: Python 3.14 + Huggingface Transformers  
**Port**: 8001

**Models**:
- GPT-like models for rule suggestions
- Embedding models for semantic search
- Fine-tuned models for DQ-specific tasks

**Environment Variables**:
- `HF_MODEL_ID` - Huggingface model ID
- `MODEL_CACHE_DIR` - Local model cache path
- `CUDA_VISIBLE_DEVICES` - GPU allocation (if available)

**Docker Compose Profile**: `llm` or `ai`

---

### Trino 482 (Query Engine)

**Purpose**: Federated SQL query engine for cross-data-source analysis

**Image**: `trinodb/trino:482`  
**Port**: 8080  
**Volume**: `trino-data` (catalogs, plugins)

**Connectors**:
- PostgreSQL
- MySQL
- S3 (via Hive)
- Elasticsearch

**Use Case**: Cross-source rule validation, data profiling

**Docker Compose Profile**: `query-engine`

---

### Apache Airflow 3.2.2

**Purpose**: Workflow orchestration and scheduling

**Image**: `apache/airflow:3.2.2-python3.11`  
**Port**: 8080  
**Database**: PostgreSQL

**Key Features**:
- DAG-based workflow definition
- Schedule rule execution
- Dependency management
- Monitoring and alerting
- Integration with other services

**Docker Compose Profile**: `orchestration`

---

### Edge Router (SNI-based Routing)

**Purpose**: SNI-aware routing for multi-tenant deployments

**Image**: `jacbeekers/dq-edge:v0.11.5-<hash>`  
**Port**: 443 (TLS)

**Key Features**:
- TLS SNI passthrough
- Multi-domain routing
- Certificate handling
- Internal service TLS enforcement

**Docker Compose Profile**: `edge` (production deployments)

---

### Zammad (Support/Legacy)

**Purpose**: Legacy support ticketing system (retained for backward compatibility)

**Image**: `zammad:latest-alpine`  
**Port**: 3000  
**Status**: ⚠️ Deprecated - consider alternative support platforms

**Docker Compose Profile**: `support` (optional)

---

## Deployment Profiles

Service organization via Docker Compose profiles enables flexible deployments:

### Profile: `core` (Minimal)
- dq-api, dq-frontend
- PostgreSQL, Redis
- Required for any deployment

```bash
docker compose --profile core up -d
```

### Profile: `gateway`
- Kong + Kong PostgreSQL
- Keycloak
- Adds: API Gateway, authentication

### Profile: `workers`
- Profiling Worker
- Execution Worker (GX)
- Test Data Generator
- Adds: Background processing

### Profile: `observability`
- Prometheus, Grafana, Loki, Tempo
- OTEL Collector
- Pushgateway, Container Metrics Exporter
- Adds: Full observability stack

### Profile: `metadata`
- OpenMetadata
- Elasticsearch
- Adds: Data catalog and discovery

### Profile: `events`
- Apache Kafka
- Adds: Event streaming

### Profile: `query-engine`
- Trino
- Adds: Federated query capability

### Profile: `orchestration`
- Apache Airflow
- Adds: Workflow scheduling

### Profile: `llm` / `ai`
- LLM Service
- Adds: AI-assisted rule generation

### Profile: `edge` (Production)
- Edge Router
- Required for multi-tenant TLS deployments

### Common Combinations

**Development** (all features):
```bash
docker compose --profile core --profile gateway --profile workers \
  --profile observability --profile metadata --profile events \
  --profile query-engine --profile llm up -d
```

**Production** (scalable):
```bash
docker compose --profile core --profile gateway --profile workers \
  --profile observability --profile edge up -d
# Scale workers separately:
docker compose up -d --scale gx-worker=3 --scale profiling-worker=2
```

**Minimal** (API only):
```bash
docker compose --profile core up -d
```

---

## Environment Setup

### Standard Environment File

Create `.env.local` (not committed):

```bash
# Core Services
POSTGRES_DB=dq
POSTGRES_USER=dq
POSTGRES_PASSWORD=secretpass123

# API Configuration
API_LOG_LEVEL=INFO
REDIS_HOST=redis
REDIS_PORT=6379

# Kong/Keycloak
KONG_PG_PASSWORD=kongpass456
KEYCLOAK_ADMIN_PASSWORD=keycloakpass789

# Observability
GRAFANA_ADMIN_PASSWORD=grafanapass000
PROMETHEUS_RETENTION=15d

# TLS & Security
INTERNAL_CA_BUNDLE_PATH=/tmp/certs/trust/internal-ca-bundle.pem
MKCERT_ROOT_CA=/tmp/certs/mkcert-rootCA.pem
```

### Loading Environment

```bash
# Load custom environment
source .env.local
docker compose up -d

# Or specify directly
docker compose --env-file .env.local up -d
```

---

## Certificate & Security

### TLS Enforcement (WF7)

All inter-service communication uses TLS with mkcert:

**Certificate Structure**:
```
/tmp/certs/
├── mkcert-rootCA.pem          # Root CA (all services trust this)
├── services/                  # Per-service leaf certificates
│   ├── dq-api/
│   │   ├── tls.crt
│   │   ├── tls.key
│   │   └── san.conf
│   ├── postgres/
│   └── ...
└── trust/
    └── internal-ca-bundle.pem # Canonical trust bundle
```

**Generation**:
```bash
./scripts/create_certs.sh
```

**Validation**:
```bash
./scripts/validate_tls_*.sh
```

### Environment Variables

Services mount certificates via:
- `INTERNAL_CA_BUNDLE_PATH` - Path to trust bundle
- `TLS_CERT_PATH` - Service certificate
- `TLS_KEY_PATH` - Service private key

---

## Publishing & Versioning

### Build & Push

```bash
# Build all images
docker compose build

# Push to registry (requires credentials)
./scripts/push_images.sh

# With custom registry
DOCKER_REGISTRY=myregistry.azurecr.io docker compose push
```

### Version Tags

Images use semantic versioning with content hash:
```
jacbeekers/dq-api:v0.11.5-3a8c2f1e
                    ↑ semantic version
                            ↑ content hash (ensures reproducibility)
```

**For Production Use**: Always specify semantic versions, never use `latest`

```bash
docker pull jacbeekers/dq-api:v0.11.5-3a8c2f1e
```

---

## Troubleshooting

### Service Health Checks

```bash
# Check all service health
docker compose ps

# View logs for a service
docker compose logs -f dq-api

# Test API connectivity
curl -k https://localhost:4001/health

# Connect to database
docker compose exec postgres psql -U dq -d dq
```

### Common Issues

**PostgreSQL Connection Refused**:
- Verify `POSTGRES_PASSWORD` matches in env and connection string
- Check port 5432 is not in use by another service

**Kong Gateway Not Routing**:
- Verify Kong admin API accessible at `http://localhost:8001`
- Check routes configured: `curl http://localhost:8001/routes`

**Observability Not Collecting**:
- Verify OTEL Collector is receiving metrics: `curl http://localhost:4318/healthz`
- Check Prometheus scrape targets: `http://localhost:9090/targets`

**TLS Certificate Errors**:
- Regenerate certificates: `./scripts/create_certs.sh`
- Verify trust bundle mounted: `docker compose exec dq-api cat $INTERNAL_CA_BUNDLE_PATH`

---

## Additional Resources

- **Deployment Guide**: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- **Architecture Reference**: [architecture/README.md](architecture/README.md)
- **TLS Setup**: [docs/implementation-details/SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md](docs/implementation-details/SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md)
- **Docker Compose**: [docker-compose.yml](docker-compose.yml)
- **Scripts**: [scripts/](scripts/) (see `common_startup.sh`, `pull_images.sh`, `create_certs.sh`)
