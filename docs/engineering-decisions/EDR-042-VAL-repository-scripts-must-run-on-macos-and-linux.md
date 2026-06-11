# EDR-042 [VAL]: Repository Scripts Must Run on macOS and Linux

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: VAL

## Context
This repository relies heavily on shell scripts for validation, local setup, seed flows, debugging, maintenance tasks, and container orchestration. Those scripts are run by contributors from both macOS and Linux environments.

In practice, platform drift has caused recurring breakage:

- scripts used macOS-only command flags such as `base64 -D` or `sed -i ''`
- machine-specific paths leaked into scripts instead of using repo-relative paths
- wrapper scripts assumed one host environment even when the repository is intended to be usable from both macOS and Linux

These failures are avoidable and create needless friction for validation and local development. The repository already has platform-specific handling where required, for example `scripts/python_arm64.sh` only forces `arch -arm64` on Apple Silicon and degrades to normal execution elsewhere.

## Decision
Adopt the following repository rule for scripts:

- Repository scripts intended to be run from a checked-out workspace MUST run on both macOS and Linux.
- New and modified scripts MUST avoid platform-exclusive command forms unless they are guarded by a portable fallback.
- Scripts MUST use repo-relative paths and environment-derived paths rather than machine-specific absolute paths.
- If a script invokes another tool with known platform differences, the script MUST normalize that behavior internally rather than assuming one platform.
- Container-only scripts may assume the container runtime environment, but any host-side wrapper that launches them MUST still work on macOS and Linux.

## Rationale
- Contributors should not need to rewrite or patch core repo scripts depending on whether they are on macOS or Linux.
- Validation, setup, and maintenance tooling are part of the repository contract and should behave consistently across supported host operating systems.
- Encoding portability in the script itself is cheaper and more reliable than relying on tribal knowledge about BSD-versus-GNU tool differences.
- The repository already accepts platform-specific implementation details when they are contained behind a portable wrapper; that pattern should be the default for all scripts.

## Scope Boundaries
This decision applies to repository scripts that are expected to be launched from the workspace checkout, including validation wrappers, setup helpers, seed helpers, generators, and operational/debugging scripts.

It does not require:
- Windows-native support
- identical implementation details across macOS and Linux when a guarded compatibility branch is needed
- host-side execution of scripts that are intentionally container-only, image-entrypoint-only, or otherwise executed solely inside a Linux container runtime

## Consequences
**Positive**
- Repository scripts become predictable across the two supported host operating systems.
- Contributors are less likely to hit avoidable BSD/GNU shell-tool differences.
- Portability regressions become reviewable policy violations instead of ad hoc cleanup work.

**Negative**
- Script authors must spend more effort on portable command usage and path handling.
- Some existing scripts need incremental cleanup when they are touched.
- A few scripts may need compatibility helpers instead of the shortest platform-specific command.

## Implementation Guidance
- Prefer portable shell patterns and guard BSD/GNU differences explicitly when unavoidable.
- Use repo-relative path discovery such as `SCRIPT_DIR` and `ROOT_DIR` instead of hardcoded host paths.
- Keep macOS-specific handling behind explicit conditionals and ensure Linux continues to execute normally.
- When using external tools with incompatible flags across platforms, add an internal compatibility helper rather than documenting a manual workaround.
- Treat portability checks as part of script review for any new or modified repository script.

## Related Artifacts
- `scripts/python_arm64.sh`
- `scripts/test_jwt_flow.sh`
- `dq-db/scripts/update_schema_version.sh`
- `scripts/validate_support_request_by_mail.sh`
- `docs/engineering-decisions/EDR-041-VAL-python-arm64-launcher-required-on-apple-silicon.md`
- `/memories/repo/dq-rulebuilder-shell-linux-portability-note.md`