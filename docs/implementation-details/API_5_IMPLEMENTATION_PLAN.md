# API-5: Business Terms Integration - Implementation Plan

**Status**: Starting Phase 1  
**Target**: Catalog connectivity foundation  
**Date**: March 12, 2026

Current-state references:
- [API-5 Business Metadata Integration](../features/current/API_5_METADATA_INTEGRATION.md)
- [Management feature summary](../features/current/MANAGEMENT_FEATURE_SUMMARY.md)

---

## Overview

API-5 integrates an external business catalog (e.g., DataHub, Collibra, Informatica) as the authoritative source for business terms used in rule expressions.

**Key Benefits:**
- Single source of truth for business terms
- Automatic business term resolution with fallback to manual mapping
- Provenance tracking (Catalog vs Manual)
- Resilience during catalog outages (local caching)

## Terminology Proposal

This proposal establishes one canonical vocabulary for the governance UI and its related docs.

### Canonical Terms

| Current label | Proposed label | Meaning |
|---|---|---|
| Alias | Business Term | The business-facing concept used in rule expressions and catalog matching |
| Affected Aliases | Affected Business Terms | Business terms whose meaning, mapping, or resolution changed |
| Alias-level drift | Business Term drift | Drift detected in the business term layer |
| Attribute | Technical Attribute | The governed technical field or column attached to a data-object version |
| Attribute-level drift | Technical Attribute drift | Drift detected in the technical field layer |
| Catalog Suggestions | Business Term suggestions | Catalog-sourced matches that help resolve a business term |
| Manual Override | Manual Mapping | User-provided mapping when catalog resolution is not sufficient |

### UI Wording Rules

- Use **Business Term** when the screen is about the logical meaning of a rule token.
- Use **Technical Attribute** when the screen is about the data-object-version field surface.
- Keep **Catalog** and **Manual** as provenance badges only; do not treat them as the core domain object names.
- Reserve **Data Element** for model documentation only if it is explicitly mapped to the technical attribute layer; do not use it as a replacement for business term labels.

### Governance Screen Copy

- Catalog Drift summary cards should use `Business Term drift` and `Technical Attribute drift`.
- The affected-rule list should say `Affected Business Terms` when describing what changed.
- Audit entries should summarize reviews as `Reviewed N business terms for catalog drift`.
- The mapping modal should use `Map Business Terms to Technical Attributes` as its primary action framing.

### Rollout Rule

- Update the governance UI copy first.
- Keep the underlying payload keys and backend contracts stable until the label change is complete.
- If a screen must show both layers, present the business term first and the technical attribute second.

The formal architecture record for this terminology lives under [architecture/adr](../../architecture/adr) and is indexed from [architecture/ARCHITECTURAL_DECISIONS.md](../../architecture/ARCHITECTURAL_DECISIONS.md).

---

## Phase 1: Catalog Connectivity (Foundation)

**Goal**: Establish communication with external catalog and implement caching layer.

### 1.1 Database Schema

**New Tables:**

```sql
-- Cache for synced business terms from catalog
CREATE TABLE business_terms (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  term_key VARCHAR(255) NOT NULL UNIQUE,
  term_name VARCHAR(255) NOT NULL,
  term_description TEXT,
  data_type VARCHAR(50),
  domain VARCHAR(255),
  glossary_id VARCHAR(255),
  source_system VARCHAR(100) NOT NULL DEFAULT 'catalog',
  last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  catalog_metadata JSONB,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Track alias mappings with source provenance
CREATE TABLE alias_source_metadata (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_version_id VARCHAR(255) NOT NULL,
  alias_name VARCHAR(255) NOT NULL,
  source_type VARCHAR(50) NOT NULL CHECK (source_type IN ('catalog', 'manual')),
  resolved_term_id UUID REFERENCES business_terms(id),
  manual_mapping_id VARCHAR(255),
  resolved_data_type VARCHAR(50),
  sync_timestamp TIMESTAMP,
  is_current BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(rule_version_id, alias_name, is_current)
);

-- Health/status tracking for catalog sync
CREATE TABLE catalog_sync_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sync_type VARCHAR(100),
  status VARCHAR(50) NOT NULL CHECK (status IN ('success', 'partial', 'failed')),
  total_terms_synced INTEGER,
  terms_added INTEGER,
  terms_updated INTEGER,
  terms_removed INTEGER,
  error_message TEXT,
  duration_ms INTEGER,
  started_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_business_terms_term_key ON business_terms(term_key);
CREATE INDEX idx_business_terms_source ON business_terms(source_system);
CREATE INDEX idx_business_terms_created ON business_terms(created_at);
CREATE INDEX idx_alias_source_rule_version ON alias_source_metadata(rule_version_id);
CREATE INDEX idx_alias_source_term ON alias_source_metadata(resolved_term_id);
CREATE INDEX idx_catalog_sync_status ON catalog_sync_log(status);
CREATE INDEX idx_catalog_sync_completed ON catalog_sync_log(completed_at DESC);
```

