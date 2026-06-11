# Validation scripts

This repository uses `scripts/validate.sh` as a wrapper to run validation and smoke-test scripts.

User-facing rule:
- Invoke validation and smoke scripts only from `scripts/`.
- Never invoke implementations from subdirectories under `scripts/` directly.
- `scripts/validation/` contains the internal implementations that the top-level wrappers call.

## How grouping works

The wrapper auto-discovers internal validation implementations under `scripts/validation/` whose basenames start with `validate_`.

It then runs the matching top-level wrapper under `scripts/` with the same basename.

Each validate script may declare its group membership via a header tag:

- `# validate: groups=repo,api`

Notes:

- Groups are case-insensitive.
- Separate groups with commas.

### Helper scripts

Some validate scripts are helpers called by another script (e.g. lifecycle runner). Mark them so they are listed, but not executed directly:

- `# validate: include=false`

### Ignored scripts

If a `validate_*.sh` file should be completely ignored by the wrapper:

- `# validate: ignore=true`

## Supported groups

- `all`: runs validation smoke scripts plus all directly includable `validate_*.sh` scripts, excluding `include=false` helpers and `ignore=true` entries.
- `repo`: repo-only checks (typically no Docker).
- `governance`: governance logging, monitoring, and release-policy checks used by CI gates.
- `api`: API validations and API observability smoke.
- `regression`: end-to-end regression validations for high-value workflows.
- `ui`: UI → gateway → API propagation validations.
- `engine`: engine validations.
- `profiling`: profiling worker lifecycle validations.
- `observability`: monitoring/observability validations.
- `openmetadata`: OpenMetadata smoke validations.
- `other`: runs untagged `validate_*.sh` scripts (scripts without any `# validate: ...` tag).

## Usage

- Run the full default set: `scripts/validate.sh`
- List groups and scripts: `scripts/validate.sh --list`
- Run a group: `scripts/validate.sh repo`
- Run governance gates only: `scripts/validate.sh governance`
- Run untagged scripts: `scripts/validate.sh other`

## Interactive terminal-safe usage

When running validations from a command-launched terminal, wrap the command with `scripts/run_keepalive.sh` so failures are reported and recorded without closing the terminal session:

- Run a validation group and keep the terminal alive: `scripts/run_keepalive.sh scripts/validate.sh regression`
- Run a single top-level validation wrapper and keep the terminal alive: `scripts/run_keepalive.sh scripts/validate_user_login_end_to_end.sh`

The wrapper writes the latest child exit status to `tmp/last_terminal_command_status`. Automation that must receive the original non-zero status can call validation scripts directly or use `scripts/run_keepalive.sh --propagate ...`.

## Adding a new validate script

1. Create a new internal implementation under `scripts/validation/` with basename `validate_<something>.sh`.
2. Create a top-level wrapper `scripts/validate_<something>.sh` that execs the internal implementation.
3. Add `set -euo pipefail`.
4. Add a short documentation header near the top:

	- `# Purpose: ...`
	- `# What it does:` bullets
	- `# Version: ...`
	- `# Last modified: YYYY-MM-DD`
	- Optional but preferred for modified scripts: `# Changelog:` with 1-3 versioned bullets, for example `# - 1.2 (2026-04-22): Replaced GNU-only xargs -r with a portable empty-input guard.`

5. Add a tag near the top, e.g. `# validate: groups=repo`.
6. If it is a helper only called by another validate script, add `# validate: include=false`.
