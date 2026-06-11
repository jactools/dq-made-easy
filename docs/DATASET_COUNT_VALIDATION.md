# Dataset Count Validation Control

## Overview

As part of the seeding process, a control has been added to ensure the number of data sets in the database per workspace matches the number of data sets in the mock-data CSV file (`dq-db/mock-data/data-sets.csv`).

This validation helps prevent data integrity issues where:
- CSV mock-data is updated with new datasets but the count is not reflected in the database after seeding
- Database migrations or manual edits result in missing or extra datasets
- Workspace-specific dataset counts are inconsistent between configuration and actual database state

## Implementation

### Automated Validation (During Seeding)

The validation is automatically executed at the end of the seeding process in `dq-db/scripts/apply_seeds_in_container.sh`:

1. **CSV Count Phase**: Reads `dq-db/mock-data/data-sets.csv` and counts datasets per workspace
2. **Database Query Phase**: Queries the database for actual dataset counts per workspace
3. **Comparison Phase**: Compares expected vs actual counts
4. **Reporting Phase**: Reports results with detailed mismatches
5. **Exit Code**: Returns exit code 1 if mismatches found, 0 if all counts match

The validation **fails the seeding process** if any mismatches are detected, preventing the system from running with incomplete or incorrect data.

### Standalone Validation

Two standalone scripts are provided for manual validation:

#### Bash Script
```bash
scripts/validate_datasets_per_workspace.sh [csv_file] [db_host] [db_port] [db_name] [db_user]
```

Environment variables (optional):
- `DQ_DB_HOST` - Database host (default: localhost)
- `DQ_DB_PORT` - Database port (default: 5432)  
- `DB_NAME` - Database name (default: dq)
- `DB_USER` - Database user (default: postgres)
- `POSTGRES_PASSWORD` - Database password

Example:
```bash
./scripts/validate_datasets_per_workspace.sh
# or with custom database
DQ_DB_HOST=staging.example.com ./scripts/validate_datasets_per_workspace.sh
```

#### Python Script
```bash
python3 scripts/validate_datasets_per_workspace.py [csv_file] [--db-host HOST] [--db-port PORT] [--db-name NAME] [--db-user USER] [--db-password PASSWORD]
```

Options:
- `csv_file` - Path to data-sets.csv (default: `dq-db/mock-data/data-sets.csv`)
- `--db-host` - Database host (default: localhost)
- `--db-port` - Database port (default: 5432)
- `--db-name` - Database name (default: dq)
- `--db-user` - Database user (default: postgres)
- `--db-password` - Database password (default: from POSTGRES_PASSWORD env var)

Example:
```bash
python3 scripts/validate_datasets_per_workspace.py
# or with detailed output
python3 scripts/validate_datasets_per_workspace.py --db-host localhost --db-port 5432
```

## Current Mock-Data Configuration

As of 2026-05-31, the mock-data contains:

| Workspace | Dataset Count |
|-----------|---------------|
| corporate-banking | 1 |
| retail-banking | 6 |
| risk-compliance | 1 |
| treasury | 2 |
| **Total** | **10** |

Note: 2 datasets have empty workspace_id (standalone datasets) and are not counted in workspace-specific totals.

## Output Examples

### Success Case
```
== Validating dataset counts per workspace ==
Expected dataset counts from CSV:
  corporate-banking: 1
  retail-banking: 6
  risk-compliance: 1
  treasury: 2

Actual dataset counts from database:
  corporate-banking: 1
  retail-banking: 6
  risk-compliance: 1
  treasury: 2

✓ corporate-banking: 1 datasets
✓ retail-banking: 6 datasets
✓ risk-compliance: 1 datasets
✓ treasury: 2 datasets

✓ All workspace dataset counts match
```

### Failure Case (Mismatch Detected)
```
== Validating dataset counts per workspace ==
Expected dataset counts from CSV:
  retail-banking: 6

Actual dataset counts from database:
  retail-banking: 5

✗ MISMATCH workspace_id='retail-banking': expected 6, got 5

ERROR: Found 1 workspace(s) with dataset count mismatches
```

## Integration with Seeding Process

When running the standard seeding process:

```bash
./scripts/seed_all.sh
# or
./scripts/seed_local_postgres.sh
# or via compose
docker-compose --profile seed run --rm db-seed
```

The validation runs automatically after all seed SQL is applied. If validation fails:
1. Error message is displayed
2. Seeding process exits with code 1
3. System remains in inconsistent state (requires investigation)

## When to Update Mock-Data

When adding new datasets to the system:

1. Add the new row(s) to `dq-db/mock-data/data-sets.csv`
2. Ensure the `workspace_id` field is populated with the correct workspace
3. Run seeding (`./scripts/seed_all.sh` or `./scripts/seed_local_postgres.sh`)
4. Validation will confirm the new dataset count is correct
5. If validation fails, review the CSV for formatting issues or missing workspace assignments

## Troubleshooting

### Validation Fails After Adding Datasets

1. **Check CSV Format**: Ensure CSV is valid with all fields properly quoted/escaped
2. **Verify Workspace ID**: Confirm each dataset row has the correct `workspace_id` value
3. **Check for Duplicates**: Ensure no accidental duplicate rows in the CSV
4. **Review Database State**: Query the database directly:
   ```sql
   SELECT workspace_id, COUNT(*) FROM data_sets 
   GROUP BY workspace_id ORDER BY workspace_id;
   ```

### Validation Passes but Expected Counts Wrong

If you manually edited the CSV but the counts don't seem right:
1. Run the standalone validation script to get detailed information
2. Verify the CSV has not been corrupted (check line endings, encoding, etc.)
3. Clear workspace-specific filter in editor and recount manually

### Cannot Connect to Database

- Ensure database is running and accessible
- Check `DQ_DB_HOST`, `DQ_DB_PORT`, `DB_USER`, `POSTGRES_PASSWORD` environment variables
- Verify firewall/network connectivity if using remote database
- Test connection: `psql -h host -p port -U user -d dq`

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All dataset counts match; validation passed |
| 1 | Dataset count mismatch detected; seeding failed |
