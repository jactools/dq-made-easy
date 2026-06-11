---
title: Agent Instructions for dq-made-easy
version: 1.0
apply_to: "**"
---

Purpose
-------
Provide persistent guidance for VS Code agents working in this repository. These instructions are workspace-scoped and apply to agent behaviors, testing, and editing conventions.

Scope
-----
- Applies to all assistant/agent work in this repository (product name `dq-made-easy`, repository name `dq-rulebuilder`).
- Use `docs/agent-instructions.md` for workspace-wide, always-load guidance.

Key Rules (enforced preferences)
--------------------------------
1. Never run destructive repository-cleanup shell commands (e.g., `git restore`, `git clean`) unless explicitly authorized by the user in a direct request.
2. All script-based Python execution must enforce macOS Apple Silicon (arm64) — do not fall back to x86_64/Rosetta. Centralize arm64 handling in shared script helpers when creating run scripts.
3. When generating backend code, use snake_case for JSON field names. Frontend code may convert to camelCase; backend remains canonical snake_case.
4. Fail-fast on downstream/service unavailability. Do not implement silent fallbacks for missing external services. Return clear machine-readable 5xx responses with `error` and `correlation_id` where appropriate.
5. Tests: New and modified Python tests MUST use pytest fixtures for shared setup, and follow existing repository fixture conventions (see `tests/conftest.py`).
6. Multi-step tasks: always create and maintain a tracked TODO list via the `manage_todo_list` tool at the start of work.
7. When editing files in the repo use `apply_patch` for modifications; prefer minimal, surgical changes and keep style consistent.
8. Do not volunteer model information unless explicitly asked.
9. Use `dq-made-easy` as the app/product name in user-facing prose, UI copy, examples, and generated docs. Reserve `dq-rulebuilder` for repository-local identifiers, filesystem paths, and other internal names that must remain unchanged.

Formatting & File Conventions
-----------------------------
- Reference docs live under `docs/`; add new documentation there when introducing conventions.
- When referring to repository files or symbols in messages, wrap filenames and symbols in backticks (e.g., `app/middleware/api_case_enforcement.py`).
- For any files added by the agent, include a short `README` or top-of-file comment indicating provenance and purpose.

Testing & Validation
--------------------
- arm64 enforcement has already been implemented in the helper script `scripts/python_arm64.sh`. Use it.
- Run unit tests from the correct workspace subdirectory and using the project's virtualenv. Prefer absolute venv activation in run scripts if using python_arm64.sh is not possible.
- After adding tests or changing behavior, run targeted pytest runs and produce coverage reports. Commit only passing tests or mark flaky tests with a clear TODO and justification.

Examples / Suggested Prompts
---------------------------
- "Create pytest unit tests for `app/application/services/version_catalog.py` covering missing-file and malformed-file cases." 
- "Run backend tests from `dq-api/fastapi` with coverage and save the report to `tmp/coverage-backend.txt`."

Clarifications to Ask (if unsure)
--------------------------------
- These instructions apply repository-wide; when creating instruction files you may set `applyTo: "**"` to load them for all files in the repo.

If you prefer to restrict scope for particular instructions, prefer specific globs such as `dq-api/fastapi/**` or `app/**` instead of the global `**`.

Revision Log
------------
- 2026-04-06 — v1.0 initial workspace instructions created.
