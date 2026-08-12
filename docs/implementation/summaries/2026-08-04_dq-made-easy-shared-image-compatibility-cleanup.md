# Implementation Summary: dq-made-easy shared image compatibility cleanup

**Date**: 2026-08-04  
**Status**: Complete

## Objective and Scope

This follow-up cleanup removes the last temporary shared-image compatibility shim in the `dq-made-easy` pull tooling and tightens the operator entrypoint so tagged shared images can be planned without falling back to the old helper behavior.

The scope of the change was:

- remove the bare-scope fallback from `scripts/pull_images.sh`
- make `scripts/stack_ctl.sh pull --dry-run` report shared image refs without executing pulls
- allow tagged shared image refs to flow through the operator plan surface
- keep dq-api auth consumers pointed at the dedicated `auth_scopes` adapter while preserving the compatibility wrappers for external callers
- add pytest module classification markers to the new auth-scope tests

## Results

| Metric | Before | After |
|---|---|---|
| Bare shared-image scope handling | Accepted as a silent fallback in `scripts/pull_images.sh` | Rejected with a clear `--scope` error |
| `stack_ctl.sh pull --dry-run` | Still executed the pull path for `platform-ingestion-runner:tag` | Prints the resolved plan without pulling |
| Shared image ref planning | Tagged shared refs were rejected by `stack_ctl.sh` | Tagged shared refs are preserved in the pull plan |
| Internal auth scope imports | Mixed through `app.core.auth` shims | Internal consumers now import `app.core.auth_scopes` directly |
| Auth-scope test metadata | New tests lacked module classification | New tests now declare `classification: unit` and `pytestmark = pytest.mark.unit` |

## Updated files

- `scripts/pull_images.sh`
- `scripts/stack_ctl.sh`
- `dq-api/fastapi/app/api/presenters/suggestions.py`
- `dq-api/fastapi/app/api/v1/endpoints/agent.py`
- `dq-api/fastapi/app/api/v1/endpoints/auth.py`
- `dq-api/fastapi/app/api/v1/endpoints/data_protection.py`
- `dq-api/fastapi/app/api/v1/endpoints/exception_reports.py`
- `dq-api/fastapi/app/api/v1/endpoints/exceptions.py`
- `dq-api/fastapi/app/api/v1/endpoints/onboarding.py`
- `dq-api/fastapi/app/domain/comment_governance.py`
- `dq-api/fastapi/app/domain/status_governance.py`
- `dq-api/fastapi/app/infrastructure/repositories/in_memory_admin_repository.py`
- `dq-api/fastapi/app/infrastructure/repositories/postgres_admin_repository.py`
- `dq-api/fastapi/tests/core/test_auth_compatibility.py`
- `dq-api/fastapi/tests/core/test_auth_scopes.py`

## Validation

- `venv/bin/python scripts/validate_module_rules.py`
- `bash -n scripts/pull_images.sh && bash -n scripts/stack_ctl.sh`
- `TLS_INTERNAL_CA_BUNDLE=tmp/certs/internal-ca-bundle.pem bash scripts/stack_ctl.sh pull --dry-run --env-file .env.prod.local --scope shared --image platform-ingestion-runner:latest`
- `TLS_INTERNAL_CA_BUNDLE=tmp/certs/internal-ca-bundle.pem bash scripts/pull_images.sh --env-file .env.prod.local core`
- `cd dq-api/fastapi && ../../venv/bin/python -m pytest tests/core/test_auth_scopes.py tests/core/test_auth_compatibility.py tests/unit/test_core_auth.py tests/api/test_suggestions_presenters.py -q`

## Known Issues or Remaining Work

- The shared-image verification follow-up now uses the local Nexus mirror tag rather than public Docker Hub because public Docker Hub access is not available in this environment.
- `pull_images.sh` now rejects the bare `core|repo|shared` shortcut, so operator docs should continue to use `--scope` explicitly.

## Next Steps

1. Decide whether the remaining compatibility wrappers in `app.core.auth` should stay as public backward-compatibility helpers or be removed in a later cleanup.
2. Keep the shared-image operator surface aligned with the published registry contract.
