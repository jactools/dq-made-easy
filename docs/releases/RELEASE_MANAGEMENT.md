# Release Management

This document describes how releases are managed, what "concluding a release" means, and what must change when you advance to the next version.

## Core Principle

**A concluded release no longer accepts changes.** When you conclude a release, the version is frozen: its test proofs, release notes, and documentation are locked. All active development then targets the next version.

## Version Identity

The app version is defined in four files and must always be consistent:

| File | Key | Purpose |
|------|-----|---------|
| `VERSION_MANIFEST.json` | `apps.ui` | Docker image base version (`major.minor` derived from this) |
| `VERSION_MANIFEST.json` | `apps.api` | API app version (must match `apps.ui`) |
| `dq-ui/package.json` | `version` | Frontend npm package version |
| `dq-ui/docs-site/package.json` | `version` | Docs-site npm package version |

These four values are always the same. They define the **current development version**.

### Tracked Components

`VERSION_MANIFEST.json` tracks which components changed in the current version under `components`:

```json
"components": {
  "Documentation": "0.11.6",
  "Infrastructure": "0.11.6",
  "Testautomation": "0.11.6"
}
```

Only components that actually changed in the release carry the current version. Other components keep their last-bumped version. This gives a per-component change history.

## Release Lifecycle

```
Develop on v0.11.6  ──→  Conclude v0.11.6  ──→  Develop on v0.11.7
     │                        │                        │
     │                        │                        │
  test proofs in           test proofs              new test
  0.11.6/                  frozen in 0.11.6/        proofs in 0.11.7/
  release notes            locked                    release notes
  version markers          bumped to 0.11.7          version markers
  pointing at 0.11.6       pointing at 0.11.7        pointing at 0.11.7
```

### During Active Development (before conclusion)

While developing on a version (e.g. `0.11.6`):

- All version markers point at `0.11.6`
- New test proofs are created under `test-results/test-proof/<current-version>/<proof_type>/`
- Release notes draft lives in `docs/releases/RELEASE_<version>_*.md`
- `TECHNICAL.md` changelog has an open `### v<version>` section
- `RELEASE_NOTES_USER.md` has an open `## v<version>` section
- `docs/releases/README.md` lists the current version as "Latest releases"
- **Do not** add changes to concluded (previous) version sections — always target the current version

### Concluding a Release

To conclude release `v0.11.6` and begin `v0.11.7`:

1. **Finalize the release documentation**
   - Complete `RELEASE_NOTES_USER.md` section for v0.11.6
   - Complete `TECHNICAL.md` changelog entry for v0.11.6
   - Ensure `docs/releases/RELEASE_0_11_6_*.md` captures all changes
   - Verify test proofs under `test-results/test-proof/0.11.6/` are complete and valid

2. **Freeze test proofs**
   - Test proofs stay in their version directory (`test-results/test-proof/0.11.6/`)
   - No new proofs are added to concluded versions
   - `publish_test_proof.sh` generates Markdown pages under `docs/test-proof/0.11.6/`
   - Run `./scripts/validation/validate_test_proof.sh` to confirm all proofs are schema-compliant

3. **Bump version markers** (these changes open the next development window)

   - Determine the next version: increment the patch digit (e.g. `0.11.6` → `0.11.7`). For minor releases, increment the minor digit and reset the patch (e.g. `0.11.x` → `0.12.0`).
   - Update all four version markers to the new version:
     - `dq-ui/package.json`: `"version": "0.11.6"` → `"0.11.7"`
     - `dq-ui/docs-site/package.json`: `"version": "0.11.6"` → `"0.11.7"`
     - `VERSION_MANIFEST.json` `apps.ui`: `"0.11.6"` → `"0.11.7"`
     - `VERSION_MANIFEST.json` `apps.api`: `"0.11.6"` → `"0.11.7"`
   - Update `VERSION_MANIFEST.json` `components`: bump only components that actually changed in the concluded release to the new version. Leave all other components at their previous value. If you are unsure which components changed, ask the user.
   - Update `docs/releases/README.md`: change "Latest releases" to list the new version
   - Add a new entry in `RELEASE_NOTES_USER.md`: `## v0.11.7 - <title> (<date>)` with a brief description line
   - Add a new entry in `TECHNICAL.md`: `### v0.11.7 (<date>)` (initially can be empty or have a placeholder)

