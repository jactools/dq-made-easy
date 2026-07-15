# ADR-002: Correlation IDs for Distributed Tracing

**Status**: Implemented  
**Date**: 2026-03-02

### Context
Without request IDs, debugging issues across microservices and tracing requests through the system is difficult. This becomes critical when deploying behind an API gateway.

### Decision
Implement correlation ID middleware that:
- Accepts `X-Correlation-ID` header from clients/gateway
- Generates UUID if not provided
- Attaches to all log statements
- Returns in response headers

**Implementation**:
- Created `correlation-id.middleware.ts`
- Applied globally in `app.module.ts`
- Used by RFC 7807 error filter for `traceId` field

### Consequences
**Positive**:
- End-to-end request tracing across services
- Easier debugging and log correlation
- Gateway can inject IDs for unified tracing
- Clients can provide IDs for support inquiries

**Negative**:
- Minor overhead for UUID generation
- Must be adopted by all services for full benefit

---

