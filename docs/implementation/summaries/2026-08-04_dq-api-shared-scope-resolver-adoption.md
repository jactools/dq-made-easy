# Implementation Summary: dq-api shared scope resolver adoption

**Date**: 2026-08-04  
**Status**: Complete

## Objective and Scope

This change starts Workstream 5 adoption in `dq-made-easy` by moving the dq-api scope collection and scope matching helpers onto the shared `platform_auth` scope resolver.

The scope of the change was:

- replace the dq-api local scope expansion logic with `platform_auth.create_dq_scope_resolver()`
- replace dq-api scope extraction with `platform_auth.get_scopes_from_claims()`
- keep the existing dq-api auth request routing and JWT decoding behavior intact
- verify the existing auth-focused tests still pass after the shared helper adoption

## Results

| Metric | Before | After |
|---|---|---|
| Scope extraction | dq-api-local helper logic | `platform_auth.get_scopes_from_claims()` |
| Scope expansion / matching | dq-api-local wildcard and expansion logic | `platform_auth.create_dq_scope_resolver()` |
| Shared auth helper usage | token-url helpers only | token-url helpers plus shared scope resolver |
| Regression status | not explicitly verified after the refactor | auth-focused pytest suite passed |

## Updated files

- `dq-api/fastapi/app/core/auth.py`

## Validation

- `cd dq-api/fastapi && ../../venv/bin/python -m pytest tests/unit/test_core_auth.py tests/core/test_auth_compatibility.py -q --no-cov`

## Known Issues or Remaining Work

- dq-api still uses local JWT parsing/validation for its browser/session auth flow; this step only moved scope extraction and matching to the shared helper.
- Further Workstream 5 steps can continue by replacing additional dq-api auth seams where the behavior is still app-specific.

## Next Steps

1. Continue Workstream 5 with the remaining dq-made-easy auth and image-adoption seams.
2. Consider whether dq-api should also adopt the shared JWT validation primitives where the shared contract fits the current auth flow.
3. Keep the dq-api auth behavior covered by the existing compatibility tests while the migration continues.
