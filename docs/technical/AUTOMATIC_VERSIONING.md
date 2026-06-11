# Automatic Docker Image Versioning

This system automatically generates version tags for Docker images using **semantic versioning (major.minor) + content hash**. This ensures:

- **Semantic versioning**: Use major.minor for releases (e.g., `0.10`, `1.0`, `2.0`)
- **Deterministic builds**: Same content = same tag (e.g., both produce `0.11-a3f5d8e`)
- **Automatic change detection**: Changed content = new tag
- **No manual tagging required**: Version tags are generated automatically
- **Efficient builds**: Only rebuild when content actually changes

## How It Works

When you run `./scripts/build_and_push_all.sh`:

1. **Read Base Version**: Reads `VERSION_MANIFEST.json` (`apps.ui`) and derives `major.minor` (e.g., `0.10`)
2. **Content Hashing**: Each image hashes the real Docker build inputs it depends on
3. **Short Hash**: First 7 characters of the hash are appended to the base version
4. **Final Tag**: Format is `major.minor-contenthash` (e.g., `1.0-a3f5d8e`)
5. **Per-Image Tags**: Each image gets its own tag based on its own inputs

By default the build wrapper targets the **core** product images. Use `--scope repo` (or `--all-repo-images`) to include the wider repo-managed image set such as `db-seed`, metadata helper images, `container-metrics`, and `zammad-seed`.

### Example

```
VERSION_MANIFEST.json apps.ui: 0.11.2
dq-ui major.minor derived: 0.11
dq-api Dockerfile content hash: a3f5d8e2... → DQ_API_TAG=0.11-b7c2e1f
dq-ui Dockerfile content hash:  b7c2e1f4... → DQ_FRONTEND_TAG=0.11-b7c2e1f
(if UI changes, but API doesn't: next build might be 0.11-a3f5d8e for API and 0.11-c9d6a4b for UI)
```

## Usage

### Default (Automatic Semantic Versioning)

```bash
./scripts/build_and_push_all.sh
```

**Output:**
```
Calculating version tags from Docker build inputs (major.minor: 0.11)...
Auto-detected version tags based on content hash:
========================================
Calculated Version Tags
========================================
Base version: 0.11

Core images:
DQ_BASE_TAG:      0.11-a3f5d8e
DQ_API_TAG:       0.10-b7c2e1f
DQ_ENGINE_TAG:    0.10-c9d6a4b
DQ_PROFILING_TAG: 0.10-d2e8f3c
DQ_FRONTEND_TAG:  0.10-e1f4a6d
DQ_KONG_TAG:      0.10-f5a7b2c

Auxiliary repo images:
DQ_DB_SEED_TAG:     0.10-a1b2c3d
DQ_ZAMMAD_SEED_TAG: 0.11-f6e5d4c
========================================
```

Each image is built with its own version tag.

### Bump Major or Minor Version

Update the UI app marker in `VERSION_MANIFEST.json` (e.g., `apps.ui: <current> → 0.11.2`).

All images will then be tagged with `0.11-<hash>`.

### Manual Version Override

Force all services to use a specific version tag:

```bash
./scripts/build_and_push_all.sh --version v2.0.0
```

This will tag all images as `v2.0.0` regardless of content or VERSION file.

### Other Options

```bash
./scripts/build_and_push_all.sh --no-cache          # Build without cache
./scripts/build_and_push_all.sh --no-push            # Build only, don't push
./scripts/build_and_push_all.sh --no-cache --no-push # Build fresh, don't push
./scripts/build_and_push_all.sh --scope repo         # Build core + repo-managed auxiliary images
```

## How Tags Are Calculated

The `scripts/calculate_versions.sh` script:

1. **Reads VERSION_MANIFEST.json**: Uses `apps.ui` to derive a `major.minor` base
2. **Hashes each image**: SHA256 hash of the Dockerfile, copied scripts/assets, and other Docker build inputs
3. **Combines**: Creates final tag as `major.minor-contenthash`

### Example Tag Calculation

```bash
# View calculated tags
./scripts/calculate_versions.sh --display

# Or source it to use tags in your own scripts
source ./scripts/calculate_versions.sh
echo "API version: $DQ_API_TAG"
```

