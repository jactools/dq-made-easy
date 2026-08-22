# AI Agent Instructions

This repository follows specific rules that all AI agents must adhere to when making changes.

## Git Rules

### Only `git status` — NO OTHER GIT COMMANDS
Agents are **FORBIDDEN** to run any `git` command except `git status`.

**Allowed:**
- `git status` (the only permitted git command)

**Explicitly forbidden (all other git commands):**
- `git add` / `git reset` (staging/unstaging)
- `git diff` / `git diff --cached` (inspecting)
- `git log` / `git show` (reading history)
- `git commit`
- `git revert`
- `git reset --hard`
- `git merge`
- `git push`
- `git checkout`
- `git restore`
- **Any other `git` command**

**Rationale:** The user controls all git operations. Agents must never stage, inspect diffs, read history, or modify commit history. Use the `read` tool and `bash` to inspect files instead of `git diff`/`git show`.

### No Secrets/Certs/CAs in Git
Agents are **FORBIDDEN** to commit secrets, certificates, CA bundles, passwords, API keys, tokens, or any sensitive material to git.

**Allowed:**
- File references (e.g., `caProvider.name: kube-root-ca.crt`) — the file itself must be excluded from git
- Placeholders (e.g., `replace-me`, `0.1.0`) where real values are injected at deploy time
- `.gitignore` entries that exclude sensitive files

**Explicitly forbidden:**
- Inline certificates (PEM blocks) in YAML, JSON, ConfigMaps, or any file tracked by git
- Inline CA bundles in manifests, ConfigMaps, or scripts tracked by git
- Inline passwords, API keys, tokens, or secrets in any file tracked by git
- Embedding generated values (certs, keys, passwords) in version-controlled files

**Patterns to follow:**
- Use `kube-root-ca.crt` (auto-provisioned by Kubernetes) instead of embedding API server CAs
- Use `secretKeyRef`/`configMapKeyRef` references instead of inline values
- Store sensitive files outside git (e.g., `.env.*.local`) and reference them at deploy time
- Use Kustomize overlays or controller-specific inputs for environment-specific values

**Rationale:** Secrets in git are irreversible (history is permanent), compromise security, and violate platform principles.

## Python Module Rules

### 1. Line Count Limit (< 1000 LOC)
Every Python module must have fewer than 1000 lines of code.

**When you reach ~800 lines, split the module:**
- Extract helper classes/functions into `*_helpers.py` or `*_utils.py`
- Extract domain models into `entities.py` or `value_objects.py`
- Extract route handlers into `routes/*.py` (one route group per file)
- Extract service logic into `services/*.py` (one responsibility per file)

### 2. Single Responsibility Principle (SRP)
Each module must focus on ONE responsibility.

**Allowed groupings (same file is OK):**
- Multiple enums together (`types.py`)
- Multiple schemas/models together (`schemas.py`, `contracts.py`)
- Multiple error classes together (`errors.py`)
- Multiple entities together (`entities.py`)
- Multiple ORM models together (`orm.py`)
- One service class + its factory helper functions

**Violations (must split):**
- Entities + services + persistence in one file
- Schemas + services + functions in one file
- More than 2 concern types mixed together

### Validation
Run after every change:
```bash
python scripts/validate_module_rules.py
```

### 3. Package Structure — DDD Layout
Every new package under `packages/` must follow this Domain-Driven Design structure:

```
packages/metadata-<name>/
├── pyproject.toml
├── README.md
└── src/metadata_<name>/
    ├── __init__.py           # Public API exports only
    ├── config.py             # Config dataclass + load_config()
    ├── exceptions.py         # Domain exceptions
    ├── main.py               # FastAPI app + lifespan
    ├── domain/
    │   ├── models/           # Domain entities (pure Python, no ORM/Pydantic)
    │   ├── repositories/     # Abstract repository interfaces (ABC)
    │   ├── services/         # Domain services (business logic)
    │   └── vo/               # Value objects
    ├── application/
    │   ├── commands/         # Write operations (CQRS)
    │   ├── queries/          # Read operations (CQRS)
    │   └── services/         # Application-level orchestration
    ├── infrastructure/
    │   ├── database/         # SQLAlchemy ORM + engine management
    │   ├── repositories/     # Repository implementations (PostgreSQL + in-memory)
    │   └── extern/           # External service clients (HTTP, etc.)

**In-memory repositories** must always be provided alongside PostgreSQL implementations:
- `infrastructure/repositories/in_memory.py` — in-memory implementations of all repository interfaces
- Used by **unit tests only** — no database dependency
- Production/integration tests use PostgreSQL repositories exclusively
- SQLite is NOT supported; in-memory stores replace it for unit tests
    └── interface/
        ├── api/              # FastAPI route groups (one per resource)
        ├── schemas/          # Pydantic request/response models
        └── dependencies/     # Dependency injection (get_db, etc.)
```

