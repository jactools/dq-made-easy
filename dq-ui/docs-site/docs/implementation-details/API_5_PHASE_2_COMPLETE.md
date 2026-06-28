# API-5 Phase 2: Alias Resolution & Validation Enrichment - Complete

**Status**: Phase 2 Complete ✅  
**Date**: March 12, 2026  
**Target**: Core logic for alias resolution and provenance tracking

---

## Overview

Phase 2 implements the core logic for resolving business term aliases using a precedence-based system:

1. **Catalog terms** (primary) – Exact match, then fuzzy match
2. **Manual mappings** (fallback) – User-provided attribute mappings
3. **Raw token** (final fallback) – Use alias name as-is
4. **Unresolved** – Couldn't resolve with any method

Each resolution is tracked with provenance for diagnostics.

---

## Key Components Implemented

### 1. Alias Resolver Service (`alias_resolver.py`)

**Purpose**: Resolves aliases to business terms using precedence logic

**Classes**:
- `AliasSourceType` (Enum) – CATALOG, MANUAL, RAW_TOKEN, UNRESOLVED
- `ResolvedAlias` (Dataclass) – Result with term info + confidence
- `AliasResolver` (Service) – Main resolution engine

**Key Methods**:
```python
async def resolve_alias(
    alias_name: str,
    manual_mappings: Optional[Dict[str, str]] = None,
    fuzzy_match: bool = True,
) -> ResolvedAlias
```

**Resolution Precedence**:
1. **Exact Catalog Match**
   - Query: `SELECT * FROM business_terms WHERE term_name ILIKE 'amount'`
   - Confidence: 1.0 (100%)

2. **Fuzzy Catalog Match**
   - String similarity scoring (Levenshtein-like)
   - Threshold: 70% confidence
   - Example: "amt" → "amount" (0.75 confidence)

3. **Manual Mapping**
   - Lookup in user-provided `manual_mappings` dict
   - Confidence: 1.0 if exists, skip if not

4. **Unresolved**
   - No match found in any source
   - Reported in validation results for user action

**Example Usage**:
```python
resolver = AliasResolver(session)

# Single alias
result = await resolver.resolve_alias(
    'transaction_amount',
    manual_mappings={'customer': 'attr-123'},  # Optional
    fuzzy_match=True
)
# Returns: ResolvedAlias(
#   alias_name='transaction_amount',
#   source=CATALOG,
#   resolved_term_name='amount',
#   confidence=0.85
# )

# Batch resolution
results = await resolver.resolve_all_aliases(
    ['amount', 'customer_id', 'date'],
    manual_mappings={...}
)
# Returns dict: {'amount': ResolvedAlias(...), ...}
```

---

### 2. Validation Enricher Service (`validation_enricher.py`)

**Purpose**: Enriches validation results with catalog metadata + provenance

**Classes**:
- `AliasSourceType` – Maps aliases to resolution sources
- `EnrichedAliasDiagnostic` – Diagnostic for single alias
- `EnrichedValidationResult` – Full enriched validation
- `ValidationEnricher` – Main enrichment service

**Key Features**:
- Takes validation result (is_valid, unresolved_aliases, issues)
- Resolves each alias to catalog term (if available)
- Captures provenance: "This alias came from Catalog"
- Enriches with datatype, domain, confidence
- Logs to `alias_source_metadata` table for audit trail

**Example Usage**:
```python
enricher = ValidationEnricher(session)

enriched = await enricher.enrich_validation(
    rule_id='rule-123',
    rule_version_id='v1',
    is_valid=False,
    unresolved_aliases=['amount'],  # Didn't map to attribute
    issues=['Unresolved alias: amount'],
    detected_aliases=['amount', 'customer'],  # All aliases in rule
    manual_alias_mappings={'customer': 'attr-456'},
)

# enriched.alias_diagnostics['amount'].source == 'catalog'
# enriched.alias_diagnostics['customer'].source == 'manual'
# enriched.stats.catalog_sourced_aliases == 1
# enriched.stats.manual_sourced_aliases == 1
```

**Output Format** (for API response):
```json
{
  "ruleId": "rule-123",
  "isValid": false,
  "unresolvedAliases": [],
  "diagnostics": {
    "amount": {
      "resolutionStatus": "resolved",
      "source": "catalog",
      "resolvedTermName": "transaction_amount",
      "resolvedDataType": "DECIMAL",
      "domain": "Transactions",
      "confidence": 1.0,
      "warning": null
    },
    "customer": {
      "resolutionStatus": "resolved",
      "source": "manual",
      "resolvedTermName": "customer_id",
      "confidence": 1.0
    }
  },
  "stats": {
    "catalogSourcedAliases": 1,
    "manualSourcedAliases": 1,
    "unresolvedCount": 0
  }
}
```

---

### 3. Validation Enrichment API Routes

**Endpoint 1: Enrich Rule Validation**
```
POST /api/rulebuilder/v1/rules/{rule_id}/validate/enriched
Authorization: Bearer TOKEN
```

