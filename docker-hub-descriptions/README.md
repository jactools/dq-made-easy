# Docker Hub Descriptions

This directory contains the Docker Hub repository descriptions for all Data Quality Made Easy images.

## Structure

Each image has three description files:

- `<image-name>-short.txt` - Short description (max 100 characters, displayed in search results)
- `<image-name>-full.md` - Full description (Markdown formatted, displayed on repository page)
- `<image-name>-categories.txt` - Categories (one per line, for Docker Hub classification)

## Images

| Image | Repository | Description Files |
|-------|------------|-------------------|
| npm-base | jacbeekers/npm-base | `npm-base-short.txt`, `npm-base-full.md`, `npm-base-categories.txt` |
| dq-api | jacbeekers/dq-api | `dq-api-short.txt`, `dq-api-full.md`, `dq-api-categories.txt` |
| dq-engine | jacbeekers/dq-engine | `dq-engine-short.txt`, `dq-engine-full.md`, `dq-engine-categories.txt` |
| dq-profiling | jacbeekers/dq-profiling | `dq-profiling-short.txt`, `dq-profiling-full.md`, `dq-profiling-categories.txt` |
| dq-frontend | jacbeekers/dq-frontend | `dq-frontend-short.txt`, `dq-frontend-full.md`, `dq-frontend-categories.txt` |
| dq-kong | jacbeekers/dq-kong | `dq-kong-short.txt`, `dq-kong-full.md`, `dq-kong-categories.txt` |
| dq-db | jacbeekers/dq-db | `dq-db-short.txt`, `dq-db-full.md`, `dq-db-categories.txt` |
| dq-keycloak | jacbeekers/dq-keycloak | `dq-keycloak-short.txt`, `dq-keycloak-full.md`, `dq-keycloak-categories.txt` |

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
