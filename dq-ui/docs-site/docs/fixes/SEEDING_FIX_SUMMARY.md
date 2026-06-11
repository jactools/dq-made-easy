# PostgreSQL Seeding Fix Summary

## Problem
`./scripts/start-containers.sh --seed-all` was failing with:
```
Failed resetting schema in container
ERROR: Postgres seed script failed
```

Additionally, validation showed empty rule versioning tables:
- `rule_versions: 0 rows` (expected >0)
- `rule_version_diffs: 0 rows`
- `rule_rollbacks: 0 rows`
- `rule_version_relationships: 0 rows`

## Root Causes

### 1. Missing Rule Versioning Initialization
The seed script was not applying `zzz_initialize_rule_versions.sql` after the schema reset, which meant:
- Rule versioning schema was created (`04_rule_versioning.sql`)
- But the `initialize_rule_versioning()` function was never called
- All 19 rules were never initialized with version 1

### 2. Overly Strict Validation Logic
The validation checked that ALL tables must have rows >0, but didn't account for:
- `rule_version_diffs`: Only populated when versions are compared/differ
- `rule_rollbacks`: Only populated when rollback operations occur
- `rule_version_relationships`: Only populated when versions have dependencies

These are **operational tables** populated during normal use, not initial seeding.

### 3. Poor Error Reporting
The `docker_psql_retry` function's error output was being suppressed, making it hard to debug failures.

### 4. Support-Only Zammad CSVs Were Included in Shared Seed Generation
The generic SQL seed generator was converting Zammad support CSVs into `generated_seed_*.sql` files and applying them to the main `dq` database. Those files belong to the separate Zammad support flow and must not be seeded into the shared app schema.

## Solution

### Changes to `scripts/seed_local_postgres.sh`

#### 1. Added Rule Versioning Initialization (After Line 327)
```bash
# Initialize rule versions for all existing rules
RULE_VERSIONING_INIT="${DB_ROOT}/init/zzz_initialize_rule_versions.sql"
if [ -f "$RULE_VERSIONING_INIT" ]; then
  echo "Initializing rule versions from $RULE_VERSIONING_INIT"
  if [ "$RUN_IN_CONTAINER" = true ]; then
    echo "-- Applying $(basename "$RULE_VERSIONING_INIT") into container"
    docker cp "$RULE_VERSIONING_INIT" "$CONTAINER":/tmp/ || true
    docker_psql_file_retry dq "/tmp/$(basename "$RULE_VERSIONING_INIT")" || { echo "Failed initializing rule versions in container"; exit 1; }
  else
    echo "-- Applying $RULE_VERSIONING_INIT locally"
    psql -v ON_ERROR_STOP=1 -U postgres -d dq -f "$RULE_VERSIONING_INIT" || { echo "Failed initializing rule versions locally"; exit 1; }
  fi
else
  echo "No $RULE_VERSIONING_INIT found; skipping rule version initialization"
fi
```

#### 2. Improved Error Reporting (Lines 208-223, 229-232)
Capture error output from `docker_psql_retry` calls:
```bash
reset_output=$(docker_psql_retry dq "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" 2>&1) || {
  echo "ERROR: Failed resetting schema in container"
  echo "Output: $reset_output"
  exit 1
}
```

#### 3. Split Validation into Required vs Optional Tables (Lines 376-442)

**REQUIRED_TABLES** (must have rows >0):
- Core seeded data tables: rules, users, roles, approvals, attributes, data_objects, etc.
- rule_versions (newly populated during initialization)

**OPTIONAL_TABLES** (allowed to be empty on fresh initialization):
- rule_version_diffs
- rule_rollbacks
- rule_version_relationships

### Changes to `dq-api/scripts/generate_sql_seeds.py`

The generator now skips the support-only Zammad CSVs:
- `dq-db/mock-data/zammad-admin.csv`
- `dq-db/mock-data/zammad-generated-users.csv`
- `dq-db/mock-data/zammad-user-template.csv`

This keeps the shared Postgres seed path focused on the core app database and prevents `COPY zammad_admin ...` failures during `common_startup.sh --with-observability`.

## Results

### Before
```
Table rule_versions: 0 rows
Table rule_version_diffs: 0 rows
ERROR: Table rule_version_diffs has 0 rows (expected >0)
Table rule_rollbacks: 0 rows
ERROR: Table rule_rollbacks has 0 rows (expected >0)
Table rule_version_relationships: 0 rows
ERROR: Table rule_version_relationships has 0 rows (expected >0)
Seeding validation failed: one or more required tables missing or empty.
Exit code: 2 ❌
```

### After
```
Table rule_versions: 19 rows ✓
Table rule_version_diffs: 0 rows (optional) ✓
Table rule_rollbacks: 0 rows (optional) ✓
Table rule_version_relationships: 0 rows (optional) ✓
Seeding validation passed: all required tables present and populated.
Exit code: 0 ✅
```

## Rule Versioning Initialization Output
```
Starting version initialization for all rules...
  Initialized 10 rules so far...
✓ Version initialization complete:
  - Initialized: 19 rules
  - Skipped (already versioned): 0 rules
  - Total rules: 19
✓ Verification passed: All rules have version 1 created
```

## Testing

### Run seeding manually:
```bash
bash scripts/seed_local_postgres.sh
```

### Run full stack with seeding:
```bash
./scripts/start-containers.sh --seed-all
```

## Files Modified
- `scripts/seed_local_postgres.sh` - Fixed seeding and validation logic
- `dq-api/scripts/generate_sql_seeds.py` - Excluded support-only Zammad CSVs from shared seed generation

## Commits
- `0d6ec34` - Fix PostgreSQL seeding: Add rule versioning initialization and improve validation
