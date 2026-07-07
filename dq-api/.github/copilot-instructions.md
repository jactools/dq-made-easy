Use this file for dq-api-specific guidance.

- Prefer the local `venv` and `scripts/python_arm64.sh` for Python and pytest commands in this workspace.
- Keep FastAPI and repository changes aligned with the existing module split pattern in `dq-api/fastapi/app/infrastructure/repositories/`.
- Reference `.github/instructions/python-test-module-boundary.instructions.md` for the rule that every Python production module must have its own dedicated unit test module.
- Keep instructions concise and repo-specific; do not add generic scaffolding checklists here.