### 1.2 Backend: Catalog Adapter Interface

**File**: `dq-api/src/services/catalog/CatalogAdapter.ts`

```typescript
export interface BusinessTerm {
  termKey: string
  termName: string
  description?: string
  dataType?: string
  domain?: string
  glossaryId?: string
  metadata?: Record<string, unknown>
}

export interface CatalogConfig {
  provider: string // 'datahub', 'collibra', 'informatica'
  endpoint: string
  apiKey: string
  timeout: number
  retryAttempts: number
}

export interface CatalogSyncResult {
  success: boolean
  termsAdded: number
  termsUpdated: number
  termsRemoved: number
  totalProcessed: number
  errors: string[]
  durationMs: number
}

export abstract class CatalogAdapter {
  abstract connect(): Promise<void>
  abstract disconnect(): Promise<void>
  abstract isHealthy(): Promise<boolean>
  abstract fetchAllTerms(): Promise<BusinessTerm[]>
  abstract fetchTermsByDomain(domain: string): Promise<BusinessTerm[]>
  abstract searchTerms(query: string): Promise<BusinessTerm[]>
}
```

### 1.3 Backend: Concrete Adapter Implementation (DataHub)

**File**: `dq-api/src/services/catalog/DataHubCatalogAdapter.ts`

- Connects to DataHub GraphQL API
- Implements term fetching with pagination
- Filters by entity type (Data Quality Dimension)
- Maps DataHub schema to BusinessTerm interface

### 1.4 Backend: Sync Service

**File**: `dq-api/src/services/catalog/CatalogSyncService.ts`

- Fetch all terms from catalog via adapter
- Upsert into `business_terms` table
- Track old terms for removal detection
- Log sync stats to `catalog_sync_log`
- Handle partial failures gracefully

### 1.5 Backend: API Endpoints

**GET `/api/v1/catalog/health`**
- Returns last sync status, timestamp, term count
- No auth required (for health checks)

**GET `/api/v1/catalog/terms?domain=...&search=...`**
- Fetch cached terms from database
- Requires analyst+ role
- Supports filtering by domain, searching by term name

**POST `/api/v1/catalog/sync`** (admin only)
- Trigger manual sync from catalog
- Returns sync result
- Defaults to nightly schedule via job

**GET `/api/v1/catalog/sync-status`**
- Latest sync log entry with stats
- Useful for UI status display

### 1.6 Frontend: Hook for Business Terms

**File**: `dq-ui/src/hooks/useCatalogTerms.ts`

```typescript
export const useCatalogTerms = () => {
  const [terms, setTerms] = useState<BusinessTerm[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastSync, setLastSync] = useState<Date | null>(null)

  // Fetch all terms on mount
  useEffect(() => {
    fetchTerms()
  }, [])

  const fetchTerms = async (domain?: string) => {
    setLoading(true)
    try {
      const response = await fetch(`/api/v1/catalog/terms?${domain ? `domain=${domain}` : ''}`)
      const data = await response.json()
      setTerms(data.terms)
      setLastSync(new Date(data.lastSynced))
    } catch (err) {
      setError('Failed to load catalog terms')
    } finally {
      setLoading(false)
    }
  }

  const searchTerms = (query: string) => {
    return terms.filter(t => t.termName.toLowerCase().includes(query.toLowerCase()))
  }

  return { terms, loading, error, lastSync, searchTerms, refetch: fetchTerms }
}
```

