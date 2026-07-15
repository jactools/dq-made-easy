# Repo Coverage Test Plan

Status: Planned
**Owner**: Test coverage uplift
**Target**: 90% repo-wide line coverage, 100% branch coverage
**Baseline**: 29% overall line coverage, 2% branch coverage from `test-results/coverage.json`
**Last updated**: 2026-05-22

## Goal

Raise repo-wide coverage by removing the lowest-effort gaps first, then working through the remaining branch-heavy modules until the repo reaches the target thresholds.

## Progress

- Completed batch: `app/schemas/problem_details.py`, `app/schemas/pagination.py`, `app/application/services/join_consistency_metrics_calculator.py`, and `app/domain/entities/execution_metrics.py`
- Coverage refresh: the focused batch is now at 100% line coverage for those four modules in `test-results/coverage.json`
- Completed batch: `app/application/services/rule_expression.py` and `app/application/services/rule_join_consistency_mapping.py`
- Coverage refresh: both service modules are now above the 90% line-coverage threshold in `test-results/coverage.json`
- Completed batch: `app/application/services/check_type_expression_generator.py`
- Coverage refresh: the generator module is now above the 90% line-coverage threshold in `test-results/coverage.json`
- Completed batch: `app/api/presenters/data_catalog.py`
- Coverage refresh: the presenter module is now above the 90% line-coverage threshold in `test-results/coverage.json`
- Completed batch: `app/application/services/gx_expectations.py`
- Coverage refresh: the expectations helper/service module is now above the 90% line-coverage threshold in `test-results/coverage.json`
- Completed batch: `app/infrastructure/repositories/in_memory_testing_repository.py`
- Coverage refresh: the repository adapter is now above the 90% line-coverage threshold in `test-results/coverage.json`
- Completed batch: `app/application/services/rule_join_consistency_mapping.py`
- Coverage refresh: the join-consistency mapping module is now above the 90% line-coverage threshold in `test-results/coverage.json`
- Completed batch: `app/api/presenters/support.py`
- Coverage refresh: the support presenter module is now at 100% line coverage in `test-results/coverage.json`
- Completed batch: `app/application/services/rule_expression.py`
- Coverage refresh: the rule-expression helper module is now at 100% line coverage in `test-results/coverage.json`
- Completed batch: `app/api/v1/endpoints/approvals.py`
- Coverage refresh: the approvals endpoint is now at 90% line coverage in `test-results/coverage.json`
- Completed batch: `app/application/services/exception_reason_analytics_projection.py`
- Coverage refresh: the exception-reason analytics projection service is now at 100% line coverage in `test-results/coverage.json`
- Completed batch: `app/application/services/test_data_materialization_service.py`
- Coverage refresh: the test-data materialization service is now at 90% line coverage in `test-results/coverage.json`
- Next batch: `app/infrastructure/repositories/postgres_admin_repository.py`

## Success Criteria

- Repo-wide line coverage is at least 90%.
- Repo-wide branch coverage is 100%.
- Every new batch has focused tests, passes locally, and is validated with coverage output.
- Any remaining uncovered branch is either exercised by a real test or removed/refactored.

## Current Hotspots

Start with the current lowest-coverage modules from `test-results/coverage.json`:

| Priority | Module | Why it is a good target | Estimated effort |
|---|---|---|---|
| done | `app/schemas/problem_details.py` | Tiny file, covered by focused schema tests | XS, 1 focused test file |
| done | `app/schemas/pagination.py` | Tiny file, covered by focused schema tests | XS, 1 focused test file |
| done | `app/application/services/join_consistency_metrics_calculator.py` | Small logic surface with a limited branch set | S, 1 focused test file |
| done | `app/domain/entities/execution_metrics.py` | Small entity/helper module | XS to S, 1 focused test file |
| done | `app/application/services/rule_expression.py` | Branch-heavy pure logic, likely high payoff once isolated | L, 1 to 2 focused test files |
| done | `app/application/services/check_type_expression_generator.py` | Large but deterministic logic, good candidate for branch sweeps | XL, multiple focused test files |
| done | `app/api/v1/endpoints/approvals.py` | Large endpoint surface; current live next batch | L, 1 to 2 focused test files |
| done | `app/application/services/gx_expectations.py` | Branch-heavy logic with many generated outputs | XL, multiple focused test files |
| done | `app/domain/entities/rules_join_consistency_endpoint_support.py` | Small support surface | S, 1 focused test file |
| done | `app/infrastructure/repositories/in_memory_testing_repository.py` | Repository adapter; fake-backed tests should be cheap | L, 1 to 2 focused test files |
| done | `app/api/presenters/support.py` | Support helper module | L, 1 focused test file |
| done | `app/application/services/test_data_materialization_service.py` | Materialization orchestration and validation helpers | L, 1 to 2 focused test files |
| 12 | `app/infrastructure/repositories/postgres_admin_repository.py` | Repository adapter with small fake-backed surface | L, 1 to 2 focused test files |
| 13 | `app/infrastructure/repositories/in_memory_rules_repository.py` | In-memory repository with direct branch coverage potential | L, 1 focused test file |
| 14 | `app/infrastructure/repositories/postgres_rules_repository.py` | Postgres repository adapter; fake-backed tests should be cheap | L, 1 to 2 focused test files |
| 15 | `app/infrastructure/repositories/postgres_gx_suite_repository.py` | Postgres GX suite repository adapter | L, 1 to 2 focused test files |

