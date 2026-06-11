# API Gateway Integration Design

## Overview

This document describes how to expose DQ APIs through an API gateway for consumption by multiple applications beyond dq-ui.

**Gateway Selected**: 🎉 **Kong Gateway (Open Source)**  
**Decision Date**: 2026-03-02  
**Implementation Guide**: [KONG_GATEWAY_SETUP.md](./KONG_GATEWAY_SETUP.md)

## Current State vs. Target State

### Current (Direct Access)
```
dq-ui → http://dq-api:4001/api/rules
      → http://dq-api:4001/api/suggestions
```

### Target (Gateway-Mediated)
```
dq-ui        ↘
BI App        → https://api.example.com/dq/v1/rules
ETL Service  ↗    → dq-api:4001/rules (internal)
```

## API Gateway Responsibilities

### 1. Authentication & Authorization
- **User Tokens**: OAuth2/OIDC via Keycloak
  - Scopes: `dq:read`, `dq:write`, `dq:admin`
  - User-facing apps (dq-ui, mobile apps)
  
- **Service Tokens**: Client credentials flow
  - Per-application client ID/secret
  - Machine-to-machine (ETL, batch jobs, integrations)
  - Scopes: `dq:api:read`, `dq:profiling:request`

### 2. Rate Limiting & Quotas
```yaml
# Per consumer limits
consumers:
  dq-ui:
    rate: 1000 req/min
    quota: unlimited
  
  bi-app:
    rate: 500 req/min
    quota: 100000 req/day
  
  etl-service:
    rate: 100 req/min
    quota: 50000 req/day
```

### 3. Request/Response Transformation
- Remove internal implementation details
- Standardize error formats
- Add correlation IDs
- HATEOAS links for discoverability

### 4. Versioning
- URL-based: `/v1/rules`, `/v2/rules`
- Header-based: `Accept: application/vnd.dq.v1+json`
- Deprecation headers for sunset versions

### 5. Policy Enforcement
- IP allowlisting (for sensitive operations)
- Payload size limits
- Request validation against OpenAPI schema
- Response caching where appropriate

## API Redesign for Multi-Consumer Use

### Remove UI-Specific Assumptions

**Before (UI-centric):**
```typescript
// Assumes x-user-id header from UI middleware
@Get('/rules')
async getRules(@Headers('x-user-id') userId: string) {
  // ...
}
```

**After (Consumer-agnostic):**
```typescript
// Use OAuth token claims
@Get('/v1/rules')
async getRules(@Request() req) {
  const userId = req.user.sub // From JWT
  const scopes = req.user.scope
  // ...
}
```

### Add Consistent Pagination

**Standard pattern:**
```typescript
@Get('/v1/rules')
async getRules(
  @Query('page') page: number = 1,
  @Query('pageSize') pageSize: number = 20,
  @Query('sort') sort: string = 'created_at:desc'
) {
  const offset = (page - 1) * pageSize
  // ...
  return {
    data: rules,
    pagination: {
      page,
      pageSize,
      totalCount,
      totalPages: Math.ceil(totalCount / pageSize),
      hasNext: page < Math.ceil(totalCount / pageSize),
      hasPrev: page > 1
    },
    links: {
      self: `/v1/rules?page=${page}`,
      next: hasNext ? `/v1/rules?page=${page + 1}` : null,
      prev: hasPrev ? `/v1/rules?page=${page - 1}` : null
    }
  }
}
```

### Standardized Error Format

**RFC 7807 Problem Details:**
```typescript
// middleware/error-handler.ts
export class ApiError {
  type: string // URI reference identifying the problem type
  title: string // Short human-readable summary
  status: number // HTTP status code
  detail: string // Human-readable explanation
  instance: string // URI reference for this occurrence
  traceId?: string // For debugging
}

// Example
{
  "type": "https://api.example.com/problems/rate-limit-exceeded",
  "title": "Rate Limit Exceeded",
  "status": 429,
  "detail": "You have exceeded your quota of 100000 requests per day",
  "instance": "/v1/rules",
  "traceId": "abc-123-def-456",
  "retryAfter": "2026-03-03T00:00:00Z"
}
```

### Add API Metadata Endpoints