### 1.7 Frontend: Update Business-Term Mapping Modal

Add business-term suggestions to the mapping section:

```typescript
const catalogTerms = useCatalogTerms()

{aliasExpectations.map(alias => (
  <div key={alias.alias} className="alias-mapping-row">
    <div className="alias-meta">
      <div className="alias-name">{alias.alias}</div>
      <div className="alias-type">Expected: {alias.expected}</div>
    </div>
    
    {/* NEW: Show catalog suggestions */}
    {catalogTerms.loading ? (
      <div className="catalog-suggestions">Loading suggestions...</div>
    ) : (
      <div className="catalog-suggestions">
        <small>Business-term suggestions:</small>
        {catalogTerms.searchTerms(alias.alias).map(term => (
          <button 
            key={term.termKey}
            className="suggestion-badge"
            onClick={() => handleSelectCatalogTerm(alias.alias, term)}
          >
            {term.termName} 
            <span className="source-badge catalog">Catalog</span>
          </button>
        ))}
      </div>
    )}
    
    {/* Existing dropdown for manual override */}
    <RdsSelect value={...} onChange={...} />
  </div>
))}
```

---

## Implementation Checklist - Phase 1

### Backend (dq-api)
- [ ] Create database schema migration (run with db-init)
- [ ] Implement `CatalogAdapter` interface
- [ ] Implement `DataHubCatalogAdapter` (concrete)
- [ ] Implement `CatalogSyncService`
- [ ] Create `/api/v1/catalog/health` endpoint
- [ ] Create `/api/v1/catalog/terms` endpoint
- [ ] Create `/api/v1/catalog/sync` endpoint
- [ ] Create `/api/v1/catalog/sync-status` endpoint
- [ ] Add nightly sync job (via APScheduler or similar)
- [ ] Add error handling and logging

### Frontend (dq-ui)
- [ ] Create `useCatalogTerms` hook
- [ ] Create `useCatalogHealth` hook (for status display)
- [ ] Update `AssignAttributesModal` with suggestions
- [ ] Add CSS for suggestion badges and source indicators
- [ ] Add loading/error states
- [ ] Test with mock data

### Testing
- [ ] Unit tests for CatalogAdapter implementations
- [ ] Integration tests for sync endpoint
- [ ] E2E test: Modal shows suggestions, user can click and apply

### Documentation
- [ ] Catalog provider setup guide (DataHub)
- [ ] Configuration reference (endpoints, API keys)
- [ ] Troubleshooting guide (sync failures, timeouts)

---

## Configuration (Environment Variables)

```env
# dq-api
CATALOG_PROVIDER=datahub
CATALOG_ENDPOINT=http://datahub:8080/api/graphql
CATALOG_API_KEY=your-key-here
CATALOG_SYNC_INTERVAL_HOURS=24
CATALOG_TIMEOUT_SECONDS=30
CATALOG_RETRY_ATTEMPTS=3

# dq-ui
VITE_CATALOG_ENABLED=true
VITE_CATALOG_SYNC_INTERVAL_MINUTES=60
```

---

## Next Steps After Phase 1

- **Phase 2**: Implement business-term resolution precedence logic
- **Phase 3**: Add governance/drift detection
- **Phase 4**: Add UI for override tracking and audit trail

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Catalog unavailable | Fallback to cached terms, show warning badge |
| Large term count (10k+) | Paginate API, implement local filtering |
| Sync takes too long | Implement incremental sync, async processing |
| Terms change frequently | Add versioning, cache invalidation strategy |
| Performance impact on rule validation | Index by term_key, cache in memory layer |

