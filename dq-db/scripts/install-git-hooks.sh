#!/bin/bash

# Install Git Hooks for Database Schema Versioning
# This script installs the pre-commit hook that enforces version updates

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GIT_HOOKS_DIR="$REPO_ROOT/.git/hooks"
HOOK_SOURCE="$SCRIPT_DIR/git-hooks/pre-commit"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Database Schema Versioning Git Hook Installation${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check if .git directory exists
if [ ! -d "$REPO_ROOT/.git" ]; then
    echo "Error: .git directory not found"
    echo "This must be run from within a git repository"
    exit 1
fi

# Create hooks directory if it doesn't exist
mkdir -p "$GIT_HOOKS_DIR"

# Check if pre-commit hook already exists
if [ -f "$GIT_HOOKS_DIR/pre-commit" ]; then
    echo -e "${YELLOW}⚠${NC}  Existing pre-commit hook found"
    echo ""
    read -p "Backup existing hook and install new one? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled"
        exit 1
    fi
    
    # Backup existing hook
    BACKUP_FILE="$GIT_HOOKS_DIR/pre-commit.backup.$(date +%Y%m%d-%H%M%S)"
    mv "$GIT_HOOKS_DIR/pre-commit" "$BACKUP_FILE"
    echo -e "${GREEN}✓${NC} Existing hook backed up to: ${BACKUP_FILE##*/}"
fi

# Copy and install the hook
cp "$HOOK_SOURCE" "$GIT_HOOKS_DIR/pre-commit"
chmod +x "$GIT_HOOKS_DIR/pre-commit"

echo -e "${GREEN}✓${NC} Pre-commit hook installed successfully"
echo ""
echo -e "${BLUE}Configuration Options:${NC}"
echo ""
echo "The hook behavior can be controlled with the DB_VERSION_AUTO_INCREMENT variable:"
echo ""
echo -e "  ${GREEN}prompt${NC} (default) - Ask what to do when schema changes"
echo -e "  ${GREEN}auto${NC}            - Automatically increment PATCH version"
echo -e "  ${GREEN}strict${NC}          - Block commits if version not updated"
echo -e "  ${GREEN}skip${NC}            - Skip version check (not recommended)"
echo ""
echo "Example usage:"
echo -e "  ${BLUE}DB_VERSION_AUTO_INCREMENT=auto git commit -m \"fix: update schema\"${NC}"
echo ""
echo "To set globally for this repository:"
echo -e "  ${BLUE}git config hooks.dbVersionMode auto${NC}"
echo ""
echo -e "${GREEN}Installation complete!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
