# Technical Documentation — For Developers & Admins

> **For end-user documentation:** See [RELEASE_NOTES_USER.md](./RELEASE_NOTES_USER.md) for features and usage instructions.

## Changelog

### v0.11.5 (July 9, 2026)

- **SEC-5 end-to-end TLS enforcement (W6–W7):** The local edge now uses SNI/TCP passthrough (`ssl_preread on`) for all browser-facing hostnames, eliminating the double-termination path that previously ran through `zammad-https`. The Zammad Rails server and WebSocket server both own native TLS listeners with certificates that include the user-facing SNI hostname as a SAN.
- **TLS-verified healthchecks:** `zammad-railsserver` and `zammad-websocket` gained `healthcheck` blocks that verify the CA bundle on every probe rather than just testing connectivity.
- **Transparent proxy routing:** `dq-edge` LOCAL mode SNI map updated to route support traffic directly to `zammad-railsserver:3000`; `zammad-https` retained as an optional backwards-compat container for PUBLIC mode only (see ARCH-EXC-0011).
- **Certificate SAN expansion:** `scripts/create_certs.sh` now injects `EDGE_LOCAL_SUPPORT_HOST` into the Zammad backend certificate SANs so the edge can pass through encrypted traffic without a certificate mismatch.
- **Validation suite:** `scripts/validate_tls_backend_direct_routing.sh` (10 tests) and `scripts/validate_tls_service_paths.sh` (12 tests) verify no-proxy-termination compliance; all seven SEC-5 acceptance criteria confirmed met.
- **Cutover runbook and observability guide:** `docs/implementation-details/SEC_5_W7_CUTOVER_RUNBOOK.md` documents the per-service migration sequence, rollback procedure, and incident response. `docs/implementation-details/SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md` documents Prometheus alerts, Loki query patterns, and manual TLS troubleshooting steps.
- **Exception registry updated:** ARCH-EXC-0010 (Airflow HTTP listener) and ARCH-EXC-0011 (zammad-https deprecation) added with owner and retirement dates.
- **Agent guidance:** `.github/copilot/07-tls-transport-enforcement.md` captures the no-HTTP rule, edge routing model, certificate generation constraints, and exception registry so future contributors preserve the TLS contract.
- **Versioning and docs sync:** tracked manifest components `Infrastructure` and `Testautomation` bumped to `0.11.5`; release and deployment docs advanced to the `0.11.5` release line.

### v0.10.5 (May 22, 2026)

- **Public documentation portal:** The UI build now publishes a Docusaurus public docs portal at `/docs/`, keeping documentation available outside authenticated application routes.
- **Unified docs tree:** The docs build now copies `docs/` and `architecture/` into one Docusaurus docs tree, then normalizes copied links and MDX-sensitive Markdown before rendering.
- **Versioning and docs sync:** `dq-ui` and `dq-ui-docs-site` were bumped to `0.10.5`, the tracked manifest components were updated for `Infrastructure`, `Documentation`, and `Testautomation`, and release, deployment, and versioning docs were advanced to the `0.10.5` release line.

### v0.10.4 (May 17, 2026)

- **DQ-10 completion:** The natural-language rule drafting preview is now captured in the current-state docs, with the current-state snapshot moved under `docs/features/current`.
- **Versioning and docs sync:** `dq-ui` and `dq-api` were bumped to `0.10.4`, the tracked manifest components were updated for `Authentication`, `Infrastructure`, `DataCatalog`, `Documentation`, and `Testautomation`, and the release, deployment, and versioning docs were advanced to the `0.10.4` release line.

### v0.10.3 (May 13, 2026)

- **AIStor migration:** Local object storage now runs on the AIStor free edition with an explicit license-file requirement, while the app-side storage contract stays generic S3.
- **Login and UI stability:** Keycloak reseeding now treats generated passwords as data, and the AsyncRequestTrackerProvider now resolves its auth, settings, and performance dependencies correctly so the UI mounts cleanly.
- **Versioning and docs sync:** `dq-ui` and `dq-api` were bumped to `0.10.3`, the tracked manifest components were updated for `Authentication`, `Infrastructure`, `DataCatalog`, `Documentation`, and `Testautomation`, and the release, deployment, and versioning docs were advanced to the `0.10.3` release line.

### v0.10.2 (May 9, 2026)

