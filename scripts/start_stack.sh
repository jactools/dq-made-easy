#!/usr/bin/env bash
set -euo pipefail


# Purpose: Start selected stack components (no seeding logic).
#
# What it does:
# - Parses profile flags (core/auth/gateway/engine/etc.).
# - Dispatches dedicated startup blocks for each selected profile.
# - Starts the selected docker compose services.
# - Can optionally include observability components.
#
# Version: 1.10
# Last modified: 2026-06-02
# Changelog:
# - 1.2 (2026-04-22): Reworked stale container cleanup to avoid GNU-only `xargs -r`.
# - 1.3 (2026-04-26): Made docker compose operations honor ROOT_ENV_FILE for env-aware startup flows.
# - 1.4 (2026-04-27): Added direct env-file selection for non-default startup targets.
# - 1.5 (2026-04-29): Switched startup env selection to the canonical dev/test/prod contract.
# - 1.6 (2026-05-08): Split startup routing into dedicated per-block scripts with pre/post dispatch.
# - 1.7 (2026-05-09): Stopped after startup; post-start reconciliation now runs from a separate entrypoint.
# - 1.8 (2026-05-10): Added explicit --with-edge support for the edge compose profile.
# - 1.9 (2026-05-30): Added explicit --with-airflow support for the Airflow compose profile.
# - 1.10 (2026-06-02): Added explicit --with-spark support for the distributed Spark cluster profile.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
my_name="start_stack.sh"
source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/env/selection.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
init_root_env_file "$ROOT_DIR"

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  exit 1
fi

REMAINING_ARGS=("${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}")

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
  error "$my_name" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

validate_selected_root_env_file "$ROOT_DIR" full

export ROOT_ENV_FILE

set -a
source "$ROOT_ENV_FILE"
set +a

source "$ROOT_DIR/scripts/supporting/setup_env.sh"
source "$ROOT_DIR/scripts/supporting/readiness.sh"

START_ALL="${START_ALL:-false}"
START_BASE="${START_BASE:-false}"
START_REDIS="${START_REDIS:-false}"
START_CORE="${START_CORE:-false}"
START_GATEWAY="${START_GATEWAY:-false}"
START_AUTH="${START_AUTH:-false}"
START_EDGE="${START_EDGE:-false}"
START_SPARK="${START_SPARK:-false}"
START_ENGINE="${START_ENGINE:-false}"
START_WORKERS="${START_WORKERS:-false}"
START_AIRFLOW="${START_AIRFLOW:-false}"
START_PROFILING="${START_PROFILING:-false}"
START_METADATA="${START_METADATA:-false}"
START_METADATA_INGESTION="${START_METADATA_INGESTION:-false}"
START_LLM="${START_LLM:-false}"
START_SUPPORT="${START_SUPPORT:-false}"
START_OBSERVABILITY="${START_OBSERVABILITY:-false}"

if [ "$START_CORE" = "true" ] || [ "$START_METADATA" = "true" ]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/scripts/load_seeded_user_credentials.sh" --env-file "$ROOT_ENV_FILE" --quiet

  if [ -z "${SMOKE_LOGIN_EMAIL:-}" ] || [ -z "${SMOKE_LOGIN_PASSWORD:-}" ]; then
    error "$my_name" "Seeded smoke credentials are required to start the core or metadata profiles"
    exit 1
  fi

  export CATALOG_OIDC_USERNAME="$SMOKE_LOGIN_EMAIL"
  export CATALOG_OIDC_PASSWORD="$SMOKE_LOGIN_PASSWORD"
fi

STARTUP_BLOCKS=(base redis spark core gateway auth edge engine workers airflow profiling metadata metadata_ingestion llm support observability)
for startup_block in "${STARTUP_BLOCKS[@]}"; do
  source "$ROOT_DIR/scripts/startup/${startup_block}.sh"
done

KONG_HEALTHCHECK_URL="${KONG_LOCAL_PROBE_BASE_URL:-${KONG_PUBLIC_URL%/}}/system/v1/health"

set -- "${REMAINING_ARGS[@]}"

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [ -f "$KONG_CA_CERT" ] && [ -z "${CURL_CA_BUNDLE:-}" ]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi

