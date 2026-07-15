# Validation Run Plan Seed Summary

## Overview

This document summarizes the DQ Plan CSV entries in `dq-db/mock-data/` that should be seeded into the PostgreSQL database, along with their associated failure records.

## Seeding Process

The mock data is seeded through the Docker container:
```bash
docker-compose --profile seed up dq-seed
```

This runs `/workspace/dq-db/scripts/run_db_seed_container.sh` which:
1. Sanitizes CSV files (handles JSON special characters)
2. Generates SQL seed files from CSVs
3. Resets the database schema
4. Applies Alembic migrations
5. Seeds all tables from CSV files
6. Validates row counts

## Validation Run Plans CSV

### File: `validation-run-plans.csv`

**Total Rows**: 10 plans

| Plan ID | Business Key | Status | Active Version | Last Dispatched |
|---------|-------------|--------|----------------|-----------------|
| `019e0488-9a56-7caa-b001-000000000005` | `retail-banking:customer:mixed_soda_gx:v1` | active | `...00000006` | - |
| `019e0488-9a56-7caa-b001-00000000000a` | `retail-banking:customer:filtered_row_count:single_suite` | active | `...0000000b` | - |
| `019e0488-9a56-7caa-b001-00000000000d` | `retail-banking:customer:email_format_high_invalid_rows:single_suite` | active | `...0000000e` | - |
| `019e0488-9a54-7425-bf22-812b600f1ffe` | `retail-banking:transaction:quantile:single_suite` | active | `...80bdcbf` | - |
| `019e0488-9a54-7c1c-bcfb-2dc4d0b6b4c2` | `retail-banking:customer:v3:single_suite` | active | `...c73ac5bbfe5e` | `019e0488-9a54-720c-ad63-80fc923aeb82` |
| `019e0488-9a54-7acc-bd27-3c4bcc7a86c8` | `retail-banking:contact:v23:single_suite` | draft | - | - |
| `019e0488-9a54-722f-9f71-08af2a69691b` | `retail-banking:transaction:v9:single_suite` | active | `...63b3dffd4882` | `019e0488-9a54-7714-a768-28870e5765f2` |
| `019e0488-9a54-71e3-8325-5be6bff6fb38` | `retail-banking:inventory:v24:single_suite` | draft | - | - |
| `019e0488-9a56-7d10-b001-000000000001` | `retail-banking:transaction:multi_engine_aggregate_comparison:grouped_scope` | active | `...00000002` | - |

**Statuses**:
- 7 plans are **active**
- 2 plans are **draft**

### File: `gx-run-plans.csv`

**Total Rows**: 5 plans (GX-specific)

Same as validation-run-plans but for GX execution engine.

## Validation Run Plan Versions

### File: `validation-run-plan-versions.csv`

**Total Rows**: 10 versions

Key versions for execution:

| Version ID | Run Plan ID | Artifact ID | Status | Effective From |
|------------|-------------|-------------|--------|----------------|
| `019e0488-9a56-7caa-b001-000000000006` | `...00000005` | `soda_customer_email_unique` | validated | 2026-05-19 |
| `019e0488-9a56-7caa-b001-00000000000b` | `...0000000a` | `gx_customer_filtered_row_count_condition` | validated | 2026-05-19 |
| `019e0488-9a56-7caa-b001-00000000000e` | `...0000000d` | `gx_customer_email_format_high_invalid_rows` | validated | 2026-05-19 |
| `019e0488-9a54-7621-b273-c73ac5bbfe5e` | `...bcfb2dc4d0b6b4c2` | `019e0488-9a54-74a7-8a42-123dac4c8bff` | validated | 2026-04-12 |
| `019e0488-9a54-781f-99cf-63b3dffd4882` | `...9f71-08af2a69691b` | `019e0488-9a54-768e-aa7c-e1115ffb25a1` | validated | 2026-04-12 |

## Validation Run Items (Failure Records)

### File: `validation-run-items.csv`

**Total Rows**: 3 items

| Item ID | Run ID | Rule ID | Rule Name | Valid | Errors | Warnings |
|---------|--------|---------|-----------|-------|--------|----------|
| `019e0488-9a56-7d06-afe1-75e21a025b00` | `...9d4-a65a-99d918568b44` | `...9b2b-0ec5dadbbe34` | email-format-validation | **true** | 0 | 0 |
| `019e0488-9a56-7184-ad35-93ce43e1c0ce` | `...9d4-a65a-99d918568b44` | `...9d2b-53b000dabc44` | phone-number-format | **false** | **1** | 0 |
| `019e0488-9a56-7502-b07e-f1207c4fc1a8` | `...9d4-a65a-99d918568b44` | `...a35b-ff7b9de2d5b4` | account-active-status | **true** | 0 | **1** |

### Failure Records Analysis

**Total Failed Items**: 1 out of 3

#### 1. Phone Number Format Validation Failure

