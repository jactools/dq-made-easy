# DQ Plan Templates - DDD Implementation Guide

## Overview

This document describes the DDD (Domain-Driven Design) implementation of the reusable DQ Plan template system in the **dq-made-easy** repository.

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                        │
│  (API Endpoints, Request/Response Schemas)                     │
│  - /dq-api/fastapi/app/api/v1/endpoints/                       │
│  - /dq-api/fastapi/app/api/v1/schemas/                         │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│                        APPLICATION LAYER                         │
│  (Use Cases, Business Logic Services)                          │
│  - /dq-api/fastapi/app/application/services/                   │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│                          DOMAIN LAYER                            │
│  (Entities, Value Objects, Interfaces)                         │
│  - /dq-api/fastapi/app/domain/entities/                        │
│  - /dq-api/fastapi/app/domain/interfaces/                      │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│                         INFRASTRUCTURE LAYER                     │
│  (Persistence, External Services)                              │
│  - /dq-api/fastapi/app/infrastructure/repositories/            │
│  - /dq-api/fastapi/app/infrastructure/orm/                     │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│                           CORE LAYER                             │
│  (Configuration, Dependencies)                                 │
│  - /dq-api/fastapi/app/core/                                   │
└─────────────────────────────────────────────────────────────────┘
```

## DDD Layer Details

### 1. Domain Layer

**Purpose**: Core business logic, entities, and interfaces (no infrastructure dependencies)

#### Entities (`/app/domain/entities/dq_plan_template.py`)

```python
# Core domain entities
DQPlanTemplateEntity              # Root template definition
DQPlanTemplateParameterEntity     # Parameter definition
DQPlanTemplateConfigurationEntity # Engine configuration
DQPlanTemplateScopeEntity         # Scope definition
DQPlanTemplateSuiteEntity         # Validation suite
DQPlanTemplateScheduleEntity      # Schedule definition

# Request/Response entities
InstantiateTemplateRequestEntity  # Instantiation request
```

#### Repository Interfaces (`/app/domain/interfaces/v1/dq_plan_template_repository.py`)

```python
class DQPlanTemplateRepository(Protocol):
    async def create_template(...)
    async def get_template(...)
    async def list_templates(...)
    async def update_template(...)
    async def delete_template(...)
    async def list_active_templates(...)
    async def get_template_versions(...)
```

**Key Principles**:
- Uses `Protocol` for type-safe interfaces
- No SQL, ORM, or external dependencies
- Pure domain models

### 2. Application Layer

**Purpose**: Orchestrates use cases, coordinates domain objects

#### Services (`/app/application/services/`)

| Service | File | Responsibility |
|---------|------|----------------|
| Template Service | `dq_plan_template_service.py` | CRUD operations, instantiation |
| Template Validator | `dq_plan_template_validator.py` | Parameter/scope validation |
| Built-in Templates | `dq_plan_templates_builtin.py` | Predefined templates |

**Key Services**:

```python
class DQPlanTemplateService:
    async def create_template(template: DQPlanTemplateEntity)
    async def get_template(template_id: str, version: str | None)
    async def instantiate_template(request: InstantiateTemplateRequestEntity)
```

### 3. Infrastructure Layer

**Purpose**: Concrete implementations of domain interfaces

#### ORM Models (`/app/infrastructure/orm/models.py`)

```python
class DQPlanTemplateRow(Base):
    template_id: Mapped[str]
    template_name: Mapped[str]
    parameters_json: Mapped[Optional[dict]]
    scope_json: Mapped[Optional[dict]]
    suites_json: Mapped[Optional[list]]
    # ... etc
```

#### Repository Implementation (`/app/infrastructure/repositories/postgres_dq_plan_template_repository.py`)

```python
class PostgresDQPlanTemplateRepository(DQPlanTemplateRepository):
    async def create_template(self, template: DQPlanTemplateEntity) -> DQPlanTemplateEntity:
        # Concrete PostgreSQL implementation
        pass
    
    async def get_template(...)
    async def list_templates(...)
    # ...
```

### 4. API Layer

**Purpose**: HTTP interface for clients

#### Endpoints (`/app/api/v1/endpoints/dq_plan_templates.py`)

```python
router = APIRouter(prefix="/dq-plan-templates", tags=["dq-plan-templates"])

