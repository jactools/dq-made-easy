# dq-api

Backend API service for the Data Quality Rulebuilder stack.

## 🚀 Kong API Gateway (NEW)

**Priority 1 Implementation**: Kong Gateway for multi-consumer API access

- **Quick Start**: [KONG_QUICKSTART.md](./KONG_QUICKSTART.md) - Deploy Kong in 5 minutes
- **Full Guide**: [KONG_GATEWAY_SETUP.md](./KONG_GATEWAY_SETUP.md) - Complete setup documentation
- **Architecture**: [ARCHITECTURAL_DECISIONS.md](../architecture/ARCHITECTURAL_DECISIONS.md) - ADR-009 explains the choice

### Deploy Kong Gateway

```bash
# From repository root
docker-compose up -d kong
./scripts/configure_kong.sh

# Test the gateway
curl http://localhost:8000/v1/health
```

Access Kong Manager UI: https://localhost:8444/ops/kong

---

## Quick start

### Local development

```bash
cd dq-api
npm install
npm run start
```

API runs on `http://localhost:4010`.

### Build

```bash
cd dq-api
npm run build
```

### FastAPI runtime

The active API runtime is FastAPI in `fastapi/`.

```bash
cd dq-api/fastapi
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../../.env.dev.example ../../.env.dev.local
set -a
source ../../.env.dev.local
set +a
uvicorn app.main:app --reload --host 0.0.0.0 --port 4010
```

Or from `dq-api/` with npm scripts:

```bash
npm run start:fastapi
```

## Scripts

- `npm run start:fastapi` / `npm run start:fastapi:prod` — run FastAPI baseline on port `4010`
- `npm run start` — alias to `start:fastapi`
- `npm run build` — no-op build placeholder for FastAPI runtime
- `npm run test` — run Vitest tests
- `npm run test:regression:apply-flow` — run apply-flow regression test
- `npm run lint` — run ESLint
- `npm run format` — run Prettier

## Docker / stack mode

From repository root, use the orchestration scripts:

```bash
./scripts/start-containers.sh --seed-all
```

Or build and run services directly:

```bash
docker compose --env-file .env.dev.local build api profiling-worker
docker compose --env-file .env.dev.local up -d api profiling-worker
```

## Smoke tests

From repository root:

- `./scripts/smoke_test_stack.sh` — checks Keycloak, API, and UI availability in stack mode
- `./scripts/smoke_test.sh` — checks core frontend/API endpoints

## Rule Suggestions flow docs

For the end-to-end Rule Suggestions profiling flow (UI path, API sequence, and verification commands), see [../README.md](../README.md) under **Rule Suggestions flow**.

## Server structure

The active backend source lives under `fastapi/`:

```
fastapi/
├── app/                         # FastAPI application package
│   ├── api/v1/                  # Versioned API routes
│   ├── core/                    # Auth, config, error utilities
│   ├── domain/                  # Domain interfaces and entities
│   ├── application/             # Use cases and resolvers
│   └── infrastructure/          # Repositories and ORM/session wiring
└── tests/                       # API/core/infrastructure/smoke tests
```

Legacy Node/NestJS code is preserved under `server-archive/` for historical reference only.

## Key endpoints (Rule Suggestions)

- `GET /api/suggestions/data-sources`
- `POST /api/suggestions/data-sources/:dataSourceId/request-profiling`
- `GET /api/suggestions/profiling-requests/:profilingRequestId/status`
- `GET /api/suggestions?status=pending&dataSourceId=:dataSourceId`

## Data Contracts (ODCS)

This API serves **Open Data Contract Standard (ODCS)** contracts for data sources. See [ODCS_INTEGRATION.md](./ODCS_INTEGRATION.md) for the full integration guide.

For data products, the product-level governing terminology is Open Data Product Specification 4.1; ODCS 3.1 remains the contract-level specification for delivery and data-quality rules.

**Endpoints:**
- `GET /api/data-contracts` — List all available contracts
- `GET /api/data-contracts/:dataSourceId` — Get contract (YAML or JSON)
- `GET /api/data-contracts/:dataSourceId/quality-rules` — Extract quality rules from contract

**Sample contract:** [../data_sources/contracts/demo-azure-payments-sql.odcs.yaml](../data_sources/contracts/demo-azure-payments-sql.odcs.yaml)

## API Gateway Integration

For production deployments with multiple consumer applications, see [API_GATEWAY_DESIGN.md](./API_GATEWAY_DESIGN.md) for:
- Gateway architecture and configuration
- OAuth2/OIDC authentication flows
- Rate limiting and quota management
- Versioning strategy
- Multi-consumer API design patterns
- Migration roadmap

## Notes

- The API uses Postgres (`DATABASE_URL`) and Redis (`REDIS_HOST`, `REDIS_PORT`) in stack mode.
- Seeded demo data sources include:
  - `demo-azure-customer-blob`
  - `demo-azure-payments-sql`
