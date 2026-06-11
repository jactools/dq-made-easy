# Docker Hub Update Script - Quick Reference

## Usage

```bash
# Option 1: Set token in .env file (recommended)
# Edit .env and add your DOCKER_HUB_TOKEN
# Then just run:
./scripts/update_docker_hub.sh

# Option 2: Export token manually
export DOCKER_HUB_TOKEN="dckr_pat_your_token_here"
./scripts/update_docker_hub.sh

# Preview changes without applying (no token needed)
./scripts/update_docker_hub.sh --dry-run
```

> **Note**: The script automatically sources `.env` if present, so you can store your token there for convenience.

## Creating a Docker Hub Access Token

1. Go to https://hub.docker.com/settings/security
2. Click **"New Access Token"**
3. Name it (e.g., "dq-rulebuilder-ci")
4. Select permissions: **Read, Write, Delete**
5. Click **"Generate"**
6. Copy the token (starts with `dckr_pat_...`)
7. Save it securely (you won't see it again)

## What Gets Updated

The script updates **all 8 repositories**:

- ✅ `jacbeekers/npm-base` - Base Node.js image
- ✅ `jacbeekers/dq-api` - REST API backend  
- ✅ `jacbeekers/dq-engine` - Python rule executor
- ✅ `jacbeekers/dq-profiling` - Background worker
- ✅ `jacbeekers/dq-frontend` - React web UI
- ✅ `jacbeekers/dq-kong` - Kong API Gateway
- ✅ `jacbeekers/dq-db` - PostgreSQL database image
- ✅ `jacbeekers/dq-keycloak` - Keycloak realm image

For each repository:
- Short description (100 char summary)
- Full description (Markdown formatted)

## Command Line Options

```bash
# Specify username
./scripts/update_docker_hub.sh --username myusername

# Pass token via command line (less secure)
./scripts/update_docker_hub.sh --token "dckr_pat_..."

# Dry run mode (preview changes)
./scripts/update_docker_hub.sh --dry-run

# Show help
./scripts/update_docker_hub.sh --help
```

## Example Output

```
ℹ Authenticating with Docker Hub...
✓ Authenticated as jacbeekers
ℹ Updating npm-base...
✓ Updated npm-base
ℹ Updating dq-api...
✓ Updated dq-api
ℹ Updating dq-engine...
✓ Updated dq-engine
ℹ Updating dq-profiling...
✓ Updated dq-profiling
ℹ Updating dq-frontend...
✓ Updated dq-frontend
ℹ Updating dq-kong...
✓ Updated dq-kong
✓ Updated dq-db
✓ Updated dq-keycloak

========================================
Update Summary
========================================
Successful: 8
Failed: 0
========================================
✓ All repositories updated successfully!
```

## Troubleshooting

### Authentication Failed
```bash
✗ Authentication failed
Error: Incorrect authentication credentials
```
**Solution:** Check your token is correct and has not expired

### jq Not Found
```bash
✗ jq is required but not installed
```
**Solution:** 
- macOS: `brew install jq`
- Ubuntu: `apt-get install jq`

### Repository Not Found
```bash
✗ Failed to update dq-api: Object not found
```
**Solution:** Repository must exist on Docker Hub before updating description

## CI/CD Integration

### GitHub Actions

```yaml
name: Update Docker Hub Descriptions

on:
  push:
    branches: [main]
    paths:
      - 'scripts/update_docker_hub.sh'

jobs:
  update-docker-hub:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install jq
        run: sudo apt-get install -y jq
      
      - name: Update Docker Hub
        env:
          DOCKER_HUB_TOKEN: ${{ secrets.DOCKER_HUB_TOKEN }}
        run: ./scripts/update_docker_hub.sh
```

### GitLab CI

```yaml
update-docker-hub:
  stage: deploy
  image: alpine:latest
  before_script:
    - apk add --no-cache bash curl jq
  script:
    - ./scripts/update_docker_hub.sh
  only:
    - main
```

## Security Notes

- ✅ Use access tokens, not passwords
- ✅ Store tokens in environment variables or secrets
- ✅ Never commit tokens to git
- ✅ Rotate tokens regularly (every 90 days)
- ✅ Use read-only tokens when possible
- ⚠️ This script requires "Write" permissions

## Modifying Descriptions

To change descriptions, edit the heredoc sections in the script:

```bash
# Example: Update dq-api short description
read -r -d '' DQ_API_SHORT <<'EOF' || true
Your new short description here (max 100 chars)
EOF
```

## Testing Without Applying

Always test with `--dry-run` first:

```bash
# Preview all changes
./scripts/update_docker_hub.sh --dry-run

# Review output, then apply
./scripts/update_docker_hub.sh
```

## Related Documentation

- [DOCKER_HUB_PUBLISHING.md](../DOCKER_HUB_PUBLISHING.md) - Full publishing guide
- [DOCKER_HUB_DESCRIPTIONS.md](../DOCKER_HUB_DESCRIPTIONS.md) - All descriptions reference
