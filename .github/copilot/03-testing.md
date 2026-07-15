# Testing Rules

## Python test execution

- Always use the repository virtual environment at `<repo-root>/venv` for Python test execution.
- Always run Python tests through `scripts/python_arm64.sh` to avoid x86_64/arm64 architecture mismatches.
- Do not run `pytest`, `python`, or `python3` directly for repo Python tests.

### Correct

```bash
# From repo root
scripts/python_arm64.sh --python-bin ./venv/bin/python -m pytest dq-engine/tests/test_xxx.py -v
```

### Wrong — do not do this

```bash
# System python — wrong venv, wrong architecture
python3 -m pytest ...
python3 dq-engine/tests/test_xxx.py

# Direct venv python — may trigger arm64/x86_64 binary mismatch
./venv/bin/python -m pytest ...
venv/bin/python -m pytest ...

# Bare pytest — uses system python, not repo venv
pytest ...
```

### Error patterns that indicate you used the wrong launcher

- `ImportError: ... incompatible architecture (have 'arm64', need 'x86_64')`
- `ImportError: ... incompatible architecture (have 'x86_64', need 'arm64')`
- `ModuleNotFoundError: No module named 'jsonschema'` (system python lacks repo deps)
- `ModuleNotFoundError: No module named 'dq_plan_execution_types'` (missing `dq-engine` on sys.path)
- `ModuleNotFoundError: No module named 'dq_utils'` (missing `dq-utils/src` on sys.path)

### Import path rules

- Run pytest from **repo root** so that `conftest.py` adds `dq-engine`, `dq-utils/src`, and other `src/` dirs to `sys.path`.
- Do not cd into `dq-engine/` and run `pytest` from there — the top-level `conftest.py` won't load and imports will fail.
- If a new package dir is missing from `conftest.py`'s `local_src_paths`, add it.

## Why

- Keeps test runs aligned with the repo-managed dependencies.
- Avoids architecture-specific failures caused by mixed arm64/x86_64 environments.
- Makes local and CI test behavior consistent.