**Service Discovery:**
```typescript
// GET /v1
{
  "version": "1.0.0",
  "links": {
    "rules": "/v1/rules",
    "suggestions": "/v1/suggestions",
    "dataContracts": "/v1/data-contracts",
    "openapi": "/v1/openapi.json",
    "health": "/v1/health"
  }
}

// GET /v1/health
{
  "status": "healthy",
  "version": "1.0.0",
  "checks": {
    "database": "healthy",
    "redis": "healthy",
    "queue": "healthy"
  }
}
```

## Gateway Configuration Examples

### Azure API Management

```xml
<!-- APIM Policy: Validate OAuth2 token -->
<policies>
  <inbound>
    <validate-jwt header-name="Authorization" 
                  failed-validation-httpcode="401"
                  failed-validation-error-message="Unauthorized">
      <openid-config url="https://keycloak.example.com/realms/dq/.well-known/openid-configuration" />
      <required-claims>
        <claim name="scope" match="any">
          <value>dq:read</value>
          <value>dq:write</value>
        </claim>
      </required-claims>
    </validate-jwt>
    
    <!-- Rate limiting per subscription key -->
    <rate-limit-by-key calls="1000" 
                       renewal-period="60" 
                       counter-key="@(context.Subscription.Id)" />
    
    <!-- Add correlation ID -->
    <set-header name="X-Correlation-Id" exists-action="skip">
      <value>@(Guid.NewGuid().ToString())</value>
    </set-header>
    
    <!-- Route to backend -->
    <set-backend-service base-url="http://dq-api:4001" />
    <rewrite-uri template="/rules" copy-unmatched-params="true" />
  </inbound>
  
  <outbound>
    <!-- Add CORS headers -->
    <cors>
      <allowed-origins>
        <origin>https://dq-ui.example.com</origin>
      </allowed-origins>
      <allowed-methods>
        <method>GET</method>
        <method>POST</method>
        <method>PUT</method>
        <method>DELETE</method>
      </allowed-methods>
    </cors>
    
    <!-- Cache GET requests -->
    <cache-store duration="60" />
  </outbound>
</policies>
```

### Kong API Gateway

```yaml
# kong.yml
_format_version: "3.0"

services:
  - name: dq-api
    url: http://dq-api:4001
    routes:
      - name: rules-api
        paths:
          - /v1/rules
        strip_path: false
        plugins:
          - name: jwt
            config:
              claims_to_verify:
                - exp
              key_claim_name: iss
              uri_param_names:
                - jwt
          
          - name: rate-limiting
            config:
              minute: 1000
              hour: 50000
              policy: redis
              redis_host: redis
          
          - name: correlation-id
            config:
              header_name: X-Correlation-Id
              generator: uuid
          
          - name: request-transformer
            config:
              add:
                headers:
                  - X-Gateway: kong
          
          - name: response-transformer
            config:
              remove:
                headers:
                  - X-Internal-Only

consumers:
  - username: dq-ui
    jwt_secrets:
      - key: https://keycloak.example.com/realms/dq
        algorithm: RS256
        rsa_public_key: |
          -----BEGIN PUBLIC KEY-----
          ...
          -----END PUBLIC KEY-----
    plugins:
      - name: rate-limiting
        config:
          minute: 1000

  - username: bi-app
    jwt_secrets:
      - key: bi-app-client-id
        algorithm: HS256
        secret: bi-app-secret
    plugins:
      - name: rate-limiting
        config:
          minute: 500
          day: 100000
```

## Authentication Flows

### 1. User Flow (dq-ui, Web Apps)

```
User Browser
    ↓
1. Redirect to Keycloak login
    ↓
2. User authenticates
    ↓
3. Keycloak issues access_token (JWT)
    ↓
4. Browser → API Gateway (Authorization: Bearer <token>)
    ↓
5. Gateway validates JWT
    ↓
6. Gateway → dq-api with token claims
    ↓
7. Response
```

**Access Token Claims:**
```json
{
  "sub": "user-123",
  "email": "user@example.com",
  "name": "John Doe",
  "scope": "dq:read dq:write",
  "realm_access": {
    "roles": ["analyst", "data-steward"]
  },
  "iss": "https://keycloak.example.com/realms/dq",
  "exp": 1709424000
}
```

### 2. Service-to-Service Flow (ETL, Batch Jobs)

```
ETL Service
    ↓
1. Request token from Keycloak
   POST /realms/dq/protocol/openid-connect/token
   client_id=etl-service
   client_secret=secret
   grant_type=client_credentials
   scope=dq:api:read
    ↓
2. Keycloak issues access_token
    ↓
3. ETL → API Gateway (Authorization: Bearer <token>)
    ↓
4. Gateway validates token & scope
    ↓
5. Gateway → dq-api
    ↓
6. Response
```

