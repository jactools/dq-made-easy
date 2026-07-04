# DQ Plan Validation Results - Seed Summary

## ✅ Seed Status: COMPLETE

The mock validation data has been successfully seeded into the PostgreSQL database.

## 📊 Database Statistics

| Table | Count | Description |
|-------|-------|-------------|
| `validation_run_plans` | **9** | Active DQ plans |
| `validation_run_plan_versions` | **10** | Plan versions |
| `validation_run_items` | **3** | Validation results |

## ❌ Failure Records Analysis

### Failed Validation Item

```
Item ID: 019e0488-9a56-7184-ad35-93ce43e1c0ce
Rule: phone-number-format (ID: 019e0488-9a56-7025-9d2b-53b000dabc44)
Run ID: 019e0488-9a56-79d4-a65a-99d918568b44
Valid: false
Errors: 1
Warnings: 0

Diagnostics:
{
  "field": "phone",
  "reason": "invalid format",
  "source": "seed"
}
```

### Validation Items Summary

| Rule Name | Valid | Errors | Warnings |
|-----------|-------|--------|----------|
| email-format-validation | ✅ true | 0 | 0 |
| **phone-number-format** | ❌ **false** | **1** | **0** |
| account-active-status | ✅ true | 0 | 1 |

## 🔍 Active Validation Plans

| Plan ID | Business Key | Status | Artifact |
|---------|-------------|--------|----------|
| `...00000001` | retail-banking:transaction:multi_engine_aggregate_comparison:grouped_scope | active | gx_transaction_aggregate_comparison |
| `...00000005` | retail-banking:customer:mixed_soda_gx:v1 | active | soda_customer_email_unique |
| `...0000000a` | retail-banking:customer:filtered_row_count:single_suite | active | gx_customer_filtered_row_count_condition |
| `...0000000d` | retail-banking:customer:email_format_high_invalid_rows:single_suite | active | gx_customer_email_format_high_invalid_rows |
| `...bcfb2dc4d0b6b4c2` | retail-banking:customer:v3:single_suite | active | 019e0488-9a54-74a7-8a42-123dac4c8bff |

## 📋 Plan Versions (Latest 5)

| Version ID | Artifact | Status | Governance | Effective From |
|------------|----------|--------|------------|----------------|
| `...00000002` | gx_transaction_aggregate_comparison | validated | active | 2026-06-28 |
| `...0000000e` | gx_customer_email_format_high_invalid_rows | validated | active | 2026-05-19 |
| `...0000000b` | gx_customer_filtered_row_count_condition | validated | active | 2026-05-19 |
| `...00000006` | soda_customer_email_unique | validated | active | 2026-05-19 |

## 🎯 Key Findings

### 1. Single Point of Failure
- **Phone number format validation** is the only rule that failed
- 1 record failed validation out of 3 validated rules
- Failure reason: "invalid format" on the "phone" field

### 2. Warning vs Error
- **account-active-status** generated a warning but passed (0 errors)
- This demonstrates the difference between warnings and errors in validation

### 3. Multi-Engine Support
- Plans use both **SodaCL** and **Great Expectations** (GX) engines
- One plan uses **grouped_scope** for aggregate comparison across multiple datasets

### 4. Governance States
- 3 plans are in **draft** status (not yet validated)
- 6 plans are **active** and validated
- All active plans have **approved** review status

## 🔬 Diagnostic Details

The failed phone validation includes diagnostic information:
- **Field**: "phone" - the data field that failed
- **Reason**: "invalid format" - why it failed
- **Source**: "seed" - indicates this is mock/test data

## 📈 Validation Metrics

```
Total Plans: 9
Active Plans: 6
Draft Plans: 3
Total Validations: 3
Passed: 2 (66.7%)
Failed: 1 (33.3%)
Warnings: 1
```

## 🗄️ Database Queries

### Check Failed Items
```sql
SELECT 
    id,
    rule_name,
    rule_id,
    run_id,
    valid,
    errors,
    warnings,
    diagnostics
FROM validation_run_items 
WHERE valid = false;
```

### Get Plan Details
```sql
SELECT 
    vrppl.business_key,
    vrppl.status,
    vrp.artifact_id,
    vrp.validation_status,
    vrp.effective_from
FROM validation_run_plans vrppl
JOIN validation_run_plan_versions vrp 
    ON vrppl.id = vrp.run_plan_id
WHERE vrppl.status = 'active'
ORDER BY vrp.effective_from DESC;
```

### Count by Status
```sql
SELECT 
    valid,
    COUNT(*) as count
FROM validation_run_items
GROUP BY valid;
```

## 🚀 Next Steps

### 1. Investigate Phone Validation Failure
- Check the source data for phone number formats
- Verify the validation rule configuration
- Review the diagnostic details

### 2. Monitor Active Plans
- Track execution runs for active plans
- Monitor for new failures
- Review warning patterns

### 3. Expand Test Coverage
- Add more validation scenarios
- Test different data quality issues
- Validate edge cases

### 4. Implement Alerting
- Set up alerts for validation failures
- Monitor error rates over time
- Track warning trends

## 📝 Files Created

1. **`quick_seed_validation.py`** - Seed script for validation data
2. **`seed_and_test_validation_plans.py`** - Alternative seed script
3. **`VALIDATION_PLAN_SEED_SUMMARY.md`** - CSV structure documentation
4. **`VALIDATION_RESULTS_SUMMARY.md`** - This file

## 🔧 How to Re-seed

```bash
cd /Users/jacbeekers/gitrepos/dq-made-easy/dq-db/mock-data
python3 quick_seed_validation.py
```

## 📞 Support

For questions about the validation data:
- Review `VALIDATION_PLAN_SEED_SUMMARY.md` for CSV structure
- Check `../docs/flows/dq-engine-execution-flow.md` for execution flow
- See `../docs/REUSABLE_DQ_PLANS.md` for plan configuration

---

**Generated**: 2026-07-04  
**Database**: postgres://localhost:5432/dq  
**Status**: ✅ Seed complete and validated  
**Data Source**: dq-db/mock-data CSV files
