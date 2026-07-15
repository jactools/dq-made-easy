# ADR-006: Versioned API Routes

**Status**: ✅ Implemented (Big Bang Migration)  
**Date**: 2026-03-02

### Context
Current API has no versioning. Breaking changes affect all consumers immediately. Gateway pattern requires explicit versioning strategy.

### Decision
Adopt URL path versioning: `/v1/*`, `/v2/*`, etc.

**Implementation Approach**: Big Bang Migration (Option C)
- All endpoints migrated to `/v1/*` simultaneously
- No backward compatibility or gradual migration period
- Clean break requiring coordinated deployment

**Rationale**:
- Clear version in URL (visible in logs, easy to route)
- Simpler than header-based versioning for API gateway configuration
- Industry standard (Stripe, Twilio, AWS, etc.)
- Small consumer base enables coordinated deployment

**Current State**: ✅ **Fully Implemented**
- All endpoints now at `/v1/*`
- Controllers updated: AppController, SuggestionsController, DataContractsController
- Health endpoints remain at `/v1/health`, `/v1/ready`, `/v1/live`, `/v1/info`
- Complete OpenAPI documentation with @Api* decorators

**See**: [V1_MIGRATION_BIG_BANG.md](./V1_MIGRATION_BIG_BANG.md) for complete endpoint mapping and migration guide.

### Consequences
**Positive**:
- Clean, unambiguous versioning from day one
- No technical debt from dual-path support
- Gateway can enforce different policies per version
- Clear foundation for future v2 when needed
- Forces consistent adoption across all consumers

**Negative**:
- Breaking change for all consumers (requires immediate action)
- Requires coordinated frontend deployment
- No gradual rollout safety net

**Breaking Changes**:
- Frontend (dq-ui) must update all API calls to use `/v1/` prefix
- External integrations must update URLs immediately
- See migration guide for sed script to update frontend code

### Deprecation Policy
- Minimum 6 months notice before version removal
- Security fixes backported to N-1 version
- Documentation of breaking changes in release notes

---

