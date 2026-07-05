# Agent Instructions

This file is for AI coding assistants (Copilot, Claude, Cursor, etc.).

## Where to find the rules

Read `.github/copilot/01-general.md` for the authoritative repository rules:
- Python file size limit (< 1000 lines)
- Module naming conventions
- Dependency layering (no upward imports)
- Test-proof file layout

Additional instruction files (if they exist):
- `.github/copilot/02-fastapi-sqlalchemy.md` — FastAPI + SQLAlchemy
- `.github/copilot/03-testing.md` — Testing conventions; Python tests must use `<repo-root>/venv` and `scripts/python_arm64.sh`
- `.github/copilot/04-database.md` — Database migrations
- `.github/copilot/05-versioning.md` — Versioning rules

## When you are about to create or modify a Python file

1. Check if the file already exists and how many lines it has.
2. If it will exceed 800 lines, plan the split **before** writing code.
3. If modifying an existing file over 1000 lines, extract new logic into a new module rather than adding to the large file.
4. Run the validation script through `scripts/python_arm64.sh --python-bin ./venv/bin/python` (see `.github/copilot/03-testing.md`) when done to verify.

## Conflict resolution

If a rule conflicts with an explicit developer or system instruction, raise the conflict to the user. Do not silently override.
