# ADR-004: OpenAPI 3.0 Specification with Swagger

**Status**: Implemented  
**Date**: 2026-03-02

### Context
No machine-readable API documentation exists. Gateway integration requires OpenAPI spec for route configuration and client SDK generation.

### Decision
Generate OpenAPI 3.0 specification using Swagger-compatible tooling.

**Implementation**:
- Enabled OpenAPI schema generation in the API runtime
- Exposed interactive docs and JSON schema export endpoints
- Documented authentication (Bearer JWT)
- Linked to ODCS contracts

**Spec location**: `http://localhost:4010/docs`  
**JSON export**: `http://localhost:4010/openapi.json`

### Consequences
**Positive**:
- Self-documenting API for consumers
- Gateway can import routes automatically from spec
- Enables client SDK generation (TypeScript, Python, Go, etc.)
- Interactive testing via Swagger UI
- Specification-first development workflow

**Negative**:
- Swagger UI exposes API structure (acceptable for authenticated gateway)

### Next Steps
- Configure gateway to import OpenAPI spec
- Generate client SDK for dq-ui

---