- **Suggestions and drafting flow:** Accept now creates the rule directly, the separate Apply-as-Rule path was removed, and natural-language drafting now supports RapidFuzz vs LLM provider selection with Redis-queued LLM work and async request tracking.
- **Runtime and observability hardening:** dq-llm startup health is fixed, the OpenMetadata configure/sync helpers now include the shared logging support they require at runtime, and Grafana infrastructure health now includes dq-llm container status alongside the queue panels.
- **Versioning and docs sync:** `dq-ui` and `dq-api` were bumped to `0.10.2`, the tracked manifest components `Infrastructure` and `Documentation` were updated, and the release, deployment, and versioning docs were advanced to the `0.10.2` release line.

### v0.10.0 (May 4, 2026)

- **Migration closure:** The DQ-7 mock-data migration plan is now complete after the canonical `2.0.0` seed rewrite and reusable-asset promotion.
- **Versioning and docs sync:** `dq-ui` and `dq-api` were bumped to `0.10.0`, and the release, deployment, and versioning docs were updated to the `0.10` release line.
- **Reusable asset read-only flow:** Locked rules now expose reusable filter and reusable join icons in the selected card, and the associated modals now show read-only details only.

### v0.9.3 (May 2, 2026)

- **Read-only role access:** Auditor and regulator users now get an explicit header badge, can open Delivery Inventory, and can access the admin read pages without needing the mutable admin role.
- **Versioning and docs sync:** `dq-ui` and `dq-api` were bumped to `0.9.3`, tracked component markers in `VERSION_MANIFEST.json` were updated for `Admin`, `UserManagement`, `RoleManagement`, `DataCatalog`, `Authentication`, `Documentation`, and `Testautomation`, and the release/deployment/versioning docs were synchronized.
- **Role access contract alignment:** Admin read endpoints now allow the canonical read scope set for read-only users, keeping the UI gates and backend contract aligned.

### v0.9.2 (May 1, 2026)

- **Validation path alignment:** The Test/public validation path now reads the selected root env consistently, so Grafana, OpenMetadata, Kong Admin, and edge ingress checks use the same deployment contract as the running compose stack.
- **Browser-backed Grafana access:** Grafana datasource smoke tests now complete the Keycloak browser flow and reuse the resulting session cookie for OAuth-backed datasource APIs.
- **OpenMetadata and edge routing alignment:** OpenMetadata readiness now probes the mounted `/metadata/api/v1/system/version` path, while the edge ingress validator branches on the selected env's public or local route shape.
- **Versioning and docs sync:** `dq-ui` and `dq-api` were bumped to `0.9.2`, tracked component markers in `VERSION_MANIFEST.json` were updated for `Authentication`, `Infrastructure`, `Testautomation`, and `Documentation`, and the release/deployment/versioning docs were synchronized.

### v0.9.0 (April 29, 2026)

- **Release baseline alignment:** `dq-ui` and `dq-api` package metadata were both bumped to `0.9.0`, while the tracked component markers in `VERSION_MANIFEST.json` were aligned to the same release version.
- **Image release-line refresh:** Repo-managed image examples and manifest app markers now use the `0.9-<hash>` release line for deterministic Docker tags.
- **Documentation synchronization:** Release notes, deployment guides, quick-start instructions, and automatic versioning docs were updated together so operators and developers see one consistent current release baseline.

### v0.8.8 (April 27, 2026)

- **Startup migration ownership:** Normal stack startup now runs an `api-migrate` one-shot service from the existing `dq-api` image before the `api` service starts, instead of relying on the API container entrypoint to run Alembic inline.
- **Reseed runtime alignment:** Containerized Postgres reseeding now uses live workspace-mounted seed sources inside `db-seed`, so updated seed scripts, Alembic code, and generators apply without rebuilding `dq-api`.
- **Deployment env propagation:** Compose services that still pinned `.env` now follow `ROOT_ENV_FILE`, keeping deployment startup, reseed, warmup, and support seed flows aligned with `.env.prod.local` or an explicit external env file.
- **Versioning and docs sync:** `dq-ui` was bumped to `0.8.8`, `dq-api` was aligned to `0.8.6`, changed manifest component markers were updated for `Infrastructure` and `Documentation`, and operational docs were synchronized.

### v0.8.5 (April 26, 2026)