START_ALL="${START_ALL:-false}"
START_BASE="${START_BASE:-false}"
START_REDIS="${START_REDIS:-false}"
START_CORE="${START_CORE:-false}"
START_GATEWAY="${START_GATEWAY:-false}"
START_AUTH="${START_AUTH:-false}"
START_EDGE="${START_EDGE:-false}"
START_SPARK="${START_SPARK:-false}"
START_ENGINE="${START_ENGINE:-false}"
START_WORKERS="${START_WORKERS:-false}"
START_AIRFLOW="${START_AIRFLOW:-false}"
START_PROFILING="${START_PROFILING:-false}"
START_METADATA="${START_METADATA:-false}"
START_METADATA_INGESTION="${START_METADATA_INGESTION:-false}"
START_LLM="${START_LLM:-false}"
START_SUPPORT="${START_SUPPORT:-false}"
REMOVE_ORPHANS="${REMOVE_ORPHANS:-false}"
SKIP_FRONTEND_START="${SKIP_FRONTEND_START:-false}"
SKIP_POST_STACK_KONG_REFRESH="${SKIP_POST_STACK_KONG_REFRESH:-false}"
START_OBSERVABILITY="${START_OBSERVABILITY:-false}"
NO_BUILD=false

print_usage() {
  printf '%s\n' \
    "Usage: ./scripts/start_stack.sh [OPTIONS]" \
    "" \
     "Canonical env options:" \
     "  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local" \
     "  --env-file PATH          Use an explicit env file for CI, /etc, or diagnostics" \
    "" \
    "Profile options:" \
    "  --all                    Start the default stack profiles only (use --with-llm separately)" \
    "  --with-base" \
    "  --with-redis" \
    "  --with-core" \
    "  --with-gateway" \
    "  --with-auth" \
    "  --with-edge" \
    "  --with-spark" \
    "  --with-engine" \
    "  --with-workers" \
    "  --with-airflow" \
    "  --with-profiling" \
    "  --with-metadata" \
    "  --with-metadata-ingestion" \
    "  --with-llm" \
    "  --with-support" \
    "  --with-observability" \
    "" \
    "Other options:" \
    "  --remove-orphans" \
    "  -h, --help"
 
info "$my_name" "Environment selection: $(describe_root_env_file_selection "$ROOT_DIR" "$ROOT_ENV_FILE") -> $ROOT_ENV_FILE"
}

# Only parse startup-related flags

# Accept --no-build and --force-build as valid (internal) options
while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) START_ALL=true; shift ;;
    --with-base) START_BASE=true; shift ;;
    --with-redis) START_REDIS=true; shift ;;
    --with-core) START_CORE=true; shift ;;
    --with-gateway) START_GATEWAY=true; shift ;;
    --with-auth) START_AUTH=true; shift ;;
    --with-edge) START_EDGE=true; shift ;;
    --with-spark) START_SPARK=true; shift ;;
    --with-observability) START_OBSERVABILITY=true; shift ;;
    --with-engine) START_ENGINE=true; shift ;;
    --with-workers) START_WORKERS=true; shift ;;
    --with-airflow) START_AIRFLOW=true; shift ;;
    --with-profiling) START_PROFILING=true; shift ;;
    --with-metadata) START_METADATA=true; shift ;;
    --with-metadata-ingestion) START_METADATA_INGESTION=true; shift ;;
    --with-llm) START_LLM=true; shift ;;
    --with-support) START_SUPPORT=true; shift ;;
    --remove-orphans) REMOVE_ORPHANS=true; shift ;;
    --no-build) NO_BUILD=true; shift ;;
    --force-build) NO_BUILD=false; shift ;;
    -h|--help) print_usage; exit 0 ;;
    *) error "$my_name" "Unknown arg: $1"; print_usage; exit 1 ;;
  esac
done

if [ "$START_ALL" = "true" ]; then
  START_BASE=true
  START_REDIS=true
  START_CORE=true
  START_GATEWAY=true
  START_AUTH=true
  START_EDGE=true
  START_ENGINE=true
  START_WORKERS=true
  START_PROFILING=true
  START_METADATA=true
  START_METADATA_INGESTION=true
  START_SUPPORT=true
  START_OBSERVABILITY=true
fi

if [ "$START_WORKERS" = "true" ] && [ "$START_GATEWAY" != "true" ]; then
  START_GATEWAY=true
fi