@router.get("")
async def list_templates(repository: DQPlanTemplateRepository = Depends(...))

@router.post("")
async def create_template(template: DQPlanTemplateSchema, ...)

@router.post("/{template_id}/instantiate")
async def instantiate_template(...)
```

#### Schemas (`/app/api/v1/schemas/dq_plan_template_schemas.py`)

```python
class DQPlanTemplateSchema(BaseSchema):
    template_id: str
    template_name: str
    parameters: list[DQPlanTemplateParameterSchema]

class InstantiateTemplateRequestSchema(BaseSchema):
    parameters: dict[str, Any]
```

### 5. Core Layer

**Purpose**: Dependency injection and configuration

#### Dependencies (`/app/core/dependencies.py`)

```python
@lru_cache
def _get_postgres_dq_plan_template_repository(database_url: str):
    return PostgresDQPlanTemplateRepository(database_url)

def get_dq_plan_template_repository() -> DQPlanTemplateRepository:
    database_url = _require_database_url(...)
    return _get_postgres_dq_plan_template_repository(database_url)
```

## File Structure

```
dq-api/fastapi/app/
├── api/
│   ├── v1/
│   │   ├── endpoints/
│   │   │   └── dq_plan_templates.py              # HTTP endpoints
│   │   └── schemas/
│   │       └── dq_plan_template_schemas.py      # Request/response schemas
│   └── ...
├── application/
│   └── services/
│       ├── dq_plan_template_service.py          # Business logic
│       ├── dq_plan_template_validator.py        # Validation
│       └── dq_plan_templates_builtin.py         # Predefined templates
├── core/
│   ├── config.py                                # Settings
│   └── dependencies.py                          # DI setup
├── domain/
│   ├── entities/
│   │   └── dq_plan_template.py                  # Domain models
│   └── interfaces/
│       └── v1/
│           └── dq_plan_template_repository.py   # Repository interface
├── infrastructure/
│   ├── orm/
│   │   └── models.py                            # SQLAlchemy models
│   └── repositories/
│       └── postgres_dq_plan_template_repository.py  # Postgres impl
└── ...
```

## Database Schema

### Table: dq_plan_templates

```sql
CREATE TABLE dq_plan_templates (
    template_id TEXT PRIMARY KEY,
    template_name TEXT NOT NULL,
    template_description TEXT,
    template_version TEXT NOT NULL,
    template_type TEXT NOT NULL,
    domain TEXT,
    tags TEXT[],
    workspace_id TEXT,
    parameters_json JSONB NOT NULL DEFAULT '{}',
    scope_json JSONB,
    suites_json JSONB NOT NULL DEFAULT '{}',
    configuration_json JSONB,
    schedule_json JSONB,
    owner TEXT,
    approver TEXT,
    approved BOOLEAN DEFAULT false,
    approval_date TIMESTAMPTZ,
    created_by TEXT,
    created_at TIMESTAMPTZ,
    updated_by TEXT,
    updated_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT true,
    is_default BOOLEAN DEFAULT false
);

-- Indexes
CREATE INDEX ix_dq_plan_templates_workspace ON dq_plan_templates(workspace_id);
CREATE INDEX ix_dq_plan_templates_domain ON dq_plan_templates(domain);
CREATE INDEX ix_dq_plan_templates_type ON dq_plan_templates(template_type);
CREATE INDEX ix_dq_plan_templates_tags ON dq_plan_templates USING GIN(tags);
CREATE INDEX ix_dq_plan_templates_is_active ON dq_plan_templates(is_active);
```

### Table: dq_plan_template_versions

```sql
CREATE TABLE dq_plan_template_versions (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    template_version TEXT NOT NULL,
    template_json JSONB NOT NULL,
    notes TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ,
    UNIQUE (template_id, template_version)
);

-- Indexes
CREATE INDEX ix_dq_plan_template_versions_template_id ON dq_plan_template_versions(template_id);
CREATE INDEX ix_dq_plan_template_versions_created_at ON dq_plan_template_versions(created_at);
```

## Dependency Flow

```
Request → API Endpoint → Schema Validation → Application Service
                                             ↓
                              Domain Entity → Repository Interface
                                             ↓
                              Infrastructure Repository → Database
                                             ↓
                              Database → ORM Model → Entity