- **Reseed/startup alignment:** `start-containers.sh` performs the Postgres reseed/init flow before the full stack is started, preventing Alembic head skew and API crash loops during `--all --seed-all --init-db` runs.
- **Build scope and hashing:** `build_and_push_all.sh` now exposes an explicit `core` vs `repo` image scope, while `calculate_versions.sh` hashes the real Docker build inputs for both core and auxiliary repo-managed images.
- **Validation runner semantics:** `validate.sh` now treats the default `all` group as the union of smoke scripts and all directly includable validate scripts, matching the documented default behavior.
- **Versioning and docs sync:** `dq-ui` and `dq-api` were bumped to `0.8.5`, changed tracked component markers in `VERSION_MANIFEST.json` were updated, and release/technical docs were synchronized.

### v0.8.4 (April 26, 2026)

- **Edge ingress topology:** Added the dedicated `edge` service, public path-prefix routing for browser-facing services, and env-driven host binding controls so public exposure can be limited to the single ingress surface.
- **Startup env selection:** `common_startup.sh`, `start-containers.sh`, `start_stack.sh`, `seed_stack.sh`, and the local UI helper now honor a selected env file instead of assuming only the repo `.env`.
- **Validation coverage:** Added local and public ingress validation scripts so the rendered edge configuration and public loopback exposure model can be checked explicitly.
- **Versioning and docs sync:** `dq-ui` and `dq-api` were bumped to `0.8.4`, changed tracked component markers in `VERSION_MANIFEST.json` were updated, and release pointers were synchronized.

### v0.8.3 (April 25, 2026)

- **Architecture documentation refresh:** The API layering and DDD architecture docs now describe the current FastAPI endpoint-adapter split, application use-case and service seams, typed repository/domain boundaries, and fail-fast runtime composition.
- **Diagram alignment:** The standalone Mermaid sources and generated SVG diagrams were regenerated so the architecture visuals match the current written docs.
- **Versioning and docs sync:** `dq-ui` and `dq-api` were bumped to `0.8.3`, tracked component markers in `VERSION_MANIFEST.json` were updated, and the latest release pointers were synchronized.

### v0.8.2 (April 18, 2026)

- **Delivery inventory and notes:** Delivery notes can now be enriched with storage-backed file names and object counts on demand, while unsupported delivery formats surface explicit warnings instead of blocking the read path.
- **Offline seeding runtime:** dq-engine now bakes Spark jars during the image build and supports parquet, csv, json, avro, delta, and iceberg without downloading dependencies at container start-up.
- **Versioning and docs sync:** dq-ui version bumped to `0.8.1`, dq-api version bumped to `0.8.2`, and version manifest markers were refreshed for the tracked UI components.

### v0.8.1 (April 15, 2026)

- **Zammad requester resolution:** Support requests now resolve the requester email from authenticated user claims when the local user id does not match the stored admin row, preventing false 400 responses for valid Zammad tickets.
- **Versioning and docs sync:** `dq-api` version bumped to `0.8.1` and release notes updated in root and UI published copies.

### v0.7.0 (March 28, 2026)

- **Contract alignment (UI):** Removed workspace and identity fallback logic in rules and approvals flows; canonical fields are now required end-to-end.
- **Backend quality gates:** Added focused tests for auth callback/logout branches, validation-runs pagination helper coverage, and API metrics store behavior.
- **Test policy compliance:** Updated non-ORM unit test modules to satisfy fixture-usage policy checks required by the official backend unit script.
- **Versioning and docs sync:** `dq-api` and `dq-ui` versions bumped to `0.7.0` and release notes updated in root and UI published copies.

### v0.5.0 (March 16, 2026)

- **DQ-8: Rule test execution with attribute selection and plain-language results.**
  - `TestRuleModal.tsx`: Added attribute-selection panel; user selects which assigned attribute(s) to test; cross-version selection is blocked with a validation message; `versionId` resolved from selection (no extra API call).
  - `useRuleActions.ts`: `handleTestRule` now accepts `{ sampleCount, versionId, selectedAttributes }`; reads `totalTests`/`passedCount`/`failedCount`/`successRate` from `test-with-generated-data` response; guards on `testedCount <= 0`; persists `selectedAttributes` in proofData; auto-closes modal on success.
  - `Rules.tsx`: `attributeCatalog` entries now carry `versionId` and `dataObjectId`; `activeRuleAssignedAttributes` memo feeds `TestRuleModal`.
  - `RuleDetailsModal.tsx`: Added `testExplanation` memo and collapsible *What does this mean?* explainer panel with failure analysis (explicit reasons → diagnostics → null/empty field hotspots → sample row → fallback).
  - `Reports.tsx`: Added *Attributes* column to test-results table reading `proofData.selectedAttributes`.
  - `testing.py` (FastAPI): Returns HTTP 400 when `totalTests <= 0` after a test run.
