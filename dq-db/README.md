# dq-db: Database Management

This directory contains all database-related configuration, initialization scripts, and utilities for Data Quality Made Easy.

## Structure

```
dq-db/
├── init/              # Database initialization and seeding
│   ├── 01_schema.sql  # Core database schema
│   ├── 02_profiling_schema.sql # Profiling/suggestions schema
│   ├── 03_profiling_demo_seed.sql # Demo profiling + suggestions data
│   ├── generated_seed_*.sql  # Generated seed data (tables, records)
│   ├── backup/        # Backup of schema and seeds
│   └── generated_backup/  # Generated backups from runs
├── mock-data/         # CSV seed sources + external JSON payloads
│   └── archive/       # Temporary/scratch CSVs not used by generation
└── scripts/           # Legacy wrapper scripts
    └── seed_local_postgres.sh  # Delegates to root scripts/seed_local_postgres.sh
```

## Files

### `ERD.md`
Reconstructed database entity-relationship diagram for the current live schema.

Open it here: [DATABASE_ERD.md](../docs/technical/DATABASE_ERD.md)

### `init/01_schema.sql`
Core database schema defining all tables:
- `rules` - Data quality rules
- `approvals` - Rule approval workflow
- `users` - User accounts and permissions
- `roles` - User roles
- `data_objects` - Lifecycle-managed data objects
- `data_sets` - Datasets
- `data_products` - Data products
- `data_objects_catalog` - Dataset-scoped catalog objects
- `data_object_versions` - Version history per catalog object
- `attributes_catalog` - Versioned attributes belonging to a specific data object version
- `audit` - Audit trail
- `workspaces` - Workspace definitions

### `init/generated_seed_*.sql`
Auto-generated seed data files containing:
- Mock workspaces
- Test rules (especially retail-banking rules)
- Sample users and roles
- Data product, dataset, data object, and versioned attribute information

### `scripts/seed_local_postgres.sh`
Legacy wrapper for compatibility. Delegates to the canonical repository-level seed script.

### `scripts/validate_seed_headers.py`
Validates generated `COPY ... FROM stdin` seed headers against the current table definitions in `dq-db/init`.

Usage:
```bash
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python dq-db/scripts/validate_seed_headers.py
```

This check normalizes unquoted PostgreSQL identifiers, so DDL names like `createdBy` correctly match stored column names like `createdby`.

Usage:
```bash
./scripts/seed_local_postgres.sh
```

Notes:
- SQL generation skips temporary CSV files ending in `-temp.csv` or `_temp.csv`.
- Keep temporary/scratch CSVs in `dq-db/mock-data/archive/`.

## Docker Integration

The `docker-compose.yml` file builds a custom `dq-db` image from `dq-db/Dockerfile.db`.

That image contains:
- `/docker-entrypoint-initdb.d` (copied from `dq-db/init`) for first-time PostgreSQL initialization
- `/opt/dq-db/init` and `/opt/dq-db/mock-data` for operational reseeding
- `/opt/dq-db/scripts/reseed_in_container.sh` for reseeding while the container is running
- `/opt/dq-db/scripts/reseed_running_db.sh` as the stable in-image reseed entrypoint

Because these files are baked into the image, reseeding does not rely on host bind mounts.

- **Database**: PostgreSQL 18
- **User**: postgres
- **Password**: postgres (development only)
- **Database Name**: dq
- **Port**: 5432

## Workflow

1. When Docker Compose starts, PostgreSQL container is created
2. SQL files in `/docker-entrypoint-initdb.d` initialize schema + seed data on first boot
3. For live reseeding, run `bash ./scripts/reseed_running_db.sh` to execute the in-image reseed script
4. Database is ready for application use

Repository-independent operations:

```bash
# Reseed from inside a running container
docker exec -it <db-container-name> bash /opt/dq-db/scripts/reseed_running_db.sh

# Healthcheck-safe verification (no reseed)
docker exec -i <db-container-name> bash -lc 'test -x /opt/dq-db/scripts/reseed_running_db.sh && psql -U postgres -d dq -c "SELECT 1" >/dev/null'
```

Related image-bundled setup:

- Keycloak realm import is bundled in the `dq-keycloak` image (`/opt/keycloak/data/import/dqprototype-realm.json`).
- Kong API gateway bootstrap is bundled in the `dq-kong` image (`/opt/dq-kong/scripts/bootstrap_kong.sh`) and runs at container startup.

## Mock Data

