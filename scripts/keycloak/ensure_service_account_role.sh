#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="ensure_service_account_role.sh"

SETUP_SCRIPT="$ROOT_DIR/scripts/patches/keycloak-setup-client.sh"
ASSIGN_SCRIPT="$ROOT_DIR/scripts/patches/keycloak_assign_view_users_role.sh"

info "$my_name" "ROOT_DIR=$ROOT_DIR"

if [ -x "$SETUP_SCRIPT" ]; then
  info "$my_name" "Running client setup script: $SETUP_SCRIPT"
  bash "$SETUP_SCRIPT" || warning "$my_name" "client setup failed (continuing)"
else
  info "$my_name" "Client setup script not found or not executable; skipping setup"
fi

if [ -x "$ASSIGN_SCRIPT" ]; then
  info "$my_name" "Running role assignment script: $ASSIGN_SCRIPT"
  bash "$ASSIGN_SCRIPT" || { error "$my_name" "role assignment failed"; exit 1; }
  success "$my_name" "Role assignment completed successfully"
else
  info "$my_name" "Role assignment script $ASSIGN_SCRIPT not found or not executable; skipping role enforcement"
fi

exit 0