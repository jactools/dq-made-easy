# ADR-007: Dual-Standard API Contracts (OpenAPI + ODCS)

**Status**: Implemented  
**Date**: 2026-03-01

### Context
APIs typically document HTTP endpoints (OpenAPI) but not data quality contracts. DQ API serves data quality rules derived from data source schemas. Need both HTTP contracts and data-level contracts.

### Decision
Maintain two complementary standards:
1. **OpenAPI (OAS 3.0)**: HTTP API contracts (endpoints, auth, request/response schemas)
2. **ODCS 3.1.0**: Data quality contracts (schema, SLOs, quality specifications)

**Implementation**:
- `data_sources/contracts/*.odcs.yaml` - ODCS contracts for data sources
- `data-contracts.controller.ts` - API to serve ODCS contracts
- OpenAPI spec links to `/api/data-contracts` for discovery
- See `ODCS_INTEGRATION.md` for full details

**Relationship**:
```
OpenAPI (HTTP layer)
    └─> /api/data-contracts/:id/quality-rules
        └─> Returns ODCS quality spec (SodaCL)
            └─> Maps to DQ rules in database
```

### Consequences
**Positive**:
- Contract-first development for both HTTP and data layers
- Consumers can discover data quality requirements programmatically
- Gateway can validate requests against OpenAPI
 - CI/CD can validate data contracts in pipelines
- Supports auto-generation of DQ rules from ODCS specs

**Negative**:
- Two specs to maintain (automated generation mitigates)
- Requires team familiarity with both standards

---