**Service Token Claims:**
```json
{
  "sub": "service-account-etl-service",
  "azp": "etl-service",
  "scope": "dq:rules:view dq:rules:test dq:profiling:request",
  "client_id": "etl-service",
  "iss": "https://keycloak.example.com/realms/dq",
  "exp": 1709424000
}
```

**Granular Scope Set (Current Implementation):**
- `dq:rules:view`
- `dq:rules:create`
- `dq:rules:edit`
- `dq:rules:delete`
- `dq:rules:test`
- `dq:rules:approve`
- `dq:rules:activate`
- `dq:users:manage`
- `dq:workspace:manage`
- `dq:config:manage`
- `dq:profiling:request`

## Implementation Roadmap

### Phase 1: Prepare Backend APIs (Week 1-2)

**Tasks:**
- [x] Add `/v1` prefix to all routes
- [x] Implement JWT validation middleware (Bearer + OIDC-compatible claims)
- [ ] Add pagination to all list endpoints
- [x] Standardize error responses (RFC 7807)
- [x] Add `/v1/health` and `/v1` metadata endpoints
- [x] Generate OpenAPI 3.0 spec

**Files to modify:**
- `dq-api/server/app.controller.ts` → move to versioned routes
- `dq-api/server/auth.middleware.ts` → add JWT validation
- Create `dq-api/server/v1/` subdirectory for versioned controllers

### Phase 2: Gateway Setup (Week 2-3)

**Tasks:**
- [x] Deploy API Gateway (Kong, local Docker Compose)
- [x] Configure Keycloak realm/client for JWT bearer flow
- [x] Set up routing rules (external `/v1/*` → internal `/api/*`)
- [x] Apply rate limiting policies
- [x] Configure CORS for dq-ui domain
- [x] Add logging and monitoring (gateway plugin baseline)

### Phase 2b: Authorization Hardening (Current)

**Tasks:**
- [x] Enforce JWT on Kong `/v1/*` route (health/info excluded)
- [x] Add granular scope-based authorization in API middleware
- [x] Align scope mapping with UI roles (`admin`, `data-steward`, `analyst`, `viewer`)
- [ ] Configure production Entra ID/AD OIDC settings

### Phase 3: Consumer Onboarding (Week 3-4)

**Tasks:**
- [ ] Create Keycloak clients for each consumer app
- [ ] Issue credentials and document authentication flow
- [ ] Publish OpenAPI spec at gateway URL
- [ ] Create SDK/client libraries (Python, JavaScript)
- [ ] Write consumer integration guide

### Phase 4: Observability (Week 4+)

**Tasks:**
- [ ] Set up per-consumer metrics (requests, latency, errors)
- [ ] Dashboard showing API usage by consumer
- [ ] Alerting for rate limit breaches
- [ ] SLO tracking (availability, latency p95/p99)
- [ ] Usage billing data (if needed)

## Consumer Integration Example

### Python Client Library

```python
# dq_client.py
import requests
from typing import Optional, Dict, List

class DQClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str):
        self.base_url = base_url
        self.token_url = "https://keycloak.example.com/realms/dq/protocol/openid-connect/token"
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
    
    def _get_token(self):
        """Get access token using client credentials flow"""
        response = requests.post(self.token_url, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": "dq:api:read"
        })
        response.raise_for_status()
        self.access_token = response.json()["access_token"]
    
    def _headers(self) -> Dict[str, str]:
        if not self.access_token:
            self._get_token()
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }
    
    def get_rules(self, page: int = 1, page_size: int = 20) -> Dict:
        """Fetch data quality rules"""
        url = f"{self.base_url}/v1/rules"
        response = requests.get(
            url,
            headers=self._headers(),
            params={"page": page, "pageSize": page_size}
        )
        response.raise_for_status()
        return response.json()
    
    def get_data_contract(self, data_source_id: str) -> Dict:
        """Fetch ODCS contract for a data source"""
        url = f"{self.base_url}/v1/data-contracts/{data_source_id}"
        response = requests.get(
            url,
            headers=self._headers(),
            params={"format": "json"}
        )
        response.raise_for_status()
        return response.json()
    
    def execute_rule(self, rule_id: str, dataset: str) -> Dict:
        """Execute a rule against a dataset"""
        url = f"{self.base_url}/v1/rules/{rule_id}/execute"
        response = requests.post(
            url,
            headers=self._headers(),
            json={"dataset": dataset}
        )
        response.raise_for_status()
        return response.json()

# Usage
client = DQClient(
    base_url="https://api.example.com/dq",
    client_id="etl-service",
    client_secret="secret"
)

# Fetch rules
rules = client.get_rules(page=1, page_size=50)
for rule in rules["data"]:
    print(f"Rule: {rule['name']}")

# Get data contract
contract = client.get_data_contract("demo-azure-payments-sql")
slos = contract["quality"]["slos"]
print(f"Completeness SLO: {slos['completeness']['target']}")
```