- **Zero-row false-pass guard**: Both the frontend (`useRuleActions.ts`) and the backend (`testing.py`) now block test runs that produce zero records.
- **Business-friendly failure analysis**: Explainer panel uses plain language — "Likely cause", "blank or missing", "one failing record contained" — instead of raw field/API terminology.

### v0.4.0 (March 16, 2026)

- **API platform migration complete (API-6.11)**: Legacy NestJS API (port 4001) decommissioned. FastAPI (`dq-api/fastapi/`, port 4010) is now the sole active API server.
- All API traffic continues to route through Kong Gateway on port 9111 — no external contract changes.
- `dq-api/server/` archived to `dq-api/server-archive/` (preserved for reference).
- `docker-compose.yml` `api` service now builds from `Dockerfile.fastapi`.
- Kong upstream updated to `http://api:4010`; public OIDC callback generation now uses `OIDC_REDIRECT_BASE_URL` when set and otherwise reuses `KONG_PUBLIC_URL`.
- `WF-4.10` closed: 55 FastAPI test files covering all API surfaces using `pytest` + `TestClient`.

### v0.3.3 (March 13, 2026)

- **`dq-ui/src/main.tsx`**: Removed a duplicate web-component runtime bundle import. Having both `dist/index.js` and the ESM bundle registered two Stencil runtimes, causing `NotAllowedError: Sheet constructor document doesn't match` in Vite dev mode and preventing icons from rendering.
- **`dq-ui/vite.config.ts`**: Added startup-time icon alias mirroring into `public/assets/icon/` and `public/assets/assets/icon/` so Vite dev correctly resolves both hashed and bare icon names used by the icon component.

### v0.3.2 (March 11, 2026)

- Fixed Keycloak SSO issuer URL inside container network (`keycloak.local` vs `localhost`).
- Fixed Kong JWT credential issuer aliasing for local hostnames.
- Fixed API CORS allowlist to include `dq-made-easy.local:5174`.
- Fixed `app-config.service.ts` to let env SSO overrides take precedence over stale DB values.

---

## Rule Suggestions System Architecture

### Overview

The Rule Suggestions feature consists of three main components:

1. **Frontend** — React/TypeScript UI for requesting profiling and managing suggestions
2. **Backend API** — FastAPI controller handling HTTP requests and business logic
3. **Job Queue** — Async profiling jobs via Bull/Redis

```
Frontend (React)
    ↓
Backend API (FastAPI)
    ↓
Job Queue (Bull/Redis) → Profiling Engine
    ↓
Database (PostgreSQL)
```

### API Reference

All endpoints are prefixed with `/api/suggestions`.

Interactive API docs: [OAS/Swagger UI](/openapi/)  
OpenAPI index: [/openapi/index.json](/openapi/index.json)

#### Data Sources

**GET** `/data-sources`
- List data sources available for profiling
- Returns: `{ success: true, dataSources: DataSource[], canRequestProfiling: boolean }`
- Auth: `x-user-id` header (optional, for permission checks)
- Role: All authenticated users (profiling restricted to analyst/admin/data-steward)

Example:
```bash
curl http://localhost:4001/api/suggestions/data-sources \
  -H "x-user-id: user123"
```

#### Profiling Requests

**POST** `/data-sources/:dataSourceId/request-profiling`
- Request on-demand data profiling for a data source
- Auth: Requires `x-user-id` header
- Roles: `analyst`, `data-steward`, `admin`
- Rate limit: 1 request per 30 minutes per source per user
- Returns: `{ success: boolean, profilingRequestId?: string, message: string }`

Errors:
- `401` — Not authenticated
- `403` — Insufficient role
- `429` — Rate limit exceeded (cooldown active)
  - Response includes `minutesRemaining` and `lastRequestedAt`

