---
title: "Stack lifecycle scripts: syntax, password rotation, secrets reuse, orchestrator"
description: "Test proof for the new stack lifecycle scripts and supporting modules."
---

# Stack lifecycle scripts

This page was generated from [test-results/test-proof/0.11.6/infra/stack-scripts-test-proof.json](../../../../test-results/test-proof/0.11.6/infra/stack-scripts-test-proof.json).

## Summary

Test proof for the new stack lifecycle scripts (`stack.sh`, `stack_destroy.sh`, `stack_start.sh`, `stack_stop.sh`, `stack_restart.sh`, `stack_seed.sh`) and supporting modules (`stack_lifecycle.sh`, `generate_secrets.sh --reuse-admin`, `seed_password_rotation.py --no-admin-rotate`).

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.6 |
| Proof Type | infra |
| Status | passed |
| Total Tests | 83 |
| Passed | 83 |
| Failed | 0 |
| Success Rate | 100% |
| Confidence | high |

## Test Suites

### 1. Stack Syntax Validation

| Metric | Value |
| --- | --- |
| Tests | 8 |
| Passed | 8 |
| Failed | 0 |
| Evidence | `test-results/evidence/0.11.6/infra/20260714T120000Z-stack-syntax-validation` |

Shell syntax validation for all 8 new/modified scripts:
- `stack.sh`
- `stack_destroy.sh`
- `stack_start.sh`
- `stack_stop.sh`
- `stack_restart.sh`
- `stack_seed.sh`
- `supporting/stack_lifecycle.sh`
- `generate_secrets.sh`

### 2. Password Rotation (Python)

| Metric | Value |
| --- | --- |
| Tests | 12 |
| Passed | 12 |
| Failed | 0 |
| Evidence | `test-results/evidence/0.11.6/infra/20260714T120001Z-password-rotation` |

- All imports successful
- `_ADMIN_PASSWORD_VARS` has 8 entries
- Known admin vars present (DQ_DB_PASSWORD, KEYCLOAK_SYSTEM_ADMIN_PASSWORD, etc.)
- Service vars correctly excluded from admin set
- `skip_admin=True` blocks admin password rotation
- `skip_admin=False` allows admin password rotation
- `skip_admin=True` still rotates service passwords
- Non-password vars never rotate
- `DOCKER_HUB_` prefix skipped
- Generated password length = 32
- 10 unique passwords generated

### 3. Secrets Reuse (generate_secrets.sh --reuse-admin)

| Metric | Value |
| --- | --- |
| Tests | 3 |
| Passed | 3 |
| Failed | 0 |
| Evidence | `test-results/evidence/0.11.6/infra/20260714T120002Z-secrets-reuse-admin` |

- DQ_DB_PASSWORD reused across `--reuse-admin` run
- KEYCLOAK_SYSTEM_ADMIN_PASSWORD reused across `--reuse-admin` run
- DQ_ENGINE_OIDC_CLIENT_SECRET rotated (new value) across `--reuse-admin` run

### 4. Env Password Rotation (seed_password_rotation.py --no-admin-rotate)

| Metric | Value |
| --- | --- |
| Tests | 6 |
| Passed | 6 |
| Failed | 0 |
| Evidence | `test-results/evidence/0.11.6/infra/20260714T120003Z-env-password-rotation` |

- DQ_DB_PASSWORD unchanged (admin)
- KEYCLOAK_SYSTEM_ADMIN_PASSWORD unchanged (admin)
- DQ_ENGINE_OIDC_CLIENT_SECRET rotated (service)
- GRAFANA_OIDC_SECRET rotated (service)
- DB_HOST unchanged (non-password)

### 5. Stack Lifecycle Helpers (stack_lifecycle.sh)

| Metric | Value |
| --- | --- |
| Tests | 24 |
| Passed | 24 |
| Failed | 0 |
| Evidence | `test-results/evidence/0.11.6/infra/20260714T120004Z-stack-lifecycle-helpers` |

- 8 admin password vars correctly classified
- 4 service/non-admin vars correctly excluded
- 6 env suffix derivation tests (dev, test, prod, development, testing, production)
- Project prefix derivation from env file
- 5 stateful volume entries verified

### 6. Stack Orchestrator (stack.sh)

| Metric | Value |
| --- | --- |
| Tests | 19 |
| Passed | 19 |
| Failed | 0 |
| Evidence | `test-results/evidence/0.11.6/infra/20260714T120005Z-stack-orchestrator` |

- Help output mentions all 6 actions (destroy, stop, start, restart, init, seed)
- Help output mentions all 4 options (--seed, --force-build, --no-build, --init-db)
- Help output mentions env contract
- Invalid env rejected
- Missing action rejected
- Invalid action rejected
- All 5 child scripts exist and are executable

### 7. Documentation Consistency

| Metric | Value |
| --- | --- |
| Tests | 11 |
| Passed | 11 |
| Failed | 0 |
| Evidence | `test-results/evidence/0.11.6/infra/20260714T120006Z-docs-consistency` |

- STACK_SCRIPT_CONTRACT.md references stack.sh
- QUICKSTART_DEPLOY.md references stack.sh
- workflow-operator.md references stack.sh
- All 5 lifecycle scripts listed in contract doc
- Password Management Policy section present
- Fresh vs warm start distinction documented
- WF-5 doc references stack.sh

## Password Policy Verification

| Password Type | Examples | Behavior |
| --- | --- | --- |
| Admin | DQ_DB_PASSWORD, KEYCLOAK_SYSTEM_ADMIN_PASSWORD | Reused when volumes exist; regenerated on fresh start or destroy |
| Service | DQ_ENGINE_OIDC_CLIENT_SECRET, GRAFANA_OIDC_SECRET | Rotated on every start/restart |
| User | Keycloak seeded users | Rotated on every seed |

## Conclusion

All 83 tests passed. The stack lifecycle scripts, password rotation modules, and documentation are consistent and working correctly.

**Generated**: 2026-07-14
**Status**: PASSED
