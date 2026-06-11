#!/usr/bin/env bash
set -euo pipefail


# Purpose: Update Docker Hub repository descriptions via API.
#
# What it does:
# - Reads Docker Hub credentials (env/.env) and iterates known repos.
# - Uploads short/full descriptions (supports dry-run).
# - Fails fast when required credentials are missing.
#
# Version: 1.0
# Last modified: 2026-04-07

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$ROOT_DIR/scripts/supporting/logging.sh"

# Source .env file if it exists (for DOCKER_HUB_TOKEN)
if [ -f "$ROOT_DIR/.env" ]; then
    # Only source specific variables we need
    if [ -z "${DOCKER_HUB_TOKEN:-}" ]; then
        DOCKER_HUB_TOKEN=$(grep "^DOCKER_HUB_TOKEN=" "$ROOT_DIR/.env" 2>/dev/null | cut -d'=' -f2- || echo "")
    fi
    if [ -z "${DOCKER_HUB_USERNAME:-}" ]; then
        DOCKER_HUB_USERNAME=$(grep "^DOCKER_HUB_USERNAME=" "$ROOT_DIR/.env" 2>/dev/null | cut -d'=' -f2- || echo "jacbeekers")
    fi
fi

# Configuration
DOCKER_HUB_USERNAME="${DOCKER_HUB_USERNAME:-jacbeekers}"
DOCKER_HUB_TOKEN="${DOCKER_HUB_TOKEN:-}"
DRY_RUN="${DRY_RUN:-false}"

my_name="update_docker_hub.sh"

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Update Docker Hub repository descriptions for all Data Quality Made Easy images.

Options:
  --username <name>    Docker Hub username (default: $DOCKER_HUB_USERNAME)
  --token <token>      Docker Hub access token (required)
  --dry-run            Show what would be updated without making changes
  -h, --help           Show this help message

Environment Variables:
  DOCKER_HUB_USERNAME  Docker Hub username
  DOCKER_HUB_TOKEN     Docker Hub access token (or password)
  DRY_RUN              Set to 'true' for dry run mode

Examples:
  # Using access token from environment
  export DOCKER_HUB_TOKEN="dckr_pat_..."
  $(basename "$0")

  # Using command line arguments
  $(basename "$0") --username jacbeekers --token "dckr_pat_..."

  # Dry run to preview changes
  $(basename "$0") --dry-run

Notes:
  - Access tokens are recommended over passwords
  - Create token at: https://hub.docker.com/settings/security
  - Token needs "Read, Write, Delete" permissions
  - Updates both short and full descriptions

EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --username)
            DOCKER_HUB_USERNAME="$2"
            shift 2
            ;;
        --token)
            DOCKER_HUB_TOKEN="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            error "$my_name" "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate requirements
if [ "$DRY_RUN" != true ] && [ -z "$DOCKER_HUB_TOKEN" ]; then
    error "$my_name" "Docker Hub token is required"
    echo ""
    echo "Set via environment variable:"
    echo "  export DOCKER_HUB_TOKEN='your-token-here'"
    echo ""
    echo "Or via command line:"
    echo "  $0 --token 'your-token-here'"
    echo ""
    echo "Or run in dry-run mode:"
    echo "  $0 --dry-run"
    echo ""
    echo "Create a token at: https://hub.docker.com/settings/security"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    error "$my_name" "jq is required but not installed"
    echo ""
    echo "Install jq:"
    echo "  macOS: brew install jq"
    echo "  Ubuntu/Debian: apt-get install jq"
    exit 1
fi

# Login and get JWT token (skip in dry-run mode)
JWT_TOKEN=""

