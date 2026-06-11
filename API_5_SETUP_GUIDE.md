# API-5: Business Terms & Aliases Integration - Setup Guide

**Status**: Phase 1 Complete (Catalog Connectivity)  
**Last Updated**: March 12, 2026

---

## Quick Start

### 1. Database Setup

Run the migration to create catalog tables:

```bash
# Automatic migration on startup (recommended)
# Or manually:
psql dq -U postgres < dq-db/sql/migrations/API_5_001_business_terms_catalog.sql
```

**Tables Created:**
- `business_terms` – Cache of synced catalog terms
- `alias_source_metadata` – Provenance tracking for alias resolution
- `catalog_sync_log` – Audit trail of sync operations

### 2. Environment Configuration

Set these variables in your `.env` or deployment config:

```bash
# Backend (dq-api)
CATALOG_PROVIDER=datahub              # 'datahub', 'openmetadata', 'collibra', 'informatica'
CATALOG_ENDPOINT=http://datahub:8080  # Catalog API endpoint
CATALOG_API_KEY=your-auth-token       # Authentication token
CATALOG_TIMEOUT_SECONDS=30            # Request timeout
CATALOG_RETRY_ATTEMPTS=3              # Max retries on failure
CATALOG_BATCH_SIZE=100                # Terms per request
CATALOG_SYNC_INTERVAL_HOURS=24        # Nightly sync schedule

# Frontend (dq-ui)
VITE_CATALOG_ENABLED=true
VITE_CATALOG_SYNC_INTERVAL_MINUTES=60  # Show sync status refresh interval
```

### 3. DataHub Integration (Example)

If using DataHub as your catalog:

**Step 1: Get DataHub API Key**
```bash
# In DataHub UI: Settings → API → Create Personal Access Token
# Copy the token
```

**Step 2: Configure Connection**
```bash
CATALOG_PROVIDER=datahub
CATALOG_ENDPOINT=https://your-datahub-instance.com
CATALOG_API_KEY=urn:li:accessToken:YOUR_TOKEN_HERE
```

**Step 3: Verify Connection**
```bash
curl -X GET http://localhost:4001/api/v1/catalog/health \
  -H "Authorization: Bearer YOUR_APP_TOKEN"
```

### 4. OpenMetadata Integration (Example)

If using OpenMetadata as your catalog:

```bash
CATALOG_PROVIDER=openmetadata
CATALOG_ENDPOINT=https://your-openmetadata-instance.com
CATALOG_API_KEY=YOUR_OPENMETADATA_JWT_OR_API_TOKEN
```

The alias/business-term sync reads glossary terms from OpenMetadata and stores
them in the local cache used by alias resolution, drift detection, and
revalidation.

Expected response:
```json
{
  "status": "healthy",
  "last_sync": "2026-03-12T15:30:00Z",
  "term_count": 2547,
  "duration_ms": 3400
}
```

### 4. Trigger Initial Sync

**Option A: Manual (One-time)**
```bash
curl -X POST http://localhost:4001/api/v1/catalog/sync \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json"
```

Response:
```json
{
  "success": true,
  "termsAdded": 2547,
  "termsUpdated": 0,
  "termsRemoved": 0,
  "totalProcessed": 2547,
  "durationMs": 3400
}
```

**Option B: Automatic (Scheduled)**
The system runs a nightly sync job at 2 AM by default. Configure via:
```bash
CATALOG_SYNC_SCHEDULE=0 2 * * *  # Cron expression
```

---

## API Endpoints

### GET `/api/v1/catalog/health`

Check catalog health and sync status. **No auth required** (for health checks).

```bash
curl http://localhost:4001/api/v1/catalog/health
```

Response:
```json
{
  "status": "healthy",           // healthy | degraded | unknown | error
  "last_sync": "2026-03-12T15:30:00Z",
  "last_sync_status": "success", // success | partial | failed
  "term_count": 2547,
  "duration_ms": 3400,
  "sync_errors": null
}
```

### GET `/api/v1/catalog/terms?domain=...&search=...`

Fetch cached business terms. **Requires**: analyst+ role

Parameters:
- `domain` (optional): Filter by domain/glossary
- `search` (optional): Search term name or description
- Returns max 500 terms

```bash
curl "http://localhost:4001/api/v1/catalog/terms?search=customer&domain=CRM" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "terms": [
    {
      "termKey": "urn:li:dataset:...",
      "termName": "customer_id",
      "description": "Unique customer identifier",
      "dataType": "UUID",
      "domain": "CRM",
      "glossaryId": "urn:li:glossary:crm",
      "lastSynced": "2026-03-12T15:30:00Z"
    }
  ],
  "count": 1,
  "lastSynced": "2026-03-12T15:45:00Z"
}
```

### POST `/api/v1/catalog/sync` (Admin Only)

Manually trigger a full sync from catalog.

```bash
curl -X POST http://localhost:4001/api/v1/catalog/sync \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json"
```

Response:
```json
{
  "success": true,
  "termsAdded": 245,
  "termsUpdated": 156,
  "termsRemoved": 12,
  "totalProcessed": 413,
  "durationMs": 5200,
  "errors": null
}
```

### GET `/api/v1/catalog/sync-status`

Get detailed sync history. **Requires**: analyst+ role

