# Kong Gateway Setup for DQ API

**Decision Date**: 2026-03-02  
**Status**: Implementation Guide  
**Gateway**: Kong Gateway 3.x (OSS or Enterprise)

## Why Kong Gateway?

✅ **Open source** with enterprise option  
✅ **Plugin ecosystem** (1000+ plugins)  
✅ **Kubernetes-native** (Kong Ingress Controller)  
✅ **Performance** (NGINX core, handles 100k+ req/sec)  
✅ **Flexible deployment** (Docker, K8s, bare metal)  
✅ **Azure-compatible** (AKS, VMs, Container Instances)  
✅ **Active community** and commercial support available

## Architecture Overview

```
┌─────────────────┐
│   dq-ui (React) │
│  Port 5173/80   │
└────────┬────────┘
         │
         │ HTTPS
         ▼
┌─────────────────────────────────────────┐
│         Kong Gateway (Port 8443)         │
│  ┌───────────────────────────────────┐  │
│  │  Plugins Active:                   │  │
│  │  - JWT Authentication              │  │
│  │  - Rate Limiting                   │  │
│  │  - CORS                            │  │
│  │  - Request Transformer             │  │
│  │  - Response Transformer            │  │
│  │  - Correlation ID                  │  │
│  │  - Prometheus (metrics)            │  │
│  └───────────────────────────────────┘  │
│                                          │
│  Routes:                                 │
│  /v1/* → dq-api:4001                    │
└────────┬─────────────────────────────────┘
         │
         │ HTTP (internal)
         ▼
┌─────────────────────────────────────────┐
│      dq-api (FastAPI) - Port 4010       │
│  ┌───────────────────────────────────┐  │
│  │  - Receives x-user-id from Kong   │  │
│  │  - Receives x-correlation-id      │  │
│  │  - Validates business logic       │  │
│  │  - Returns RFC 7807 errors        │  │
│  └───────────────────────────────────┘  │
└────────┬─────────────────────────────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│   PostgreSQL    │      │  Keycloak    │
│   Port 5432     │      │  Port 8080   │
└─────────────────┘      └──────────────┘
```

## Quick Start: Docker Compose

### 1. Add Kong to docker-compose.yml

```yaml
version: '3.8'

services:
  # Existing services (postgres, keycloak, dq-api, etc.)...

  # Kong Database (PostgreSQL)
  kong-db:
    image: postgres:17-alpine
    container_name: kong-database
    environment:
      POSTGRES_DB: kong
      POSTGRES_USER: kong
      POSTGRES_PASSWORD: kongpass
    volumes:
      - kong-db-data-v17:/var/lib/postgresql/data
    networks:
      - dq-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U kong"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Kong Database Bootstrap
  kong-migrations:
    image: kong:3.5-alpine
    container_name: kong-migrations
    command: kong migrations bootstrap
    depends_on:
      kong-db:
        condition: service_healthy
    environment:
      KONG_DATABASE: postgres
      KONG_PG_HOST: kong-db
      KONG_PG_DATABASE: kong
      KONG_PG_USER: kong
      KONG_PG_PASSWORD: kongpass
    networks:
      - dq-network
    restart: on-failure

  # Kong Gateway
  kong:
    image: kong:3.5-alpine
    container_name: kong-gateway
    depends_on:
      kong-db:
        condition: service_healthy
      kong-migrations:
        condition: service_completed_successfully
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
      KONG_ADMIN_LISTEN: 0.0.0.0:8001
      KONG_ADMIN_GUI_URL: http://localhost:8002
      KONG_PROXY_LISTEN: 0.0.0.0:8000, 0.0.0.0:8443 ssl
    ports:
      - "8000:8000"   # HTTP proxy
      - "8443:8443"   # HTTPS proxy
      - "8001:8001"   # Admin API
      - "8002:8002"   # Kong Manager (GUI)
    networks:
      - dq-network
    healthcheck:
      test: ["CMD", "kong", "health"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  kong-db-data-v17:

networks:
  dq-network:
    driver: bridge
```

### 2. Start Kong

```bash
# Start Kong services
docker-compose up -d kong-db kong-migrations kong

# Verify Kong is running
curl -i http://localhost:8001/

# Expected: HTTP/1.1 200 OK
```

### 3. Access Kong Admin Interfaces

