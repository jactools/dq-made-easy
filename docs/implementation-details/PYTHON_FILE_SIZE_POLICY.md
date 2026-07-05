# Python File Size Policy

**Rule:** New or modified Python files must have fewer than 1000 lines of code.

## Rationale

Large files are a primary indicator of violated Single Responsibility Principle (SRP). When a file exceeds 1000 lines it typically:

- Owns multiple responsibilities that should be separated
- Is hard to review, test, and maintain
- Creates merge conflicts and cognitive overhead
- Hides coupling between concerns

This policy enforces module discipline at the point of creation, making it harder to accumulate technical debt.

## Rule details

### Scope

- Applies to all Python files (`.py`) in the repository.
- Excludes generated files, vendored code, and third-party dependencies.
- Line count measures non-empty lines (blank lines and comments excluded).

### Enforcement

| File status | Rule |
|---|---|
| **New files** | Must be < 1000 lines. Validation script exits non-zero on violation. |
| **Modified existing files** | Must stay < 1000 lines if they were already under the threshold. |
| **Existing files > 1000 lines** | Informational only. Not a blocking violation, but flagged for refactoring. |
| **Allow-listed files** | Exempt from the threshold. Must have a documented reason. |

### Validation

Run the validation script locally:

```bash
# Full report
./scripts/validation/validate_python_file_sizes.sh

# JSON output (for CI)
./scripts/validation/validate_python_file_sizes.sh --json

# Only check new files
./scripts/validation/validate_python_file_sizes.sh --new-only

# Custom threshold (e.g. stricter for dq-engine)
./scripts/validation/validate_python_file_sizes.sh --threshold 800
```

The script reports:

1. **New file violations** — files that were created or added and exceed the threshold (blocking).
2. **Existing files over threshold** — informational list of legacy files still over 1000 lines.
3. **Extreme values** — top N largest files by line count.
4. **Summary** — total files scanned, total lines, violation counts.

### Allow-list

Files that legitimately exceed 1000 lines can be exempted via `scripts/validation/python-file-allow-list.txt`:

```
# One relative path per line. Lines starting with # are comments.
dq-api/fastapi/app/infrastructure/orm/models.py          # auto-generated ORM models
dq-api/fastapi/tests/api/test_gx_endpoint.py             # monolithic endpoint test suite (refactoring tracked in PROJ-XXX)
```

Allow-list entries must include a comment explaining the exemption and a tracking reference.

## Current state

As of 2026-07-05:

- **Total Python files:** 1028
- **Total lines of code:** ~226,000
- **Files over 1000 lines:** 27
- **Largest file:** `dq-api/fastapi/tests/api/test_execution_monitoring.py` (3,987 lines)

### Extreme values (top 10)

| Rank | File | Lines |
|---|---|---|
| 1 | `dq-api/fastapi/tests/api/test_execution_monitoring.py` | 3,987 |
| 2 | `dq-api/fastapi/tests/api/test_gx_endpoint.py` | 3,953 |
| 3 | `dq-api/fastapi/app/infrastructure/repositories/postgres_rules_repository.py` | 1,998 |
| 4 | `dq-api/fastapi/app/api/v1/endpoints/execution_monitoring.py` | 1,938 |
| 5 | `dq-api/fastapi/app/api/v1/endpoints/gx.py` | 1,793 |
| 6 | `dq-llm/entrypoint.py` | 1,784 |
| 7 | `dq-api/fastapi/tests/application/use_cases/test_rule_mutation_use_cases.py` | 1,755 |
| 8 | `dq-api/fastapi/app/infrastructure/orm/models.py` | 1,731 |
| 9 | `dq-api/fastapi/tests/api/test_suggestions_endpoints.py` | 1,658 |
| 10 | `dq-api/fastapi/app/infrastructure/repositories/in_memory_rules_repository.py` | 1,455 |

### Refactoring targets

The following files are candidates for module splits (tracked in implementation plans):

| File | Lines | Reason |
|---|---|---|
| `dq-api/fastapi/app/api/v1/endpoints/gx.py` | 1,793 | Multiple endpoint groups; split by feature area |
| `dq-api/fastapi/app/infrastructure/repositories/postgres_rules_repository.py` | 1,998 | Mixed CRUD + complex queries; split by operation |
| `dq-api/fastapi/app/api/v1/endpoints/execution_monitoring.py` | 1,938 | Run + incident + approval endpoints; split by domain |
| `dq-llm/entrypoint.py` | 1,784 | Tool registration + startup + routing; split concerns |

## When you hit the limit

If your PR adds a file that exceeds 1000 lines:

1. **Split by responsibility** — Each module should own exactly one feature or concern.
2. **Extract shared helpers** — Move reused functions into a dedicated `_helpers.py` or domain module.
3. **Use sub-modules** — For packages, split into `pkg/core.py`, `pkg/io.py`, `pkg/format.py`, etc.
4. **Allow-list with tracking** — If splitting is blocked by a larger refactor, add to the allow-list with a JIRA reference.

## CI integration

This check is in the `groups=repo` validation group. It runs as part of the full repo validation but is excluded from individual smoke checks (`include=false`).

To add it to your CI pipeline:

```yaml
- name: Validate Python file sizes
  run: ./scripts/validation/validate_python_file_sizes.sh --new-only --json > file-sizes-report.json
```

## AI Agent compliance

The rule is declared in these instruction files so Copilot, Claude, Cursor, and other AI assistants see it:

- `AGENTS.md` — repo root, read by all major agents
- `.github/copilot/01-general.md` — canonical Copilot instructions (referenced by `.copilot-instructions.md`)

These files tell agents to split files before they reach 800 lines and to run the validation script after creating new Python files.

## Pre-commit hook

The hook is configured in `.pre-commit-config.yaml` and runs automatically on every `git commit`:

```yaml
repos:
  - repo: local
    hooks:
      - id: python-file-sizes
        name: Python file size check (< 1000 lines)
        entry: python3 scripts/validation/validate_python_file_sizes.py --allow-list scripts/validation/python-file-allow-list.txt --files
        language: system
        types: [python]
        stages: [pre-commit]
        pass_filenames: true
```

To install the hook:

```bash
pre-commit install
```

To run manually:

```bash
pre-commit run python-file-sizes --all-files
```

The hook checks only the staged Python files (fast, no full repo scan) and exits with code 1 if any new file exceeds 1000 lines.