```
Item ID: 019e0488-9a56-7184-ad35-93ce43e1c0ce
Rule: phone-number-format (ID: 019e0488-9a56-7025-9d2b-53b000dabc44)
Run ID: 019e0488-9a56-79d4-a65a-99d918568b44
Errors: 1
Warnings: 0
Valid: false

Diagnostic JSON: validation-run-items/019e0488-9a56-7184-ad35-93ce43e1c0ce/diagnostics.json
```

**Root Cause**: The phone number validation rule failed on 1 record. This is likely a mock data rule designed to test failure scenarios.

#### 2. Account Active Status Warning

```
Item ID: 019e0488-9a56-7502-b07e-f1207c4fc1a8
Rule: account-active-status (ID: 019e0488-9a56-73e6-a35b-ff7b9de2d5b4)
Run ID: 019e0488-9a56-79d4-a65a-99d918568b44
Errors: 0
Warnings: 1
Valid: true

Diagnostic JSON: validation-run-items/019e0488-9a56-7502-b07e-f1207c4fc1a8/diagnostics.json
```

**Note**: This is a **warning**, not a failure (errors=0, valid=true).

## GX Execution Runs

### File: `gx-execution-runs.csv`

**Total Rows**: 2 execution runs

Both are **succeeded**:

| Run ID | Suite ID | Status | Engine | Submitted | Completed |
|--------|----------|--------|--------|-----------|-----------|
| `019e0488-9a54-720c-ad63-80fc923aeb82` | `...8a42-123dac4c8bff` | succeeded | pyspark | 2026-04-12 | 2026-04-12 |
| `019e0488-9a54-7714-a768-28870e5765f2` | `...aa7c-e1115ffb25a1` | succeeded | pyspark | 2026-04-12 | 2026-04-12 |

## Expected Database State After Seeding

### Tables to be Seeded

1. **validation_run_plans** - 9 rows (active plans)
2. **validation_run_plan_versions** - 10 rows
3. **validation_run_items** - 3 rows (1 with failure)
4. **gx_execution_runs** - 2 rows (all succeeded)

### Expected Query Results

```sql
-- Count of failed validation items
SELECT COUNT(*) FROM validation_run_items WHERE valid = false;
-- Expected: 1

-- Failed items with details
SELECT id, rule_name, errors, warnings FROM validation_run_items WHERE valid = false;
-- Expected: 1 row (phone-number-format)

-- Total validation runs
SELECT COUNT(*) FROM validation_run_plans WHERE status = 'active';
-- Expected: 7

-- Validation run items by rule
SELECT rule_name, COUNT(*) FROM validation_run_items GROUP BY rule_name;
-- Expected:
--   email-format-validation: 1
--   phone-number-format: 1 (with errors)
--   account-active-status: 1 (with warnings)
```

## How to Seed and Test

### Option 1: Docker Seed (Recommended)

```bash
cd /Users/jacbeekers/gitrepos/dq-made-easy
docker-compose --profile seed up dq-seed
```

### Option 2: Direct PostgreSQL Connection

```bash
# Connect to database
psql -h localhost -U postgres -d dq

# Check validation run plans
SELECT id, business_key, status FROM validation_run_plans ORDER BY created_at;

# Check failed items
SELECT id, rule_name, errors, warnings FROM validation_run_items WHERE valid = false;
```

### Option 3: Run the Seed Script

```bash
cd /Users/jacbeekers/gitrepos/dq-made-easy/dq-db/mock-data
# Note: This requires Python environment with all dependencies
python3 seed_and_test_validation_plans.py
```

## Files to Check After Seeding

1. `validation-run-plan-versions/{version-id}/artifact_snapshot.json` - Suite definitions
2. `validation-run-plan-versions/{version-id}/execution_contract_snapshot.json` - Execution configuration
3. `validation-run-items/{item-id}/diagnostics.json` - Failure details
4. `validation-run-items/{item-id}/conflicts.json` - Conflict information

## Key Insights

1. **Single Failure Point**: Only 1 rule failed (phone-number-format) out of 3 validated rules
2. **Warning vs Error**: 1 rule generated a warning but passed (account-active-status)
3. **No Execution Runs with Failures**: The GX execution runs are all marked as "succeeded"
4. **Data Quality Pattern**: The mock data simulates a realistic scenario where:
   - Email format validation passes
   - Phone format validation fails on some records
   - Account status check generates warnings but passes

## Related Documentation

- [DQ Plan Execution Flow](/Users/jacbeekers/gitrepos/dq-made-easy/docs/flows/dq-engine-execution-flow.md)
- [Reusable DQ Plans](/Users/jacbeekers/gitrepos/dq-made-easy/docs/REUSABLE_DQ_PLANS.md)
- [Docker Seed Process](/Users/jacbeekers/gitrepos/dq-made-easy/dq-db/scripts/run_db_seed_container.sh)

---

**Generated**: 2026-07-04  
**Data Version**: Mock data from May 2026  
**Status**: Ready for seeding and testing
