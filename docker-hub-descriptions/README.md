# Docker Hub Descriptions

This directory contains the Docker Hub repository descriptions for all Data Quality Made Easy images.

## Naming Convention

All Docker Hub repositories use the `jacbeekers/dq-made-easy-*` prefix. Description files follow the pattern `dq-made-easy-<name>-*.txt/md`.

## Structure

Each image has three files:

- `dq-made-easy-<name>-short.txt` — Short description (max 100 characters, displayed in search results)
- `dq-made-easy-<name>-full.md` — Full description (Markdown formatted, displayed on repository page)
- `dq-made-easy-<name>-categories.txt` — Categories (one per line, for Docker Hub classification)

## Images

| Image | Repository | Description Files |
|-------|------------|-------------------|
| dq-made-easy-npm-base | jacbeekers/dq-made-easy-npm-base | `dq-made-easy-npm-base-short.txt`, `dq-made-easy-npm-base-full.md`, `dq-made-easy-npm-base-categories.txt` |
| dq-made-easy-api | jacbeekers/dq-made-easy-api | `dq-made-easy-api-short.txt`, `dq-made-easy-api-full.md`, `dq-made-easy-api-categories.txt` |
| dq-made-easy-engine | jacbeekers/dq-made-easy-engine | `dq-made-easy-engine-short.txt`, `dq-made-easy-engine-full.md`, `dq-made-easy-engine-categories.txt` |
| dq-made-easy-profiling | jacbeekers/dq-made-easy-profiling | `dq-made-easy-profiling-short.txt`, `dq-made-easy-profiling-full.md`, `dq-made-easy-profiling-categories.txt` |
| dq-made-easy-frontend | jacbeekers/dq-made-easy-frontend | `dq-made-easy-frontend-short.txt`, `dq-made-easy-frontend-full.md`, `dq-made-easy-frontend-categories.txt` |
| dq-made-easy-kong | jacbeekers/dq-made-easy-kong | `dq-made-easy-kong-short.txt`, `dq-made-easy-kong-full.md`, `dq-made-easy-kong-categories.txt` |
| dq-made-easy-db | jacbeekers/dq-made-easy-db | `dq-made-easy-db-short.txt`, `dq-made-easy-db-full.md`, `dq-made-easy-db-categories.txt` |
| dq-made-easy-keycloak | jacbeekers/dq-made-easy-keycloak | `dq-made-easy-keycloak-short.txt`, `dq-made-easy-keycloak-full.md`, `dq-made-easy-keycloak-categories.txt` |
| dq-made-easy-kafka | jacbeekers/dq-made-easy-kafka | `dq-made-easy-kafka-short.txt`, `dq-made-easy-kafka-full.md`, `dq-made-easy-kafka-categories.txt` |
| dq-made-easy-kafka-consumer | jacbeekers/dq-made-easy-kafka-consumer | `dq-made-easy-kafka-consumer-short.txt`, `dq-made-easy-kafka-consumer-full.md`, `dq-made-easy-kafka-consumer-categories.txt` |
| dq-made-easy-trino | jacbeekers/dq-made-easy-trino | `dq-made-easy-trino-short.txt`, `dq-made-easy-trino-full.md`, `dq-made-easy-trino-categories.txt` |
| dq-made-easy-edge | jacbeekers/dq-made-easy-edge | `dq-made-easy-edge-short.txt`, `dq-made-easy-edge-full.md`, `dq-made-easy-edge-categories.txt` |
| dq-made-easy-airflow | jacbeekers/dq-made-easy-airflow | `dq-made-easy-airflow-short.txt`, `dq-made-easy-airflow-full.md`, `dq-made-easy-airflow-categories.txt` |
| dq-made-easy-llm | jacbeekers/dq-made-easy-llm | `dq-made-easy-llm-short.txt`, `dq-made-easy-llm-full.md`, `dq-made-easy-llm-categories.txt` |
| dq-made-easy-db-seed | jacbeekers/dq-made-easy-db-seed | `dq-made-easy-db-seed-short.txt`, `dq-made-easy-db-seed-full.md`, `dq-made-easy-db-seed-categories.txt` |
| dq-made-easy-keycloak-seed-artifacts | jacbeekers/dq-made-easy-keycloak-seed-artifacts | `dq-made-easy-keycloak-seed-artifacts-short.txt`, `dq-made-easy-keycloak-seed-artifacts-full.md`, `dq-made-easy-keycloak-seed-artifacts-categories.txt` |
| dq-made-easy-openmetadata-db | jacbeekers/dq-made-easy-openmetadata-db | `dq-made-easy-openmetadata-db-short.txt`, `dq-made-easy-openmetadata-db-full.md`, `dq-made-easy-openmetadata-db-categories.txt` |
| dq-made-easy-openmetadata-server | jacbeekers/dq-made-easy-openmetadata-server | `dq-made-easy-openmetadata-server-short.txt`, `dq-made-easy-openmetadata-server-full.md`, `dq-made-easy-openmetadata-server-categories.txt` |
| dq-made-easy-metadata-configure | jacbeekers/dq-made-easy-metadata-configure | `dq-made-easy-metadata-configure-short.txt`, `dq-made-easy-metadata-configure-full.md`, `dq-made-easy-metadata-configure-categories.txt` |
| dq-made-easy-container-metrics | jacbeekers/dq-made-easy-container-metrics | `dq-made-easy-container-metrics-short.txt`, `dq-made-easy-container-metrics-full.md`, `dq-made-easy-container-metrics-categories.txt` |
| dq-made-easy-zammad-seed | jacbeekers/dq-made-easy-zammad-seed | `dq-made-easy-zammad-seed-short.txt`, `dq-made-easy-zammad-seed-full.md`, `dq-made-easy-zammad-seed-categories.txt` |
| dq-made-easy-zammad-origin | jacbeekers/dq-made-easy-zammad-origin | `dq-made-easy-zammad-origin-short.txt`, `dq-made-easy-zammad-origin-full.md`, `dq-made-easy-zammad-origin-categories.txt` |

