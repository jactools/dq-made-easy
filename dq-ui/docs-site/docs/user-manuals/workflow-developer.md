# Developer Workflow Guide

**Role:** Backend or frontend developer contributing to the dq-made-easy codebase, writing rules, or integrating pipelines with the platform API.
**Time to read:** 10 minutes
**Last updated:** 2026-05-31

## Responsibilities in scope

- Running and extending the API and UI locally.
- Writing, testing, and validating rules through the standard dev workflow.
- Running unit and integration tests before opening a PR.
- Integrating external pipelines with the platform API.
- Interpreting and acting on CI/CD validation gates.

## Core workflows

### 1. Start the local development stack

```bash
./scripts/stack.sh dev start --seed
```

The UI dev server starts on port 5173 by default. The API is available on the configured port behind Kong.

### 2. Run unit tests (FastAPI / Python)

```bash
cd dq-api/fastapi
scripts/python_arm64.sh --python-bin ../../venv/bin/python -m pytest tests/ -v
```

On macOS with arm64, always invoke pytest through `scripts/python_arm64.sh` to ensure native wheels load correctly.

### 3. Run unit tests (UI / Vitest)

```bash
cd dq-ui
npm run test
```

### 4. Author a new rule through the UI

1. Log in and select your workspace.
2. Open **Rules** → **New Rule**.
3. Configure the check type, source, target, severity, and domain.
4. Save the draft. The rule is in **Draft** state and will not execute until activated.
5. Submit for approval.
6. After approval, activate the rule to begin execution.

See the [DQ-1 Rule Validation User Guide](/docs/user-manuals/DQ-1_RULE_VALIDATION_USER_GUIDE/) for the full authoring walkthrough.

### 5. Integrate an external pipeline with the API

The platform exposes execution trigger, status query, and result-read endpoints. All request and response fields use snake_case.

**Trigger a run:**
```
POST /api/gx/v1/run-plans/{run_plan_id}/execute
Authorization: Bearer <token>
```

**Poll run status:**
```
GET /api/gx/v1/run-plans/{run_plan_id}/status
```

**Fail fast:** If the API returns 4xx or 5xx, the calling pipeline should fail fast and not continue silently. Do not swallow error responses.

For Airflow integration, use the `dq_made_easy_airflow_sdk` and `dq_made_easy_airflow_operator` wheels. See `dq-airflow-sdk/` and `dq-airflow-operator/`.

### 6. Validate your change with the smoke-test suite

```bash
./scripts/validate.sh --groups api
```

Add `--groups repo` to also validate repository-level consistency checks.

### 7. Build wheel artifacts after changing a local package

```bash
./scripts/package-releases/build_required_wheels.sh --force-build
```

Run this before restarting the stack if you changed `dq-utils`, `dq-cli`, or another local package.

### 8. Submit a rule through a git-first workflow

The recommended rule delivery path is:

1. Author the rule in the UI or API.
2. Export the rule as a versioned artifact.
3. Commit the artifact to the appropriate git branch.
4. Open a PR. CI validates the rule artifact and runs sample-data checks.
5. Merge. Deployment picks up the artifact and registers it in the rule registry.

## What to check when a test fails

- Did a migration run? Apply with `alembic upgrade head` under `dq-api/fastapi`.
- Is the venv active and using the arm64 Python interpreter?
- Did a recent schema change break a seeded fixture? Check `dq-db/mock-data/` CSV files — do not edit SQL seed files directly.
- Is a required environment variable missing from `.env.dev.local`?

## API naming conventions

- Backend API contracts use snake_case throughout.
- The frontend converts snake_case response fields to camelCase using the shared conversion utilities in `dq-ui/src/`.
- Do not introduce camelCase into backend request or response models.

## Related guides

- [DQ-1 Rule Validation User Guide](/docs/user-manuals/DQ-1_RULE_VALIDATION_USER_GUIDE/)
- [Engine Capability Guidance](/docs/user-manuals/engine-capability-guidance/)
- [GX Capability Guidance](/docs/user-manuals/gx-capability-guidance/)
- [Operator Workflow Guide](/docs/user-manuals/workflow-operator/)
- [User Manuals index](/docs/user-manuals/)
