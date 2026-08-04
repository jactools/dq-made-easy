# Implementation Summary: Pre-commit hook alignment

**Date**: 2026-08-04  
**Status**: Complete

## Objective and Scope

This change aligns the repository's pre-commit configuration with the style used in `metadata-as-a-service`.

The scope of the change was:

- switch the module-rules and snake_case hooks to direct `venv/bin/python` execution
- mark the repository-wide validation hooks as `always_run`
- disable filename passing for the repo-wide validators so they run consistently on every commit
- keep the Python file-size hook in place as a separate pre-commit check

## Results

| Metric | Before | After |
|---|---|---|
| Module-rules hook entry | Shell wrapper | Direct `venv/bin/python scripts/validate_module_rules.py` |
| snake_case hook entry | Shell wrapper | Direct `venv/bin/python scripts/validate_snake_case.py` |
| Repo-wide validation behavior | File-scoped pre-commit execution | `always_run: true`, `pass_filenames: false` |
| Style parity with `metadata-as-a-service` | Partial | Aligned for the shared validators |

## Updated files

- `.pre-commit-config.yaml`

## Known Issues or Remaining Work

- The repository still keeps shell wrappers for `scripts/validate.sh` discovery and manual invocation; those wrappers remain useful outside pre-commit.
- `pre-commit` is not installed in the current local environment, so the hook configuration was aligned by inspection and direct script validation rather than by running `pre-commit` itself.

## Next Steps

1. Install `pre-commit` locally if hook installation or execution is needed.
2. Keep the pre-commit entries aligned with any future validator changes.
3. Consider whether other repo-wide validation scripts should follow the same direct-execution pattern.
