#!/usr/bin/env bash

# Purpose: Convenience seeding for local development.
#
# What it does:
# - Generates Keycloak realm artifacts in Docker.
# - Seeds the local Postgres database.
# - Optionally initializes Kong configuration.
#
# Version: 1.0
# Last modified: 2026-04-07


ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
source "$ROOT_DIR/scripts/supporting/readiness.sh"
init_root_env_file "$ROOT_DIR"
my_name="seed_all.sh"

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

KONG_LOCAL_URL="${KONG_LOCAL_URL:-}"
KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [ -f "$KONG_CA_CERT" ] && [ -z "${CURL_CA_BUNDLE:-}" ]; then
    export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi

source "$ROOT_DIR/scripts/supporting/setup_env.sh"

info "$my_name" "Generating Keycloak realm artifacts in Docker via keycloak-seed-artifacts"
docker_compose run --rm --no-deps keycloak-seed-artifacts || {
    error "$my_name" "Keycloak seed artifact generation failed"
    exit 1
}

info "$my_name" "local postgres seed script: scripts/seed_local_postgres.sh"
SEED_SCRIPT="./scripts/seed_local_postgres.sh"
info "$my_name" "Running $SEED_SCRIPT (pre-compose)"
if [ -f "$SEED_SCRIPT" ]; then
    bash "$SEED_SCRIPT" || { error "$my_name" "Postgres seed script failed"; exit 1; }
else
    error "$my_name" "Postgres seed script not found: $SEED_SCRIPT"
    exit 1
fi

kong_container_id="$(docker ps -q -f name=^dq-made-easy-kong$ 2>/dev/null | tr -d '[:space:]' || true)"
bootstrap_script="./dq-kong/scripts/bootstrap_kong.sh"
KONG_HEALTHCHECK_URL="${KONG_LOCAL_PROBE_BASE_URL:-${KONG_LOCAL_URL%/}}/system/v1/health"

if [ -n "$kong_container_id" ]; then
    if [ -f "$bootstrap_script" ]; then
        info "$my_name" "Running Kong bootstrap from $bootstrap_script"
        if docker cp "$bootstrap_script" "${kong_container_id}:/tmp/dq-bootstrap_kong.sh" >/dev/null 2>&1 \
            && docker exec "$kong_container_id" bash -lc "bash /tmp/dq-bootstrap_kong.sh"; then
            if [ -z "${KONG_LOCAL_URL:-}" ]; then
                error "$my_name" "KONG_LOCAL_URL must be set to check Kong health and seed Kong configuration"
                exit 1
            fi
            if ! wait_for_kong_proxy_ready "$KONG_HEALTHCHECK_URL" "Kong proxy" 20 1; then
                error "$my_name" "Kong proxy did not become ready after bootstrap"
                exit 1
            fi
            success "$my_name" "Kong configuration seeded successfully"
        else
            error "$my_name" "Kong bootstrap failed"
            exit 1
        fi
    else
        error "$my_name" "Kong bootstrap script not found: $bootstrap_script"
        exit 1
    fi
else
    info "$my_name" "Kong bootstrap is handled by scripts/start_stack.sh; skipping direct Kong seeding in seed_all.sh"
fi