```bash
curl http://localhost:4001/api/v1/catalog/sync-status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "latest": {
    "startedAt": "2026-03-12T15:25:00Z",
    "completedAt": "2026-03-12T15:30:00Z",
    "status": "success",
    "totalTermsSynced": 2547,
    "termsAdded": 100,
    "termsUpdated": 50,
    "termsRemoved": 5,
    "durationMs": 3400,
    "errorMessage": null
  },
  "recentHistory": [
    { /* ... previous syncs ... */ }
  ]
}
```

---

## Frontend Integration

### Using Catalog Terms in Rules

When creating/editing a rule with aliases:

1. **Open Assign Attributes Modal**
   - Modal now shows "Catalog Suggestions" below each alias
   - Suggestions auto-appear if catalog is healthy

2. **Browse Suggestions**
   ```
   alias: "amount"
   Catalog suggestions:
   [transaction_amount (Catalog)]  [order_value (Catalog)]
   ```

3. **Click to Apply**
   - Clicking a suggestion auto-fills the alias mapping dropdown
   - Shows source badge: "Catalog" vs "Manual"

4. **Manual Override**
   - Can still select any attribute from dropdown
   - Manual overrides tracked in `alias_source_metadata`

### Using Hooks in Components

```typescript
import { useCatalogTerms } from '../hooks/useCatalogTerms'
import { useCatalogHealth } from '../hooks/useCatalogHealth'

export function MyComponent() {
  const { terms, loading, searchTerms } = useCatalogTerms()
  const { health, isAvailable } = useCatalogHealth()

  if (!isAvailable) {
    return <div className="warning">Catalog temporarily unavailable</div>
  }

  const matches = searchTerms('customer')
  
  return (
    <div>
      {matches.map(term => (
        <div key={term.termKey}>{term.termName}</div>
      ))}
    </div>
  )
}
```

---

## Troubleshooting

### "Catalog health check failed"

**Symptoms**: Health endpoint returns `status: error`

**Solutions**:
1. Check network connectivity to catalog endpoint
2. Verify `CATALOG_ENDPOINT` is correct and accessible
3. Verify `CATALOG_API_KEY` is valid and not expired
4. Check catalog logs for auth failures
5. Run: `curl http://YOUR_CATALOG_ENDPOINT/api/health`

### "Sync completed but 0 terms synced"

**Causes**:
- Catalog has no terms tagged with `data_quality_dimension`
- Query in adapter doesn't match your catalog's term types
- Adapter implementation needs filtering adjustment

**Fix**: Check DataHub (or other catalog) for what tags/types exist:
```bash
# DataHub GraphQL query
query {
  search(input: { type: DATASET, query: "*" }) {
    entities { urn }
  }
}
```

### "Terms appear in health but not in modal"

**Causes**:
- Frontend app-config not reloaded after environment change
- User hasn't opted into preview features
- Feature flag `feature_aliases_business_terms` disabled in admin settings

**Fix**:
1. Hard refresh browser (Cmd+Shift+R / Ctrl+Shift+R)
2. Check Settings → Preview Features: enabled?
3. Check Settings → Application (admin): `feature_aliases_business_terms = true`

### "Sync timeout or very slow"

**Solutions**:
- Increase `CATALOG_TIMEOUT_SECONDS` (e.g., 60)
- Reduce `CATALOG_BATCH_SIZE` (e.g., 50)
- Check catalog server load/performance
- Check network latency to catalog

### Missing catalog suggestions in modal

**Checklist**:
- [ ] Sync has completed at least once (`catalog_sync_log` table has entries)
- [ ] Health endpoint returns `status: healthy` or `degraded`
- [ ] `business_terms` table has data
- [ ] User has analyst+ role
- [ ] Feature flag enabled for user (preview features opted in)
- [ ] Modal refreshed after sync (hard refresh page)

---

## Performance Considerations

### Database Indexes

The migration creates indexes on:
- `term_key` (unique) – Fast lookup by ID
- `source_system` – Filter by catalog vs manual
- `domain` – Filter by business domain
- `created_at` – Sort by recency

Add custom indexes if filtering on other columns frequently.

### Sync Performance

**Sync duration depends on:**
- Catalog response time (network + catalog performance)
- Number of terms synced
- Database write throughput

**To improve:**
- Increase `CATALOG_BATCH_SIZE` (with caution)
- Run sync during off-hours
- Use incremental sync for specific domains

### Frontend Loading

Terms are fetched once on modal open, then cached in component state.

**To optimize:**
- Use fuzzy search (client-side) to filter large term lists
- Implement virtual scrolling if term count > 10k
- Add debouncing to search input

---

## Next Steps (Phase 2+)

- [ ] Alias resolution precedence logic (catalog → manual → raw token)
- [ ] Validation enrichment with catalog datatypes
- [ ] Provenance diagnostics UI (shows "Catalog" vs "Manual" badges)
- [ ] Drift detection for changed catalog definitions
- [ ] Rule version snapshots of resolved aliases
- [ ] Batch revalidation for affected rules

---

## Support

For questions or issues:
1. Check Troubleshooting section above
2. Review logs: `dq-api` and `dq-ui` for errors
3. Verify `catalog_sync_log` table for sync status
4. Check business_terms table row count and sample rows