Example:
```bash
curl -X POST http://localhost:4001/api/suggestions/data-sources/demo-sql/request-profiling \
  -H "x-user-id: user123"

# Response:
{
  "success": true,
  "profilingRequestId": "prof-uuid-12345",
  "message": "Data profiling started"
}
```

**GET** `/profiling-requests/:profilingRequestId/status`
- Poll the status of a profiling job
- Returns: `{ success: true, request: { status: string } }`
- Status values: `pending`, `running`, `completed`, `failed`

Example:
```bash
curl http://localhost:4001/api/suggestions/profiling-requests/prof-uuid-12345/status
```

#### Suggestions

**GET** `/`
- Fetch pending suggestions
- Query params:
  - `status` (default: `pending`) — Filter by status (pending, accepted, applied, dismissed)
  - `dataSourceId` (optional) — Filter by source
- Returns: `{ success: true, suggestions: Suggestion[], count: number }`

Example:
```bash
curl "http://localhost:4001/api/suggestions?status=pending&dataSourceId=demo-sql"
```

**POST** `/:suggestionId/accept`
- Mark a suggestion as interesting/accepted
- Auth: Requires `x-user-id`
- Updates suggestion status to `accepted`
- Records interaction for metrics
- Returns: `{ success: true, message: string }`

**POST** `/:suggestionId/dismiss`
- Dismiss a suggestion as not relevant
- Auth: Requires `x-user-id`
- Updates suggestion status to `dismissed`
- Records interaction for metrics
- Returns: `{ success: true, message: string }`

**POST** `/:suggestionId/apply`
- Apply a suggestion (creating a rule)
- Auth: Requires `x-user-id`
- Request body: `{ ruleId?: string }` — Optional existing rule ID
- If no ruleId: Creates new rule from suggestion
- Updates suggestion status to `applied`
- Records interaction with created rule ID
- Returns: `{ success: true, message: string }`

Example:
```bash
curl -X POST http://localhost:4001/api/suggestions/sug-uuid-123/apply \
  -H "Content-Type: application/json" \
  -d '{ "ruleId": "rule-uuid-456" }'
```

#### Metrics

**GET** `/metrics`
- Get suggestions and profiling usage metrics
- Returns: Summary of tracked metrics
- Auth: No special auth required

**POST** `/metrics/clear`
- Clear all recorded metrics (admin only)
- Returns: `{ success: true }`

### Database Schema

#### `profiling_requests` Table

```sql
CREATE TABLE profiling_requests (
  id UUID PRIMARY KEY,
  user_id VARCHAR NOT NULL,
  data_source_id VARCHAR NOT NULL,
  status VARCHAR NOT NULL DEFAULT 'pending', 
    -- pending, running, completed, failed
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,
  error_message TEXT,
  metadata JSONB -- Additional tracking data
);

CREATE INDEX idx_profiling_by_user ON profiling_requests(user_id);
CREATE INDEX idx_profiling_by_source ON profiling_requests(data_source_id);
CREATE INDEX idx_profiling_status ON profiling_requests(status);
```

#### `suggestions` Table

```sql
CREATE TABLE suggestions (
  id UUID PRIMARY KEY,
  user_id VARCHAR NOT NULL,
  data_source_id VARCHAR NOT NULL,
  suggested_rule JSONB NOT NULL,
    -- {name, description, expression, dimension, ruleType}
  confidence_score FLOAT NOT NULL, -- 0-1
  reason TEXT,
  rule_type VARCHAR NOT NULL,
    -- NOT_NULL, UNIQUE, FORMAT_VALIDATION, RANGE_CHECK, REFERENTIAL_INTEGRITY
  status VARCHAR NOT NULL DEFAULT 'pending',
    -- pending, accepted, dismissed, applied
  created_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP, -- 30 days after creation
  created_from_profiling_request_id UUID REFERENCES profiling_requests(id)
);

CREATE INDEX idx_suggestions_status ON suggestions(status);
CREATE INDEX idx_suggestions_datasource ON suggestions(data_source_id);
CREATE INDEX idx_suggestions_expires ON suggestions(expires_at);
```

#### `suggestion_interactions` Table

```sql
CREATE TABLE suggestion_interactions (
  id UUID PRIMARY KEY,
  suggestion_id UUID NOT NULL REFERENCES suggestions(id),
  user_id VARCHAR NOT NULL,
  action VARCHAR NOT NULL,
    -- viewed, accepted, dismissed, applied
  rule_created_id UUID, -- If action = 'applied'
  created_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_interactions_suggestion ON suggestion_interactions(suggestion_id);
CREATE INDEX idx_interactions_user ON suggestion_interactions(user_id);
```