- **Kong Admin API**: http://localhost:8001
- **Kong Manager**: http://localhost:8002

## Configuration: Automated Setup Script

### 4. Create Kong Configuration Script

Save as `scripts/configure_kong.sh`:

```bash
#!/bin/bash
set -e

KONG_ADMIN_LOCAL_URL="http://localhost:8001"
KEYCLOAK_INTERNAL_URL="http://keycloak:8080"
DQ_API_INTERNAL_URL="http://api:4010"

echo "🔧 Configuring Kong Gateway for DQ API..."

# 1. Create Service for dq-api
echo "Creating dq-api service..."
SERVICE_ID=$(curl -s -X POST ${KONG_ADMIN_URL}/services \
  --data name=dq-api \
  --data protocol=http \
  --data host=dq-api \
  --data port=4001 \
  --data path=/ \
  --data retries=5 \
  --data connect_timeout=60000 \
  --data write_timeout=60000 \
  --data read_timeout=60000 | jq -r '.id')

echo "Service created: $SERVICE_ID"

# 2. Create Route for /v1/*
echo "Creating /v1/* route..."
ROUTE_ID=$(curl -s -X POST ${KONG_ADMIN_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-v1 \
  --data 'paths[]=/v1' \
  --data 'methods[]=GET' \
  --data 'methods[]=POST' \
  --data 'methods[]=PUT' \
  --data 'methods[]=DELETE' \
  --data 'methods[]=PATCH' \
  --data strip_path=false | jq -r '.id')

echo "Route created: $ROUTE_ID"

# 3. Enable CORS Plugin
echo "Enabling CORS plugin..."
curl -s -X POST ${KONG_ADMIN_URL}/services/${SERVICE_ID}/plugins \
  --data name=cors \
  --data 'config.origins=http://localhost:5173' \
  --data 'config.origins=http://localhost:3000' \
  --data 'config.methods=GET' \
  --data 'config.methods=POST' \
  --data 'config.methods=PUT' \
  --data 'config.methods=DELETE' \
  --data 'config.methods=PATCH' \
  --data 'config.methods=OPTIONS' \
  --data 'config.headers=Accept' \
  --data 'config.headers=Accept-Version' \
  --data 'config.headers=Content-Length' \
  --data 'config.headers=Content-MD5' \
  --data 'config.headers=Content-Type' \
  --data 'config.headers=Date' \
  --data 'config.headers=X-Auth-Token' \
  --data 'config.headers=Authorization' \
  --data 'config.headers=X-Correlation-ID' \
  --data 'config.exposed_headers=X-Auth-Token' \
  --data 'config.exposed_headers=X-Correlation-ID' \
  --data 'config.credentials=true' \
  --data 'config.max_age=3600' > /dev/null

echo "✅ CORS plugin enabled"

# 4. Enable Rate Limiting (per consumer)
echo "Enabling rate limiting plugin..."
curl -s -X POST ${KONG_ADMIN_URL}/services/${SERVICE_ID}/plugins \
  --data name=rate-limiting \
  --data config.minute=1000 \
  --data config.hour=50000 \
  --data config.policy=local \
  --data config.fault_tolerant=true \
  --data config.hide_client_headers=false > /dev/null

echo "✅ Rate limiting enabled (1000/min, 50000/hour)"

# 5. Enable Request Transformer (add correlation ID if missing)
echo "Enabling request transformer..."
curl -s -X POST ${KONG_ADMIN_URL}/services/${SERVICE_ID}/plugins \
  --data name=request-transformer \
  --data 'config.add.headers=X-Forwarded-By:Kong' \
  --data 'config.add.headers=X-Gateway-Version:3.5' > /dev/null

echo "✅ Request transformer enabled"

# 6. Enable Prometheus Metrics
echo "Enabling Prometheus metrics..."
curl -s -X POST ${KONG_ADMIN_URL}/plugins \
  --data name=prometheus > /dev/null

echo "✅ Prometheus metrics enabled at :8001/metrics"

# 7. Enable Response Transformer (add HSTS, security headers)
echo "Enabling response transformer..."
curl -s -X POST ${KONG_ADMIN_URL}/services/${SERVICE_ID}/plugins \
  --data name=response-transformer \
  --data 'config.add.headers=X-Content-Type-Options:nosniff' \
  --data 'config.add.headers=X-Frame-Options:DENY' \
  --data 'config.add.headers=X-XSS-Protection:1; mode=block' \
  --data 'config.add.headers=Referrer-Policy:strict-origin-when-cross-origin' > /dev/null

echo "✅ Response transformer with security headers enabled"

# 8. Create health check route (bypass auth)
echo "Creating health check route..."
HEALTH_ROUTE_ID=$(curl -s -X POST ${KONG_ADMIN_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-health \
  --data 'paths[]=/v1/health' \
  --data 'paths[]=/v1/ready' \
  --data 'paths[]=/v1/live' \
  --data 'paths[]=/v1/info' \
  --data 'methods[]=GET' \
  --data strip_path=false | jq -r '.id')

echo "Health route created: $HEALTH_ROUTE_ID (no auth required)"

# 9. Create Consumer for dq-ui
echo "Creating dq-ui consumer..."
UI_CONSUMER_ID=$(curl -s -X POST ${KONG_ADMIN_URL}/consumers \
  --data username=dq-ui \
  --data custom_id=dq-ui-frontend | jq -r '.id')

echo "Consumer created: $UI_CONSUMER_ID"

# 10. Summary
echo ""
echo "🎉 Kong Gateway configured successfully!"
echo ""
echo "📊 Configuration Summary:"
echo "  Service:     dq-api (${SERVICE_ID:0:8}...)"
echo "  Route:       /v1/* → http://dq-api:4001"
echo "  Plugins:     CORS, Rate Limiting, Transformers, Prometheus"
echo "  Health:      /v1/health, /v1/ready, /v1/live, /v1/info"
echo "  Consumer:    dq-ui (${UI_CONSUMER_ID:0:8}...)"
echo ""
echo "🔗 Access Points:"
echo "  Proxy:       http://localhost:8000/v1/health"
echo "  Admin API:   http://localhost:8001/"
echo "  Kong Manager:http://localhost:8002/"
echo "  Metrics:     http://localhost:8001/metrics"
echo ""
echo "📝 Next Steps:"
echo "  1. Configure JWT authentication (see JWT_SETUP.md)"
echo "  2. Update dq-ui API base URL to http://localhost:8000"
echo "  3. Test: curl http://localhost:8000/v1/health"
echo ""
```