if [ "$DRY_RUN" != true ]; then
    info "$my_name" "Authenticating with Docker Hub..."

    LOGIN_RESPONSE=$(curl -s -H "Content-Type: application/json" \
        -X POST \
        -d "{\"username\": \"$DOCKER_HUB_USERNAME\", \"password\": \"$DOCKER_HUB_TOKEN\"}" \
        https://hub.docker.com/v2/users/login/)

    JWT_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.token // empty')

    if [ -z "$JWT_TOKEN" ] || [ "$JWT_TOKEN" = "null" ]; then
        error "$my_name" "Authentication failed"
        ERROR_MSG=$(echo "$LOGIN_RESPONSE" | jq -r '.message // .detail // "Unknown error"')
        error "$my_name" "Error: $ERROR_MSG"
        exit 1
    fi

    success "$my_name" "Authenticated as $DOCKER_HUB_USERNAME"
fi

# Function to update a repository
update_repository() {
    local repo_name="$1"
    local short_desc="$2"
    local full_desc="$3"
    local categories="$4"  # JSON array string
    
    info "$my_name" "Updating $repo_name..."
    
    if [ "$DRY_RUN" = true ]; then
        warning "$my_name" "[DRY RUN] Would update $repo_name"
        echo "  Short: $short_desc"
        echo "  Full: ${#full_desc} characters"
        echo "  Categories: $categories"
        return 0
    fi
    
    # Escape the full description for JSON
    local escaped_full_desc=$(jq -Rs . <<< "$full_desc")
    local escaped_short_desc=$(jq -Rs . <<< "$short_desc")
    
    # Build JSON payload with categories
    local json_payload=$(jq -n \
        --arg desc "$short_desc" \
        --arg full "$full_desc" \
        --argjson cats "$categories" \
        '{description: $desc, full_description: $full, categories: $cats}')
    
    # Update repository
    UPDATE_RESPONSE=$(curl -s -X PATCH \
        -H "Authorization: JWT ${JWT_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "$json_payload" \
        "https://hub.docker.com/v2/repositories/${DOCKER_HUB_USERNAME}/${repo_name}/")
    
    # Check for errors
    if echo "$UPDATE_RESPONSE" | jq -e '.message // .detail' > /dev/null 2>&1; then
        ERROR_MSG=$(echo "$UPDATE_RESPONSE" | jq -r '.message // .detail')
        error "$my_name" "Failed to update $repo_name: $ERROR_MSG"
        return 1
    fi
    
    success "$my_name" "Updated $repo_name"
    return 0
}

# Function to read description files
read_description() {
    local image_name="$1"
    local desc_type="$2"  # "short" or "full"
    local desc_dir="$ROOT_DIR/docker-hub-descriptions"
    local file_ext="txt"
    
    if [ "$desc_type" = "full" ]; then
        file_ext="md"
    fi
    
    local file_path="$desc_dir/${image_name}-${desc_type}.${file_ext}"
    
    if [ ! -f "$file_path" ]; then
        error "$my_name" "Description file not found: $file_path"
        return 1
    fi
    
    cat "$file_path"
}

# Function to read categories and convert to JSON array
read_categories() {
    local image_name="$1"
    local desc_dir="$ROOT_DIR/docker-hub-descriptions"
    local file_path="$desc_dir/${image_name}-categories.txt"
    
    if [ ! -f "$file_path" ]; then
        # Return empty array if no categories file
        echo "[]"
        return 0
    fi
    
    # Read categories (format: "name:slug" one per line) and convert to JSON array of objects
    # Example: "Languages & frameworks:languages-and-frameworks" -> {"name": "Languages & frameworks", "slug": "languages-and-frameworks"}
    local categories="[]"
    while IFS=':' read -r name slug || [ -n "$name" ]; do
        # Skip empty lines and comments
        [[ -z "$name" || "$name" =~ ^[[:space:]]*# ]] && continue
        # Trim whitespace
        name=$(echo "$name" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        slug=$(echo "$slug" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        # Skip if no slug
        [[ -z "$slug" ]] && continue
        # Add to array
        categories=$(echo "$categories" | jq --arg name "$name" --arg slug "$slug" '. += [{"name": $name, "slug": $slug}]')
    done < "$file_path"
    
    echo "$categories"
}

# Repository descriptions
info "$my_name" "========================================"
info "$my_name" "Docker Hub Repository Update"
info "$my_name" "========================================"
info "$my_name" "Username: $DOCKER_HUB_USERNAME"
info "$my_name" "Dry run: $DRY_RUN"
info "$my_name" "========================================"

SUCCESS_COUNT=0
FAIL_COUNT=0

# Define repositories to update
declare -a REPOSITORIES=("npm-base" "dq-api" "dq-engine" "dq-profiling" "dq-frontend" "dq-kong" "dq-db" "dq-keycloak")

# Update each repository
for repo in "${REPOSITORIES[@]}"; do
    SHORT_DESC=$(read_description "$repo" "short")
    FULL_DESC=$(read_description "$repo" "full")
    CATEGORIES=$(read_categories "$repo")
    
    if update_repository "$repo" "$SHORT_DESC" "$FULL_DESC" "$CATEGORIES"; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done

# Summary
    info "$my_name" "========================================"
    info "$my_name" "Update Summary"
    info "$my_name" "========================================"
    info "$my_name" "Successful: $SUCCESS_COUNT"
    info "$my_name" "Failed: $FAIL_COUNT"
    info "$my_name" "========================================"

if [ $FAIL_COUNT -gt 0 ]; then
    error "$my_name" "Some repositories failed to update"
    exit 1
fi

if [ "$DRY_RUN" = true ]; then
    info "$my_name" "Dry run completed - no changes were made"
    info "$my_name" "To apply changes, run without --dry-run:"
    info "$my_name" "  $0"
else
    success "$my_name" "All repositories updated successfully!"
    info "$my_name" "View your repositories at:"
    info "$my_name" "  https://hub.docker.com/u/$DOCKER_HUB_USERNAME"
fi

exit 0