### Backend Services

#### ProfilingService

```typescript
class ProfilingService {
  // List available data sources for profiling
  async listDataSources(): Promise<DataSource[]>
  
  // Get profiling request status
  async getProfilingRequestStatus(requestId: string): Promise<ProfilingRequest>
  
  // Fetch pending suggestions
  async getSuggestions(
    dataSourceId?: string, 
    status?: string
  ): Promise<Suggestion[]>
  
  // Update suggestion status
  async updateSuggestionStatus(
    suggestionId: string, 
    status: SuggestionStatus
  ): Promise<void>
  
  // Record user interaction with suggestion
  async recordSuggestionInteraction(
    suggestionId: string,
    userId: string,
    action: 'viewed' | 'accepted' | 'dismissed' | 'applied',
    ruleCreatedId?: string
  ): Promise<void>
}
```

#### SuggestionsController

```typescript
@Controller('api/suggestions')
class SuggestionsController {
  // GET /data-sources
  async getDataSources(req): Promise<{
    success: boolean
    dataSources: DataSource[]
    canRequestProfiling: boolean
  }>
  
  // POST /data-sources/:id/request-profiling
  async requestProfiling(id: string, req): Promise<{
    success: boolean
    message: string
    profilingRequestId?: string
  }>
  
  // GET /profiling-requests/:id/status
  async getProfilingStatus(id: string): Promise<{
    success: boolean
    request?: ProfilingRequest
  }>
  
  // GET /
  async getSuggestions(req): Promise<{
    success: boolean
    suggestions: Suggestion[]
  }>
  
  // POST /:id/accept
  async acceptSuggestion(id: string, req): Promise<{
    success: boolean
    message: string
  }>
  
  // POST /:id/dismiss
  async dismissSuggestion(id: string, req): Promise<{
    success: boolean
    message: string
  }>
  
  // POST /:id/apply
  async applySuggestion(id: string, body, req): Promise<{
    success: boolean
    message: string
  }>
}
```

#### SuggestionsMetricsService

Tracks operational metrics:
- `profiling.request` — Profiling job requests
- `profiling.status.poll` — Status polling events
- `profiling.dataSources.fetch` — Data source listings
- `suggestions.fetch` — Suggestion retrievals
- `suggestions.accept` — Acceptances
- `suggestions.dismiss` — Dismissals
- `suggestions.apply` — Applications/rule creations

### Job Queue (Bull/Redis)

#### Queue Configuration

```typescript
const profilingQueue = new Bull('data-profiling', {
  redis: {
    host: process.env.REDIS_HOST || 'localhost',
    port: parseInt(process.env.REDIS_PORT || '6379')
  }
})
```

#### Processing

```typescript
// Job data structure
{
  profilingRequestId: string
  dataSourceId: string
  userId: string
  // ... additional data
}

// Job states
pending → active → completed/failed

// Retry logic
{
  attempts: 3,
  backoff: { type: 'exponential', delay: 2000 }
}

// Job timeout
{ timeout: 600000 } // 10 minutes
```

#### Event Handlers

```typescript
profilingQueue.on('completed', (job) => {
  console.log(`Job ${job.id} completed successfully`)
})

profilingQueue.on('failed', (job, error) => {
  console.error(`Job ${job.id} failed: ${error.message}`)
})
```

### Access Control

#### Role-Based Permissions

| Action | Required Roles | Notes |
|--------|----------------|-------|
| View data sources | All auth | For UI dropdown |
| Request profiling | `analyst`, `data-steward`, `admin` | Rate limited |
| View suggestions | All auth | Own + shared suggestions |
| Accept suggestion | All auth | Records interaction |
| Dismiss suggestion | All auth | Records interaction |
| Apply suggestion | All auth | Creates rule |
| View metrics | All auth | Summary only |
| Clear metrics | `admin` | Admin portal |

#### Permission Check

```typescript
function hasProfilingPermission(userRoles: string[]): boolean {
  const normalizeRole = (r: string) => 
    String(r).trim().toLowerCase().replace(/[\s_]+/g, '-')
  
  const allowed = new Set(['analyst', 'data-steward', 'admin'])
  return userRoles.some(r => allowed.has(normalizeRole(r)))
}
```