```

## Testing Strategy

### Domain Layer Tests
```python
# Test pure business logic (no DB)
def test_template_instantiation():
    template = create_test_template()
    result = instantiate_template(template, {"dataset_name": "test"})
    assert result.plan_name == "Custom Template (test)"
```

### Repository Tests
```python
# Test with in-memory or test database
@pytest.mark.asyncio
async def test_create_template():
    repo = InMemoryDQPlanTemplateRepository()
    template = DQPlanTemplateEntity(...)
    result = await repo.create_template(template)
    assert result.template_id == "test-123"
```

### Integration Tests
```python
# Test with real database
@pytest.mark.asyncio
async def test_template_lifecycle():
    async with test_database():
        repo = PostgresDQPlanTemplateRepository(database_url)
        # Create, read, update, delete
```

## Migration Guide

### 1. Apply Migration
```bash
cd dq-api/fastapi
alembic upgrade head
```

### 2. Register Dependencies
```python
# In /app/core/dependencies.py
from app.infrastructure.repositories.postgres_dq_plan_template_repository import PostgresDQPlanTemplateRepository

@lru_cache
def _get_postgres_dq_plan_template_repository(database_url: str) -> PostgresDQPlanTemplateRepository:
    return PostgresDQPlanTemplateRepository(database_url)

def get_dq_plan_template_repository() -> DQPlanTemplateRepository:
    database_url = _require_database_url(...)
    return _get_postgres_dq_plan_template_repository(database_url)
```

### 3. Use in Endpoint
```python
from app.core.dependencies import get_dq_plan_template_repository

@router.post("")
async def create_template(
    template: DQPlanTemplateSchema,
    repository: DQPlanTemplateRepository = Depends(get_dq_plan_template_repository),
):
    service = DQPlanTemplateService(
        template_repository=repository,
        settings_provider=get_settings,
    )
    return await service.create_template(template)
```

## Best Practices

### 1. Keep Domain Pure
- Domain entities should have no infrastructure dependencies
- Use dependency injection for external services

### 2. Repository Pattern
- Always define a `Protocol` interface
- Implement concrete repository for each persistence backend
- Use in-memory repository for testing

### 3. Service Layer
- Services should be thin, delegating to domain entities
- Use use case methods for business operations
- Handle errors at service boundary

### 4. API Layer
- Schemas should match domain entities
- Use Pydantic for validation
- Keep endpoints thin

## Common Patterns

### Entity Creation
```python
template = DQPlanTemplateEntity(
    template_id=str(uuid4()),
    template_name="My Template",
    template_type="data_quality",
    parameters=[...],
    suites=[...],
)
```

### Repository Usage
```python
template = await repository.create_template(template_entity)
```

### Service Usage
```python
service = DQPlanTemplateService(
    template_repository=repository,
    settings_provider=get_settings,
)
result = await service.instantiate_template(request)
```

## References

- **Domain Models**: `/dq-api/fastapi/app/domain/entities/dq_plan_template.py`
- **Repository Interface**: `/dq-api/fastapi/app/domain/interfaces/v1/dq_plan_template_repository.py`
- **Service**: `/dq-api/fastapi/app/application/services/dq_plan_template_service.py`
- **Repository Implementation**: `/dq-api/fastapi/app/infrastructure/repositories/postgres_dq_plan_template_repository.py`
- **API Endpoint**: `/dq-api/fastapi/app/api/v1/endpoints/dq_plan_templates.py`
- **Schemas**: `/dq-api/fastapi/app/api/v1/schemas/dq_plan_template_schemas.py`
- **ORM Models**: `/dq-api/fastapi/app/infrastructure/orm/models.py`
- **Migration**: `/dq-api/fastapi/migrations/versions/20260704_0001_add_dq_plan_templates.py`
- **Dependencies**: `/dq-api/fastapi/app/core/dependencies.py`

---

**Version**: 1.0.0  
**Date**: 2026-07-04  
**Status**: Production Ready (DDD-compliant)