## Managing Versions

### Workflow for New Release

1. Bump version in `VERSION_MANIFEST.json` (typically `apps.ui` / `apps.api`).

2. Build and test:
   ```bash
   ./scripts/build_and_push_all.sh --no-push
   ```

3. Push to registry:
   ```bash
   ./scripts/build_and_push_all.sh
   ```

4. Commit change:
  ```bash
  git add VERSION_MANIFEST.json
  git commit -m "Release 0.11.x"
  git tag v0.11.2
  ```

## Integration with Docker Compose

The `docker-compose.yml` references version tags via environment variables:

```yaml
api:
  image: dq-api:${DQ_API_TAG:-latest}
  
dq-engine:
  image: dq-engine:${DQ_ENGINE_TAG:-latest}
```

### Using Specific Versions with Docker Compose

```bash
# Run containers with auto-detected versions
source <(./scripts/calculate_versions.sh > /dev/null)
docker-compose up

# Or with manual override
export DQ_API_TAG=0.10-custom
export DQ_ENGINE_TAG=0.10-custom
docker-compose up

# Optional: override major.minor base used by scripts/calculate_versions.sh
export MAJOR_MINOR_OVERRIDE=0.10
source <(./scripts/calculate_versions.sh > /dev/null)
```

## When Tags Change

A new version tag is generated when:

- **VERSION file is updated** (e.g., `1.0` → `1.1`)
- **Dockerfile** is modified
- **Source code** in `src/` directory changes
- **New files** are added to the service directory
- **Files are deleted** from the service directory

The tag will NOT change if:
- You modify files that are outside the image's declared Docker inputs
- You rebuild again without code/version changes

The tag can change when non-source files that are copied into an image change, for example runtime scripts, generated frontend assets, or contract files consumed by the image build.

## Benefits

1. **Semantic Versioning**: Track releases with meaningful version numbers
2. **Content Determinism**: Same content always produces same tag
3. **Change Tracking**: See which services changed in each build
4. **No Manual Tagging**: Completely automatic
5. **Zero Coordination**: Each service independently versioned based on its content
6. **Reproducible**: Same VERSION + code = same tags every time

## Examples

```bash
# Build with current version (major.minor-hash)
./scripts/build_and_push_all.sh

# Bump minor version and build
echo "1.1" > VERSION
./scripts/build_and_push_all.sh

# Test build locally without pushing
./scripts/build_and_push_all.sh --no-push

# Check what versions would be used
./scripts/calculate_versions.sh --display

# Force specific version for all services
./scripts/build_and_push_all.sh --version prod-2026-03-03
```

## Troubleshooting

### "Unable to read major.minor version from VERSION_MANIFEST.json apps.ui"

Ensure `VERSION_MANIFEST.json` exists and `apps.ui` is a valid semver string like `0.11.2`.

### Tags are different from expected
Check the current VERSION and content hashes:
```bash
./scripts/calculate_versions.sh --display
cat VERSION_MANIFEST.json
```

### Force new tags with same VERSION

If you need to force new tags without changing `major.minor`, you must change the hashed inputs for the service (e.g., Dockerfile or `src/` content).

## On-demand version determination

To compute and/or write the `apps` map in `VERSION_MANIFEST.json` based on `docker compose` images and deterministic internal tags:

```bash
node ./scripts/determine_versions.js --print
node ./scripts/determine_versions.js --write

# Convenience wrapper (recommended):
./scripts/update_version_manifest.sh
```
Modify any file in a service directory (even whitespace):
```bash
echo "" >> dq-api/Dockerfile.api.archive
./scripts/build_and_push_all.sh
```

## Advanced: Using in CI/CD

In a GitHub Actions or other CI/CD system:

```yaml
- name: Calculate versions
  run: |
    source ./scripts/calculate_versions.sh
    echo "API_TAG=$DQ_API_TAG" >> $GITHUB_ENV
    echo "ENGINE_TAG=$DQ_ENGINE_TAG" >> $GITHUB_ENV
    # ... etc

- name: Build and push
  run: ./scripts/build_and_push_all.sh
```

The build script will automatically use the calculated versions from the VERSION file + content hashes.
