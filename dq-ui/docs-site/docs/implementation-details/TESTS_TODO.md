# Test Coverage TODOs

Generated: 2026-04-06

Replace of TODOs with prioritized file-level targets derived from the latest coverage run. Work from top → down; each item is a focused test target.

1. [ ] Test `dq-api/fastapi/app/api/v1/endpoints/testing.py` — high missing-lines count (priority)
2. [ ] Test `dq-api/fastapi/app/infrastructure/repositories/postgres_testing_repository.py`
3. [ ] Test `dq-api/fastapi/app/infrastructure/repositories/in_memory_rules_repository.py`
4. [ ] Test `dq-api/fastapi/app/api/v1/endpoints/rules.py`
5. [ ] Test `dq-api/fastapi/app/infrastructure/repositories/postgres_rules_repository.py`
6. [ ] Test `dq-api/fastapi/app/core/telemetry.py`
7. [ ] Test `dq-api/fastapi/app/infrastructure/repositories/postgres_admin_repository.py`
8. [ ] Test `dq-api/fastapi/app/api/v1/endpoints/profiling_enqueue.py`
9. [ ] Test `dq-api/fastapi/app/middleware/auth_compatibility.py`
10. [ ] Test `dq-api/fastapi/app/application/services/rule_compiler.py`

Notes:
- These entries replace the prior high-level TODOs and reflect the ranked missing-line counts from the last coverage report.
- For each target, create focused unit tests first (logic and error paths) using existing pytest fixtures and faker libraries; only escalate to integration-level smoke tests after unit stabilization.
- Keep individual PRs small: one test-file or one module per PR to simplify reviews.

Next steps:
- I'll start by adding a test scaffold for #1 (`dq-api/fastapi/app/api/v1/endpoints/testing.py`) unless you prefer a different item first.