ensure_edge_cert_assets() {
  if [ "$START_EDGE" != "true" ]; then
    return 0
  fi

  if [ -z "${EDGE_SSL_CERTS_DIR:-}" ] || [ -z "${EDGE_SSL_CERT_FILE_NAME:-}" ] || [ -z "${EDGE_SSL_KEY_FILE_NAME:-}" ]; then
    error "$my_name" "edge cert directory and filenames are required when --with-edge is enabled"
    return 1
  fi

  local edge_certs_dir="$EDGE_SSL_CERTS_DIR"
  case "$edge_certs_dir" in
    ./*)
      edge_certs_dir="$ROOT_DIR/${edge_certs_dir#./}"
      ;;
    /*)
      ;;
    *)
      edge_certs_dir="$ROOT_DIR/$edge_certs_dir"
      ;;
  esac

  if [ "$edge_certs_dir" = "$ROOT_DIR/tmp/certs" ]; then
    if [ ! -f "$edge_certs_dir/$EDGE_SSL_CERT_FILE_NAME" ] || [ ! -f "$edge_certs_dir/$EDGE_SSL_KEY_FILE_NAME" ]; then
      info "$my_name" "Generating local edge certificates in $edge_certs_dir..."
      "$ROOT_DIR/scripts/create_certs.sh" >/dev/null || return 1
    fi
  fi

  if [ ! -f "$edge_certs_dir/$EDGE_SSL_CERT_FILE_NAME" ] || [ ! -f "$edge_certs_dir/$EDGE_SSL_KEY_FILE_NAME" ]; then
    error "$my_name" "missing edge certificate files in $edge_certs_dir"
    return 1
  fi
}

if ! ensure_edge_cert_assets; then
  exit 1
fi

profile_args_contains() {
  local wanted_profile="$1"
  shift || true

  while [ "$#" -gt 0 ]; do
    if [ "$1" = "--profile" ] && [ "${2:-}" = "$wanted_profile" ]; then
      return 0
    fi
    shift
  done

  return 1
}

append_env_compose_profiles() {
  local configured_profiles="${COMPOSE_PROFILES:-}"
  local old_ifs="$IFS"
  local profile_name

  if [ -z "$configured_profiles" ]; then
    return 0
  fi

  IFS=','
  for profile_name in $configured_profiles; do
    profile_name="$(printf '%s' "$profile_name" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    if [ -z "$profile_name" ]; then
      continue
    fi
    if ! profile_args_contains "$profile_name" "${PROFILE_ARGS[@]}"; then
      PROFILE_ARGS+=(--profile "$profile_name")
    fi
  done
  IFS="$old_ifs"
}

PROFILE_ARGS=()
START_PHASE=pre
for startup_block in "${STARTUP_BLOCKS[@]}"; do
  "start_stack_block_${startup_block}"
done

append_env_compose_profiles

if [ ${#PROFILE_ARGS[@]} -eq 0 ]; then
  error "$my_name" "No profiles selected. Pass one or more --with-* flags (for example --with-core --with-redis)."
  exit 1
fi

info "$my_name" "Starting docker-compose stack (building images)..."

# Enable Docker BuildKit for faster builds and cache mounts
export DOCKER_BUILDKIT=1

# If Docker Buildx is available, ensure a builder instance is selected/created
if command -v docker >/dev/null 2>&1 && docker buildx version >/dev/null 2>&1; then
  if ! docker buildx inspect dqbuilder >/dev/null 2>&1; then
    info "$my_name" "Creating docker buildx builder 'dqbuilder'..."
    docker buildx create --use --name dqbuilder || true
  else
    docker buildx use dqbuilder >/dev/null 2>&1 || true
  fi
fi

# Clean up any stale Docker state to prevent "network not found" errors
info "$my_name" "Cleaning up stale Docker containers and networks..."
# Remove any stopped/failed containers that might have stale network references
STALE_CONTAINER_IDS="$(docker ps -aq --filter "status=exited" --filter "status=created" 2>/dev/null || true)"
if [ -n "$STALE_CONTAINER_IDS" ]; then
  printf '%s\n' "$STALE_CONTAINER_IDS" | xargs docker rm 2>/dev/null || true
fi
# Prune unused networks
docker network prune -f >/dev/null 2>&1 || true

if [ "$NO_BUILD" = false ]; then
  info "$my_name" "Running docker compose build with BuildKit (shows BuildKit output)..."
  if ! COMPOSE_DOCKER_CLI_BUILD=1 DOCKER_BUILDKIT=1 docker_compose --progress=plain "${PROFILE_ARGS[@]}" build; then
    error "$my_name" "docker compose build failed; aborting startup"
    exit 1
  fi
else
  info "$my_name" "Skipping docker compose build due to --no-build flag."
fi

info "$my_name" "Starting docker-compose stack (bringing containers up)..."
UP_ARGS=(up -d)
if [ "$REMOVE_ORPHANS" = "true" ]; then
  info "$my_name" "Explicit orphan cleanup enabled for this run"
  UP_ARGS+=(--remove-orphans)
else
  info "$my_name" "Preserving unrelated running services (no orphan cleanup)"
fi

if ! docker_compose "${PROFILE_ARGS[@]}" "${UP_ARGS[@]}" --quiet-pull; then
  error "$my_name" "docker compose up failed"
  exit 1
fi


# All seeding logic has been moved to seed_stack.sh

# No post-up external_id apply stage: the SQL patch must be embedded into the
# API image at build time so Alembic inside the container can find it on startup.

success "$my_name" "Stack startup completed successfully"

exit 0