## Usage

The `update_docker_hub.sh` script automatically reads these files and publishes them to Docker Hub:

```bash
# Preview changes
./scripts/update_docker_hub.sh --dry-run

# Publish to Docker Hub
./scripts/update_docker_hub.sh
```

## Editing Descriptions

1. Edit the appropriate `.txt` or `.md` file
2. Test with dry-run: `./scripts/update_docker_hub.sh --dry-run`
3. Publish changes: `./scripts/update_docker_hub.sh`

## Short Description Guidelines

- Maximum 100 characters
- One line only (no newlines)
- Always reference "dq-made-easy" or "Data Quality Made Easy"
- No markdown formatting

## Full Description Guidelines

- Markdown formatted
- Include Quick Start section
- Document environment variables
- List exposed ports
- Add tags information
- Link to GitHub repository

## Categories Guidelines

Categories are stored in `dq-made-easy-<name>-categories.txt` files using the format: `name:slug` (one per line).

**Format:** `Category Name:category-slug`

### Docker Hub API Limitation

**Docker Hub's API does not support setting categories for community repositories.** The script includes category support, but Docker Hub silently ignores category updates via API for non-official images.

**To set categories, you must use the Docker Hub web interface:**
1. Go to https://hub.docker.com/repository/docker/jacbeekers/<image-name>
2. Click **Settings** → **General**
3. Scroll to **Categories** section
4. Select categories from the dropdown
5. Click **Update**

### Official Docker Hub Categories

The script uses proper Docker Hub category format ready for when/if API access is enabled:

- `Base images:base-images` - Foundation/parent images
- `Languages & frameworks:languages-and-frameworks` - Programming language runtimes
- `Databases & storage:databases-and-storage` - Database-related services
- `Networking:networking` - Network infrastructure/gateways
- `Operating systems:operating-systems` - OS images
- `Continuous integration & delivery:ci-cd` - CI/CD tools
- `Developer tools:developer-tools` - Development tooling
- `Application platforms:application-platforms` - Application runtimes

### Current Category Assignments

Files are configured with proper name:slug format:

- **dq-made-easy-npm-base**: `Base images:base-images`
- **dq-made-easy-api**: `Languages & frameworks:languages-and-frameworks`, `Databases & storage:databases-and-storage`
- **dq-made-easy-engine**: `Languages & frameworks:languages-and-frameworks`, `Databases & storage:databases-and-storage`
- **dq-made-easy-profiling**: `Languages & frameworks:languages-and-frameworks`, `Databases & storage:databases-and-storage`
- **dq-made-easy-frontend**: `Languages & frameworks:languages-and-frameworks`
- **dq-made-easy-kong**: `Networking:networking`, `Databases & storage:databases-and-storage`
- **dq-made-easy-db**: `Databases & storage:databases-and-storage`
- **dq-made-easy-keycloak**: `Networking:networking`
- **dq-made-easy-airflow**: `Continuous integration & delivery:ci-cd`
- **dq-made-easy-container-metrics**: `Developer tools:developer-tools`
- **dq-made-easy-db-seed**: `Databases & storage:databases-and-storage`
- **dq-made-easy-edge**: `Networking:networking`
- **dq-made-easy-kafka**: `Developer tools:developer-tools`
- **dq-made-easy-kafka-consumer**: `Developer tools:developer-tools`
- **dq-made-easy-keycloak-seed-artifacts**: `Developer tools:developer-tools`
- **dq-made-easy-llm**: `Languages & frameworks:languages-and-frameworks`
- **dq-made-easy-metadata-configure**: `Developer tools:developer-tools`
- **dq-made-easy-openmetadata-db**: `Databases & storage:databases-and-storage`
- **dq-made-easy-openmetadata-server**: `Databases & storage:databases-and-storage`
- **dq-made-easy-trino**: `Databases & storage:databases-and-storage`
- **dq-made-easy-zammad-origin**: `Application platforms:application-platforms`
- **dq-made-easy-zammad-seed**: `Developer tools:developer-tools`

**Note:** The script will attempt to set these via API, but you'll need to set them manually via the web UI to make them visible on Docker Hub.
