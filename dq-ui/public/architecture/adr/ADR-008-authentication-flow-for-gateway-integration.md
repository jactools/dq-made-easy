# ADR-008: Authentication Flow for Gateway Integration

**Status**: Implemented (Keycloak dev wiring), Entra ID pending for production  
**Date**: 2026-03-02

### Context
Current API uses `x-user-id` header (UI-specific). Gateway deployment requires standardized OAuth2/OIDC authentication for multiple consumer types.

### Decision
Implement JWT-based authentication with OIDC integration:

- **Local/dev provider**: Keycloak (already in docker-compose)
- **Production provider**: Microsoft Entra ID / Active Directory

**Flows**:
1. **User Applications** (dq-ui): OAuth2 Authorization Code flow with PKCE
2. **Service-to-Service**: OAuth2 Client Credentials flow
3. **External Partners**: API keys mapped to service accounts

**Implementation Plan**:
- Gateway validates JWTs, extracts claims, forwards as headers
- Backend reads `x-user-id` from JWT `sub` claim (forwarded by gateway)
- Scope-based authorization aligned with UI roles/capabilities

**Current State**:
- Keycloak realm is generated from seeded users/roles and imported in local/dev
- `dq-rules-ui` client emits `roles` and `realm_access.roles` claims in access tokens
- Realm roles are mapped to granular `dq:*` composite roles (create/edit/approve/test/manage)
- Kong `/v1/*` route enforces JWT bearer auth (health/info routes excluded)
- Backend enforces granular scope checks aligned to UI roles and endpoint intent

**Scope Model (Granular)**:
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

**Role Alignment (UI and API)**:
- `viewer` -> `dq:rules:view`
- `analyst` / data-owner roles -> create/edit/test/profiling + view
- `data-steward` -> analyst scopes + approve
- `admin` / cross-admin -> all scopes

**Provider Strategy**:
- Build once against standard OIDC discovery and JWT claims validation in Kong
- Use Keycloak realms for local integration and testing
- Use Microsoft Entra ID (Azure AD) tenant endpoints for production validation

**Migration Path**:
1. Deploy gateway with JWT validation
2. Gateway extracts `sub` claim, forwards as `x-user-id` (backward compatible)
3. Update dq-ui from direct API calls to gateway URLs
4. Implement scope-based authorization in backend
5. Redirect unversioned routes → new versioned routes
6. Deploy external consumer onboarding process

### Consequences
**Positive**:
- Industry-standard auth (OAuth2/OIDC)
- Centralized auth policy at gateway
- Fine-grained access control via scopes
- Existing UI code continues working (header forwarding)

**Negative**:
- Additional network hop for token validation (cached in gateway)
- External IdP availability becomes a dependency (Keycloak locally, Entra ID/AD in production)

---

