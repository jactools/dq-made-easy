# Automated Database Schema Versioning

## Overview

The database schema versioning system is now **fully automated** using git hooks. Whenever you modify schema files (`01_schema.sql`, etc.), a pre-commit hook automatically:

1. **Detects** schema changes being committed
2. **Checks** if the version was updated
3. **Prompts** you to auto-increment or update manually
4. **Records** the git commit hash for full traceability
5. **Updates** `system_info.csv` with the new version and git ref

## Quick Start

### One-Time Setup

Install the git hook (only needs to be done once per developer):

```bash
cd /Users/jacbeekers/gitrepos/dq-rulebuilder
./dq-db/scripts/install-git-hooks.sh
```

### Making Schema Changes

Just commit your changes normally:

```bash
# Edit the schema
vim dq-db/init/01_schema.sql

# Commit
git add dq-db/
git commit -m "feat(db): add new user_settings table"
```

The hook will detect the schema change and prompt:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Database Schema Changes Detected
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Changed files:
  - dq-db/init/01_schema.sql

Current schema version: 1.0.0
⚠  Schema changed but version not updated

Options:
  1) Auto-increment PATCH version (recommended for minor fixes)
  2) Run update script manually (for MAJOR/MINOR changes)
  3) Skip version check (not recommended)

Choose [1/2/3]:
```

## Hook Modes

Control the hook behavior with the `DB_VERSION_AUTO_INCREMENT` environment variable:

### 1. Prompt Mode (Default)
Interactive - asks what to do when schema changes detected:

```bash
git commit -m "feat: add table"
# Shows prompt with options 1/2/3
```

### 2. Auto Mode
Automatically increments PATCH version:

```bash
DB_VERSION_AUTO_INCREMENT=auto git commit -m "fix: update schema"
# Auto-increments: 1.0.0 → 1.0.1
# Records git commit hash automatically
```

**Use when:** Making small fixes, adding indexes, updating constraints

### 3. Strict Mode
Blocks commit if version not updated manually:

```bash
DB_VERSION_AUTO_INCREMENT=strict git commit -m "feat: add table"
# Error: COMMIT BLOCKED
# You must run: ./dq-db/scripts/update_schema_version.sh <version>
```

**Use when:** Enforcing manual version control in CI/CD pipelines

### 4. Skip Mode
Bypasses version check (not recommended):

```bash
DB_VERSION_AUTO_INCREMENT=skip git commit -m "wip: schema"
# Warning shown but commit proceeds
```

**Use when:** WIP commits, temporary testing (use sparingly!)

## Manual Version Updates

For MAJOR or MINOR version bumps, use the update script:

```bash
# For breaking changes (MAJOR)
./dq-db/scripts/update_schema_version.sh 2.0.0

# For new features (MINOR)
./dq-db/scripts/update_schema_version.sh 1.1.0

# For bug fixes (PATCH) - or let the hook auto-increment
./dq-db/scripts/update_schema_version.sh 1.0.1
```

The script:
- Updates `system_info.csv` with new version and timestamp
- Captures current git commit hash
- Updates `DB_VERSION.md` header
- Provides next-step instructions

## What Gets Tracked

### In `system_info.csv`:
```csv
info_key,info_value,description,updated_at
db_schema_version,1.0.1,Database schema version,2026-03-01 21:45:00.000000+00
db_schema_updated,2026-03-01 21:45:00.000000+00,Last schema update timestamp,2026-03-01 21:45:00.000000+00
db_git_commit,a1b2c3d,Git commit hash of schema change,2026-03-01 21:45:00.000000+00
```

### In UI System Info Modal:
- **Schema Version:** 1.0.1
- **Last Updated:** Mar 1, 2026
- **Git Commit:** a1b2c3d (with hover tooltip showing full hash)

## Traceability Flow

```
Developer edits 01_schema.sql
         ↓
git commit (pre-commit hook runs)
         ↓
Hook detects schema change
         ↓
Version auto-incremented: 1.0.0 → 1.0.1
         ↓
Git commit hash captured: a1b2c3d
         ↓
system_info.csv updated with version + git ref
         ↓
Commit proceeds
         ↓
./scripts/start-containers.sh --seed-all
         ↓
Database seeded with new version
         ↓
UI displays: "Schema v1.0.1 (a1b2c3d)"
```

## Files Modified by Hook

When auto-incrementing, the hook modifies and stages:
- `dq-db/mock-data/system_info.csv` - Version info with git commit hash

## Best Practices

### ✅ DO:
- Install the git hook for automatic tracking
- Use auto mode (`DB_VERSION_AUTO_INCREMENT=auto`) for routine changes
- Document changes in `DB_VERSION.md` after committing
- Let the hook capture git commit hashes automatically
- Test with `./scripts/start-containers.sh --seed-all` after schema changes

### ❌ DON'T:
- Skip version checks unless absolutely necessary
- Forget to document breaking changes in `DB_VERSION.md`
- Manually edit git commit hash in CSV (let the hook do it)
- Make schema changes without committing to git

## Troubleshooting

### Hook doesn't run
```bash
# Reinstall the hook
./dq-db/scripts/install-git-hooks.sh

# Check if hook is executable
ls -la .git/hooks/pre-commit
```

### Want to bypass hook temporarily
```bash
# Use --no-verify (use sparingly!)
git commit --no-verify -m "wip: schema changes"
```

### Wrong version auto-incremented
```bash
# Abort the commit
git reset HEAD~1

# Update version manually
./dq-db/scripts/update_schema_version.sh 1.1.0

# Commit again
git commit -m "feat(db): add new feature"
```

### Git commit hash not captured
The hook automatically captures the **current** HEAD commit. If you want a different hash, update manually:
```bash
# Edit system_info.csv directly (not recommended)
# Or run the update script which captures current git HEAD
./dq-db/scripts/update_schema_version.sh 1.0.1
```

## Configuration

### Set global preference for repository
```bash
# Always auto-increment
git config hooks.dbVersionMode auto

# Strict enforcement
git config hooks.dbVersionMode strict
```

### Per-commit override
```bash
# Override global config for single commit
DB_VERSION_AUTO_INCREMENT=strict git commit -m "..."
```

## Architecture

- **Hook location:** `.git/hooks/pre-commit`
- **Hook source:** `dq-db/scripts/git-hooks/pre-commit`
- **Installer:** `dq-db/scripts/install-git-hooks.sh`
- **Manual updater:** `dq-db/scripts/update_schema_version.sh`
- **Version file:** `dq-db/mock-data/system_info.csv`
- **Documentation:** `dq-db/DB_VERSION.md`
- **Checklist:** `dq-db/SCHEMA_CHANGE_CHECKLIST.md`

## Benefits

1. **Zero manual effort** - Hook handles versioning automatically
2. **Full traceability** - Every schema change linked to git commit
3. **Consistent versioning** - No more forgotten version updates
4. **Flexible modes** - Choose level of automation
5. **UI visibility** - Version and git commit displayed in system info
6. **Audit trail** - Complete history in git log + DB_VERSION.md

## Next Steps

After successful versioning is working:

1. ✅ Install git hook (one-time setup)
2. ✅ Make schema changes as normal
3. ✅ Commit and let hook handle versioning
4. ✅ Document in DB_VERSION.md
5. ✅ Test with `./scripts/start-containers.sh --seed-all`
6. ✅ Verify version in UI (click version number in header)