Continue the list in the same order from the coverage report, then move to the larger endpoint and repository modules once the smaller ones are above target.

### Effort Snapshot For The 12-Item Starter Wave

The 12 modules above are not the full path to the target. They are the first cheap batch.

- Current missing lines in these 12 modules: 1,821
- Current missing branches in these 12 modules: 900
- Repo-wide missing lines: 13,485
- Repo-wide missing branches: 5,653

If the 12 modules were taken to 100% line and branch coverage, the repo would still have roughly 11,664 missing lines and 4,753 missing branches left. That means the starter wave is useful, but it only addresses about 13.5% of the current line gap and about 15.9% of the current branch gap.

### Practical Effort Interpretation

- The first four modules are small enough to treat as fast wins, usually one focused test file each.
- The middle four modules are the expensive branch-heavy ones and will likely require parser stubbing, fake-backed fixtures, or several targeted test files.
- The last four modules are mixed-effort helper/repository surfaces, usually one to two focused files each.

For planning purposes, expect the starter wave to take about 6 to 12 focused test files total, depending on how many branches each branch-heavy module needs.

The remaining work to reach the repo goals is much larger than this first batch. After the starter wave, the backlog still includes the next low-coverage modules in the report, then the large endpoint/repository surfaces like approvals, data catalog, gx, support, and the big Postgres repositories.

The current refreshed report now points to `app/infrastructure/repositories/postgres_admin_repository.py`, `app/infrastructure/repositories/in_memory_rules_repository.py`, and `app/infrastructure/repositories/postgres_rules_repository.py` as the next low-coverage modules.

## Execution Strategy

### Phase 1: Cheap wins

Focus on helper, schema, and wrapper modules that can be covered with direct function tests.

Work items:

- Add focused unit tests for pure serializers and Pydantic-style models.
- Exercise tiny endpoint wrappers with fake dependencies.
- Prefer direct function calls over HTTP client tests when the file is only forwarding or shaping data.

Definition of done:

- Module coverage reaches at least 90% line coverage.
- Branch coverage for the module is complete or the remaining branch is proven unreachable and removed.

### Phase 2: Branch-heavy logic

Attack parser, compiler, validation, and policy modules.

Work items:

- Stub parser or upstream builders to reach invalid-input paths.
- Add tests for empty input, malformed input, enum mismatches, and defaulting branches.
- Add explicit error-path assertions for `ValueError`, `HTTPException`, and domain-specific failure types.

Definition of done:

- All conditional paths are explicitly exercised.
- Any branch that still cannot be reached is reviewed for dead code or unnecessary compatibility behavior.

### Phase 3: Repository adapters

Cover Postgres, Redis, and in-memory repository layers with fake sessions and fake clients.

Work items:

- Use fake session objects for CRUD, missing-row, duplicate-row, and commit-failure scenarios.
- Use fake Redis clients for key creation, missing-key, and status-transition coverage.
- Verify mapping helpers, serialization, and failure propagation.

Definition of done:

- Every repository method has both success and failure coverage.
- Transitions, not-found cases, and serialization helpers are all exercised.

### Phase 4: Endpoint wrappers

Use endpoint tests where routing, auth, and response-model behavior matter.

Work items:

- Add direct async tests for wrapper functions when HTTP transport is unnecessary.
- Use request/response client tests only when middleware, dependency injection, or auth are part of the behavior.
- Keep error mapping assertions exact so branch coverage stays stable.

Definition of done:

- Wrapper modules are either 90%+ or fully covered.
- HTTP-level tests validate serialization, status codes, and dependency wiring.

### Phase 5: Repo-wide enforcement

After each batch, rerun a repo-wide coverage report and regenerate the hotspot list.

Required loop:

1. Pick the next 1 to 3 lowest-effort modules.
2. Add focused tests only for those modules.
3. Run the narrow test file(s) first.
4. Run repo-wide coverage and update the hotspot list.
5. Repeat until the repo reaches target coverage.

## Suggested Order Of Work

1. Finish all tiny schema and helper modules below 90%.
2. Clear the smallest endpoint wrappers.
3. Clear the repository adapters with fake-backed tests.
4. Sweep the branch-heavy pure logic modules.
5. Return to large API surfaces like approvals, data catalog, support, and gx only after the smaller backlog is exhausted.

## Validation Commands

Use the same pattern for every batch:

```bash
cd /Users/Jac.Beekers/gitrepos/dq-rulebuilder/dq-api/fastapi
/Users/Jac.Beekers/gitrepos/dq-rulebuilder/.venv/bin/python -m pytest -q path/to/focused_test_file.py
/Users/Jac.Beekers/gitrepos/dq-rulebuilder/.venv/bin/python -m coverage run -m pytest -q path/to/focused_test_file.py
/Users/Jac.Beekers/gitrepos/dq-rulebuilder/.venv/bin/python -m coverage json -o /Users/Jac.Beekers/gitrepos/dq-rulebuilder/test-results/coverage.json
```

For repo-wide checks, run the full test suite with coverage and regenerate the coverage report before choosing the next batch.

## Exit Conditions

The plan is complete when:

- Repo-wide line coverage is at least 90%.
- Repo-wide branch coverage is 100%.
- No remaining uncovered branches are left without a documented reason.

If the final few branches cannot be covered without changing behavior, refactor or remove the branch instead of adding fallback-only tests.