### Configuration

#### Environment Variables

```bash
# API Base URL (frontend)
VITE_API_BASE_URL=http://localhost:4001

# Redis (async jobs)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=          # Optional

# Profiling Rate Limiting (minutes)
PROFILING_COOLDOWN_MINUTES=30

# Job Processing
PROFILING_JOB_TIMEOUT_MS=600000    # 10 minutes
PROFILING_JOB_ATTEMPTS=3           # Retry count
PROFILING_QUEUE_CONCURRENCY=5      # Parallel jobs

# Database Cleanup
SUGGESTION_EXPIRY_DAYS=30          # Auto-cleanup age

# Feature Flag
FEATURE_RULE_SUGGESTIONS=enabled    # Or disabled
```

#### Feature Flag Configuration

In app-config.csv:
```csv
feature_rule_suggestions,true,enabled
```

Or in Settings UI (Preview Features toggle).

### Deployment

#### Prerequisites

- Node.js 22+
- PostgreSQL 12+
- Redis 6+
- Docker (optional)

#### Database Migrations

```sql
-- Create profiling_requests table
-- Create suggestions table
-- Create suggestion_interactions table
-- Create indexes

-- Cleanup expired suggestions (run daily)
DELETE FROM suggestions 
WHERE expires_at < NOW() 
AND status IN ('dismissed', 'applied')
```

#### Redis Setup

```bash
# Local development
redis-server

# Docker
docker run -d -p 6379:6379 redis:7-alpine

# Production
# Use managed Redis service (AWS ElastiCache, Azure Cache, etc.)
```

#### Docker Compose

```yaml
version: '3.9'
services:
  api:
    image: dq-api:latest
    ports:
      - "4001:4001"
    environment:
      DATABASE_URL: postgres://user:pass@db:5432/dq
      REDIS_URL: redis://redis:6379
      PROFILING_COOLDOWN_MINUTES: 30
    depends_on:
      - db
      - redis
  
  db:
    image: postgres:18-alpine
    environment:
      POSTGRES_DB: dq
      POSTGRES_PASSWORD: password
    volumes:
      - db_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  db_data:
```

### Performance Tuning

#### Database Indexes

```sql
-- Ensure indexes exist for:
CREATE INDEX idx_profiling_status ON profiling_requests(status);
CREATE INDEX idx_suggestions_expires ON suggestions(expires_at);
CREATE INDEX idx_interactions_suggestion ON suggestion_interactions(suggestion_id);
```

#### Redis Memory

```bash
# Monitor queue size
redis-cli LLEN bull:data-profiling:active

# Monitor memory usage
redis-cli INFO memory
```

#### Job Tuning

```typescript
profilingQueue.setDefaultSettings({
  concurrency: 5,        // Parallel profiling jobs
  rateLimit: {
    max: 10,            // Max 10 jobs per
    duration: 1000      // 1 second
  }
})
```

### Monitoring & Logging

#### Metrics to Track

- Profiling request latency (p50, p95, p99)
- Queue depth and processing time
- Suggestion accuracy metrics
- Error rates and types
- User engagement with suggestions

#### Log Levels

```typescript
// Info: User actions (request profiling, apply suggestion)
// Warn: Rate limit hits, job retries
// Error: Job failures, database errors
// Debug: API call details, suggestion scoring
```

#### Example Monitoring

```typescript
// Track profiling duration
const duration = Date.now() - startTime
logger.info(`Profiling completed in ${duration}ms`, {
  requestId,
  dataSourceId,
  suggestionCount,
  duration
})
```

### Troubleshooting

#### Profiling Jobs Not Completing

```bash
# Check Redis queue
redis-cli
LLEN bull:data-profiling:active
LLEN bull:data-profiling:completed
LLEN bull:data-profiling:failed

# Check logs for errors
grep "Profiling job" logs/app.log | tail -20
```

#### Rate Limit Errors

Check cooldown enforcement in `suggestions.controller.ts`:
```typescript
const lastRequest = await getLastProfilingRequest(userId, dataSourceId)
if (lastRequest && minutesSince(lastRequest) < COOLDOWN_MINUTES) {
  return 429 // Too many requests
}
```

#### Expired Suggestions Not Cleaning Up