Request:
```json
{
  "ruleVersionId": "v1",
  "expression": "amount > 100",
  "detectedAliases": ["amount"],
  "unresolvedAliases": [],
  "issues": [],
  "manualAliasMappings": {}
}
```

Response: Enriched validation with diagnostics + stats

---

**Endpoint 2: Resolve Aliases**
```
POST /api/rulebuilder/v1/aliases/resolve
Authorization: Bearer TOKEN
```

Request:
```json
{
  "aliases": ["amount", "customer_id", "date"],
  "manualMappings": {"customer_id": "attr-456"}
}
```

Response:
```json
{
  "resolutions": {
    "amount": {
      "source": "catalog",
      "resolvedTermName": "transaction_amount",
      "resolvedDataType": "DECIMAL",
      "domain": "Transactions",
      "confidence": 1.0
    }
  }
}
```

---

**Endpoint 3: Get Alias Provenance History**
```
GET /api/rulebuilder/v1/rules/{rule_id}/{rule_version_id}/alias-provenance
Authorization: Bearer TOKEN
```

Response: Complete provenance audit trail for all aliases in rule version

---

### 4. Frontend: Enriched Validation Hook

**Hook**: `useEnrichedValidation`

```typescript
const { enrichValidation, resolveAliases, loading, error } = useEnrichedValidation()

// Enrich validation result
const result = await enrichValidation({
  ruleId: 'rule-123',
  ruleVersionId: 'v1',
  expression: 'amount > 100',
  detectedAliases: ['amount'],
  unresolvedAliases: [],
  issues: [],
})

// result.diagnostics['amount'].source === 'catalog'
// result.stats.catalogSourcedAliases === 1

// OR: Resolve aliases directly
const resolutions = await resolveAliases(['amount'], {})
// resolutions['amount'].source === 'catalog'
```

---

### 5. Frontend: Diagnostics Display Component

**Component**: `AliasDiagnosticsDisplay`

Displays enriched validation results with:
- **Sections**: Catalog-Sourced, Manual Mappings, Unresolved
- **Badges**: Source indicators (📚 Catalog, ✏️ Manual, ⚠️ Unresolved)
- **Details**: Term name, datatype, domain, confidence score
- **Health Status**: Shows catalog sync status and warnings

**Usage**:
```tsx
<AliasDiagnosticsDisplay
  diagnostics={enrichedResult.diagnostics}
  catalogAvailable={enrichedResult.catalogAvailable}
  lastSync={enrichedResult.lastSync}
/>
```

**Output Examples**:
```
Catalog-Sourced (2)
┌─ amount
│  📚 Catalog
│  transaction_amount (DECIMAL) Domain: Transactions [100% match]
│
└─ customer_id
   📚 Catalog  
   customer_identifier (UUID) Domain: Customer [85% fuzzy match]

Manual Mappings (1)
┌─ status
   ✏️ Manual
   status_code

Unresolved (1)
┌─ date_range ⚠️ Unresolved
   This alias could not be resolved. Please check the spelling or add a manual mapping.
```

---

## Database Changes

### New Table Entry: `alias_source_metadata`

Records provenance for each alias resolution:
```sql
INSERT INTO alias_source_metadata (
  rule_version_id,
  alias_name,
  source_type,           -- 'catalog' or 'manual'
  resolved_term_id,      -- UUID of business_term
  resolved_data_type,
  sync_timestamp,
  is_current             -- Latest resolution
) VALUES (...)
```

### Query Example: Get All Catalog-Sourced Aliases for a Rule Version
```sql
SELECT alias_name, resolved_term_id, resolved_data_type
FROM alias_source_metadata
WHERE rule_version_id = 'v1'
  AND source_type = 'catalog'
  AND is_current = TRUE
```

---

## Workflow: Using Phase 2 in Rules

### 1. User Creates Rule with Aliases

```
Expression: "transaction_amount > 100 AND customer_status = 'active'"
Detected Aliases: ["transaction_amount", "customer_status"]
```

### 2. System Validates

```
UnresolvedAliases: []     (All mapped to attributes)
Issues: []                (No problems)
```

### 3. System Enriches Validation

```
REST Call: POST /api/rulebuilder/v1/rules/rule-123/validate/enriched

(Routing note: internal FastAPI is `/api/rulebuilder/v1/...`; gateway/public is `/rulebuilder/v1/...`.)

Server:
  1. Resolves "transaction_amount"
     → Catalog exact match: "transaction_amount" (100% confidence)
  2. Resolves "customer_status"
     → Fuzzy match: "status" in catalog (85% confidence)
  3. Logs provenance to alias_source_metadata
  4. Returns enriched result

Response:
  {
    "diagnostics": {
      "transaction_amount": {
        "source": "catalog",
        "resolvedTermName": "transaction_amount",
        "confidence": 1.0
      },
      "customer_status": {
        "source": "catalog",
        "resolvedTermName": "status",
        "confidence": 0.85,
        "warning": "fuzzy_match"
      }
    },
    "stats": {
      "catalogSourcedAliases": 2,
      "manualSourcedAliases": 0
    }
  }
```

