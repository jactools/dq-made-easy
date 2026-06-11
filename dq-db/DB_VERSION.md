# Database Schema Version History

This file tracks all database schema changes and version updates.

**Current Version: 1.4.0**

## Version Guidelines

When making database schema changes:
1. Update the version number following semantic versioning:
   - **MAJOR** (X.0.0): Breaking changes, data migration required
   - **MINOR** (1.X.0): New tables, columns, or non-breaking changes
   - **PATCH** (1.3.X): Bug fixes, index changes, constraint updates

2. Run the update script:
   ```bash
   ./dq-db/scripts/update_schema_version.sh <new_version>
   ```

3. Document the change below with:
   - Version number
   - Date
   - Description of changes
   - Migration notes (if applicable)

---

## Version History

### 1.4.0 - 2026-05-02
**Rule DSL Contract Persistence**

Changes:
- Added `rules.dsl` to persist the canonical DQ DSL source contract for each live rule
- Added `rule_versions.dsl` to preserve the canonical DSL document for every version snapshot and rollback target
- Added Alembic migration `dq-api/fastapi/migrations/versions/20260502_0030_add_rule_dsl_contract.py`
- Updated runtime schema metadata in `dq-db/mock-data/system_info.csv` to `db_schema_version=1.4.0`

Migration notes:
- Fresh environments need the new `dsl` columns present on both `rules` and `rule_versions`
- Existing databases must apply Alembic revision `20260502_0030` before using the DSL-backed rule write API

### 1.3.0 - 2026-03-11
**Rule Validation Persistence**

Changes:
- Added `rules.validation_status` column to persist latest rule validation result (`valid` / `invalid`)
- Added `rules.validated_at` timestamp to track when validation last ran
- Added migration script `dq-db/sql/migrations/add_validation_status.sql` for existing databases
- Updated runtime schema metadata in `dq-db/mock-data/system_info.csv` to `db_schema_version=1.3.0`

Migration notes:
- Fresh environments get `validation_status` and `validated_at` from `01_schema.sql`
- Existing databases should apply `dq-db/sql/migrations/add_validation_status.sql` (or reseed)

### 1.2.0 - 2026-03-11
**Logical Alias Layer for Rule Attributes**

Changes:
- Added `rules.alias_mappings` column to persist business-term alias mappings to physical attributes
- Added frontend alias mapping UI to `AssignAttributesModal`
- Added type-compatibility validation between inferred alias expectations and selected attribute data types
- Added backend alias compatibility diagnostics in `POST /v1/rules/:id/validate`

Migration notes:
- Fresh environments get `alias_mappings` from `01_schema.sql`
- Existing databases need `ALTER TABLE rules ADD COLUMN alias_mappings TEXT` if not reseeded

### 1.1.0 - 2026-03-11
**Reusable Filter Join Table Refactor**

Changes:
- Removed serialized reusable filter storage from the `rules` table
- Added `rule_reusable_filters` intersection table between `rules` and `reusable_filters`
- Updated seed data to load rule/filter associations through the join table
- Preserved the API/UI contract for reusable filters as arrays on the rule model

Migration notes:
- Existing seeded environments should reseed or migrate rule/filter associations into `rule_reusable_filters`
- Fresh environments now load rule/filter mappings from `rule_reusable_filters.csv`

### 1.0.0 - 2026-03-01
**Initial Schema Release**

Historical note:
- This entry reflects the original legacy schema release.
- The supported FastAPI data-catalog model has since moved to `data_objects_catalog`, `data_object_versions`, and `attributes_catalog` as the canonical catalog/version/attribute surface.

Tables created:
- `rules` - Data quality rules and templates
- `approvals` - Rule approval workflow
- `users` - User accounts and authentication
- `roles` - User role definitions
- `workspace_roles` - User workspace assignments
- `workspace_collaborators` - Workspace collaboration
- `workspaces` - Workspace isolation
- `attributes` - Legacy data catalog attributes table from the initial schema
- `data_objects` - Legacy catalog data objects table from the initial schema
- `data_sets` - Dataset definitions
- `data_products` - Data product definitions
- `audit` - Comprehensive audit trail
- `rule_attributes` - Rule-to-attribute mappings
- `rule_test_proof` - Rule testing and validation
- `profiling_tasks` - Data profiling job queue
- `profiling_results` - Profiling analysis results
- `rule_suggestions` - AI-generated rule suggestions
- `rule_executions` - Rule execution history
- `validation_failures` - Data quality validation failures
- `system_info` - System metadata and versioning

Features:
- Multi-tenant workspace isolation
- Role-based access control (RBAC)
- Complete audit trail
- Data quality rule lifecycle management
- Data profiling and rule suggestion pipeline
- Rule execution tracking

---

## Upcoming Changes

<!-- Document planned schema changes here -->

### Planned for 1.1.0
- TBD

---

## Migration Notes

### When updating from x.x.x to y.y.y
<!-- Add migration instructions here when needed -->

Example:
```sql
-- Migration from 1.0.0 to 1.1.0
-- No migrations required yet
```
