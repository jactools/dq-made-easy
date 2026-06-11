# EDR-041 [VAL]: Python Arm64 Launcher Required on Apple Silicon

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: VAL

## Context
This repository is frequently worked on from Apple Silicon machines, but shells and subprocesses can still run under Rosetta translation. That creates a recurring class of failures for Python-based work:

- pytest and other Python commands load x86_64-only native extensions from the shared virtual environment
- child processes silently switch architecture depending on how `python` or `bash` is resolved
- contract generation, validation scripts, and helper tooling behave differently depending on whether the Python process is actually arm64

Those failures are environment-dependent and easy to misdiagnose as application regressions. The repository already includes `scripts/python_arm64.sh` as the shared launcher that forces Python execution under arm64 on Apple Silicon when possible.

## Decision
Adopt the following repository rule for Python execution on Apple Silicon:

- Any repository Python code that is launched from shell scripts, validation scripts, or documented command snippets MUST be executed through `scripts/python_arm64.sh`.
- Wrapper scripts that run Python MUST call `scripts/python_arm64.sh` instead of invoking `python`, `python3`, or `venv/bin/python` directly.
- If a specific interpreter path is required, it MUST be passed through `scripts/python_arm64.sh --python-bin ...` rather than executed directly.
- Direct Python invocation is acceptable only when the caller is already a Python process and no shell-level launcher choice exists.

## Rationale
- Centralizing Python launch behavior prevents Rosetta and PATH resolution from reintroducing x86_64 execution unexpectedly.
- One shared launcher makes validation, tests, generators, and support scripts behave consistently across Apple Silicon environments.
- The rule makes architecture-sensitive failures reproducible and easier to diagnose.
- The launcher still degrades safely on non-macOS or non-Apple-Silicon environments by running the resolved interpreter normally.

## Scope Boundaries
This decision applies to repository shell scripts, validation wrappers, and documented shell commands that execute Python code.

It does not by itself define:
- how the virtual environment is created or rebuilt
- every low-level Python package repair procedure for mixed-architecture wheels
- Python execution launched internally from an already running Python interpreter
- non-Python tooling such as Node, Docker, or database CLIs

## Consequences
**Positive**
- Python execution becomes architecture-stable on Apple Silicon.
- Validation and test wrappers are less likely to fail because a child process switched back to x86_64.
- The repository has one obvious and documented execution path for Python tooling.

**Negative**
- Shell wrappers must be slightly more explicit when launching Python.
- Older scripts that call Python directly need to be updated incrementally.
- Developers can still bypass the rule manually in ad hoc shells, so review discipline remains necessary.

## Implementation Guidance
- Use `scripts/python_arm64.sh` for Python-based validate scripts, generators, smoke helpers, and repo maintenance scripts.
- Prefer `scripts/python_arm64.sh --python-bin "$PYTHON_BIN" script.py` when a shared venv interpreter path is already resolved.
- Avoid calling `python`, `python3`, or `venv/bin/python` directly from new or modified shell scripts unless there is a documented exception.
- Keep architecture-sensitive validation under script wrappers instead of relying on interactive shell state.

## Related Artifacts
- `scripts/python_arm64.sh`
- `scripts/validate.sh`
- `scripts/VALIDATION.md`
- `/memories/repo/dq-rulebuilder-fastapi-arm64-venv-native-ext-note.md`