4. **Rebuild docs and frontend**
   - Run `./scripts/local_build_frontend.sh` to regenerate:
     - `dq-ui/dist/` (Vite production build with new version markers)
     - `dq-ui/public/docs/` (Docusaurus build)
     - `dq-ui/public/user-manuals/` (synced from source)
     - `dq-ui/public/architecture/adr/` (synced from source)
   - **Do not** run `start_local.sh` — it starts Vite in the background. Use `local_build_frontend.sh` which only builds without starting a server.
   - These rebuilt files carry the new version and must be committed

5. **Commit**
   ```
   git add -A
   git commit -m "bump version to 0.11.7

   - dq-ui: 0.11.6 -> 0.11.7
   - docs-site: 0.11.6 -> 0.11.7
   - VERSION_MANIFEST: ui, api, components -> 0.11.7
   - Rebuild docs and frontend dist/"
   ```

## What Does NOT Change When Concluding a Release

- **Test proof JSON files** stay in their version directory. Proofs from v0.11.6 remain under `test-results/test-proof/0.11.6/`.
- **Evidence directories** stay in their version directory under `test-results/evidence/`.
- **Released Docker images** are immutable. Their tags (`0.11-<hash>`) are already baked.
- **Published release notes** for previous versions are not modified.

## Docker Image Versioning

Docker images use `major.minor-contenthash` tags derived from `VERSION_MANIFEST.json`:

```
VERSION_MANIFEST.json apps.ui: "0.11.7"
  → major.minor derived: "0.11"
  → image tag: "0.11-a3f5d8e"
```

See [AUTOMATIC_VERSIONING.md](../../AUTOMATIC_VERSIONING.md) for details on how tags are calculated. When you bump the app version, the `major.minor` base changes for all subsequent builds.

## Test Proof Schema

All test proofs must be valid JSON conforming to the canonical schema:

- Schema: `docs/contracts/test-proof/v1/schema.json`
- Validator: `./scripts/validation/validate_test_proof.sh`
- Publisher: `./scripts/publish_test_proof.sh` (generates Markdown pages)
- Evidence root: `test-results/evidence/<version>/<proof_type>/`
- Proof root: `test-results/test-proof/<version>/<proof_type>/`

Valid `proof_type` values: `ui`, `ui-api`, `api`, `engine`, `database`, `ai`, `command`, `infra`.

When creating a new proof, the JSON must:
1. Have `app_version` matching the version directory name
2. Have `proof_type` matching the subdirectory name
3. Pass `./scripts/validation/validate_test_proof.sh` without errors

## Prebuild/Dev Hooks

The `dq-ui` package has `prebuild` and `predev` npm hooks that run the full doc generation pipeline:

```
prebuild/predev:
  1. build-public-docs.sh (copies docs, validates test proofs, builds Docusaurus)
  2. sync-adrs.mjs (copies ADRs to public/)
  3. sync-user-manuals.sh (copies manuals to public/)
  4. build:style-packages (builds Tailwind CSS)

build:
  5. vite build (produces dq-ui/dist/)
```

These hooks run on every `npm run build` and `npm run dev` (including `start_local.sh`). If the prebuild fails (e.g. a test proof is invalid), the build aborts. Fix the underlying issue — do not add `|| true` to suppress errors.

## Checklist: Concluding a Release

- [ ] All features for the release are complete
- [ ] Test proofs are created, schema-valid, and committed under `test-results/test-proof/<version>/`
- [ ] `RELEASE_NOTES_USER.md` entry is complete
- [ ] `TECHNICAL.md` changelog entry is complete
- [ ] `docs/releases/RELEASE_<version>_*.md` is finalized
- [ ] `./scripts/validation/validate_test_proof.sh` passes
- [ ] Version markers bumped to next version in all files listed above
- [ ] Docs and frontend rebuilt with `./scripts/local_build_frontend.sh`
- [ ] All changes committed with a clear bump commit message

