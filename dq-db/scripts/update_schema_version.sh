#!/bin/bash

# Purpose: Update the database schema version metadata files.
#
# What it does:
# - Validates the requested semantic version.
# - Rewrites dq-db/mock-data/system_info.csv with the new schema metadata.
# - Updates the current-version header in dq-db/DB_VERSION.md.
#
# Version: 1.1
# Last modified: 2026-04-22
# Changelog:
# - 1.1 (2026-04-22): Replaced platform-specific `sed -i` edits with a temp-file based portable update flow.

set -e

NEW_VERSION=$1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SYSTEM_INFO_CSV="$PROJECT_ROOT/dq-db/mock-data/system_info.csv"
DB_VERSION_MD="$PROJECT_ROOT/dq-db/DB_VERSION.md"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to display usage
usage() {
    echo "Usage: ./update_schema_version.sh <new_version>"
    echo "Example: ./update_schema_version.sh 1.1.0"
    echo ""
    echo "Version format: MAJOR.MINOR.PATCH (semantic versioning)"
    exit 1
}

portable_sed_in_place() {
    local expression="$1"
    local file_path="$2"
    local file_dir
    local file_name
    local tmp_path

    file_dir="$(dirname "$file_path")"
    file_name="$(basename "$file_path")"
    tmp_path="$(mktemp "${file_dir}/${file_name}.XXXXXX")"

    if ! sed "$expression" "$file_path" > "$tmp_path"; then
        rm -f "$tmp_path"
        return 1
    fi

    mv "$tmp_path" "$file_path"
}

# Validate arguments
if [ -z "$NEW_VERSION" ]; then
    echo -e "${RED}Error: Version number is required${NC}"
    usage
fi

# Validate version format (semantic versioning)
if ! echo "$NEW_VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo -e "${RED}Error: Invalid version format${NC}"
    echo "Version must follow semantic versioning: MAJOR.MINOR.PATCH (e.g., 1.1.0)"
    exit 1
fi

# Get current version
CURRENT_VERSION=$(grep "^db_schema_version," "$SYSTEM_INFO_CSV" | cut -d',' -f2)

echo -e "${YELLOW}Database Schema Version Update${NC}"
echo "================================"
echo "Current version: $CURRENT_VERSION"
echo "New version:     $NEW_VERSION"
echo ""

# Confirm update
read -p "Proceed with version update? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${RED}Aborted${NC}"
    exit 1
fi

# Update system_info.csv
CURRENT_TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S.%6N+00")
GIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "dev")
echo "Updating $SYSTEM_INFO_CSV..."

# Create temporary file with updated version
cat > "$SYSTEM_INFO_CSV.tmp" << EOF
info_key,info_value,description,updated_at
db_schema_version,$NEW_VERSION,Database schema version,$CURRENT_TIMESTAMP
db_schema_updated,$CURRENT_TIMESTAMP,Last schema update timestamp,$CURRENT_TIMESTAMP
db_git_commit,$GIT_HASH,Git commit hash of schema change,$CURRENT_TIMESTAMP
EOF

# Replace original file
mv "$SYSTEM_INFO_CSV.tmp" "$SYSTEM_INFO_CSV"

echo -e "${GREEN}✓${NC} Updated system_info.csv"

# Update DB_VERSION.md current version
portable_sed_in_place "s/\*\*Current Version: .*\*\*/\*\*Current Version: $NEW_VERSION\*\*/" "$DB_VERSION_MD"
echo -e "${GREEN}✓${NC} Updated DB_VERSION.md header"

echo ""
echo -e "${GREEN}Version updated successfully!${NC}"
echo ""
echo "Next steps:"
echo "1. Document the changes in $DB_VERSION_MD"
echo "2. Update the schema files in dq-db/init/ with your changes"
echo "3. Test the changes: ./scripts/start-all.sh --seed-all"
echo "4. Commit all changes: git add dq-db/ && git commit -m 'chore(db): update schema to v$NEW_VERSION'"
echo ""
echo "Don't forget to add a new section to DB_VERSION.md documenting:"
echo "- What changed"
echo "- Why it changed"
echo "- Any migration notes"
