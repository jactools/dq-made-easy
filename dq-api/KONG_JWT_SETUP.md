# Kong JWT Authentication Setup Guide

## Overview
This guide configures Kong Gateway to validate JWT tokens issued by Keycloak and forward authenticated requests to the DQ API with user context.

## Architecture
```
Frontend (localhost:5173)
    ↓
  Kong Gateway (localhost:9111) [JWT Validation]
    ↓
  Keycloak (localhost:8080) [Token Issuer & Validation]
    ↓
  DQ API (localhost:4001) [Protected Endpoints]
```

## Prerequisites
- Kong running on port 9111
- Keycloak running on port 8080 with dqprototype realm
- dq-api service configured in Kong (ID: 771932cc-d885-4aed-85fe-6e1737343268)

## Step 1: Configure Keycloak OIDC Client for Kong

### 1a. Get Keycloak Admin Token
```bash
TOKEN=$(curl -s -X POST http://localhost:8080/realms/master/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=admin-cli&username=admin&password=admin&grant_type=password" | jq -r '.access_token')
```

### 1b. Create Kong OIDC Client in Keycloak
```bash
curl -X POST http://localhost:8080/admin/realms/dqprototype/clients \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "clientId": "kong-gateway",
    "name": "Kong Gateway",
    "enabled": true,
    "clientAuthenticatorType": "client-secret",
    "publicClient": false,
    "protocol": "openid-connect",
    "redirectUris": ["http://localhost:9111"],
    "webOrigins": ["http://localhost:9111", "http://localhost:5173"],
    "directAccessGrantsEnabled": true,
    "standardFlowEnabled": true,
    "implicitFlowEnabled": false,
    "serviceAccountsEnabled": true
  }'
```

### 1c. Get Kong Client Secret
```bash
KONG_CLIENT_ID=$(curl -s "http://localhost:8080/admin/realms/dqprototype/clients?clientId=kong-gateway" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.[0].id')

curl -s "http://localhost:8080/admin/realms/dqprototype/clients/${KONG_CLIENT_ID}/client-secret" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.value'
```

## Step 2: Install Kong OIDC Plugin

The Kong OIDC plugin enables OIDC-based authentication with token validation:

```bash
# Enter Kong container
docker-compose exec kong /bin/sh

# Install OIDC plugin via luarocks
luarocks install kong-oidc

# Exit container
exit

# Restart Kong container
docker-compose restart kong
```

## Step 3: Configure Kong OIDC Plugin

### 3a. Create OIDC Plugin on dq-api Service
```bash
curl -X POST http://localhost:8001/plugins \
  -H "Content-Type: application/json" \
  -d '{
    "name": "oidc",
    "service": {
      "id": "771932cc-d885-4aed-85fe-6e1737343268"
    },
    "config": {
      "client_id": "kong-gateway",
      "client_secret": "YOUR_CLIENT_SECRET_HERE",
      "discovery": "http://localhost:8080/realms/dqprototype/.well-known/openid-configuration",
      "redirect_uri_path": "/v1/auth/callback",
      "scope": "openid email profile",
      "response_type": "code",
      "ssl_verify": "no"
    }
  }'
```

### 3b. Configure OIDC Routes (Optional - Authentication Filter)
```bash
# Apply OIDC to specific routes only
curl -X POST http://localhost:8001/plugins \
  -H "Content-Type: application/json" \
  -d '{
    "name": "oidc",
    "route": {
      "id": "a2755d6f-977d-47b6-a785-99ee42055f66"
    },
    "config": {
      "client_id": "kong-gateway",
      "client_secret": "YOUR_CLIENT_SECRET",
      "discovery": "http://localhost:8080/realms/dqprototype/.well-known/openid-configuration",
      "scope": "openid email profile",
      "ssl_verify": "no"
    }
  }'
```

## Step 4: Test JWT Token Flow

### 4a. Get Test User Token from Keycloak
```bash
# Request token using Resource Owner Password grant
TOKEN=$(curl -s -X POST http://localhost:8080/realms/dqprototype/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=kong-gateway" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "username=admin@dqprototype" \
  -d "password=password" \
  -d "grant_type=password" | jq -r '.access_token')

echo "Token: $TOKEN"
```

### 4b. Decode and Inspect Token
```bash
# Decode JWT (base64)
echo "$TOKEN" | cut -d'.' -f2 | base64 -d | jq .
```

### 4c. Make Request Through Kong with JWT
```bash
# Test API endpoint with JWT token
curl -X GET http://localhost:9111/v1/rules \
  -H "Authorization: Bearer $TOKEN"
```

### 4d. Verify Headers Forwarded to API
```bash
# Check what headers Kong forwards to the API
# The 'sub' claim should be available as a header or context variable
curl -X GET http://localhost:4010/api/v1/health \
  -H "Authorization: Bearer $TOKEN"
```

