---
name: Commit Validation Gate
description: All commits must pass relevant build/test validation before being created
applyTo: "**/*"
---

# Commit Validation Gate

**Rule**: All commits must be preceded by running and passing the relevant validation or build script.

## Principle

This rule enforces fail-safe-by-default. Committing without verification creates broken commits that propagate errors into CI/CD pipelines, clogs repositories with work-in-progress, and violates the fundamental error-handling principle: errors are signals that must be fixed, not ignored.

## Absolute Requirements

1. **Before every commit**: Identify and run the relevant validation script(s) for the changed files
2. **Script must succeed**: Exit code must be 0 (success)
3. **No exceptions**: If a relevant script exists and cannot be run, the commit is blocked
4. **Verification proof**: Keep the successful script output visible; do not commit without seeing it

## Validation Script Coverage

The following scripts must be run for their respective change types:

### Frontend Changes (TypeScript, React, CSS)
```bash
cd dq-ui/docs-site && npm run build
cd dq-ui && npm run build
# Also consider: npm run lint, npm run test
```

### Python Changes (FastAPI, workers, utils, engine)
```bash
scripts/python_arm64.sh --python-bin ./venv/bin/python -m pytest <test_module>
# For specific module validation
```

### Database Changes (schema, migrations, seed data)
```bash
# Validate migration syntax
./scripts/validation/validate_database_schema.sh

# Test seed data
./scripts/validation/validate_seed_data.sh
```

### Deployment/Infrastructure Changes (docker-compose, helm, terraform)
```bash
# Docker Compose syntax
docker-compose config > /dev/null

# Kubernetes manifests (if applicable)
./scripts/validation/validate_k8s_manifests.sh

# Terraform (if applicable)
terraform plan
```

### Documentation Changes (markdown, docstrings)
```bash
# Docusaurus build for docs/ changes
cd dq-ui/docs-site && npm run build

# Python docstring validation
# If adding/modifying code with docstrings
scripts/python_arm64.sh --python-bin ./venv/bin/python -m pylint <module>
```

### Configuration Changes (YAML, JSON, env)
```bash
# JSON schema validation
jq empty config-file.json

# YAML syntax
yamllint config-file.yaml

# Docker-compose syntax
docker-compose config > /dev/null
```

## Workflow

**Before you run `git commit`:**

1. **Identify changed files**: What areas were modified? (frontend, backend, docs, deployment, etc.)
2. **Find applicable scripts**: From the list above, which scripts apply?
3. **Run each script**: Execute in sequence. All must pass (exit code 0)
4. **Verify success**: Look for "SUCCESS", "✓ Compiled", exit code 0, or equivalent success signal
5. **Only then commit**: Once all scripts pass, run `git commit`

**If a script fails**:
- Fix the underlying issue (don't ignore the error)
- Re-run the script to verify the fix
- Only commit after success

**If no script can be run**:
- This is a blocker. Stop.
- Determine if validation infrastructure is missing
- Ask the user for clarification or help set up validation
- Do not proceed with commit

## Examples

### Example 1: Docusaurus Anchor Fix

**Changes**: Fixed broken anchor in `docs/implementation-details/SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md`

**Before commit**:
```bash
# Run the build that caught the error
cd dq-ui/docs-site && npm run build

# Output must show:
# [SUCCESS] Generated static files in "build".
# Exit code: 0
```

**Result**: Only after seeing success → commit

---

### Example 2: Python Backend Fix

**Changes**: Fixed bug in `dq-api/fastapi/core/auth.py`

**Before commit**:
```bash
# Run the test suite
scripts/python_arm64.sh --python-bin ./venv/bin/python -m pytest tests/unit/test_core_auth.py

# Output must show:
# passed
# Exit code: 0
```

**Result**: Only after seeing all tests pass → commit

---

### Example 3: Database Migration

**Changes**: Added new migration file `db/migrations/001_new_feature.sql`

**Before commit**:
```bash
# Validate migration syntax
./scripts/validation/validate_database_schema.sh

# Output must show migration is valid
# Exit code: 0
```

**Result**: Only after validation passes → commit

---

## Enforcement

**For AI agents (Copilot, Claude, Cursor, etc.)**:
- Do NOT create commits without running validation scripts first
- Do NOT suppress validation failures by changing error levels
- Do NOT commit to "save progress" without validation passing
- Always show the validation output in your reasoning
- If validation fails, fix the root cause and re-validate

**For developers**:
- This is a best practice enforced in code review
- Commits without validation evidence will be flagged
- Validation output should appear in commit messages or be available in recent terminal history

## When Validation Infrastructure is Missing

If no validation script exists for a change type:
1. Document the gap (e.g., "no test suite exists for X")
2. Create basic validation if possible (e.g., syntax check, linting)
3. Ask the user if commitment should be blocked pending infrastructure
4. Never silently skip validation

## Integration with CI/CD

This gate is a **developer-side** enforcement. CI/CD pipelines will re-run validation, but:
- They should pass if you've followed this rule
- If they fail, your commit was made without proper local validation (violation)
- This reduces CI/CD failures and keeps the pipeline clean

## Related Principles

- **Errors are signals**: See `.github/copilot/01-general.md` for the fundamental error-handling rule
- **Fail-safe by default**: Validation must pass before code enters the repository
- **No silent failures**: If validation can't run, block the commit rather than ignore it
