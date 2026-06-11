# FastAPI Smoke Tests

This directory now contains only pytest-safe smoke coverage that stays in-process and does not depend on live auth, Kong, or a real database.

Pytest scope:
- Manual expression override requires explicit confirmation (`POST /api/rulebuilder/v1/rules`).
- Manual expression override audit fields are returned when confirmed (`POST /api/rulebuilder/v1/rules`).

Environment-dependent smoke coverage lives under the repository shell scripts instead of `tests/`:
- `scripts/smoke_test_auth_kong.sh` for Kong + public auth redirect/login behavior.
- `scripts/smoke_test_api.sh` for seeded verification checks.
- `scripts/smoke_adhoc_rule_execution.sh` for live GX / materialization smoke execution.

Run the remaining pytest smoke tests:

```bash
cd dq-api/fastapi
pytest -q -o addopts='' tests/smoke/test_manual_override_smoke.py
```