## Step 5: Configure API to Use JWT Claims

### 5a. Extract User Context from JWT in API
In the FastAPI API, decode claims from the bearer token in a request dependency or middleware:

```python
# app/core/auth_context.py
from typing import Any

import jwt
from fastapi import Request


def extract_user_context(request: Request) -> dict[str, Any] | None:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    # Kong validates signature/issuer; API decodes claims for context.
    claims = jwt.decode(token, options={"verify_signature": False})
    return {
        "id": claims.get("sub"),
        "email": claims.get("email"),
        "roles": ((claims.get("resource_access") or {}).get("kong-gateway") or {}).get("roles", []),
        "username": claims.get("preferred_username"),
    }
```

### 5b. Register Middleware in FastAPI App
```python
# app/main.py
from fastapi import FastAPI

from app.middleware.auth_compatibility import AuthCompatibilityMiddleware

app = FastAPI()
app.add_middleware(AuthCompatibilityMiddleware)
```

## Step 6: Frontend Integration

### 6a. Update Frontend to Include JWT Token
```typescript
// src/contexts/SettingsContext.tsx
export const fetchWithAuth = async (url: string, options: RequestInit = {}) => {
  const token = localStorage.getItem('token');
  
  const headers = {
    ...options.headers,
    'Authorization': token ? `Bearer ${token}` : undefined,
  };
  
  return fetch(url, {
    ...options,
    headers: Object.fromEntries(Object.entries(headers).filter(([_, v]) => v))
  });
};
```

### 6b. Add Keycloak Login Integration
```typescript
// src/hooks/useAuth.ts
export const useAuth = () => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  
  const login = async (username: string, password: string) => {
    const response = await fetch('http://localhost:8080/realms/dqprototype/protocol/openid-connect/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        client_id: 'dq-rules-ui',
        username,
        password,
        grant_type: 'password'
      })
    });
    
    const { access_token } = await response.json();
    localStorage.setItem('token', access_token);
    setIsAuthenticated(true);
  };
  
  return { isAuthenticated, login };
};
```

## Step 7: JWT Signing and Validation

### 7a. Realm Public Key (for token validation)
Kong and the API should use Keycloak's public key for JWT validation:

```bash
# Get realm's public key
curl -s http://localhost:8080/realms/dqprototype/protocol/openid-connect/certs | jq '.keys[0]'
```

### 7b. Add Public Key to Kong JWT Config
```bash
# Option: If using Kong's native JWT validation (without OIDC)
REALM_KEY=$(curl -s http://localhost:8080/realms/dqprototype/protocol/openid-connect/certs | jq -r '.keys[0].x5c[0]')

curl -X POST http://localhost:8001/jwks \
  -H "Content-Type: application/json" \
  -d "{
    \"rsa_public_key\": \"-----BEGIN CERTIFICATE-----\n${REALM_KEY}\n-----END CERTIFICATE-----\"
  }"
```

## Troubleshooting

### Issue: Kong returns 401 Unauthorized
- Verify token is properly formatted: `Authorization: Bearer <token>`
- Check token expiration: `echo "<token>" | cut -d'.' -f2 | base64 -d | jq '.exp'`
- Confirm OIDC plugin is enabled on the service or route

### Issue: "no Route matched"
- Ensure route methods include OPTIONS for CORS preflight
- Verify route path matching (v1 vs v1/*)

### Issue: Token claims not available to API
- Check Kong plugin forwarding headers
- Add custom headers in request-transformer plugin to forward user context

### Issue: OIDC plugin not found
- Confirm plugin installed: `docker-compose exec kong luarocks list | grep oidc`
- Check Kong logs: `docker-compose logs kong`

## Security Considerations

1. **Token Expiration**: Set reasonable expiration times in Keycloak (default 5 minutes)
2. **HTTPS**: Use HTTPS in production instead of HTTP
3. **CORS**: Configure CORS appropriately for your frontend domain
4. **Rate Limiting**: Keep rate-limiting enabled on Kong
5. **Token Storage**: Never store tokens in localStorage in production; use httpOnly cookies

## References

- [Kong OIDC Plugin](https://github.com/nokia/kong-oidc)
- [Kong JWT Plugin](https://docs.konghq.com/hub/kong-inc/jwt/)
- [Keycloak Protocol Documentation](https://www.keycloak.org/docs/latest/securing_apps/)
- [RFC 7519 - JWT](https://tools.ietf.org/html/rfc7519)

## Next Steps

1. Open Keycloak admin console at http://localhost:8080/admin
2. Navigate to dqprototype realm → Clients → kong-gateway
3. Get the client secret from "Client Secret" tab
4. Run Kong OIDC plugin installation
5. Configure OIDC plugin with client credentials
6. Test token flow using curl commands above
7. Integrate JWT into frontend application
