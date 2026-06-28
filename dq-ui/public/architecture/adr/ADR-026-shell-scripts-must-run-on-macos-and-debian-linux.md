# ADR-026: Shell Scripts Must Run on macOS and Debian Linux

**Status**: Accepted
**Date**: 2026-04-22
**Related**: [ADR-012](./ADR-012-test-automation-tool-selection-and-evidence-strategy.md)

## Context

dq-rulebuilder relies heavily on shell scripts for local setup, container startup, seeding, validation, publishing, and smoke-test orchestration.

Those scripts are part of the platform surface, not disposable local helpers. They are run by maintainers and contributors on macOS laptops and by automation or Linux-based environments that are commonly Debian or Debian-derived.

The repository already shows the portability risks:

- macOS ships Bash 3.2 by default, which does not support several Bash 4+ features,
- macOS userland tools often use BSD semantics, while Debian commonly uses GNU semantics,
- shell parameter-expansion edge cases and command flags that work on one platform can fail immediately on the other,
- startup and validation workflows depend on scripts under `scripts/` and related helper locations, so one portability bug can block the whole platform workflow.

Recent failures in repository tooling were caused by exactly this class of issue: shell code that was valid in one environment but not portable across the supported host platforms.

The project needs an explicit architectural rule, not just ad hoc fixes, so shell-based operational workflows remain dependable.

## Decision

Adopt a repository-wide shell portability rule:

1. Shell scripts that are part of repository workflows MUST run on both macOS and Debian Linux.
2. This requirement applies to scripts under `scripts/` and to any other repository shell entrypoint that is invoked by documented setup, build, seed, validation, deployment, or smoke-test flows.
3. Scripts MUST target macOS default Bash 3.2 compatibility when they require Bash.
4. Scripts MUST avoid Bash 4+ only features such as `mapfile`, associative arrays, `${var,,}`, `${var^^}`, and other non-portable shell constructs that are unavailable in macOS default Bash.
5. Scripts MUST avoid assuming GNU-only command-line flags or GNU-only behavior when invoking common tools such as `sed`, `base64`, `readlink`, `date`, `mktemp`, and similar utilities.
6. If platform-specific behavior is unavoidable, scripts MUST detect the platform explicitly, branch deliberately, and keep both macOS and Debian Linux code paths working.
7. If a required tool or supported platform capability is unavailable, scripts MUST fail fast with a clear non-zero exit and an actionable error message.
8. New or modified shell scripts MUST be reviewed with macOS and Debian Linux portability as a first-class acceptance criterion, not as a follow-up cleanup.

For this ADR, “run on macOS and Debian Linux” means:

- the script can execute successfully for its supported use case on both platforms, or
- the script can detect a missing prerequisite and fail fast with a clear message on both platforms,
- without relying on undocumented shell upgrades or replacing the platform’s default toolchain expectations.

## Consequences

### Positive

- Local developer workflows become more predictable across the supported host platforms.
- CI and operational scripts are less likely to diverge from contributor workflows.
- Portability bugs are treated as architectural regressions instead of incidental shell glitches.
- Repository automation becomes easier to trust because the supported host matrix is explicit.

### Negative

- Script authors must avoid some convenient Bash 4+ features and GNU-specific shortcuts.
- Some scripts will need small helper functions or explicit branching for BSD versus GNU tool differences.
- Reviews may take longer because portability needs to be considered for shell changes.

## Implementation Guidance

- Use `#!/usr/bin/env bash` and `set -euo pipefail` for Bash scripts.
- Prefer POSIX-ish constructs when practical.
- Gate platform-specific behavior with explicit `uname` checks rather than assuming one host.
- Treat macOS default Bash 3.2 as the lower-bound compatibility target for Bash syntax.
- Prefer portable wrappers for utilities that differ between BSD and GNU implementations.
- Add or extend validation coverage when a script change affects setup, startup, seeding, or smoke-test workflows.
- Do not merge shell changes that only work on one of the supported host platforms unless the script is explicitly documented as platform-specific and out of scope for shared workflows.

## Related Artifacts

- [scripts/seed_stack.sh](../../scripts/seed_stack.sh)
- [scripts/validate_venv_architecture.sh](../../scripts/validate_venv_architecture.sh)
- [scripts/start-containers.sh](../../scripts/start-containers.sh)
- [scripts/validate.sh](../../scripts/validate.sh)
- [.github/copilot-instructions.md](../../.github/copilot-instructions.md)