The generated seed files contain realistic retail-banking test data:
- **20+ Quality Rules** for account, transaction, and customer validation
- **10+ Rules** with different approval statuses (active, pending, rejected)
- **Rule Coverage**: Completeness, Accuracy, Consistency, Timeliness, Validity, Uniqueness dimensions
- **Workspaces**: retail-banking (primary), corporate-banking, and other banking domains
- Source CSV headers mirror the ORM field names used by the seed generator.
- `rules.csv` uses `created_by` in the source data; the generator maps it to the legacy PostgreSQL `createdby` column when emitting `COPY` files.
- JSON payloads are stored as separate files under entity-specific subfolders such as `mock-data/rules/<rule-id>/dsl.json` and `mock-data/validation-run-plan-versions/<version-id>/artifact_snapshot_json.json`.
- The SQL seed generator resolves `.json` file references in CSV cells and inlines the file contents into the generated `COPY` scripts.

### Git-First Rule Registry

The canonical rule registry is tracked in Git under `dq-db/mock-data` using one CSV row per entity plus per-entity JSON payload folders:

```text
mock-data/
├── rules.csv
├── rules/<rule-id>/dsl.json
├── rule_versions.csv
├── rule_versions/<version-id>/dsl.json
├── rule_versions/<version-id>/tags.json
├── gx-suite-registry.csv
└── gx-suite-registry/<gx-suite-id>/gx_suite.json
```

Workflow:
- Update the CSV row and the matching JSON payload file(s) in the same commit.
- Run `scripts/validate_rule_registry_layout.sh` before seeding or publishing the registry.
- Use `scripts/seed_local_postgres.sh` or the stack seed flow to promote the committed registry into Postgres.

## Database Schema Versioning

**Current Schema Version: 1.3.0**

The database schema version is automatically tracked using git hooks and displayed in the UI system information modal.

### Automated Versioning with Git Hooks

A pre-commit git hook automatically detects schema changes and ensures version updates:

1. **Install the git hook:** (one-time setup)
   ```bash
   ./dq-db/scripts/install-git-hooks.sh
   ```

2. **Commit schema changes:** The hook runs automatically
   - **Prompt mode** (default): Asks what to do when schema changes detected
   - **Auto mode**: Automatically increments PATCH version
   - **Strict mode**: Blocks commits without version update
   - **Skip mode**: Bypasses check (not recommended)

3. **Control hook behavior:**
   ```bash
   # Auto-increment PATCH version
   DB_VERSION_AUTO_INCREMENT=auto git commit -m "fix: update schema"
   
   # Strict enforcement
   DB_VERSION_AUTO_INCREMENT=strict git commit -m "feat: add table"
   
   # Skip check (not recommended)
   DB_VERSION_AUTO_INCREMENT=skip git commit -m "wip: schema"
   ```

### Manual Version Updates

When you need MAJOR or MINOR version bumps:

```bash
./dq-db/scripts/update_schema_version.sh <new_version>
```

This script:
- Updates `system_info.csv` with new version and timestamp
- Records the git commit hash for traceability
- Updates `DB_VERSION.md` header
- Provides next-step instructions

### Making Schema Changes

When modifying the database schema (tables, columns, constraints, indexes):

1. **Modify the schema files:**
   - Update `init/01_schema.sql` or other schema files
   - Update seed data in `mock-data/` if needed

2. **Commit your changes:**
   ```bash
   git add dq-db/
   git commit -m "feat(db): add new table for feature"
   ```
   - The git hook detects schema changes
   - Choose to auto-increment or update manually
   - Hook records git commit hash automatically

3. **Document in `DB_VERSION.md`:**
   - Add a new version entry
   - Describe what changed and why
   - Include migration notes if needed

4. **Test the changes:**
   ```bash
   ./scripts/stop_stack.sh
   ./scripts/start-containers.sh --seed-all
   ```

5. **Verify in UI:**
   - Click version number in header
   - Check Database section shows new version and git commit

### Version Guidelines

Follow semantic versioning:
- **MAJOR** (X.0.0): Breaking changes requiring data migration
- **MINOR** (1.X.0): New tables/columns, backward-compatible changes
- **PATCH** (1.0.X): Bug fixes, index optimizations, constraint updates

### Version History

See [DB_VERSION.md](DB_VERSION.md) for complete version history and migration notes.

For detailed checklist and troubleshooting, see [SCHEMA_CHANGE_CHECKLIST.md](SCHEMA_CHANGE_CHECKLIST.md).