Configure cleanup job (daily cron):
```bash
0 2 * * * curl -X POST http://localhost:4001/api/suggestions/cleanup
```

### Future Enhancements

- **Parallel Profiling**: Profile multiple sources simultaneously
- **Custom Matchers**: User-defined suggestion rules
- **ML Scoring**: Replace heuristics with trained model
- **Suggestion Feedback**: Rate suggestion quality
- **Distributed Run**: Scale profiling across workers
- **Incremental Profiling**: Only sample data periodically

---

## SSO & Authentication Architecture (v0.3.2)

### Overview

Authentication uses Keycloak as the identity provider, Kong Gateway as the JWT-validating proxy, and FastAPI (`dq-api`) as the backend. The flow is:

```
Browser
  → Kong Gateway (:9111)     — verifies RS256 JWT (iss claim)
    → dq-api (:4010)         — resolves user from bearer token
      → Keycloak (:8080)     — token issuer / userinfo source
```

### Kong JWT Plugin Configuration

Kong's JWT plugin validates the `iss` (issuer) claim against registered credentials for consumer `oidc-issuer`. Because Keycloak is reachable at **two hostnames** (external `localhost:8080` and internal Docker network `keycloak:8080`), both issuer variants are registered with the same RS256 public key:

```
http://localhost:8080/realms/dqprototype
http://keycloak:8080/realms/dqprototype
```

Kong credentials are seeded at stack startup by `dq-kong/scripts/bootstrap_kong.sh`. The bootstrap flow:
1. Reads the live Keycloak realm and JWKS from the Keycloak Admin API
2. Reconciles Kong consumers, JWT credentials, and ACL groups from current realm state
3. Applies the Kong service, route, CORS, and telemetry configuration used by the stack startup scripts

### OIDC Callback Token Handling

`dq-api/server/app.controller.ts` handles the SSO callback at `GET /v1/auth/callback`. After the OIDC code exchange, it returns the Keycloak `access_token` (a signed JWT) as `auth_token` in the response. Kong requires a JWT for all `/v1/*` requests; previously an opaque session token was returned, causing a gateway `"Bad token; invalid JSON"` error.

### User Resolution from Bearer Token

`api.service.ts` → `resolveUserIdFromBearerToken()`:

1. Decodes the JWT to extract the `iss` claim
2. Normalizes the issuer hostname for the internal container network: `localhost` → `keycloak` (via `getBackendIssuer()`). Overridable with `SSO_INTERNAL_ISSUER`.
3. Calls Keycloak's `userinfo` endpoint using the normalized URL
4. If `userinfo` is unreachable (non-2xx or network error), falls back to `findOrCreateUserFromOidc()` using the decoded JWT claims directly — guarantees user resolution even if Keycloak is temporarily unavailable from inside the container

### Per-Request Authentication Context (`AsyncLocalStorage`)

The original implementation stored the resolved `currentUserId` as a singleton property on `ApiService`. Under concurrent requests this caused a race condition where one request could overwrite another's user state, resulting in intermittent 401 errors.

**Fix (v0.3.2):**

`api.service.ts` uses Node.js `AsyncLocalStorage` (from `node:async_hooks`) to scope auth state per request:

```typescript
private readonly authContext = new AsyncLocalStorage<{ currentUserId: string | null }>();

runWithRequestContext<T>(fn: () => T): T {
  return this.authContext.run({ currentUserId: null }, fn);
}

get currentUserId(): string | null {
  return this.authContext.getStore()?.currentUserId ?? this.fallbackCurrentUserId;
}
```

`auth.middleware.ts` wraps the entire `use()` body in `this.svc.runWithRequestContext(async () => { ... })`, ensuring each request has its own isolated store. The fallback property covers code paths that run outside a request context (e.g. startup hooks).

### Keycloak Redirect URI

The Keycloak client `dq-rules-ui` must allow the public callback URL for your active deployment. The auth endpoint prefers `OIDC_REDIRECT_BASE_URL` and otherwise reuses `KONG_PUBLIC_URL` as the public Kong/API base.

### Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `SSO_INTERNAL_ISSUER` | — | Override internal Keycloak issuer URL used for userinfo calls |
| `OIDC_REDIRECT_BASE_URL` | — | Preferred public base URL for OIDC callback generation |
| `KONG_PUBLIC_URL` | — | Public Kong/API base reused by the UI and OIDC callback generation when no explicit redirect override is set |
