# ADR-001: RFC 7807 Problem Details for Error Responses

**Status**: Implemented  
**Date**: 2026-03-02

### Context
The API currently returns inconsistent error formats, making it difficult for consumers to handle errors programmatically. As we prepare for API gateway integration with multiple consumers, standardized error responses are critical.

### Decision
Adopt RFC 7807 Problem Details for HTTP APIs as the standard error response format.

**Implementation**:
- Created `rfc7807.filter.ts` implementing global exception filter
- All errors now return structured responses with:
  - `type`: URI identifying the problem type
  - `title`: Human-readable summary
  - `status`: HTTP status code
  - `detail`: Specific error message
  - `instance`: Request path where error occurred
  - `traceId`: Correlation ID for tracing

**Example response**:
```json
{
  "type": "https://httpstatuses.com/404",
  "title": "Not Found",
  "status": 404,
  "detail": "Rule with ID xyz not found",
  "instance": "/api/rules/xyz",
  "traceId": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Consequences
**Positive**:
- Consistent error handling across all endpoints
- Standard format recognized by API gateways and monitoring tools
- Easier error parsing for API consumers
- Supports additional properties for validation errors

**Negative**:
- Breaking change for existing consumers (migration required)
- Slightly larger response payloads than simple `{ error: "message" }`

---

