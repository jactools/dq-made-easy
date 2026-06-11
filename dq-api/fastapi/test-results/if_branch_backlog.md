# If-Branch Coverage Backlog

Generated from:
- Command: `pytest -k "not test_every_if_statement_has_two_tested_branches" --cov-fail-under=0`
- Report script: `scripts/if_backlog_report.py`

Current totals:
- Files with missing if-branch outcomes: 24
- Missing if statements (at least one uncovered outcome): 130

## Priority Queue (highest missing first)
1. `app/infrastructure/repositories/postgres_admin_repository.py` (34/41)
2. `app/infrastructure/repositories/in_memory_rules_repository.py` (18/32)
3. `app/infrastructure/repositories/postgres_rules_repository.py` (16/40)
4. `app/infrastructure/repositories/postgres_approvals_repository.py` (7/10)
5. `app/infrastructure/repositories/app_config_defaults.py` (6/21)
6. `app/api/v1/endpoints/rules.py` (6/17)
7. `app/api/v1/endpoints/rule_compat.py` (6/7)
8. `app/api/v1/endpoints/auth.py` (5/27)
9. `app/infrastructure/repositories/postgres_testing_repository.py` (4/15)
10. `app/core/auth.py` (3/42)
11. `app/api/v1/endpoints/catalog_governance.py` (3/13)
12. `app/infrastructure/repositories/postgres_app_config_repository.py` (3/9)

## First Batch Completed
- Added focused tests in `tests/api/test_catalog_governance_helpers.py`.
- Covered helper and endpoint branch logic for:
  - term key normalization and alias extraction paths
  - catalog term loading skip/duplicate paths
  - revalidation job decode invalid paths
  - create job validation/defaulting paths
  - status lookup invalid/valid metadata paths

Impact after batch:
- `app/api/v1/endpoints/catalog_governance.py`: missing-if reduced from 13 -> 3
- Global missing-if reduced from 179 -> 169

## Second Batch Completed
- Added focused tests in `tests/api/test_reusable_assets_helpers.py`.
- Covered helper and endpoint branch logic for:
  - filter expression validation guards and parser edge cases
  - reusable filter creation fallback/default branches
  - reusable join string/JSON normalization branches
  - delete filter/join success + 400 + 404 branches

Impact after batch:
- `app/api/v1/endpoints/reusable_assets.py`: missing-if reduced from 18 -> 2
- Global missing-if reduced from 169 -> 153

## Third Batch Completed
- Added focused tests in `tests/infrastructure/unit/repositories/postgres/test_rules_repository_postgres.py`.
- Covered repository branch logic for:
  - early-return/not-found branches across rule/version/rollback methods
  - rollback error paths (current version, missing current, missing target)
  - rollback success path metadata and timestamp fallback branch
  - reusable asset delete branches (`missing`, `in use`, and guard exceptions)
  - helper branches (`_display_name_for_tag`, `_username_for_user`, tag filtering, lookup loaders)

Impact after batch:
- `app/infrastructure/repositories/postgres_rules_repository.py`: missing-if reduced from 39 -> 16
- Global missing-if reduced from 153 -> 130
