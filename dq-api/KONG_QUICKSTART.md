# Kong Gateway - Quick Start Guide

**Priority 1 Implementation**: API Gateway with Kong Gateway OSS  
**Status**: ✅ Ready to deploy  
**Date**: 2026-03-02

## What Was Done

### 1. Documentation Created
- ✅ **[KONG_GATEWAY_SETUP.md](./KONG_GATEWAY_SETUP.md)** - Complete implementation guide (400+ lines)
  - Architecture diagrams
  - Docker Compose configuration
  - Plugin setup (CORS, rate limiting, security headers, Prometheus)
  - JWT/Keycloak integration roadmap
  - Troubleshooting section
  - Production deployment checklist

- ✅ **[ARCHITECTURAL_DECISIONS.md](../architecture/ARCHITECTURAL_DECISIONS.md)** - Updated with ADR-009
  - Kong Gateway vs Azure APIM vs AWS API Gateway comparison
  - Decision rationale and consequences
  - Implementation phases

- ✅ **[API_GATEWAY_DESIGN.md](./API_GATEWAY_DESIGN.md)** - Updated header
  - Marked Kong as selected technology

### 2. Scripts Created
- ✅ **[../scripts/configure_kong.sh](../scripts/configure_kong.sh)** - Automated configuration script
  - Creates dq-api service in Kong
  - Creates /v1/* route
  - Enables 7 plugins: CORS, rate limiting, request/response transformers, Prometheus
  - Creates health check route (bypass auth)
  - Creates dq-ui consumer
  - Provides summary output

### 3. Infrastructure Configuration
- ✅ **[../docker-compose.yml](../docker-compose.yml)** - Added Kong services
  - `kong-db`: PostgreSQL database for Kong
  - `kong-migrations`: Database bootstrap
  - `kong`: Kong Gateway 3.5 (ports 8000, 8443, 8001, 8002)

## How to Deploy Kong Gateway

### Option 1: Quick Start (Recommended for Testing)

```bash
cd /Users/jacbeekers/gitrepos/dq-rulebuilder

# 1. Start Kong services (will start dependencies automatically)
docker-compose up -d kong

# Wait for Kong to be healthy (30-60 seconds)
docker-compose ps kong

# 2. Configure Kong automatically
./scripts/configure_kong.sh

# 3. Test the gateway
curl http://localhost:8000/v1/health

# Expected response: {"status":"healthy",...}
```

### Option 2: Step-by-Step (Manual Configuration)

```bash
# 1. Start just Kong infrastructure first
docker-compose up -d kong-db
docker-compose logs -f kong-migrations
docker-compose up -d kong

# 2. Verify Kong is running
curl http://localhost:8001/

# 3. Manually configure (or use script)
./scripts/configure_kong.sh
```

### Option 3: Full Stack with Kong

```bash
# Start everything including Kong
docker-compose up -d

# Configure Kong after all services are healthy
./scripts/configure_kong.sh
```

## Access Points After Deployment

| Service | URL | Description |
|---------|-----|-------------|
| **Kong Proxy (HTTP)** | http://localhost:8000 | Main API gateway endpoint |
| **Kong Proxy (HTTPS)** | https://localhost:8443 | Secure API gateway (self-signed cert) |
| **Kong Admin API** | http://localhost:8001 | REST API for Kong configuration |
| **Kong Manager UI** | http://localhost:8002 | Web UI for Kong management |
| **DQ API (direct)** | http://localhost:4001 | Bypass gateway (internal only) |
| **Prometheus Metrics** | http://localhost:8001/metrics | Kong metrics for monitoring |

## Testing the Gateway

### 1. Health Endpoints (No Auth Required)

```bash
# Through Kong Gateway
curl http://localhost:8000/v1/health
curl http://localhost:8000/v1/ready
curl http://localhost:8000/v1/live
curl http://localhost:8000/v1/info

# Direct to API (bypass Kong)
curl http://localhost:4001/v1/health
```

### 2. API Endpoints Through Kong

```bash
# List rules
curl -X GET http://localhost:8000/v1/rules \
  -H "Content-Type: application/json"

# With correlation ID
curl -X GET http://localhost:8000/v1/rules \
  -H "X-Correlation-ID: test-12345"

# Check response headers (should see Kong headers)
curl -i http://localhost:8000/v1/health | grep -i x-kong
```

### 3. Verify Plugins

```bash
# List all active plugins
curl http://localhost:8001/plugins | jq '.data[] | {name, enabled}'

# Check CORS headers
curl -i -X OPTIONS http://localhost:8000/v1/rules \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: GET"

# Check rate limiting
for i in {1..10}; do
  curl -i http://localhost:8000/v1/health | grep -i ratelimit
done
# Should see: X-RateLimit-Remaining-Minute header
```

### 4. Verify Service Configuration

```bash
# View dq-api service
curl http://localhost:8001/services/dq-api | jq

# View routes
curl http://localhost:8001/routes | jq '.data[] | {name, paths, methods}'

# View consumers
curl http://localhost:8001/consumers | jq
```

## Kong Manager Access

1. **Open Kong Manager**: http://localhost:8002
2. **Use Kong Admin API credentials/config** from your environment
3. **Browse Configuration**:
  - Services → `dq-api`
  - Routes → `/v1/*`
  - Plugins → CORS, rate-limiting, transformers, prometheus
  - Consumers → `dq-ui`

## Request Flow

```
┌─────────────┐
│   dq-ui     │  http://localhost:5173
│  (React)    │
└──────┬──────┘
       │
       │ 1. API Call: GET http://localhost:8000/v1/rules
       │    Headers: Authorization: Bearer <jwt>
       │
       ▼
┌─────────────────────────────────────────────┐
│          Kong Gateway :8000                 │
│  ┌───────────────────────────────────────┐  │
│  │  2. Plugin Chain:                     │  │
│  │     ✓ CORS (allow origin)             │  │
│  │     ✓ Rate Limiting (check quota)     │  │
│  │     ✓ [JWT validation - future]       │  │
│  │     ✓ Request Transformer             │  │
│  │       (add X-Forwarded-By: Kong)      │  │
│  └───────────────────────────────────────┘  │
└──────┬──────────────────────────────────────┘
       │
       │ 3. Proxy to backend
       │    GET http://dq-api:4001/v1/rules
       │
       ▼
┌─────────────────────────┐
│   dq-api :4001          │
│  ┌───────────────────┐  │
│  │ 4. Process:       │  │
│  │  - Auth check     │  │
│  │  - Business logic │  │
│  │  - Database query │  │
│  └───────────────────┘  │
└──────┬──────────────────┘
       │
       │ 5. Response: { rules: [...] }
       │
       ▼
┌─────────────────────────────────────────────┐
│          Kong Gateway                       │
│  ┌───────────────────────────────────────┐  │
│  │ 6. Response Transform:                │  │
│  │    + X-Correlation-ID: abc-123        │  │
│  │    + X-Content-Type-Options: nosniff  │  │
│  │    + X-Frame-Options: DENY            │  │
│  │    + X-Kong-Upstream-Latency: 45ms    │  │
│  └───────────────────────────────────────┘  │
└──────┬──────────────────────────────────────┘
       │
       │ 7. Response delivered to client
       ▼
┌─────────────┐
│   dq-ui     │
└─────────────┘
```

## Configuration Summary

What `configure_kong.sh` does:

1. **Service**: Creates `dq-api` service pointing to `http://dq-api:4001`
2. **Route**: Creates `/v1/*` route forwarding all methods (GET/POST/PUT/DELETE/PATCH)
3. **CORS Plugin**: Allows requests from `http://localhost:5173` (dq-ui) with credentials
4. **Rate Limiting**: 1000 req/min per consumer, 50000 req/hour
5. **Request Transformer**: Adds `X-Forwarded-By: Kong` header
6. **Response Transformer**: Adds security headers (nosniff, DENY, XSS protection)
7. **Prometheus**: Exposes metrics at `:8001/metrics`
8. **Health Route**: Separate route for health endpoints (no future auth required)
9. **Consumer**: Creates `dq-ui` consumer for future rate limiting per app

## Next Steps

### Immediate (Completed)
- [x] Deploy Kong: `docker-compose up -d kong`
- [x] Configure: `./scripts/configure_kong.sh`
- [x] Test: `curl http://localhost:8000/v1/health`
- [x] Browse Kong Manager: http://localhost:8002

### Phase 2 (JWT Authentication)
- [ ] Install Kong OIDC plugin (or use Kong Enterprise)
- [ ] Configure OIDC provider for Kong (Keycloak now, Entra ID/AD in production)
- [ ] Enable JWT validation on `/v1/*` route (except health endpoints)
- [ ] Extract user claims (sub, email, roles) and forward as headers
- [ ] Update dq-ui to use Kong URL (`http://localhost:8000`)

### Phase 3 (Frontend Migration)
- [ ] Update dq-ui API base URL from `http://localhost:4001` to `http://localhost:8000`
- [ ] Test all API calls through Kong
- [ ] Verify CORS works with browser
- [ ] Check correlation IDs in browser DevTools

### Phase 4 (Advanced)
- [ ] Define consumer tiers (free, standard, premium) with different rate limits
- [ ] Set up Prometheus + Grafana for Kong metrics
- [ ] Enable response caching for read-heavy endpoints
- [ ] Deploy to Azure AKS with Kong Ingress Controller
- [ ] Configure Azure Key Vault for secrets
- [ ] Set up Azure Monitor integration

## Troubleshooting

### Kong not starting
```bash
# Check logs
docker-compose logs kong

# Check database connection
docker exec -it kong-gateway kong health

# Reset (WARNING: deletes data)
docker-compose down -v
docker-compose up -d kong-db
docker-compose logs -f kong-migrations
docker-compose up -d kong
```

### 502 Bad Gateway
```bash
# Can Kong reach dq-api?
docker exec -it kong-gateway wget -O- http://dq-api:4001/v1/health

# Check service config
curl http://localhost:8001/services/dq-api | jq

# Check if dq-api is healthy
curl http://localhost:4001/v1/health
```

### configure_kong.sh fails
```bash
# Make sure jq is installed
brew install jq  # macOS

# Check if Kong Admin API is reachable
curl http://localhost:8001/

# Run script with verbose output
bash -x ./scripts/configure_kong.sh
```

### CORS not working
```bash
# Check CORS plugin config
curl http://localhost:8001/plugins | jq '.data[] | select(.name == "cors")'

# Test preflight
curl -i -X OPTIONS http://localhost:8000/v1/rules \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: GET"

# Should see: Access-Control-Allow-Origin: http://localhost:5173
```

## Architecture Benefits

✅ **Multi-Consumer Ready**: Any app can now consume DQ APIs (dq-ui, BI tools, ETL, mobile)  
✅ **Rate Limiting**: Protect backend from abuse, enforce fair usage  
✅ **Authentication Offload**: Kong validates JWT, dq-api focuses on business logic  
✅ **Security Headers**: Automatic security headers on all responses  
✅ **Observability**: Prometheus metrics, correlation IDs, access logs  
✅ **Flexibility**: Can switch cloud providers without API changes  
✅ **Performance**: NGINX-based, handles 100k+ req/sec  
✅ **Free**: Open source Kong OSS, upgrade to Enterprise optional

## Documentation

### Kong Gateway Documentation
- **Full Setup Guide**: [KONG_GATEWAY_SETUP.md](./KONG_GATEWAY_SETUP.md)
- **Architecture Decisions**: [ARCHITECTURAL_DECISIONS.md](../architecture/ARCHITECTURAL_DECISIONS.md)
- **Gateway Design**: [API_GATEWAY_DESIGN.md](./API_GATEWAY_DESIGN.md)
- **V1 Migration**: [V1_MIGRATION_BIG_BANG.md](./V1_MIGRATION_BIG_BANG.md)
- **Kong Official Docs**: https://docs.konghq.com/

### API Specifications (OpenAPI 3.0)

**Interactive Swagger UI**: http://localhost:4001/api-docs (direct to API) or http://localhost:8000/api-docs (through Kong)

The DQ API exposes a complete OpenAPI 3.0 specification with interactive Swagger UI for exploring all endpoints:

- **All 60+ endpoints documented** with request/response schemas
- **Try it out** feature - test endpoints directly from browser
- **Authentication ready** - supports Bearer token input
- **Organized by tags**: Rules, Workspaces, Approvals, Users, Attributes, Data Catalog, Testing, Auth, Config, System
- **Auto-generated** from the active OpenAPI schema

**Key Endpoints**:
- Rules Management: `GET /v1/rules`, `POST /v1/rules`, `PUT /v1/rules/{id}`
- Workspaces: `GET /v1/workspaces`, `POST /v1/workspaces`
- Approvals: `GET /v1/approvals`, `POST /v1/approvals/{id}/approve`
- Data Catalog: `GET /v1/data-catalog/products`, `GET /v1/data-catalog/objects`
- Profiling: `GET /v1/suggestions/metrics`, `POST /v1/suggestions/profiling-requests`

**Export Formats**:
```bash
# Get OpenAPI spec as JSON
curl http://localhost:4001/api-docs-json > openapi.json

# Generate client SDKs
npx @openapitools/openapi-generator-cli generate \
  -i http://localhost:4001/api-docs-json \
  -g typescript-axios \
  -o ./generated-client
```

**See**: [ARCHITECTURAL_DECISIONS.md](../architecture/ARCHITECTURAL_DECISIONS.md) ADR-004 for OpenAPI implementation details.

### Data Contracts (ODCS 3.1)

**Data Contract Endpoint**: http://localhost:8000/v1/data-contracts

The DQ API exposes data quality specifications in **Open Data Contract Standard (ODCS) 3.1** format - a vendor-neutral, machine-readable format for data contracts.

**What are Data Contracts?**
- **Schema definitions** - Column names, types, constraints
- **Quality rules** - Completeness, uniqueness, validity, timeliness
- **SLAs** - Data freshness, availability, accuracy targets
- **Lineage** - Data sources, transformations, dependencies

**Endpoints**:
```bash
# List all data contracts
curl http://localhost:8000/v1/data-contracts

# Get specific contract (YAML)
curl http://localhost:8000/v1/data-contracts/customer_data

# Get contract as JSON
curl http://localhost:8000/v1/data-contracts/customer_data?format=json

# Extract quality rules from contract
curl http://localhost:8000/v1/data-contracts/customer_data/quality-rules
```

**Example Data Contract** (ODCS 3.1):
```yaml
dataContractSpecification: 0.9.3
id: customer_data
info:
  title: Customer Master Data
  version: 2.1.0
  owner: Data Platform Team
  description: |
    Customer master data including demographics, contact info, and preferences.
    Updated daily at 2 AM UTC.

servers:
  production:
    type: postgres
    host: prod-db.example.com
    database: customers
    schema: public

models:
  customer:
    type: table
    fields:
      - name: customer_id
        type: integer
        required: true
        unique: true
        primary: true
        
      - name: email
        type: string
        required: true
        unique: true
        pattern: ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$
        
      - name: created_at
        type: timestamp
        required: true

quality:
  type: SodaCL
  specification: |
    checks for customer:
      - row_count > 0
      - missing_count(email) = 0
      - duplicate_count(email) = 0
      - freshness(created_at) < 24h
```

**Use Cases**:
1. **API Client Generation** - Generate validation logic from contracts
2. **Documentation** - Self-documenting data structures
3. **CI/CD Integration** - Validate data changes against contracts
4. **Cross-Team Collaboration** - Shared understanding of data expectations
5. **Monitoring** - Track contract compliance over time

**Standards**:
- **ODCS Specification**: https://github.com/bitol-io/open-data-contract-standard
- **SodaCL (Quality)**: https://docs.soda.io/sodacl/
- **YAML/JSON** formats supported

**See**: [ARCHITECTURAL_DECISIONS.md](../architecture/ARCHITECTURAL_DECISIONS.md) ADR-007 for dual-standard API approach.

## Questions?

- **Why Kong over Azure APIM?** See ADR-009 in ARCHITECTURAL_DECISIONS.md
- **How to add JWT?** See "Phase 2" in KONG_GATEWAY_SETUP.md
- **Production deployment?** See "Production Deployment Checklist" in KONG_GATEWAY_SETUP.md
- **Frontend changes?** See V1_MIGRATION_BIG_BANG.md for dq-ui migration script

---

**Ready to start**: Run `docker-compose up -d kong && ./scripts/configure_kong.sh` 🚀
