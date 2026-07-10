# Docker Hub Descriptions

This directory contains the Docker Hub repository descriptions for all Data Quality Made Easy images.

## Structure

Each image usually has two description files, plus an optional categories file:

- `<image-name>-short.txt` - Short description (max 100 characters, displayed in search results)
- `<image-name>-full.md` - Full description (Markdown formatted, displayed on repository page)
- `<image-name>-categories.txt` - Categories (one per line, for Docker Hub classification)

## Images

| Image | Repository | Description Files |
|-------|------------|-------------------|
| npm-base | jacbeekers/npm-base | `npm-base-short.txt`, `npm-base-full.md`, `npm-base-categories.txt` |
| dq-base | jacbeekers/dq-base | `dq-base-short.txt`, `dq-base-full.md` |
| dq-api | jacbeekers/dq-api | `dq-api-short.txt`, `dq-api-full.md`, `dq-api-categories.txt` |
| dq-engine | jacbeekers/dq-engine | `dq-engine-short.txt`, `dq-engine-full.md`, `dq-engine-categories.txt` |
| dq-profiling | jacbeekers/dq-profiling | `dq-profiling-short.txt`, `dq-profiling-full.md`, `dq-profiling-categories.txt` |
| dq-frontend | jacbeekers/dq-frontend | `dq-frontend-short.txt`, `dq-frontend-full.md`, `dq-frontend-categories.txt` |
| dq-kong | jacbeekers/dq-kong | `dq-kong-short.txt`, `dq-kong-full.md`, `dq-kong-categories.txt` |
| dq-db | jacbeekers/dq-db | `dq-db-short.txt`, `dq-db-full.md`, `dq-db-categories.txt` |
| dq-keycloak | jacbeekers/dq-keycloak | `dq-keycloak-short.txt`, `dq-keycloak-full.md`, `dq-keycloak-categories.txt` |
| dq-kafka | jacbeekers/dq-kafka | `dq-kafka-short.txt`, `dq-kafka-full.md` |
| dq-kafka-consumer | jacbeekers/dq-kafka-consumer | `dq-kafka-consumer-short.txt`, `dq-kafka-consumer-full.md` |
| dq-trino | jacbeekers/dq-trino | `dq-trino-short.txt`, `dq-trino-full.md` |
| dq-edge | jacbeekers/dq-edge | `dq-edge-short.txt`, `dq-edge-full.md` |
| dq-airflow | jacbeekers/dq-airflow | `dq-airflow-short.txt`, `dq-airflow-full.md` |
| dq-llm | jacbeekers/dq-llm | `dq-llm-short.txt`, `dq-llm-full.md` |
| dq-db-seed | jacbeekers/dq-db-seed | `dq-db-seed-short.txt`, `dq-db-seed-full.md` |
| dq-keycloak-seed-artifacts | jacbeekers/dq-keycloak-seed-artifacts | `dq-keycloak-seed-artifacts-short.txt`, `dq-keycloak-seed-artifacts-full.md` |
| dq-openmetadata-db | jacbeekers/dq-openmetadata-db | `dq-openmetadata-db-short.txt`, `dq-openmetadata-db-full.md` |
| dq-openmetadata-server | jacbeekers/dq-openmetadata-server | `dq-openmetadata-server-short.txt`, `dq-openmetadata-server-full.md` |
| dq-metadata-configure | jacbeekers/dq-metadata-configure | `dq-metadata-configure-short.txt`, `dq-metadata-configure-full.md` |
| dq-container-metrics | jacbeekers/dq-container-metrics | `dq-container-metrics-short.txt`, `dq-container-metrics-full.md` |
| dq-zammad-seed | jacbeekers/dq-zammad-seed | `dq-zammad-seed-short.txt`, `dq-zammad-seed-full.md` |
| dq-zammad-origin | jacbeekers/dq-zammad-origin | `dq-zammad-origin-short.txt`, `dq-zammad-origin-full.md` |

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
- Focus on the primary function
- No markdown formatting

## Full Description Guidelines

- Markdown formatted
- Include Quick Start section
- Document environment variables
- List exposed ports
- Add tags information
- Link to GitHub repository

## Categories Guidelines

Categories are stored in `<image-name>-categories.txt` files using the format: `name:slug` (one per line).

**Format:** `Category Name:category-slug`

### ⚠️ Important: Docker Hub API Limitation

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
- `Message queues:message-queues` - Queue/messaging systems (may not be available)
  
### Current Category Assignments

Files are configured with proper name:slug format:

- **npm-base**: `Base images:base-images`
- **dq-api**: `Languages & frameworks:languages-and-frameworks`, `Databases & storage:databases-and-storage`
- **dq-engine**: `Languages & frameworks:languages-and-frameworks`, `Databases & storage:databases-and-storage`
- **dq-profiling**: `Languages & frameworks:languages-and-frameworks`, `Databases & storage:databases-and-storage`
- **dq-frontend**: `Languages & frameworks:languages-and-frameworks`
- **dq-kong**: `Networking:networking`, `Databases & storage:databases-and-storage`
- **dq-db**: `Databases & storage:databases-and-storage`
- **dq-keycloak**: `Networking:networking`

**Note:** The script will attempt to set these via API, but you'll need to set them manually via the web UI to make them visible on Docker Hub.
