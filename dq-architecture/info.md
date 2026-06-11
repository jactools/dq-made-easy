# Data Quality Made Easy - Architecture

## Purpose of This Document

This file provides the high-level system architecture overview (services, data flow, and deployment topology).

For formal Architecture Decision Records (ADRs), use:
- `architecture/ARCHITECTURAL_DECISIONS.md`

## Overview

Data Quality Made Easy is a comprehensive system for managing, testing, and monitoring data quality rules across diverse data sources. It consists of multiple microservices, a modern React frontend, and supporting infrastructure.

## System Architecture

```mermaid

graph TB
    subgraph Client["Frontend (Browser)"]
        React["React + Vite\nPort 5173\nAuth via Keycloak"]
    end
    
    subgraph API["API Layer"]
        APIServer["FastAPI API\nPort 4010\nRule Management\nApprovals\nData Catalog"]
    end
    
    subgraph Processing["Rule Processing"]
        Engine["Python Rules Engine\nPort 8000\nRule Translation\nTest Execution"]
    end
    
    subgraph Data["Data & Auth"]
        Keycloak["Keycloak\nPort 8080\nUser Authentication\nRole Management"]
        PostgreSQL["PostgreSQL\nPort 5432\nRule Definitions\nApprovals\nAudit Log\nUser Data"]
    end
    
    React -->|HTTP/REST| APIServer
    React -->|OAuth2| Keycloak
    APIServer -->|Query/Seed| PostgreSQL
    APIServer -->|gRPC/HTTP| Engine
    Engine -->|Query Rules| PostgreSQL
    Keycloak -->|Verify Token| APIServer

    style React fill:#61dafb,stroke:#333,color:#000
    style APIServer fill:#e74c3c,stroke:#333,color:#fff
    style Engine fill:#3776ab,stroke:#333,color:#fff
    style Keycloak fill:#4a90e2,stroke:#333,color:#fff
    style PostgreSQL fill:#336791,stroke:#333,color:#fff
```

## Project Structure

```
dq-rulebuilder/
├── dq-api/              # FastAPI API Server
│   ├── server/          # Backend source code
│   ├── package.json
│   └── Dockerfile.fastapi (active)
│
├── dq-ui/               # React + Vite Frontend
│   ├── src/             # React source
│   ├── package.json
│   └── Dockerfile.frontend
│
├── dq-engine/           # Python Rules Engine
│   ├── main.py
│   ├── rule_translator.py
│   ├── requirements.txt
│   └── Dockerfile.engine
│
├── dq-db/               # Database Configuration & Seeding
│   ├── init/            # SQL schemas & generated seeds
│   ├── mock-data/       # CSV test data
│   ├── scripts/         # Database utilities
│   └── sql/             # SQL configurations
│
├── dq-base/             # Docker Base Image
│   └── Dockerfile       # Pre-built image with dependencies
│
├── dq-keycloak/         # Keycloak Authentication Config
│   └── dqprototype-realm.json
│
├── dq-architecture/     # This documentation
│   └── info.md
│
├── docker-compose.yml   # Orchestration
└── scripts/             # Utility scripts
```

## Microservices

### 1. **Frontend (dq-ui)**
- **Technology**: React 18, Vite, TypeScript
- **Port**: 5173 (development), 80 (production)
- **Purpose**: User interface for rule management, approval workflows, and data catalog browsing
- **Features**:
  - Rule creation and editing
  - Approval workflows
  - Data quality dashboard
  - Test result visualization
  - Data product/dataset catalog
  - Real-time status updates

### 2. **API Server (dq-api)**
- **Technology**: Python, FastAPI
- **Port**: 4001
- **Purpose**: REST API for all business operations
- **Endpoints**:
  - `/rules` - Rule CRUD and management
  - `/approvals` - Approval workflow
  - `/data-products` - Data catalog
  - `/data-sets` - Dataset management
  - `/attributes-catalog` - Data attribute definitions
  - `/rules/:id/test` - Rule testing
  - `/rules/:id/activate` - Rule activation

### 3. **Rules Engine (dq-engine)**
- **Technology**: Python, FastAPI
- **Port**: 8003 externally, 8000 inside the container
- **Purpose**: Rule translation and execution
- **Features**:
  - Translates rule expressions
  - Executes tests against data
  - Validates rule syntax
  - Returns test results and coverage metrics

### 4. **Database (dq-db)**
- **Technology**: PostgreSQL 15
- **Port**: 5432
- **Purpose**: Persistent storage for all application data
- **Tables**:
  - `rules` - DQ rule definitions (20+ retail-banking rules)
  - `approvals` - Approval workflow tracking
  - `users` - User accounts and preferences
  - `roles` - Role-based access control
  - `data_products` - Product catalog
  - `data_sets` - Dataset definitions
  - `data_objects_catalog` - Data objects/entities
  - `data_object_versions` - Schema versions
  - `attributes_catalog` - Column/attribute definitions
  - `audit` - Audit trail

### 5. **Authentication (dq-keycloak)**
- **Technology**: Keycloak 22
- **Port**: 8080
- **Purpose**: OAuth2/OpenID Connect provider
- **Features**:
  - User authentication
  - Role-based access control
  - Real-time token management
  - SSO capable

