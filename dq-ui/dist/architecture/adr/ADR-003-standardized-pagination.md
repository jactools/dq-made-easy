# ADR-003: Standardized Pagination

**Status**: Implemented (utilities only)  
**Date**: 2026-03-02

### Context
List endpoints currently return all results, which doesn't scale. Some endpoints have ad-hoc pagination. Need consistent pagination before gateway deployment.

### Decision
Implement cursor-free offset pagination with standard response envelope.

**Implementation**:
- Created `pagination.ts` utilities
- Standard query parameters: `page` (default 1), `limit` (default 20, max 100)
- Response envelope:
```typescript
{
  data: T[],
  pagination: {
    total: number,
    page: number,
    limit: number,
    totalPages: number,
    hasNext: boolean,
    hasPrevious: boolean
  }
}
```

**Status**: Utilities created, endpoint migration pending.

### Consequences
**Positive**:
- Consistent pagination across all list endpoints
- Clear metadata for building UI pagination controls
- Performance improvement for large datasets
- Gateway can cache paginated responses efficiently

**Negative**:
- Breaking change for endpoints currently returning flat arrays
- Offset pagination doesn't handle concurrent modifications gracefully (accepted tradeoff)

### Future Consideration
For very large datasets (> 100k records), consider cursor-based pagination.

---