### 4. UI Displays Results

Shows AliasDiagnosticsDisplay with:
- ✅ Both aliases resolved from catalog
- 📚 Badges showing source
- Confidence warnings for fuzzy match
- Last sync time

---

## Performance Considerations

### Fuzzy Matching Performance

**Current Implementation**: Levenshtein-like similarity (O(n*m) complexity)

**For production (10k+ terms)**:
- Option 1: Use PostgreSQL trigram index (`pg_trgm`)
  ```sql
  CREATE INDEX idx_business_terms_trgm ON business_terms 
  USING gin (term_name gin_trgm_ops);
  ```
  
- Option 2: Elasticsearch for fuzzy search

- Option 3: Cache frequently resolved aliases in memory

### Batch Resolution Performance

- Fetches all terms once (max 1000 from DB)
- Fuzzy match all at once (faster than individual queries)
- Suitable for typical rule size (&lt;50 aliases)

### API Caching

- Could cache resolution results per rule version
- Invalidate on catalog sync or manual mapping change
- Reduces repeated queries

---

## Error Handling & Fallbacks

### Scenario 1: Catalog Unavailable

```
⚠️ Catalog temporarily unavailable - using cached data

- Fuzzy matching disabled
- Only exact matches used
- Manual mappings still work
- User sees warning in diagnostics
```

### Scenario 2: Sync Failure

```
Catalog sync failed at 2:30 AM
- Previous sync data still used (cached)
- Resolution works with old metadata
- Admin sees warning in health endpoint
```

### Scenario 3: Unresolved Alias

```
alias_name="quarterly_revenue"
source: "unresolved"
suggestion: "Did you mean 'quarterly_total_revenue'?"
```

---

## Testing

### Unit Tests

```python
# Test exact match
resolved = await resolver.resolve_alias('amount')
assert resolved.source == AliasSourceType.CATALOG
assert resolved.confidence == 1.0

# Test fuzzy match
resolved = await resolver.resolve_alias('amt')
assert resolved.source == AliasSourceType.CATALOG
assert resolved.confidence > 0.7

# Test manual mapping
resolved = await resolver.resolve_alias(
    'status',
    manual_mappings={'status': 'attr-123'}
)
assert resolved.source == AliasSourceType.MANUAL

# Test unresolved
resolved = await resolver.resolve_alias('zzzzzzz')
assert resolved.source == AliasSourceType.UNRESOLVED
```

### Integration Tests

- Mock DataHub with test terms
- Validate end-to-end enrichment
- Verify provenance logging

### E2E Tests

- UI: Show diagnostics with correct badges
- UI: Fuzzy match warnings display correctly
- UI: Unresolved sections guide users

---

## Next Steps (Phase 3+)

### Phase 3: UI Integration
- [ ] Update AssignAttributesModal with catalog suggestions
- [ ] Add source badges to alias dropdowns
- [ ] Implement click-to-apply suggestions
- [ ] Show enriched validation in validation results

### Phase 4: Governance
- [ ] Detect when catalog definitions change (drift)
- [ ] Notify users of affected rules
- [ ] Batch revalidation for impacted rules
- [ ] Rule version snapshots of resolved aliases

---

## Configuration

No new environment variables needed for Phase 2.
Inherits from Phase 1:
- `CATALOG_PROVIDER`
- `CATALOG_ENDPOINT`
- `CATALOG_API_KEY`

---

## Files Created/Modified

| File | Type | Changes |
|------|------|---------|
| `alias_resolver.py` | NEW | Main resolution engine with precedence logic |
| `validation_enricher.py` | NEW | Validation enrichment + provenance logging |
| `validation_enrichment_routes.py` | NEW | 3 API endpoints |
| `useEnrichedValidation.ts` | NEW | React hook for enriched validation |
| `AliasDiagnosticsDisplay.tsx` | NEW | UI component for diagnostics display |
| `AliasDiagnosticsDisplay.css` | NEW | Styling for diagnostics |
| `catalog/__init__.py` | MODIFIED | Export new services |

---

## Summary

**Phase 2 delivers:**
- ✅ Precedence-based alias resolution (catalog → manual → unresolved)
- ✅ Fuzzy matching with confidence scoring
- ✅ Provenance tracking (know where each alias came from)
- ✅ 3 new API endpoints for validation + alias resolution
- ✅ Frontend hook for enriched validation data
- ✅ UI component to display diagnostics with source badges
- ✅ Audit trail in database for governance

**Key Benefits:**
1. **Transparency** – Users see where aliases were resolved from
2. **Flexibility** – Works with catalog, manual mappings, or unresolved
3. **Resilience** – Falls back gracefully if catalog unavailable
4. **Auditability** – Complete provenance trail for compliance