Make executable and run:

```bash
chmod +x scripts/configure_kong.sh
./scripts/configure_kong.sh
```

## Testing the Gateway

### Test Health Endpoints

```bash
# Direct to API (bypass Kong)
curl http://localhost:4001/v1/health

# Through Kong Gateway
curl http://localhost:8000/v1/health
```

### Test API Endpoints

```bash
# List rules through Kong
curl -X GET http://localhost:8000/v1/rules \
  -H "Content-Type: application/json"

# With correlation ID
curl -X GET http://localhost:8000/v1/rules \
  -H "X-Correlation-ID: test-123"

# Check response headers
curl -i http://localhost:8000/v1/health
# Should see: X-Kong-Upstream-Latency, X-Kong-Proxy-Latency, X-Correlation-ID
```

### Verify Plugins

```bash
# List all plugins
curl http://localhost:8001/plugins | jq

# Check rate limiting
for i in {1..10}; do
  curl -i http://localhost:8000/v1/health
done
# Should see: X-RateLimit-Remaining-Minute header
```

## JWT Authentication Setup

Current local implementation uses:
- Kong `jwt` plugin on `/v1/*` route
- Keycloak realm role composites that emit granular `dq:*` scopes in token role claims
- Backend scope checks aligned with UI roles

### Phase 1: Kong JWT Plugin (No Keycloak Yet)

For testing, enable basic JWT validation:

```bash
# Enable JWT plugin on main route
ROUTE_ID="<your-route-id>"

curl -X POST http://localhost:8001/routes/${ROUTE_ID}/plugins \
  --data name=jwt \
  --data config.claims_to_verify=exp \
  --data config.key_claim_name=kid \
  --data config.uri_param_names=jwt
```

Generate test consumer with JWT credential:

```bash
# Create test consumer
curl -X POST http://localhost:8001/consumers \
  --data username=test-user

# Create JWT credential
curl -X POST http://localhost:8001/consumers/test-user/jwt \
  --data key=test-key \
  --data algorithm=HS256 \
  --data secret=test-secret
```

### Phase 2: OIDC Integration (Keycloak for Dev, Entra ID/AD for Production)