## Multi-Tenancy Considerations

If serving multiple organizations:

### 1. Tenant Isolation
```typescript
// Extract tenant from token
@Get('/v1/rules')
async getRules(@Request() req) {
  const tenantId = req.user.tenant_id // From JWT claim
  const rules = await this.rulesService.findByTenant(tenantId)
  return rules
}
```

### 2. Tenant-Specific Rate Limits
```yaml
# Gateway config
tenants:
  - id: tenant-a
    rate_limit: 5000 req/min
  - id: tenant-b
    rate_limit: 1000 req/min
```

### 3. Tenant-Specific Data Contracts
```
/v1/data-contracts?tenantId=tenant-a
```

## Security Checklist

- [ ] TLS/HTTPS only (no HTTP)
- [ ] OAuth2 tokens validated at gateway
- [ ] Scope-based authorization enforced
- [ ] Rate limiting per consumer
- [ ] Input validation (schema validation)
- [ ] SQL injection protection (parameterized queries)
- [ ] CORS configured for known origins
- [ ] Sensitive data redacted in logs
- [ ] API keys rotated regularly
- [ ] Audit logging for all mutations
- [ ] DDoS protection at gateway
- [ ] Secrets in vault (not in code)

## Monitoring & Alerting

**Key Metrics:**
- Request rate per consumer
- Error rate (4xx, 5xx)
- Latency (p50, p95, p99)
- Rate limit hits
- Token validation failures

**Alerts:**
- Error rate > 5%
- Latency p99 > 2s
- Consumer approaching quota
- Repeated 401/403 (potential attack)

## Cost Allocation

Track API usage for chargeback:

```sql
-- Usage tracking table
CREATE TABLE api_usage_log (
  id UUID PRIMARY KEY,
  consumer_id VARCHAR NOT NULL,
  endpoint VARCHAR NOT NULL,
  method VARCHAR NOT NULL,
  status_code INT NOT NULL,
  latency_ms INT NOT NULL,
  request_size_bytes INT,
  response_size_bytes INT,
  timestamp TIMESTAMP NOT NULL
);

-- Monthly usage report
SELECT 
  consumer_id,
  COUNT(*) as total_requests,
  SUM(CASE WHEN status_code >= 200 AND status_code < 300 THEN 1 ELSE 0 END) as successful_requests,
  AVG(latency_ms) as avg_latency_ms,
  SUM(request_size_bytes + response_size_bytes) / 1024 / 1024 as total_data_mb
FROM api_usage_log
WHERE timestamp >= '2026-03-01' AND timestamp < '2026-04-01'
GROUP BY consumer_id;
```

## Migration Path

### Step 1: Dual Mode (No Breaking Changes)
- Deploy gateway alongside direct access
- dq-ui continues direct access initially
- New consumers use gateway

### Step 2: Migrate dq-ui
- Update dq-ui to use gateway URL
- Switch authentication to OAuth2
- Test thoroughly

### Step 3: Deprecate Direct Access
- Mark direct API URLs as deprecated (6 month window)
- Add deprecation headers
- Monitor usage

### Step 4: Gateway Only
- Restrict dq-api to internal network only
- All traffic via gateway
- Remove direct access routes

## References

- [RFC 6749: OAuth 2.0](https://datatracker.ietf.org/doc/html/rfc6749)
- [RFC 7807: Problem Details](https://datatracker.ietf.org/doc/html/rfc7807)
- [OpenAPI 3.0 Specification](https://spec.openapis.org/oas/v3.0.0)
- [ODCS 3.1.0 Specification](https://github.com/bitol-io/open-data-contract-standard)