**Layering rules:**
- **domain/** — pure Python, no framework imports. Depends on nothing else.
- **application/** — depends on domain only. Commands/queries orchestrate domain logic + repository interfaces.
- **infrastructure/** — depends on domain. Provides concrete implementations (PostgreSQL + in-memory).
- **interface/** — depends on everything. API boundary (Pydantic schemas, FastAPI routes).

**Test strategy:**
- **Unit tests** — use in-memory repositories (no database, fast)
- **Integration tests** — use PostgreSQL repositories (fail if DB not available, never skip)
- **Smoke tests** — test service starts and responds
- See `docs/development/TEST_CLASSIFICATION.md` for details

**Existing packages** (metadata-api, metadata-zone-coordinator) retain their current layout. **New packages** must follow DDD.

## General Guidelines

### Environment
- Always use `venv/bin/python` for all Python commands (never bare `python`)
- All paths are relative to the repository root

### Platform Services — Consumption Only
Platform-managed shared services (e.g., `platform-redis`, `platform-kafka`, `platform-kong`) are **strictly owned by the platform**.

**Allowed:**
- Consume platform services via published consumer contracts
- Create/update tenant-side ConfigMaps, Secrets, and manifest references
- Raise platform infrastructure requests if a shared service requires configuration changes

**Explicitly forbidden:**
- Modifying manifests inside `platform-argocd-apps/apps/platform/` or the `platform-*` namespaces
- Altering, patching, or overriding platform TLS secrets, CA bundles, or admin credentials
- Deploying a separate service instance to replace or shadow a platform service
- Using `kubectl apply/patch` to mutate platform-owned infrastructure resources

**Rationale:** Platform services enforce strict multi-tenant isolation, credential scoping, and access control. Consumers must adopt the published service contract without mutating the underlying infrastructure.

### Deployment — GitOps Controller Of Record
All services **MUST be deployed through the GitOps controller of record** for the target environment. Agents are **FORBIDDEN** to deploy manifests directly.

**Current direction:**
- Flux v2.9 is the only forward GitOps control-plane direction
- Dev and test Flux Git sources must use SSH
- Production Flux Git sources must use HTTPS
- **ArgoCD is frozen — no new ArgoCD development is authorized.** ArgoCD assets may only be touched for: (a) stability maintenance of existing unmigrated environments, or (b) controlled retirement during migration. No new ArgoCD Applications, AppProjects, ApplicationSets, hooks, or sync-wave flows.
- Migration governance is tracked in `docs/implementation/platform-gitops-control-plane-migration-plan.md` and `docs/architecture/adr/ADR-002-flux-gitops-control-plane-direction.md`

**Flux bootstrap assets location:**
All Flux bootstrap and control-plane assets live in `platform-foundation/flux/`:
- `flux/manifests/flux-system/` — committed controller configuration (CRDs, namespace, RBAC, controllers, services, network policies)
- `flux/bootstrap/<env>/flux-system.yaml` — environment-specific root self-management seeds
- `flux/sources/` — shared `GitRepository` catalog (`base/` + environment overlays)
- `flux/catalog/platform/` — shared platform wrapper `Kustomization` catalog
- `flux/catalog/tenants/` — shared tenant wrapper `Kustomization` catalog
- `flux/instances/<env>/` — canonical environment assemblies watched by the root `Kustomization`
- `scripts/flux_bootstrap.sh` — repeatable bootstrap script
- `scripts/kind.sh` — Kind cluster lifecycle (create/delete/load)

### Canonical Flux Layout

Agents must use the current canonical Flux structure:

- Environment entrypoints live under `flux/instances/<env>/`.
- Root self-management seeds live under `flux/bootstrap/<env>/flux-system.yaml`.
- Shared Git source definitions live under `flux/sources/`.
- Shared platform wrapper `Kustomization` objects live under `flux/catalog/platform/`.
- Shared tenant wrapper `Kustomization` objects live under `flux/catalog/tenants/`.

**Do not** introduce new canonical entrypoints under the retired `flux/overlays/` path.
That path is historical only; new work must target `flux/instances/` and the shared catalogs.

Tenant workload manifests remain owned by tenant repositories. Do not move tenant workload YAML into `platform-foundation`.

**Allowed:**
- Create/update Kustomize overlays consumed by the current controller of record
- Create/update Flux bootstrap, source, and `Kustomization` resources when they are part of the approved migration plan
- Maintain or retire existing ArgoCD assets only when required to keep current environments stable or to remove Argo ownership during migration
- Use repo-managed controller workflows that match the active controller of record; legacy ArgoCD workflows remain operational only for unmigrated environments
- Use `kubectl` to **inspect** state (get pods, logs, describe, events)

**Explicitly forbidden:**
- `kubectl apply -f` or `kubectl apply -k` to deploy manifests
- `kubectl create` to create Deployments, Services, ConfigMaps, Secrets, Jobs
- `kubectl patch` to modify running resources instead of GitOps-managed manifests
- Manual `kubectl rollout restart` to trigger deployments instead of controller reconciliation
- Creating new ArgoCD Applications, AppProjects, ApplicationSets, hooks, or sync-wave-based flows for forward development
- Expanding `platform-argocd-apps` scope except for controlled retirement or stability maintenance
- Allowing ArgoCD and Flux to reconcile the same resource set in the same environment at the same time

**Rationale:** GitOps remains the source of truth, but the controller may change over time. Manual `kubectl apply` creates drift regardless of controller. During the Flux transition, the key rule is single-controller ownership per resource set. ArgoCD is in retirement-only mode; all new development must use Flux.

### Port Safety — Process Killing
**Only kill processes on ports in the 10000–11999 range** (dev/test environments).

**Allowed:**
- `kill <pid>` or `kill <port>` for processes on ports **10000–10999** (dev) or **11000–11999** (test)
- `docker compose down` for compose-managed containers

**Explicitly forbidden:**
- Killing any process on ports **below 10000** (system services, host apps)
- Killing any process on ports **above 11999** (prod ports, other user services)
- Using `kill -9` or force-killing processes outside the 10000–11999 range

**Rationale:** Ports below 10000 may be used by system services (SSH, DNS, etc.) or other user applications. Never touch them. The agent only manages dev (10000+) and test (11000+) environments.

### Testing
- All tests must pass: `venv/bin/python -m pytest tests/ -q`
- Coverage must be ≥ 90%: `venv/bin/python -m pytest tests/ --cov=packages/ --cov-report=term`
- **No inline JSON payloads** — API request/response payloads must live in `tests/fixtures/*.json` files. Never embed JSON-like dicts (e.g. `{"delivery_id": "…", "producer_system": "…"}`) directly in test code. Use the `load_json_fixture()` helper from `conftest.py`.
  - *Exception:* trivial single-field dicts used for assertions (e.g. `assert data["status"] == "OK"`) are fine.

### Test Classification
Every test file must declare its classification in the module docstring:
- `classification: unit` — fast, no external dependencies (default run)
- `classification: integration` — requires external infrastructure (PostgreSQL, etc.)
- `classification: smoke` — quick sanity checks that a service starts and responds

Additionally, apply the matching pytest marker at module level:
```python
pytestmark = pytest.mark.unit      # or .integration, .smoke
```

Default `pytest` run excludes `integration` tests (`-m "not integration"`).
To run integration tests: `pytest -m integration` (requires `CONTROL_PLANE_DATABASE_URL`).

**Full documentation:** `docs/development/TEST_CLASSIFICATION.md`

### UI Testing — Playwright
Every significant UI change **must** have automated Playwright tests with test proof generation.

**Location:** `packages/metadata-web/tests/ui/*.spec.ts`

**Setup:**
```bash
# Install Playwright browsers (once)
cd packages/metadata-web && npx playwright install --with-deps chromium
```

**Run tests:**
```bash
# Requires dev stack running: docker compose -f docker-compose.dev.yml up -d
npx playwright test   # uses http://maas-ui.dev.jac.dot:10300 (from /etc/hosts)
```

**Generate test proof:**
```bash
# Runs tests + generates test proof JSON + publishes docs
./scripts/run_ui_tests.sh dev
```

**Validate test proofs (requires env):**
```bash
# Sources .env.<env>.local and validates all proof artifacts
./scripts/validate_test_proof.sh dev
./scripts/validate_test_proof.sh test
./scripts/publish_test_proof.sh dev
```

**Test proof artifacts:**
- JSON: `test-results/test-proof/0.1.0/ui/ui-playwright-001.json`
- Docs: `docs/test-proof/0.1.0/ui/ui-playwright-001.md` (via `publish_test_proof.sh`)

**Rules:**
- Each UI feature gets its own `.spec.ts` file (e.g. `topology-overview.spec.ts`)
- Tests require the full demo stack (BFF + backends) — no mocking
- Screenshots captured automatically on failure
- Test proof must be committed alongside the feature

### Approved Naming
- Use `Central Registry` / `CR`
- Use `IVC`

### Enum Values — ALL_CAPS
All Python `enum` values **MUST be `ALL_CAPS`**.

**Correct:**
```python
class DeliveryStatus(str, Enum):
    REGISTERED = "REGISTERED"
    COMPLETED = "COMPLETED"
    SUPERSEDED = "SUPERSEDED"
```

**Forbidden:**
```python
class DeliveryStatus(str, Enum):
    registered = "registered"   # ❌ lowercase
    Completed = "Completed"     # ❌ mixed case
```

### Enum Values — ALL_CAPS
All Python `enum` values **MUST be `ALL_CAPS`**.

**Correct:**
```python
class DeliveryStatus(str, Enum):
    REGISTERED = "REGISTERED"
    COMPLETED = "COMPLETED"
    SUPERSEDED = "SUPERSEDED"
```

**Forbidden:**
```python
class DeliveryStatus(str, Enum):
    registered = "registered"   # ❌ lowercase
    Completed = "Completed"     # ❌ mixed case
```

### API Payloads — snake_case Only
All API request bodies, response bodies, and query parameters **MUST use `snake_case`**.

**Forbidden in API payloads:**
- `camelCase` field names (e.g. `deliveryId`, `zoneId`, `syncStatus`)
- Pydantic `Field(alias="camelCase")` declarations
- `ConfigDict(populate_by_name=True)` used to enable camelCase

**Allowed in API payloads:**
- `snake_case` field names (e.g. `delivery_id`, `zone_id`, `sync_status`)
- `snake_case` everywhere — request bodies, response bodies, query parameters, path parameters

**CamelCase is only allowed in:**
- The React frontend (BFF responses are snake_case, the UI may display camelCase labels)
- External system integrations that mandate camelCase (e.g. AIStor/MinIO API)

**Rationale:** Consistent API contract. The API never transforms field names.

### Validation
```bash
python scripts/validate_snake_case.py
```

### Timestamps
All timestamps must be in UTC.

### Database
- SQLite is NOT supported. PostgreSQL only.
- `DATABASE_URL` is required.
- Database engine must be lazily initialized.

### Diagrams
- **Never use text/ASCII diagrams** in markdown files.
- **Always use Mermaid diagrams** (````mermaid` blocks) for any visual representation (architecture, flow, sequence, dependency, topology).
- **Always generate `.mmd` and `.svg` files** alongside every Mermaid diagram:
  - `.mmd` — the raw Mermaid source (single diagram per file)
  - `.svg` — the rendered image (generated via `npx @mermaid-js/mermaid-cli`)
  - Store both in `<current_dir>/images/` (relative to the document referencing them)
  - Naming: `<diagram-name>.mmd` / `<diagram-name>.svg`
  - Example: `docs/demo/foo.md` → `docs/demo/images/bar.mmd` + `docs/demo/images/bar.svg`
- If `mermaid-cli` is not installed, use: `npx --yes @mermaid-js/mermaid-cli -i <input.mmd> -o <output.svg>`

### Audit Columns
All database tables must include:
- `created_at_utc`, `created_by`
- `updated_at_utc`, `updated_by`
- `deleted_at_utc`, `deleted_by`

Actor context is passed via the `X-Actor` header.

## Document Store — Platform Knowledge Base

The platform document store indexes all Markdown documents from 3 repositories (134 documents) and is searchable via REST API and MCP tools.

**Skill**: `.pi/skills/document-store/SKILL.md` — auto-loaded by pi agents.

**Use the document store before:**
- Writing an implementation summary (check if one already exists)
- Making a platform decision (check past ADRs or lessons learned)
- Debugging a known issue (lessons learned may have the answer)
- Onboarding a new repository (consumer contracts, onboarding guides)
- Designing something new (check existing design docs)

**Quick commands:**
```bash
# Check service status
.pi/skills/document-store/scripts/docstore.sh status

# Search for documents
.pi/skills/document-store/scripts/docstore.sh search "ArgoCD bootstrap"

# Get full document content
.pi/skills/document-store/scripts/docstore.sh get <document_id>

# List lessons learned
.pi/skills/document-store/scripts/docstore.sh lessons

# Upload a document (auto-detects type and project)
.pi/skills/document-store/scripts/docstore.sh upload docs/implementation/summaries/2026-08-13_my-summary.md
```

**Document types**: `IMPLEMENTATION_SUMMARY`, `IMPLEMENTATION_PLAN`, `LESSONS_LEARNED`, `CONSUMER_CONTRACT`, `OPERATOR_MANUAL`, `DESIGN_DOC`, `RELEASE_NOTES`, `ADR`

**Projects indexed**: `platform-foundation` (64), `dq-made-easy` (58), `platform-argocd-apps` (12)

**Auto-upload rule**: After creating any implementation summary, lessons learned, or plan document, **always upload it** to the document store:
```bash
.pi/skills/document-store/scripts/docstore.sh upload <path-to-file.md>
```

**Sandbox note**: When running inside a container (pi sandbox), `localhost` is the container itself, not the host. Use:
```bash
DOCSTORE_URL=http://host.docker.internal:10093 .pi/skills/document-store/scripts/docstore.sh upload <path-to-file.md>
```

## Repository Structure

```
packages/
├── metadata-sdk/               # Core domain (legacy layout)
├── metadata-api/               # FastAPI service (legacy layout)
├── metadata-cli/               # CLI tool
├── metadata-streaming/         # Streaming abstraction
├── metadata-registry/          # Registry projection & persistence
├── metadata-utils/             # Shared utilities (UUIDv7, etc.)
├── metadata-zone-coordinator/  # Zone coordinator (legacy layout)
├── metadata-telemetry/         # Telemetry package (legacy layout)
├── metadata-health/            # Health endpoints (legacy layout)
├── metadata-control-plane/     # Telemetry ingestion + status (legacy layout)
├── metadata-central-repo/      # Delivery state + catalog (DDD layout)
└── metadata-bff/               # Backend For Frontend (thin proxy + React UI)
```

**Layout note:** Packages created after 2026-07-25 follow the DDD structure (see rule #3 above).

## Implementation Plan
See `docs/implementation/IMPLEMENTATION_PLAN.md` for current phase status and future stages.
See `docs/implementation/IMPLEMENTATION_Dev_Path.md` for the dev→test→prod roadmap (44 tasks, 6 phases).

## Implementation Summaries

**Every significant implementation effort must be documented as an implementation summary.**

### Rules
- **Location:** `docs/implementation/summaries/`
- **Format:** Markdown (`.md`)
- **Naming:** `YYYY-MM-DD_<functional-descriptive-name>.md`
  - Prefix with today's date (`YYYY-MM-DD`)
  - Followed by underscore and a functional, descriptive name
  - Use kebab-case for the name (e.g., `srp-refactoring`, `package-rename`, `policy-engine-integration`)
- **Content:**
  - Date and status
  - Objective and scope
  - Results table (metrics before/after)
  - New modules/files created
  - Known issues or remaining work
  - Next steps

### When to Generate
- After completing an implementation plan stage
- After executing a refactoring plan
- After completing any significant architectural change
- When a feature or epic is marked as done

### Example
```
docs/implementation/summaries/
├── 2026-07-23_package-rename-delivery-to-metadata.md
├── 2026-07-23_srp-refactoring.md
└── 2026-07-24_policy-engine-integration.md
```

### Index
Always update the index table in `docs/implementation/summaries/README.md` when adding a new summary.