See [KONG_KEYCLOAK_INTEGRATION.md](./KONG_KEYCLOAK_INTEGRATION.md) for full local Keycloak setup.
For production, point Kong OIDC configuration to your Microsoft Entra ID (Azure AD) discovery endpoint.

**Prerequisites**:
- Kong Enterprise (for OIDC plugin) OR
- Kong Gateway OSS + [kong-oidc plugin](https://github.com/nokia/kong-oidc)

```bash
# Install OIDC plugin (OSS)
luarocks install kong-oidc

# Enable OIDC plugin
curl -X POST http://localhost:8001/routes/${ROUTE_ID}/plugins \
  --data name=oidc \
  --data config.client_id=dq-api \
  --data config.client_secret=<your-keycloak-secret> \
  --data config.realm=dqprototype \
  --data config.discovery=http://keycloak:8080/realms/dqprototype/.well-known/openid-configuration \
  --data config.scope=openid profile email \
  --data config.bearer_only=yes \
  --data config.logout_path=/logout \
  --data config.redirect_after_logout_uri=/
```

Production note:
- Replace `config.discovery`, `config.client_id`, and `config.client_secret` with Entra ID application values.
- Keep claim forwarding contract stable (`sub` -> `X-User-ID`, roles/scopes -> authorization headers).

## Request Flow with JWT

```
1. User logs in via Keycloak
   └─> dq-ui receives JWT access token

2. dq-ui calls API through Kong
   └─> GET http://localhost:8000/v1/rules
   └─> Header: Authorization: Bearer <jwt-token>

3. Kong validates JWT
   ├─> Checks signature against Keycloak JWKS
   ├─> Verifies expiration
  ├─> Extracts claims (sub, email, roles/scopes)
   └─> If valid, proceeds

4. Kong transforms request
   ├─> Adds X-User-ID: <sub-from-jwt>
   ├─> Adds X-Correlation-ID: <uuid> (if missing)
  ├─> Adds X-User-Roles: <roles-from-jwt>
   └─> Forwards to dq-api:4001

5. dq-api processes request
  ├─> Reads identity from JWT-compatible claims/user context
  ├─> Applies granular scope checks per endpoint
   └─> Returns response

6. Kong transforms response
   ├─> Adds security headers
   ├─> Adds X-Correlation-ID to response
   └─> Returns to client
```

## Role to Scope Alignment

Local Keycloak realm role composites map to granular scopes as follows:
- `viewer` -> `dq:rules:view`
- `analyst` -> `dq:rules:view`, `dq:rules:create`, `dq:rules:edit`, `dq:rules:test`, `dq:profiling:request`
- `data-steward` -> analyst scopes + `dq:rules:approve`
- `admin` / `cross-admin` -> all granular scopes

Granular scope set:
- `dq:rules:view`, `dq:rules:create`, `dq:rules:edit`, `dq:rules:delete`
- `dq:rules:test`, `dq:rules:approve`, `dq:rules:activate`
- `dq:users:manage`, `dq:workspace:manage`, `dq:config:manage`
- `dq:profiling:request`

## Rate Limiting Per Consumer

```bash
# Advanced rate limiting with tiers
curl -X POST http://localhost:8001/consumers/free-tier/plugins \
  --data name=rate-limiting \
  --data config.minute=100 \
  --data config.hour=5000

curl -X POST http://localhost:8001/consumers/premium-tier/plugins \
  --data name=rate-limiting \
  --data config.minute=10000 \
  --data config.hour=500000
```

## Monitoring & Observability

### Prometheus Metrics

Kong exposes metrics at `http://localhost:8001/metrics`:

```prometheus
# Response times
kong_http_requests_total
kong_latency_bucket
kong_upstream_latency_ms

# Rate limiting
kong_rate_limiting_exceeded_total

# Bandwidth
kong_bandwidth_bytes
```

### Grafana Dashboard

Import Kong dashboard:
- Dashboard ID: 7424 (Kong Official)
- Data source: Prometheus pointing to `:8001/metrics`

### Logging

```bash
# Kong access logs (JSON format)
docker logs -f kong-gateway | jq

# Filter by correlation ID
docker logs kong-gateway 2>&1 | grep "correlation_id" | jq
```

## Production Deployment Checklist

### Infrastructure

- [ ] Deploy Kong on Azure Kubernetes Service (AKS) using Kong Ingress Controller
- [ ] Or deploy on Azure Container Instances / App Service
- [ ] Separate Kong database (Azure Database for PostgreSQL)
- [ ] Redis for rate limiting (Azure Cache for Redis)
- [ ] TLS certificates (Let's Encrypt or Azure Key Vault)

### Security

- [ ] Enable HTTPS only (disable HTTP on 8000)
- [ ] Restrict Admin API (8001) to internal network
- [ ] Enable WAF plugin (Enterprise) or ModSecurity
- [ ] API key rotation policy
- [ ] Secrets in Azure Key Vault, not environment variables

### High Availability

- [ ] Deploy Kong in multiple availability zones
- [ ] Database replication (PostgreSQL primary + read replicas)
- [ ] Redis cluster for rate limiting
- [ ] Load balancer (Azure Load Balancer / Application Gateway)
- [ ] Health checks configured

### Monitoring

- [ ] Prometheus → Azure Monitor or Grafana Cloud
- [ ] Application Insights integration
- [ ] Alert on rate limit exceeded
- [ ] Alert on 5xx errors > 1%
- [ ] Alert on latency > 500ms (p95)

### Performance

- [ ] Kong worker processes = CPU cores
- [ ] Database connection pooling tuned
- [ ] Rate limiting using Redis (not local)
- [ ] Response caching for read-heavy endpoints
- [ ] gzip compression enabled

## Kong vs Azure APIM Comparison

| Feature | Kong Gateway | Azure APIM |
|---------|-------------|------------|
| **Cost** | Free (OSS) or $$ (Enterprise) | $$$$ (expensive) |
| **Deployment** | Flexible (Docker, K8s, VMs) | Azure only |
| **Performance** | Very high (NGINX core) | Good |
| **Plugin Ecosystem** | 1000+ plugins | Limited |
| **Learning Curve** | Moderate | Steep |
| **Azure Integration** | Via plugins | Native |
| **Self-Hosted** | Yes | No |
| **Community** | Large, active | Microsoft-driven |

**Decision: Kong wins for this project** because:
✅ Open source option for cost control  
✅ Better performance for high-volume APIs  
✅ Flexibility to deploy anywhere (not locked to Azure)  
✅ Rich plugin ecosystem  
✅ Can upgrade to Enterprise later if needed

## Troubleshooting

### Kong not starting

```bash
# Check logs
docker logs kong-gateway

# Check database connection
docker exec -it kong-gateway kong health

# Reset database
docker-compose down -v
docker-compose up -d kong-db kong-migrations kong
```

### 502 Bad Gateway

```bash
# Check if dq-api is reachable from Kong container
docker exec -it kong-gateway curl http://dq-api:4001/v1/health

# Check service configuration
curl http://localhost:8001/services/dq-api

# Check route configuration
curl http://localhost:8001/routes
```

### Rate limit not working

```bash
# Verify plugin is enabled
curl http://localhost:8001/services/dq-api/plugins | jq '.data[] | select(.name == "rate-limiting")'

# Check rate limit policy
# local = in-memory (dev only)
# redis = production (required for multiple Kong instances)
```

### CORS issues

```bash
# Verify CORS plugin configuration
curl http://localhost:8001/services/dq-api/plugins | jq '.data[] | select(.name == "cors")'

# Test CORS preflight
curl -i -X OPTIONS http://localhost:8000/v1/rules \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: GET"
```

## Next Steps

1. **JWT Authentication**: Configure Keycloak integration
2. **Frontend Update**: Point dq-ui to Kong (http://localhost:8000)
3. **Rate Limiting Tiers**: Define consumer tiers (free/standard/premium)
4. **Monitoring**: Set up Prometheus + Grafana
5. **Production Deploy**: AKS with Kong Ingress Controller

## References

- [Kong Documentation](https://docs.konghq.com/)
- [Kong Plugin Hub](https://docs.konghq.com/hub/)
- [Kong with Kubernetes](https://docs.konghq.com/kubernetes-ingress-controller/)
- [Keycloak Integration](https://docs.konghq.com/hub/kong-inc/openid-connect/)
- [API_GATEWAY_DESIGN.md](./API_GATEWAY_DESIGN.md) - Architecture decisions
- [V1_MIGRATION_BIG_BANG.md](./V1_MIGRATION_BIG_BANG.md) - Endpoint migration
