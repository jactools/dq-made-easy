#!/usr/bin/env bash
set -euo pipefail


# Purpose: Run post-seed Keycloak tasks for local/dev bootstrap.
#
# What it does:
# - Waits for Keycloak readiness.
# - Ensures the configured client has the required role mapping.
# - Uses the canonical env-provided Keycloak client secret for verification and patch generation.
#
# Version: 1.0
# Last modified: 2026-05-09

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

my_name="keycloak_post_seed_tasks.sh"

init_root_env_file "$ROOT_DIR"

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  exit 1
fi

set -- "${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"
if [ "$#" -gt 0 ]; then
  error "$my_name" "Unknown arg: $1"
  exit 1
fi

if [ ! -f "$ROOT_ENV_FILE" ]; then
  error "$my_name" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

validate_selected_root_env_file "$ROOT_DIR" full

set -a
# shellcheck disable=SC1090
source "$ROOT_ENV_FILE"
set +a

: "${KEYCLOAK_REALM:=jaccloud}"
: "${KEYCLOAK_CLIENT_ID:=dq-rules-ui}"
: "${KEYCLOAK_CLIENT_SECRET:?Need KEYCLOAK_CLIENT_SECRET from the selected env file or environment}"

# Enforce in-network only operation (deterministic inside Docker Compose).
# Always use the compose service host and require an operator-provided
# `KEYCLOAK_CLIENT_SECRET` for client_credentials flow.
KEYCLOAK_NETWORK="${KEYCLOAK_NETWORK:-dq-rulebuilder_default}"
KEYCLOAK_HOST="${KEYCLOAK_HOST:-keycloak:8080}"

kc_ready_url="http://${KEYCLOAK_HOST}/realms/${KEYCLOAK_REALM}/.well-known/openid-configuration"

info "$my_name" "Keycloak post-seed: starting (realm=${KEYCLOAK_REALM} client=${KEYCLOAK_CLIENT_ID} host=${KEYCLOAK_HOST} network=${KEYCLOAK_NETWORK})"

# rely on wait_for_keycloak_ready from scripts/supporting/keycloak_readiness.sh if available
. "$ROOT_DIR/scripts/supporting/keycloak_readiness.sh"

if ! wait_for_keycloak_ready "$kc_ready_url" "Keycloak"; then
  echo "Keycloak did not become ready for post-seed tasks" >&2
  exit 1
fi

# 0) Ensure client is confidential + service-account enabled and has the role

# Use the canonical role-assignment helper. The client secret is expected to be
# provided through the selected stack env, not generated here.
admin_user="${KEYCLOAK_SYSTEM_ADMIN_USERNAME:-}"
admin_pass="${KEYCLOAK_SYSTEM_ADMIN_PASSWORD:-}"
if [ -z "$admin_user" ] || [ -z "$admin_pass" ]; then
  error "$my_name" "KEYCLOAK_SYSTEM_ADMIN_USERNAME and KEYCLOAK_SYSTEM_ADMIN_PASSWORD are required"
  exit 1
fi

info "$my_name" "Ensuring realm-management:view-users is assigned to the service-account user..."
KEYCLOAK_NETWORK="$KEYCLOAK_NETWORK" \
  KEYCLOAK_HOST="$KEYCLOAK_HOST" \
  ADMIN_USER="$admin_user" \
  ADMIN_PASS="$admin_pass" \
  REALM="$KEYCLOAK_REALM" \
  CLIENT_ID="$KEYCLOAK_CLIENT_ID" \
  ./scripts/patches/keycloak_assign_view_users_role.sh


# 1) Verify the service-account can authenticate and search admin users using
# the canonical env-provided client secret.
FIRST_EMAIL=$(awk -F',' 'NR==2{gsub(/"/,"",$4); print $4; exit}' dq-db/mock-data/users.csv || true)
if [ -n "$FIRST_EMAIL" ]; then
  info "$my_name" "Verifying service-account access with sample user '$FIRST_EMAIL'..."
  KEYCLOAK_NETWORK="$KEYCLOAK_NETWORK" \
    KEYCLOAK_HOST="$KEYCLOAK_HOST" \
    ADMIN_USER="$admin_user" \
    ADMIN_PASS="$admin_pass" \
    REALM="$KEYCLOAK_REALM" \
    CLIENT_ID="$KEYCLOAK_CLIENT_ID" \
    CLIENT_SECRET="$KEYCLOAK_CLIENT_SECRET" \
    EMAIL="$FIRST_EMAIL" \
    ./scripts/patches/keycloak_verify_service_account.sh
else
  warning "$my_name" "Could not determine a sample email from dq-db/mock-data/users.csv; skipping service-account verification"
fi

# 2) Run the canonical patch generator to produce SQL output.
info "$my_name" "Running external_id generator to produce SQL patch (in-network only)..."

# When probing via host (localhost), docker-run inside the network still
# needs to address Keycloak by its service name. Use a compose-service host
# for the generator when appropriate.
GENERATOR_KEYCLOAK_HOST="$KEYCLOAK_HOST"
if printf '%s' "$KEYCLOAK_HOST" | grep -Eq '^localhost(:|$)|^127\.0\.0\.1(:|$)'; then
  GENERATOR_KEYCLOAK_HOST="keycloak:8080"
fi

KEYCLOAK_NETWORK="$KEYCLOAK_NETWORK" \
  KEYCLOAK_HOST="$GENERATOR_KEYCLOAK_HOST" \
  KEYCLOAK_CLIENT_SECRET="$KEYCLOAK_CLIENT_SECRET" \
  KEYCLOAK_TOKEN_REALM="${KEYCLOAK_TOKEN_REALM:-$KEYCLOAK_REALM}" \
  bash ./scripts/patches/run_generate_external_id_patch.sh

exit 0