## Data Flow

### Rule Creation & Approval Workflow
```
Frontend (User)
    ↓ (Create rule)
    → API Server (REST /rules)
    → PostgreSQL (Insert rule with status=draft)
    ↓ (User submits for review)
    → API Server (REST /approvals)
    → PostgreSQL (Create approval record)
    ↓ (Approver reviews)
    → API Server (approve/reject)
    → PostgreSQL (Update rule status, audit log)
    ↓ (Activate)
    → API Server (activate)
    → Rules Engine (cache rule)
    ↓ (Real-time monitoring)
    → Data (Check violations)
```

### Rule Testing Flow
```
Frontend (Test button)
    ↓
    → API Server (POST /rules/{id}/test)
    ↓
    → Rules Engine (Execute tests)
    ↓
    → Query test data
    ↓
    → Return results (coverage, failures, pass rate)
    ↓
    → PostgreSQL (Store test results)
    ↓
    → Frontend (Display in UI)
```

### Data Catalog Navigation
```
Frontend (Browse)
    ↓
    → API Server (lazy-load endpoints)
    → PostgreSQL (Query hierarchy)
    ↓ (Products → Datasets → Objects → Versions → Attributes)
    → Cache in frontend state
    ↓
    → Display attributes with metadata
```

## Key Design Decisions

### 1. **Microservice Separation**
- Each service has a single responsibility
- Independent scaling and deployment
- Clear API boundaries

### 2. **Docker-Based Infrastructure**
- Consistent development and production environments
- dq-base image with pre-built dependencies reduces build time
- All services orchestrated via docker-compose

### 3. **Lazy-Loading Architecture**
- Frontend caches loaded data at each hierarchy level
- Prevents unnecessary database queries
- Validates cache before returning cached data

### 4. **Mock Data Strategy**
- CSV files in dq-db/mock-data seed the database
- 20+ retail-banking rules for testing
- Multiple rule statuses (active, pending, rejected) for workflow testing
- Consistent with production schema

### 5. **Dual Data Quality Metrics**
- **Test Coverage**: Average test completeness (how well rules are tested)
- **Data Quality Score**: Percentage of active rules passing (real data performance)

## Authentication & Authorization

- **Provider**: Keycloak (OAuth2/OpenID Connect)
- **Token Storage**: localStorage (frontend)
- **Authorization Header**: `Authorization: Bearer {token}`
- **Roles**: viewer, editor, reviewer, admin
- **Protected Routes**: All API endpoints validate token via middleware

## Database Initialization

1. Docker starts PostgreSQL container
2. Runs `dq-db/init/01_schema.sql` - Creates all tables
3. Runs `dq-db/init/generated_seed_*.sql` - Populates test data
4. Loads mock data from `dq-db/mock-data/*.csv`
5. Applies config from `dq-db/sql/create_app_config.sql`

## Development Workflow

```bash
# Start all services
docker compose up -d

# Services available at:
# Frontend:   http://localhost:5173
# API:        http://localhost:4001
# Engine:     http://localhost:8000
# Keycloak:   http://localhost:8080
# Database:   postgresql://postgres:postgres@localhost:5432/dq

# View logs
docker compose logs -f api    # API logs
docker compose logs -f dq-engine  # Engine logs
docker compose logs -f db     # Database logs

# Rebuild after code changes
docker compose up --build api
```

## Production Considerations

- Replace Keycloak with managed auth service
- Use managed PostgreSQL (AWS, Azure Postgres, Cloud SQL)
- Store frontend assets in CDN
- Use container orchestration (Kubernetes, ECS, AKS)
- Implement proper monitoring and logging
- Use environment-specific configurations
- SSL/TLS for all external traffic

## Performance Metrics

- Rule loading: < 100ms (cached)
- API response: < 200ms (typical)
- Full page load: < 2s
- Test execution: 1-5s (depending on data volume)
- Database query: < 50ms (indexed)

## Security Measures

- OAuth2 authentication required
- JWT token validation on all endpoints
- Role-based access control
- SQL injection prevention (parameterized queries)
- CORS configured appropriately
- Secure cookie handling
- Audit trail for all changes

## Scaling Strategy

### Horizontal Scaling
- **Frontend**: Serve from multiple CDN locations
- **API**: Run multiple instances behind load balancer
- **Engine**: Scale workers for parallel rule processing

### Vertical Scaling
- Increase database connection pool
- Optimize slow queries
- Cache frequently accessed data
- Implement paginated endpoints

## Monitoring & Observability

- Application logs to stdout (Docker logs)
- API request/response logging
- Database query performance tracking
- Rule execution metrics
- Error tracking and alerting
- Audit trail for compliance

## Dependencies

### Backend (Node.js)
- fastapi - Web framework
- uvicorn - ASGI server
- pg - PostgreSQL client
-axios - HTTP client

### Frontend (React)
- react - UI framework
- vite - Build tool
- typescript - Type safety
- axios - HTTP client

### Engine (Python)
- fastapi - Web framework
- sqlalchemy - ORM
- pydantic - Data validation

### Infrastructure
- PostgreSQL 15 - Database
- Keycloak 22 - Authentication
- Docker - Containerization
