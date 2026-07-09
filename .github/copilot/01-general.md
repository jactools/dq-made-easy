# General Rules

## Error Handling and Validation (Fundamental)

**NEVER disable, suppress, or work around errors to make them go away.** Errors are signals that indicate:
- Configuration or structural problems that need fixing
- Invalid assumptions about code or data  
- Broken contracts or dependencies

**When an error appears:**
1. **Analyze** — Understand the root cause. Is it a missing file? Invalid configuration? Broken link? Logic error?
2. **Fix** — Address the underlying issue, not the symptom. For example:
   - If a build system reports broken links, find and fix the links (don't change error level to 'warn')
   - If validation fails, correct the invalid state (don't skip the validation)
   - If a dependency is missing, install it (don't remove the dependency declaration)
3. **Verify** — Re-run the tool/test/build to confirm the fix works

**Exception:** Only suppress or work around errors if you've **explicitly asked the user** and received **explicit approval** for that approach. Document the decision and the justification in code comments or commit messages.

## Python File Size (Enforced)

- **Every new or modified Python file must have fewer than 1000 non-empty lines.**
- If you are writing a file that approaches 800 lines, stop and split it into smaller modules before continuing.
- Existing files over 1000 lines are tracked in `scripts/validation/python-file-allow-list.txt` and must not grow further.
- Validation script: `scripts/validation/validate_python_file_sizes.py` (runs in `validate.sh repo`).
- The rule exists because large files violate SRP, are hard to review, and hide coupling. Split by responsibility, not arbitrarily.

## Module Naming Conventions

- Shared execution modules: `dq_plan_execution*.py` (engine-agnostic)
- Shared lowerer modules: `dq_plan_lowerers*.py` (engine-specific rule lowering)
- Engine-specific execution adapters: `<engine>_execution_adapter.py`
- Engine-specific dispatch: `<engine>_dispatch*.py` (e.g., `gx_dispatch_worker.py`)
- Never use `gx_` prefix for engine-agnostic types or helpers.

## Dependency Layering (No Upward Imports)

```
Layer 0 (types):          dq_plan_execution_types.py
Layer 1 (contract):       dq_plan_execution_contract.py
Layer 2 (lowerers):       dq_plan_lowerers.py, dq_plan_lowerers_*.py
Layer 3 (shared exec):    dq_plan_execution_payload.py, _api.py, _orchestrator.py
Layer 3.5 (shared output): dq_plan_execution_report.py, _persistence.py, _streaming.py
Layer 4 (facade):         dq_plan_execution.py
Layer 5 (engine-specific): *_execution_adapter.py
Layer 6 (dispatch):       gx_dispatch_*.py, *_dispatch*.py
```

- A layer may only import from equal-or-lower layers. Never import upward.
- Engine-specific modules must not import from each other.
- Architecture reference: `docs/technical/DQ_ENGINE_MODULE_ARCHITECTURE.md`

## Test-Proof Layout

- Proof files: `test-results/test-proof/<app_version>/<proof_type>/<file>.json` (flat, no subdirectories under `proof_type`)
- Evidence: `test-results/evidence/<app_version>/<evidence_dir>/`
- Markdown docs: `docs/test-proof/<app_version>/` (not in test-results)
- Shared writer: `scripts/validation/_test_proof.py`

## Documentation

- Implementation plans go in `docs/implementation-details/`
- Technical reference docs go in `docs/technical/`
- Policy docs go in `docs/policies/`
- Always update docs when code changes. If you modify a module, update its architecture doc reference.

## Running Tests

- Never run `python3`, `pytest`, or `venv/bin/python` directly for tests.
- Always use `scripts/python_arm64.sh --python-bin ./venv/bin/python -m pytest ...`
- See `.github/copilot/03-testing.md` for the full rules and error patterns.

## Conflict Resolution

If a rule conflicts with an explicit developer or system instruction, raise the conflict to the user. Do not silently override.