## Instructions for AI Agents

When you are working on this repository, follow these rules for versioning, test proofs, and releases.

### Version markers — always consistent

The four version markers must always match the **current development version**:

| File | Key | Must equal |
|------|-----|------------|
| `dq-ui/package.json` | `version` | current dev version |
| `dq-ui/docs-site/package.json` | `version` | current dev version |
| `VERSION_MANIFEST.json` | `apps.ui` | current dev version |
| `VERSION_MANIFEST.json` | `apps.api` | current dev version |

If you change any of these, update all four. If you find them out of sync, raise the conflict to the user.

### Test proofs — must be schema-compliant

Every test proof JSON under `test-results/test-proof/<version>/<proof_type>/` must:

1. Have `app_version` matching the version directory name
2. Have `proof_type` matching the subdirectory name and be one of: `ui`, `ui-api`, `api`, `engine`, `database`, `ai`, `command`, `infra`
3. Contain all required fields from the schema
4. Pass `./scripts/validation/validate_test_proof.sh` without errors

Schema: `docs/contracts/test-proof/v1/schema.json`

If a proof fails validation, **fix the proof** (add missing fields, correct values). Do not add `|| true`, skip the validation, or suppress the error.

### When creating a test proof

1. Place it under `test-results/test-proof/<app_version>/<proof_type>/` as `<proof_id>.json`
2. Set `proof_id` to match the filename (without `.json`)
3. Set `app_version` to the current development version
4. Set `proof_type` to the directory name
5. Populate `test_files` with actual file paths (not placeholders)
6. Populate `assertions` with specific, checkable statements (not generic summaries)
7. Set `raw_evidence_directory` to point to the corresponding directory under `test-results/evidence/`
8. Run `./scripts/validation/validate_test_proof.sh` to verify
9. Run the doc rebuild to publish the Markdown page

### When asked to conclude a release

Do not modify any files inside the concluded version directory (`test-results/test-proof/<concluded-version>/`). Instead:

1. Verify the release documentation is complete:
   - `RELEASE_NOTES_USER.md` has a complete section for the concluded version
   - `TECHNICAL.md` has a complete changelog entry for the concluded version
   - `docs/releases/RELEASE_<version>_*.md` exists and captures the changes
2. Verify test proofs for the version are complete and valid by running `./scripts/validation/validate_test_proof.sh`
3. Bump all version markers to the next version (see "Concluding a Release" for the full procedure)
4. Rebuild docs and frontend using `./scripts/local_build_frontend.sh`
5. Commit the bump with a clear message (see template below)

### When the prebuild/predev hooks fail

The `prebuild` and `predev` npm hooks in `dq-ui/package.json` run the doc generation pipeline. If they fail:

1. Read the error message carefully
2. Fix the underlying issue (stale test proof, broken link, missing file)
3. Re-run to confirm it passes
4. **Never** add `|| true` or other error suppression

### Frontend dist/ — always in git

`dq-ui/dist/` is committed to git. After any change that affects the frontend build (code, docs, test proofs, ADRs, manuals):

1. Run `./scripts/local_build_frontend.sh` to rebuild
2. The rebuild runs the full pipeline: doc generation → test proof validation → Docusaurus build → ADR sync → manual sync → vite build
3. Commit the updated `dq-ui/dist/` files alongside your source changes
4. **Do not** skip the rebuild or commit source changes without the matching dist/

If the rebuild fails, fix the root cause (stale test proof, broken link, missing file). Do not add `|| true` or suppress errors.

### When in doubt

- Check the current version: `grep '"version"' dq-ui/package.json`
- Check the manifest: `python3 -c "import json; d=json.load(open('VERSION_MANIFEST.json')); print(d['apps']['ui'], d['apps']['api'])"`
- Validate proofs: `./scripts/validation/validate_test_proof.sh`
- Rebuild docs: `./scripts/local_build_frontend.sh`
