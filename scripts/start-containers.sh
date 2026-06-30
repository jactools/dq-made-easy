#!/usr/bin/env bash
set -euo pipefail


# Purpose: Orchestrate starting the local docker compose stack.
#
# What it does:
# - Parses profile flags (core/auth/gateway/engine/workers/etc.).
# - Loads repo env and helper libraries.
# - Starts the selected docker compose services (and optional seed steps).
#
# Version: 1.18
# Last modified: 2026-06-30
# Changelog:
# - 1.4 (2026-04-26): Added env selectors and env-aware docker compose wrappers for local and deployment startup flows.
# - 1.5 (2026-04-27): Documents the api-migrate one-shot service and its build/reseed behavior in help text and startup logs.
# - 1.6 (2026-04-29): Switched startup env selection to the canonical dev/test/prod contract.
# - 1.7 (2026-05-09): Removed inline smoke validation; use scripts/smoke_stack.sh as an explicit follow-up command.
# - 1.8 (2026-05-10): Added explicit --with-edge startup support for the edge compose profile.
# - 1.9 (2026-05-12): Documented metadata startup auth reconciliation and seeded credential refresh.
# - 1.10 (2026-05-13): Stopped restarting Keycloak during metadata post-start so seed-all does not rotate credentials again before OpenMetadata token minting.
# - 1.11 (2026-05-30): Added first-class Airflow startup support and delegated dq-airflow-sdk wheel preparation to this build seam.
# - 1.12 (2026-05-31): Under --force-build, prebuild repo Python packages (dq-cli, dq-utils, dq-domain-validation) before compose startup.
# - 1.13 (2026-05-31): Consolidated Airflow SDK/operator wheel builds behind scripts/package-releases/build_dq_airflow_wheels.sh.
# - 1.14 (2026-05-31): Switched startup to one wrapper script that builds all required wheel artifacts.
# - 1.16 (2026-06-02): Added explicit --with-spark startup support for the distributed Spark cluster profile.
# - 1.17 (2026-06-30): Added Trino to --all startup and explicit --with-trino support.
# - 1.18 (2026-06-30): Runs the Trino AIStor catalog seed after --seed-all delivery seeding.
# - 1.15 (2026-05-31): Delegated Airflow DAG artifact build calls through scripts/package-releases/build_dq_airflow_dag_artifact.sh.

# Source generic logging function
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SCRIPT_DIR/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/auth.sh"
source "$ROOT_DIR/scripts/supporting/openmetadata.sh"
source "$ROOT_DIR/scripts/supporting/env/selection.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
set_log_level INFO
my_name="start-containers.sh"

PYTHON_RUNNER="$ROOT_DIR/scripts/python_arm64.sh"
PYTHON_BIN="$ROOT_DIR/venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi
init_root_env_file "$ROOT_DIR"

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  exit 1
fi

set -- "${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"

if [ ! -f "$ROOT_ENV_FILE" ]; then
  error "$my_name" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

validate_selected_root_env_file "$ROOT_DIR" full

export ROOT_ENV_FILE

info "$my_name" "Environment selection: $(describe_root_env_file_selection "$ROOT_DIR" "$ROOT_ENV_FILE") -> $ROOT_ENV_FILE"

# source repository-level .env
source "$ROOT_ENV_FILE"
source "$ROOT_DIR/scripts/supporting/setup_env.sh"
source "$ROOT_DIR/scripts/supporting/keycloak_readiness.sh"
cd "$ROOT_DIR"

# Ensure canonical public Kong URL is present. Scripts expect this to be set
# (do not silently fall back to an implicit default here).
if [ -z "${KONG_PUBLIC_URL:-}" ]; then
  error "$my_name" "KONG_PUBLIC_URL is not set; please set KONG_PUBLIC_URL in $ROOT_ENV_FILE or the environment"
  exit 1
fi

ensure_keycloak_engine_worker_client_secret_matches_env() {
  # If the Keycloak realm was imported earlier with a different secret, the
  # worker will fail with 401 until Keycloak is updated or the realm is re-imported.
  # This keeps local startup deterministic by reconciling Keycloak to the configured
  # worker secret from .env / compose environment.
  local token_url="${DQ_ENGINE_OIDC_TOKEN_URL:-}"
  local issuer="${DQ_ENGINE_OIDC_ISSUER:-}"
  local client_id="${DQ_ENGINE_OIDC_CLIENT_ID:-dq-engine-gx-worker}"
  local client_secret="${DQ_ENGINE_OIDC_CLIENT_SECRET:-}"
  local required_role="${DQ_ENGINE_OIDC_REALM_ROLE:-dq:rules:write}"

  if [ -z "$client_id" ] || [ -z "$client_secret" ]; then
    error "$my_name" "Worker OIDC vars are missing; cannot reconcile Keycloak client secret"
    return 1
  fi

  # Only attempt reconciliation when the worker is configured to talk to the
  # in-compose Keycloak service (or issuer). Otherwise, assume an external IdP.
  if [[ "$token_url" != *"://keycloak:"* ]] && [[ "$issuer" != *"://keycloak:"* ]]; then
    info "$my_name" "Worker token endpoint is not in-compose Keycloak; skipping Keycloak client secret reconciliation"
    return 0
  fi

  if [ -z "${KEYCLOAK_REALM:-}" ] || [ -z "${KEYCLOAK_SYSTEM_ADMIN_USERNAME:-}" ] || [ -z "${KEYCLOAK_SYSTEM_ADMIN_PASSWORD:-}" ]; then
    error "$my_name" "Keycloak admin env is not configured (KEYCLOAK_REALM/KEYCLOAK_SYSTEM_ADMIN_USERNAME/KEYCLOAK_SYSTEM_ADMIN_PASSWORD)"
    return 1
  fi

  if [ -z "$(docker_compose ps -q keycloak 2>/dev/null || true)" ]; then
    error "$my_name" "Keycloak container is not running, but worker token URL points to in-compose Keycloak. Start with --with-auth."
    return 1
  fi

  info "$my_name" "Reconciling Keycloak secret for service client '$client_id' (if needed)..."

  if ! docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://127.0.0.1:8080 --realm master --user "$KEYCLOAK_SYSTEM_ADMIN_USERNAME" --password "$KEYCLOAK_SYSTEM_ADMIN_PASSWORD" >/dev/null 2>&1; then
    error "$my_name" "Unable to authenticate to Keycloak via kcadm"
    return 1
  fi

  local client_uuid
  client_uuid="$(docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get clients -r "$KEYCLOAK_REALM" -q "clientId=$client_id" | \
    jq -r '.[0].id // empty')"

  if [ -z "$client_uuid" ]; then
    error "$my_name" "Keycloak client '$client_id' was not found in realm '$KEYCLOAK_REALM'"
    return 1
  fi

  local service_account_user_id
  service_account_user_id="$(docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get "clients/${client_uuid}/service-account-user" -r "$KEYCLOAK_REALM" | \
    jq -r '.id // empty')"

  if [ -z "$service_account_user_id" ]; then
    error "$my_name" "Unable to resolve service-account user for Keycloak client '$client_id'"
    return 1
  fi

  local keycloak_secret
  keycloak_secret="$(docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get "clients/${client_uuid}/client-secret" -r "$KEYCLOAK_REALM" | \
    jq -r '.value // empty')"

  if [ -z "$keycloak_secret" ]; then
    error "$my_name" "Unable to read current Keycloak client secret for '$client_id'"
    return 1
  fi

  local env_hash kc_hash
  env_hash="$client_secret"
  kc_hash="$keycloak_secret"

  if [ "$env_hash" = "$kc_hash" ]; then
    info "$my_name" "✓ Keycloak secret already matches configured worker auth env"
  else
    warning "$my_name" "Keycloak stored secret differs from configured worker auth env; updating Keycloak client secret"
    if ! docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh update "clients/${client_uuid}" -r "$KEYCLOAK_REALM" -s "secret=${client_secret}" >/dev/null; then
      error "$my_name" "Failed to update Keycloak client secret for '$client_id'"
      return 1
    fi

    info "$my_name" "✓ Keycloak client secret updated"
  fi

  local has_required_role
  has_required_role="$(docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get "users/${service_account_user_id}/role-mappings/realm" -r "$KEYCLOAK_REALM" | \
    jq -r --arg role "$required_role" 'any(.[]?; (.name // empty) == $role) | tostring')"

  if [ "$has_required_role" != "true" ]; then
    warning "$my_name" "Assigning realm role '$required_role' to Keycloak service account for '$client_id'"
    if ! docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh add-roles -r "$KEYCLOAK_REALM" --uid "$service_account_user_id" --rolename "$required_role" >/dev/null; then
      error "$my_name" "Failed to assign realm role '$required_role' to Keycloak client '$client_id'"
      return 1
    fi
    info "$my_name" "✓ Keycloak service account role '$required_role' assigned"
  else
    info "$my_name" "✓ Keycloak service account already has realm role '$required_role'"
  fi

  return 0
}

ensure_keycloak_openmetadata_client_redirect_matches_env() {
  local keycloak_local_base="${KEYCLOAK_LOCAL_URL:-${KEYCLOAK_PUBLIC_URL:-http://${KEYCLOAK_PUBLIC_HOSTNAME:-keycloak.jac.dot}:8080}}"
  local keycloak_ready_url="${keycloak_local_base}/realms/${KEYCLOAK_REALM}/.well-known/openid-configuration"
  local openmetadata_callback="${OPENMETADATA_CALLBACK:-https://openmetadata.jac.dot:8585/callback}"
  local openmetadata_origin="${openmetadata_callback%/callback}"
  local admin_user="${KEYCLOAK_SYSTEM_ADMIN_USERNAME:-}"
  local admin_password="${KEYCLOAK_SYSTEM_ADMIN_PASSWORD:-}"
  local admin_token
  local client_uuid
  local client_json
  local updated_client_json
  local put_code

  if [ -z "$admin_user" ] || [ -z "$admin_password" ]; then
    error "$my_name" "Keycloak admin env is not configured (KEYCLOAK_SYSTEM_ADMIN_USERNAME/KEYCLOAK_SYSTEM_ADMIN_PASSWORD)"
    return 1
  fi

  info "$my_name" "Checking Keycloak readiness for OpenMetadata client reconciliation..."
  if ! wait_for_keycloak_ready "$keycloak_ready_url" "Keycloak"; then
    error "$my_name" "✗ Keycloak did not become ready during OpenMetadata client reconciliation"
    return 1
  fi
  KEYCLOAK_READY_ALREADY_CONFIRMED=true

  if ! docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://127.0.0.1:8080 --realm master --user "$admin_user" --password "$admin_password" >/dev/null 2>&1; then
    error "$my_name" "Unable to authenticate to Keycloak via kcadm for OpenMetadata client reconciliation"
    return 1
  fi

  client_uuid="$(docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get clients -r "$KEYCLOAK_REALM" -q "clientId=openmetadata" \
    | jq -r '.[0].id // empty')"

  if [ -z "$client_uuid" ]; then
    error "$my_name" "Keycloak client 'openmetadata' was not found in realm '$KEYCLOAK_REALM'"
    return 1
  fi

  admin_token="$(curl -sS -X POST "${keycloak_local_base}/realms/master/protocol/openid-connect/token" \
    -H 'content-type: application/x-www-form-urlencoded' \
    -d 'grant_type=password' \
    -d "client_id=${KEYCLOAK_MASTER_CLIENT_ID:-admin-cli}" \
    -d "username=${admin_user}" \
    -d "password=${admin_password}" \
    | jq -r '.access_token // empty' 2>/dev/null || true)"

  if [ -z "$admin_token" ]; then
    error "$my_name" "Failed to obtain Keycloak admin token for OpenMetadata client reconciliation"
    return 1
  fi

  client_json="$(curl -sS --max-time 10 \
    -H "Authorization: Bearer ${admin_token}" \
    "${keycloak_local_base}/admin/realms/${KEYCLOAK_REALM}/clients/${client_uuid}")"
  updated_client_json="$(printf '%s' "$client_json" | OPENMETADATA_CALLBACK="$openmetadata_callback" OPENMETADATA_ORIGIN="$openmetadata_origin" jq -c '
    .redirectUris = [env.OPENMETADATA_CALLBACK]
    | .webOrigins = [env.OPENMETADATA_ORIGIN]
  ')"

  if [ -z "$updated_client_json" ]; then
    error "$my_name" "Failed to prepare updated OpenMetadata client JSON"
    return 1
  fi

  put_code="$(printf '%s' "$updated_client_json" | curl -sS -o /dev/null -w '%{http_code}' \
    -X PUT "${keycloak_local_base}/admin/realms/${KEYCLOAK_REALM}/clients/${client_uuid}" \
    -H "Authorization: Bearer ${admin_token}" \
    -H 'content-type: application/json' \
    --data-binary @- \
    || true)"

  if [ "$put_code" != "204" ] && [ "$put_code" != "200" ]; then
    error "$my_name" "Failed to update Keycloak client 'openmetadata' redirect URI settings"
    return 1
  fi

  client_json="$(curl -sS --max-time 10 \
    -H "Authorization: Bearer ${admin_token}" \
    "${keycloak_local_base}/admin/realms/${KEYCLOAK_REALM}/clients/${client_uuid}")"
  if ! printf '%s' "$client_json" | OPENMETADATA_CALLBACK="$openmetadata_callback" OPENMETADATA_ORIGIN="$openmetadata_origin" jq -e '
      .redirectUris == [env.OPENMETADATA_CALLBACK]
      and .webOrigins == [env.OPENMETADATA_ORIGIN]
    ' >/dev/null; then
    error "$my_name" "Keycloak client 'openmetadata' did not retain the expected redirect URI settings"
    return 1
  fi

  info "$my_name" "✓ Keycloak openmetadata client redirect URI updated"
  return 0
}

rebuild_root_venv() {
  local venv_dir="$ROOT_DIR/venv"
  local host_python
  local -a venv_creator
  local candidate

  host_python="$(command -v python3 || true)"

  # If root venv is currently active (or broken), python3 may point inside it.
  # Never use that interpreter to rebuild the same venv.
  if [ -n "$host_python" ] && [[ "$host_python" == "$venv_dir"/* ]]; then
    host_python=""
  fi

  # Fall back to known stable python locations.
  if [ -z "$host_python" ]; then
    for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3 /Library/Frameworks/Python.framework/Versions/3.13/bin/python3; do
      if [ -x "$candidate" ]; then
        host_python="$candidate"
        break
      fi
    done
  fi

  if [ -z "$host_python" ] || [ ! -x "$host_python" ]; then
    error "$my_name" "python3 is not available on PATH"
    return 1
  fi

  venv_creator=("$host_python")

  # Require arm64 interpreter on Apple Silicon.
  if command -v arch >/dev/null 2>&1 && arch -arm64 /usr/bin/true >/dev/null 2>&1; then
    if arch -arm64 "$host_python" -V >/dev/null 2>&1; then
      venv_creator=(arch -arm64 "$host_python")
    else
      error "$my_name" "unable to execute $host_python under arch -arm64"
      return 1
    fi
  fi

  info "$my_name" "Rebuilding clean root Python virtual environment..."
  rm -rf "$venv_dir"
  "${venv_creator[@]}" -m venv "$venv_dir" || {
    error "$my_name" "unable to create virtual environment at $venv_dir"
    return 1
  }

  info "$my_name" "Installing root Python dependencies..."
  "$PYTHON_RUNNER" --python-bin "$venv_dir/bin/python" -m pip install --quiet --upgrade pip setuptools wheel || {
    error "$my_name" "start-containers failed: unable to upgrade pip tooling in $venv_dir"
    return 1
  }

  "$PYTHON_RUNNER" --python-bin "$venv_dir/bin/python" -m pip install --quiet --no-cache-dir \
    -r "$ROOT_DIR/dq-api/fastapi/requirements-dev.txt" \
    -r "$ROOT_DIR/dq-metadata/scripts/requirements.txt" || {
      error "$my_name" "start-containers failed: unable to install Python requirements into $venv_dir"
      return 1
    }
}

SEED_POSTGRES=false
SEED_KEYCLOAK=false
SEED_ZAMMAD=false
SEED_OPENMETADATA=false
SEED_ALL=false
SEED_AUTH=false
REMOVE_ORPHANS=false
START_ALL=false
START_BASE=false
START_REDIS=false
START_CORE=false
START_GATEWAY=false
START_AUTH=false
START_EDGE=false
START_SPARK=false
START_ENGINE=false
START_WORKERS=false
START_TRINO=false
START_AIRFLOW=false
START_PROFILING=false
START_METADATA=false
START_METADATA_INGESTION=false
START_LLM=false
START_SUPPORT=false
START_OBSERVABILITY=false
VERIFY_FASTAPI_TESTS=false
KEYCLOAK_READY_ALREADY_CONFIRMED=false
INIT_DB=false
RESET_VENV=false
FORCE_BUILD=false
SEED_DELIVERIES=false
NO_SEED_DELIVERIES=false
PURGE_BUCKET=false
WIPE_AISTOR=false

print_usage() {
  printf '%s\n' \
    "Usage: ./scripts/start-containers.sh [OPTIONS]" \
    "" \
    "Canonical env options:" \
    "  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local" \
    "  --env-file PATH          Use an explicit env file for CI, /etc, or diagnostics" \
    "" \
    "Container profile options:" \
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
    "  --with-trino" \
    "  --with-airflow" \
    "  --with-profiling" \
    "  --with-metadata            Start OpenMetadata and reconcile Keycloak auth/seeded credentials first" \
    "  --with-metadata-ingestion" \
    "  --with-llm" \
    "  --with-support" \
    "  --with-observability" \
    "" \
    "Seeding options:" \
    "  --seed-postgres" \
    "  --seed-keycloak" \
    "  --seed-zammad" \
    "  --seed-deliveries" \
    "  --no-seed-deliveries" \
    "  --purge-bucket" \
    "  --wipe-aistor" \
    "  --seed-all" \
    "" \
    "Other options:" \
    "  --remove-orphans" \
    "  --force-build" \
    "  --test-verify" \
    "  --init-db" \
    "  --reset-venv" \
    "" \
    "Migration/build notes:" \
    "  - Normal startup runs the api-migrate one-shot service from the dq-api image before api starts." \
    "  - With the default --no-build path, new Alembic revisions are only picked up after --force-build or a prior dq-api build." \
    "  - When Postgres reseeding runs, start-containers prebuilds dq-api and db-seed from the same workspace snapshot before the later --no-build compose up." \
    "  -h, --help"
}

regenerate_oas_and_swagger_assets_for_seed_all() {
  local generator_script="$ROOT_DIR/dq-api/scripts/generate_oas_per_tag.py"
  local output_dir="$ROOT_DIR/dq-ui/public/openapi"
  local swagger_index="$output_dir/index.html"
  local api_container

  api_container="$(docker_compose ps -q api 2>/dev/null | tr -d '[:space:]')"
  if [ -z "$api_container" ]; then
    error "$my_name" "OAS regeneration failed: API container is not running"
    return 1
  fi

  mkdir -p "$output_dir"

  info "$my_name" "Regenerating per-category OpenAPI JSON files via running API container..."
  docker cp "$generator_script" "$api_container:/tmp/generate_oas_per_tag.py" || {
    error "$my_name" "OAS regeneration failed: unable to copy generator into API container"
    return 1
  }

  docker exec "$api_container" python3 /tmp/generate_oas_per_tag.py /tmp/openapi_out || {
    error "$my_name" "OAS regeneration failed."
    return 1
  }

  docker cp "$api_container:/tmp/openapi_out/." "$output_dir/" || {
    error "$my_name" "OAS regeneration failed: unable to copy generated files from API container"
    return 1
  }

  if [ ! -f "$swagger_index" ]; then
    error "$my_name" "Swagger UI page missing at $swagger_index"
    return 1
  fi

  info "$my_name" "Rebuilding frontend assets to include refreshed OpenAPI files..."
  "$ROOT_DIR/scripts/local_build_frontend.sh" || {
    error "$my_name" "Frontend build step failed"
    return 1
  }

  info "$my_name" "Restarting frontend container..."
  docker_compose up -d frontend >/dev/null || {
    error "$my_name" "Frontend start failed."
    return 1
  }

  success "$my_name" "PASS: OpenAPI JSON + Swagger UI assets are ready"
  return 0
}

ensure_kong_seed_reconciliation() {

  local keycloak_local_base="${KEYCLOAK_LOCAL_URL:-${KEYCLOAK_PUBLIC_URL:-http://${KEYCLOAK_PUBLIC_HOSTNAME:-keycloak.jac.dot}:8080}}"
  # If KONG_PUBLIC_URL is unset or empty, skip Kong reconciliation. Some environments
  # no longer expose a KONG_PUBLIC_URL host variable and reconciliation should be
  # treated as optional (non-fatal).
  if [ -z "${KONG_PUBLIC_URL:-}" ]; then
    info "$my_name" "Kong reconciliation skipped: KONG_PUBLIC_URL is not set"
    return 0
  fi

  local keycloak_ready_url="${keycloak_local_base}/realms/${KEYCLOAK_REALM}/.well-known/openid-configuration"
  local kong_probe_base_url="${KONG_LOCAL_PROBE_BASE_URL:-${KONG_PUBLIC_URL%/}}"
  local app_config_url="${kong_probe_base_url%/}/system/v1/app-config"
  local me_url="${kong_probe_base_url%/}/admin/v1/me"
  local kong_container_id
  local bootstrap_src="$ROOT_DIR/dq-kong/scripts/bootstrap_kong.sh"
  local bootstrap_dst="/tmp/dq-bootstrap_kong.sh"
  local app_cfg sso_enabled sso_issuer
  local cors_has_traceparent=false
  local jwt_auth_works=false
  local token_endpoint token auth_code
  local seeded_credentials_file
  local login_email
  local login_password

  info "$my_name" "Checking Keycloak readiness for Kong reconciliation..."
  if ! wait_for_keycloak_ready "$keycloak_ready_url" "Keycloak"; then
    error "$my_name" "✗ Keycloak did not become ready during Kong reconciliation"
    return 1
  fi
  KEYCLOAK_READY_ALREADY_CONFIRMED=true

  if ! dq_source_seeded_user_credentials --quiet; then
    error "$my_name" "Unable to load seeded Keycloak credentials for Kong reconciliation"
    return 1
  fi

  seeded_credentials_file="${DQ_SEEDED_CREDENTIALS_ENV_FILE:-}"
  login_email="${KEYCLOAK_JACCLOUD_USERNAME:-}"
  login_password="${KEYCLOAK_JACCLOUD_PASSWORD:-}"

  if [ -z "$seeded_credentials_file" ] || [ ! -f "$seeded_credentials_file" ]; then
    error "$my_name" "Seeded Keycloak credentials file not found"
    return 1
  fi

  if [ -z "$login_email" ] || [ -z "$login_password" ]; then
    error "$my_name" "Seeded Keycloak login credentials are missing"
    return 1
  fi

  kong_container_id="$(docker ps -q -f name=^dq-made-easy-kong$ 2>/dev/null | tr -d '[:space:]' || true)"
  if [ -z "$kong_container_id" ]; then
    warning "$my_name" "Kong reconciliation skipped: dq-made-easy-kong is not running"
    return 0
  fi

  if [ ! -f "$bootstrap_src" ]; then
    error "$my_name" "✗ Kong reconciliation failed: bootstrap script not found at $bootstrap_src"
    return 1
  fi

  if docker cp "$bootstrap_src" "${kong_container_id}:${bootstrap_dst}" >/dev/null 2>&1 \
    && docker exec "$kong_container_id" bash -lc "bash '${bootstrap_dst}'"; then
    success "$my_name" "✓ Kong reconciliation bootstrap executed"
  else
    error "$my_name" "✗ Kong reconciliation bootstrap execution failed"
    return 1
  fi

  app_cfg="$(curl_kong_host_probe -s --max-time 5 "$app_config_url" || true)"
  sso_enabled="$(printf '%s' "$app_cfg" | jq -r '.ssoEnabled // false' 2>/dev/null || false)"
  sso_issuer="$(printf '%s' "$app_cfg" | jq -r '.ssoIssuer // empty' 2>/dev/null || true)"

  if curl -s http://localhost:8001/services/dq-api/plugins \
    | jq -e '.data[]? | select(.name=="cors") | (.config.headers // []) | index("traceparent") != null' >/dev/null 2>&1; then
    cors_has_traceparent=true
  fi

  if [ "$sso_enabled" = "true" ] && [ -n "$sso_issuer" ]; then
    token_endpoint="${sso_issuer%/}/protocol/openid-connect/token"
    host_name="${KEYCLOAK_PUBLIC_HOSTNAME}"
    token_endpoint="${token_endpoint/http:\/\/${host_name}/http:\/\/localhost}"

    token="$(curl -s --max-time 10 "$token_endpoint" \
      -H 'Content-Type: application/x-www-form-urlencoded' \
      --data-urlencode \"client_id=${KEYCLOAK_CLIENT_ID}\" \
      --data-urlencode 'grant_type=password' \
      --data-urlencode "username=${login_email}" \
      --data-urlencode "password=${login_password}" \
      | jq -r '.access_token // empty' 2>/dev/null || true)"

    if [ -n "$token" ]; then
      auth_code="$(curl_kong_host_probe -s -o /dev/null -w '%{http_code}' --max-time 10 \
        -H "Authorization: Bearer $token" \
        "${me_url}" || true)"
      if [ "$auth_code" = "200" ]; then
        jwt_auth_works=true
      fi
    fi
  else
    jwt_auth_works=true
  fi

  if [ "$cors_has_traceparent" = true ] && [ "$jwt_auth_works" = true ]; then
    success "$my_name" "✓ Kong reconciliation verified (CORS telemetry headers + JWT auth check)"
    return 0
  fi

  error "$my_name" "✗ Kong reconciliation verification failed"
  if [ "$cors_has_traceparent" != true ]; then
    error "$my_name" "  Missing traceparent in Kong CORS allowed headers"
  fi
  if [ "$jwt_auth_works" != true ]; then
    error "$my_name" "  Kong JWT auth check failed for /admin/v1/me using seeded dq-admin user"
  fi
  return 1
}

build_schema_owner_images_if_needed() {
  local preseed_build_required=false

  if [ "$SEED_POSTGRES" = true ] || [ "$INIT_DB" = true ]; then
    preseed_build_required=true
  fi

  if [ "$SEED_KEYCLOAK" = true ] || [ "$SEED_ALL" = true ]; then
    preseed_build_required=true
  fi

  if [ "$preseed_build_required" != true ]; then
    return 0
  fi

  if [ "$FORCE_BUILD" = true ]; then
    info "$my_name" "Preseed image policy: --force-build is enabled, but reseeding runs before the later full-stack build, so one-shot seed images are being rebuilt now"
  fi

  if [ "$SEED_POSTGRES" = true ] || [ "$INIT_DB" = true ]; then
    info "$my_name" "Building dq-api image before Postgres reseed so api-migrate and api use the same workspace snapshot as db-seed"
    if ! docker_compose --profile core --profile gateway --profile observability build api; then
      warning "$my_name" "Failed to build dq-api image before Postgres reseed"
      exit 1
    fi

    info "$my_name" "Building db-seed image before Postgres reseed so containerized Alembic and seed orchestration use the current dependency set"
    if ! docker_compose --profile auth --profile seed build db-seed; then
      warning "$my_name" "Failed to build db-seed image before Postgres reseed"
      exit 1
    fi
  fi

  if [ "$SEED_POSTGRES" = true ] || [ "$INIT_DB" = true ] || [ "$SEED_KEYCLOAK" = true ] || [ "$SEED_ALL" = true ]; then
    info "$my_name" "Building keycloak-seed-artifacts image before Keycloak/Postgres reseed so realm generation uses the current UI origin contract"
    if ! docker_compose --profile auth --profile seed build keycloak-seed-artifacts; then
      warning "$my_name" "Failed to build keycloak-seed-artifacts image before reseeding"
      exit 1
    fi
  fi
}

ensure_required_wheel_artifacts() {
  local -a wheel_args=()

  if [ "$FORCE_BUILD" = true ]; then
    wheel_args+=(--force-build)
  fi
  if [ "$START_AIRFLOW" = true ]; then
    wheel_args+=(--with-airflow)
  fi

  if [ "${#wheel_args[@]}" -eq 0 ]; then
    return 0
  fi

  if [ "$FORCE_BUILD" = true ] && [ "$START_AIRFLOW" = true ]; then
    info "$my_name" "Wheel policy: running unified wheel build wrapper for force-build and Airflow artifacts"
  elif [ "$FORCE_BUILD" = true ]; then
    info "$my_name" "Wheel policy: running unified wheel build wrapper for force-build package artifacts"
  else
    info "$my_name" "Wheel policy: running unified wheel build wrapper for Airflow artifacts"
  fi

  if ! "$ROOT_DIR/scripts/package-releases/build_required_wheels.sh" "${wheel_args[@]}" >/dev/null; then
    error "$my_name" "Failed to build required wheel artifacts"
    exit 1
  fi
}

ensure_airflow_dag_artifact() {
  local airflow_dag_artifact_dir="$ROOT_DIR"/tmp/dq-airflow-dags-dist
  local airflow_dag_artifact="$airflow_dag_artifact_dir/dq-airflow-dags.zip"

  if [ "$START_AIRFLOW" != true ]; then
    return 0
  fi

  if [ "$FORCE_BUILD" != true ] && [ -f "$airflow_dag_artifact" ]; then
    info "$my_name" "Airflow DAG artifact policy: using existing DAG artifact at tmp/dq-airflow-dags-dist/"
    return 0
  fi

  if [ "$FORCE_BUILD" = true ]; then
    info "$my_name" "Airflow DAG artifact policy: --force-build enabled, rebuilding the DAG artifact before compose build/up"
  else
    info "$my_name" "Airflow DAG artifact policy: artifact missing, building the DAG artifact before compose build/up"
  fi

  if ! "$ROOT_DIR/scripts/package-releases/build_dq_airflow_dag_artifact.sh" >/dev/null; then
    error "$my_name" "Failed to build the Airflow DAG artifact required by the Airflow profile"
    exit 1
  fi
}

enforce_keycloak_username_prompt_after_logout() {
  if [ "$START_AUTH" != true ] && [ "$SEED_KEYCLOAK" != true ] && [ "$SEED_ALL" != true ]; then
    return 0
  fi

  local keycloak_local_base="${KEYCLOAK_LOCAL_URL:-${KEYCLOAK_PUBLIC_URL:-http://${KEYCLOAK_PUBLIC_HOSTNAME:-keycloak.jac.dot}:8080}}"
  local keycloak_ready_url="${keycloak_local_base}/realms/${KEYCLOAK_REALM}/.well-known/openid-configuration"
  local admin_user="${KEYCLOAK_ADMIN:-admin}"
  local admin_password="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
  local cookie_execution_id
  local cookie_requirement
  local admin_token
  local put_body_file
  local put_code

  if [ "$KEYCLOAK_READY_ALREADY_CONFIRMED" = true ]; then
    info "$my_name" "Using prior Keycloak readiness result for username prompt enforcement..."
  else
    info "$my_name" "Checking Keycloak readiness for username prompt enforcement..."
    if ! wait_for_keycloak_ready "$keycloak_ready_url" "Keycloak"; then
      warning "$my_name" "⚠ Keycloak not ready; skipping username prompt enforcement"
      return 0
    fi
    KEYCLOAK_READY_ALREADY_CONFIRMED=true
  fi

  if ! docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://localhost:8080 --realm master --user "$admin_user" --password "$admin_password" >/dev/null 2>&1; then
    warning "$my_name" "⚠ Unable to authenticate kcadm for Keycloak username prompt enforcement"
    return 0
  fi

  cookie_execution_id="$(docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get authentication/flows/browser/executions -r "$KEYCLOAK_REALM" \
    | jq -r '.[] | select(.providerId=="auth-cookie") | .id' | head -1)"

  if [ -z "$cookie_execution_id" ]; then
    warning "$my_name" "⚠ Keycloak browser flow cookie execution not found; skipping username prompt enforcement"
    return 0
  fi

  cookie_requirement="$(docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get authentication/flows/browser/executions -r "$KEYCLOAK_REALM" \
    | jq -r '.[] | select(.providerId=="auth-cookie") | .requirement' | head -1)"

  if [ "$cookie_requirement" = "DISABLED" ]; then
    success "$my_name" "✓ Keycloak browser cookie execution already disabled"
    return 0
  fi

  # Disable cookie execution (best-effort).
  # Using the Keycloak Admin REST endpoint directly is more reliable than
  # kcadm file handling across different local Docker environments.
  # Expected: HTTP 202 with a flow payload.
  admin_token="$(curl -sS -X POST "${keycloak_local_base}/realms/${KEYCLOAK_TOKEN_REALM:-master}/protocol/openid-connect/token" \
    -H 'content-type: application/x-www-form-urlencoded' \
    -d 'grant_type=password' \
    -d "client_id=${KEYCLOAK_MASTER_CLIENT_ID:-admin-cli}" \
    -d "username=${admin_user}" \
    -d "password=${admin_password}" \
    | jq -r '.access_token // empty' 2>/dev/null || true)"

  if [ -z "$admin_token" ]; then
    warning "$my_name" "⚠ Failed to obtain Keycloak admin token; skipping username prompt enforcement"
    return 0
  fi

  put_body_file="$(mktemp -t keycloak-cookie-put.XXXXXX.json)"
  printf '{"id":"%s","requirement":"DISABLED"}' "$cookie_execution_id" >"$put_body_file"

  local put_response_file
  put_response_file="$(mktemp -t keycloak-cookie-put.response.XXXXXX.json)"

  put_code="$(curl -sS -o "$put_response_file" -w '%{http_code}' \
    -X PUT "${keycloak_local_base}/admin/realms/${KEYCLOAK_REALM}/authentication/flows/browser/executions" \
    -H "Authorization: Bearer ${admin_token}" \
    -H 'content-type: application/json' \
    --data-binary "@${put_body_file}" \
    || true)"

  rm -f "$put_body_file" || true

  if [ "$put_code" = "202" ] || [ "$put_code" = "200" ] || [ "$put_code" = "204" ]; then
    rm -f "$put_response_file" || true
    success "$my_name" "✓ Keycloak browser cookie execution disabled (username field enforced)"
    return 0
  fi

  warning "$my_name" "⚠ Failed to disable Keycloak browser cookie execution (HTTP ${put_code:-unknown})"
  head -c 400 "$put_response_file" 2>/dev/null | sed 's/^/[keycloak-admin] /' || true
  rm -f "$put_response_file" || true

  return 0
}

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
    --with-engine) START_ENGINE=true; shift ;;
    --with-workers) START_WORKERS=true; shift ;;
    --with-trino) START_TRINO=true; shift ;;
    --with-airflow) START_AIRFLOW=true; shift ;;
    --with-profiling) START_PROFILING=true; shift ;;
    --with-observability) START_OBSERVABILITY=true; shift ;;
    --seed-postgres) SEED_POSTGRES=true; shift ;;
    --seed-keycloak) SEED_KEYCLOAK=true; shift ;;
    --seed-zammad) SEED_ZAMMAD=true; shift ;;
    --seed-openmetadata) SEED_OPENMETADATA=true; shift ;;
    --seed-deliveries) SEED_DELIVERIES=true; shift ;;
    --no-seed-deliveries) NO_SEED_DELIVERIES=true; shift ;;
    --purge-bucket) PURGE_BUCKET=true; shift ;;
    --wipe-aistor) WIPE_AISTOR=true; shift ;;
    --seed-all) SEED_ALL=true; SEED_POSTGRES=true; SEED_KEYCLOAK=true; SEED_DELIVERIES=true; SEED_ZAMMAD=true; shift ;;
    --init-db) INIT_DB=true; shift ;;
    --remove-orphans) REMOVE_ORPHANS=true; shift ;;
    --with-metadata) START_METADATA=true; shift ;;
    --with-metadata-ingestion) START_METADATA_INGESTION=true; shift ;;
    --with-llm) START_LLM=true; shift ;;
    --with-support) START_SUPPORT=true; shift ;;
    --test-verify) VERIFY_FASTAPI_TESTS=true; shift ;;
    --reset-venv) RESET_VENV=true; shift ;;
    --force-build) FORCE_BUILD=true; shift ;;
    -h|--help) print_usage; exit 0 ;;
    *) echo "Unknown arg: $1"; print_usage; exit 1 ;;
  esac
done

if [ "$START_ALL" = true ]; then
  START_BASE=true
  START_REDIS=true
  START_CORE=true
  START_GATEWAY=true
  START_AUTH=true
  START_ENGINE=true
  START_WORKERS=true
  START_TRINO=true
  START_PROFILING=true
  START_METADATA=true
  START_METADATA_INGESTION=true
  START_SUPPORT=true
  START_OBSERVABILITY=true
fi

if [ "$START_METADATA" = true ]; then
  START_AUTH=true
fi

if [ "$SEED_ALL" = true ]; then
  START_SUPPORT=true
  SEED_ZAMMAD=true
fi

# Allow callers (env var NO_SEED_DELIVERIES or CLI flag --no-seed-deliveries) to opt-out
# of deliveries seeding even when --seed-all is used. This lets wrapper scripts
# (for example local startup helpers) disable only deliveries seeding while
# preserving other --seed-all side effects.
if [ "${NO_SEED_DELIVERIES:-false}" = "true" ]; then
  SEED_DELIVERIES=false
  info "$my_name" "NO_SEED_DELIVERIES: disabling deliveries seeding"
fi

if [ "$START_METADATA" = true ] || [ "$START_METADATA_INGESTION" = true ] || [ "$SEED_ALL" = true ]; then
  info "$my_name" "Ensuring OpenMetadata TLS assets are present..."
  "$ROOT_DIR/scripts/create_certs.sh" || exit 1
fi

if [ "$SEED_ZAMMAD" = true ]; then
  START_SUPPORT=true
fi

if [ "$RESET_VENV" = true ]; then
  info "$my_name" "virtual environment will be reset"
  rebuild_root_venv || exit 1
fi

if [ "$START_METADATA" = true ]; then
  info "$my_name" "--seed-all requested: enabling metadata ingestion profile for repeatable OpenMetadata sync"
  START_METADATA_INGESTION=true
fi

# Seeding requires backing services to be started.
if [ "$SEED_POSTGRES" = true ]; then
  START_CORE=true
  START_REDIS=true
fi

if [ "$SEED_KEYCLOAK" = true ]; then
  START_CORE=true
  START_REDIS=true
  START_AUTH=true
fi

info "$my_name" "start-containers: with_base=$START_BASE with_redis=$START_REDIS with_core=$START_CORE with_gateway=$START_GATEWAY with_auth=$START_AUTH with_observability=$START_OBSERVABILITY"
info "$my_name" "start-containers: with_edge=$START_EDGE with_spark=$START_SPARK with_engine=$START_ENGINE with_workers=$START_WORKERS with_trino=$START_TRINO with_airflow=$START_AIRFLOW with_profiling=$START_PROFILING"
info "$my_name" "start-containers: with_metadata=$START_METADATA with_metadata_ingestion=$START_METADATA_INGESTION with_llm=$START_LLM"
info "$my_name" "start-containers: with_support=$START_SUPPORT"
info "$my_name" "start-containers: seed_postgres=$SEED_POSTGRES seed_keycloak=$SEED_KEYCLOAK seed_zammad=$SEED_ZAMMAD seed_deliveries=$SEED_DELIVERIES purge_bucket=$PURGE_BUCKET wipe_aistor=$WIPE_AISTOR seed_all=$SEED_ALL"
info "$my_name" "start-containers: verify_fastapi_tests=$VERIFY_FASTAPI_TESTS"
info "$my_name" "start-containers: reset_venv=$RESET_VENV"

export APK_REPOSITORIES
info "$my_name" "Environment variables set for stack start: REGISTRY=$REGISTRY"

info "$my_name" "Starting stack via docker-compose..."

# Note: FORCE_BUILD is set during argument parsing. Do not attempt to scan "$@" here
# because all args have already been shifted by the parser.

# Pass seed/profile flags explicitly to start_stack.sh
STACK_ARGS=()
PRESEED_ARGS=()
POSTSTACK_SEED_ARGS=()
PRESEED_BEFORE_STACK=false

if [ "$START_ALL" = true ]; then STACK_ARGS+=(--all); fi
if [ "$SEED_POSTGRES" = true ]; then SEED_ARGS+=(--seed-postgres); fi
if [ "$SEED_ZAMMAD" = true ]; then SEED_ARGS+=(--seed-zammad); fi
if [ "$SEED_DELIVERIES" = true ]; then SEED_ARGS+=(--seed-deliveries); fi
if [ "$PURGE_BUCKET" = true ]; then SEED_ARGS+=(--purge-bucket); fi
if [ "$WIPE_AISTOR" = true ]; then SEED_ARGS+=(--wipe-aistor); fi
if [ "$REMOVE_ORPHANS" = true ]; then STACK_ARGS+=(--remove-orphans); fi
if [ "$INIT_DB" = true ]; then SEED_ARGS+=(--init-db); fi

if [ "$SEED_POSTGRES" = true ] || [ "$INIT_DB" = true ]; then
  PRESEED_BEFORE_STACK=true
  PRESEED_ARGS+=(--seed-postgres)
  if [ "$INIT_DB" = true ]; then PRESEED_ARGS+=(--init-db); fi
fi

if [ "$SEED_KEYCLOAK" = true ] || [ "$SEED_ALL" = true ]; then
  POSTSTACK_SEED_ARGS+=(--seed-keycloak)
fi

if [ "$SEED_ZAMMAD" = true ]; then
  POSTSTACK_SEED_ARGS+=(--seed-zammad)
fi

if [ "$SEED_DELIVERIES" = true ]; then
  POSTSTACK_SEED_ARGS+=(--seed-deliveries)
fi

if [ "$PURGE_BUCKET" = true ]; then
  POSTSTACK_SEED_ARGS+=(--purge-bucket)
fi

if [ "$WIPE_AISTOR" = true ]; then
  POSTSTACK_SEED_ARGS+=(--wipe-aistor)
fi

if [ "$SEED_OPENMETADATA" = true ]; then
  POSTSTACK_SEED_ARGS+=(--seed-openmetadata)
fi

if [ "$FORCE_BUILD" = true ] && [ "${#PRESEED_ARGS[@]}" -gt 0 ]; then
  PRESEED_ARGS+=(--force-build)
fi

if [ "$FORCE_BUILD" = true ] && [ "${#POSTSTACK_SEED_ARGS[@]}" -gt 0 ]; then
  POSTSTACK_SEED_ARGS+=(--force-build)
fi

if [ "$START_ALL" = false ]; then
  if [ "$START_BASE" = true ]; then STACK_ARGS+=(--with-base); fi
  if [ "$START_REDIS" = true ]; then STACK_ARGS+=(--with-redis); fi
  if [ "$START_CORE" = true ]; then STACK_ARGS+=(--with-core); fi
  if [ "$START_GATEWAY" = true ]; then STACK_ARGS+=(--with-gateway); fi
  if [ "$START_AUTH" = true ]; then STACK_ARGS+=(--with-auth); fi
  if [ "$START_EDGE" = true ]; then STACK_ARGS+=(--with-edge); fi
  if [ "$START_SPARK" = true ]; then STACK_ARGS+=(--with-spark); fi
  if [ "$START_ENGINE" = true ]; then STACK_ARGS+=(--with-engine); fi
  if [ "$START_WORKERS" = true ]; then STACK_ARGS+=(--with-workers); fi
  if [ "$START_TRINO" = true ]; then STACK_ARGS+=(--with-trino); fi
  if [ "$START_AIRFLOW" = true ]; then STACK_ARGS+=(--with-airflow); fi
  if [ "$START_PROFILING" = true ]; then STACK_ARGS+=(--with-profiling); fi
  if [ "$START_METADATA" = true ]; then STACK_ARGS+=(--with-metadata); fi
  if [ "$START_METADATA_INGESTION" = true ]; then STACK_ARGS+=(--with-metadata-ingestion); fi
  if [ "$START_LLM" = true ]; then STACK_ARGS+=(--with-llm); fi
  if [ "$START_SUPPORT" = true ]; then STACK_ARGS+=(--with-support); fi
  if [ "$START_OBSERVABILITY" = true ]; then STACK_ARGS+=(--with-observability); fi
fi

if [ "$START_OBSERVABILITY" = true ]; then
  if [ -z "${VITE_OTEL_ENABLED:-}" ]; then
    VITE_OTEL_ENABLED="true"
    export VITE_OTEL_ENABLED
  fi

  if [ -z "${OTEL_EXPORTER_OTLP_ENDPOINT:-}" ]; then
    OTEL_EXPORTER_OTLP_ENDPOINT="http://dq-made-easy-otel-collector:4317"
    export OTEL_EXPORTER_OTLP_ENDPOINT
  fi

  if [ -z "${VITE_OTEL_ENDPOINT:-}" ]; then
    VITE_OTEL_ENDPOINT="${GRAFANA_PUBLIC_URL%/}/otlp"
    export VITE_OTEL_ENDPOINT
  fi
fi

# Add --no-build unless --force-build is passed
if [ "$FORCE_BUILD" = false ]; then
  STACK_ARGS+=(--no-build)
fi

if [ "$FORCE_BUILD" = true ]; then
  info "$my_name" "Migration/build policy: --force-build enabled, so api-migrate and api will use a freshly built dq-api image for Alembic/runtime changes."
else
  info "$my_name" "Migration/build policy: api-migrate runs from the current dq-api image; with the default --no-build path, Alembic revision changes require --force-build or a prior dq-api build."
fi
info "$my_name" "Migration/build policy: when Postgres reseeding runs, start-containers prebuilds dq-api and db-seed from the same workspace snapshot before the later --no-build compose up."

ensure_required_wheel_artifacts
ensure_airflow_dag_artifact

info "$my_name" "Invoking start_stack.sh with arguments: ${STACK_ARGS[*]}"
if [ "$SEED_ALL" = true ]; then
  export KEYCLOAK_SYSTEM_ADMIN_USERNAME KEYCLOAK_SYSTEM_ADMIN_PASSWORD
fi

if [ "${#POSTSTACK_SEED_ARGS[@]}" -gt 0 ]; then
  info "$my_name" "Post-stack seeding will run after stack startup via seed_stack.sh: ${POSTSTACK_SEED_ARGS[*]}"
fi

build_schema_owner_images_if_needed

if [ "$PRESEED_BEFORE_STACK" = true ]; then
  info "$my_name" "Running pre-stack seeding for Postgres so startup never races stale persisted state"
  ./scripts/seed_stack.sh "${PRESEED_ARGS[@]}" || {
    warning "$my_name" "Database seeding failed before stack startup"
    exit 1
  }
  info "$my_name" "Pre-stack seeding completed before stack startup"
fi

if [ "$SEED_ALL" = true ]; then
  SKIP_FRONTEND_START=true SKIP_POST_STACK_KONG_REFRESH=true ./scripts/start_stack.sh "${STACK_ARGS[@]}"
else
  SKIP_POST_STACK_KONG_REFRESH=true ./scripts/start_stack.sh "${STACK_ARGS[@]}"
fi

if [ "${#POSTSTACK_SEED_ARGS[@]}" -gt 0 ]; then
  info "$my_name" "Running post-stack seeding after stack startup..."
  ./scripts/seed_stack.sh "${POSTSTACK_SEED_ARGS[@]}" || {
    warning "$my_name" "Stack seeding failed during start-containers.sh execution"
    exit 1
  }
  info "$my_name" "Post-stack seeding completed successfully"
fi

if [ "$SEED_ALL" = true ] && [ "$SEED_DELIVERIES" = true ]; then
  trino_seed_args=(--env-file "$ROOT_ENV_FILE")
  if [ "$FORCE_BUILD" = true ]; then
    trino_seed_args+=(--force-build)
  fi
  info "$my_name" "Running Trino AIStor catalog seed after --seed-all delivery seeding..."
  ./scripts/seed_trino_aistor_catalogs.sh "${trino_seed_args[@]}" || {
    warning "$my_name" "Trino AIStor catalog seeding failed during start-containers.sh --seed-all execution"
    exit 1
  }
  info "$my_name" "Trino AIStor catalog seed completed successfully"
fi

if [ "$SEED_KEYCLOAK" = true ] || [ "$SEED_ALL" = true ]; then
  ensure_kong_seed_reconciliation || exit 1
  enforce_keycloak_username_prompt_after_logout || true
fi

if [ "$START_WORKERS" = true ]; then
  ensure_keycloak_engine_worker_client_secret_matches_env || exit 1
fi

if [ "$START_AUTH" = true ] || [ "$START_METADATA" = true ] || [ "$SEED_KEYCLOAK" = true ] || [ "$SEED_ALL" = true ]; then
  ensure_keycloak_openmetadata_client_redirect_matches_env || exit 1
fi

if [ "$SEED_ALL" = true ]; then
  info "$my_name" "--seed-all requested: regenerating OpenAPI + Swagger assets after stack startup"
  regenerate_oas_and_swagger_assets_for_seed_all || exit 1
fi

if [ "$START_METADATA" = true ]; then
  info "$my_name" "Running OpenMetadata post-start configuration in Docker..."
  if [ "$SEED_ALL" = true ]; then
    if ! dq_source_seeded_user_credentials --quiet; then
      error "$my_name" "Unable to load seeded Keycloak credentials for OpenMetadata configuration"
      exit 1
    fi
    docker_compose up -d openmetadata-server openmetadata-ingestion || exit 1
    prepare_openmetadata_access_token || exit 1
    docker_compose --profile metadata run --rm openmetadata-configure --seed-all || exit 1
  else
    docker_compose up -d openmetadata-server || exit 1
    if [ "$SEED_KEYCLOAK" != true ] && [ "$SEED_ALL" != true ]; then
      info "$my_name" "Reseeding Keycloak so OpenMetadata can mint tokens with the current generated credentials"
      ./scripts/seed_stack.sh --seed-keycloak || exit 1
    fi
    if ! dq_source_seeded_user_credentials --quiet; then
      error "$my_name" "Unable to load seeded Keycloak credentials for OpenMetadata configuration"
      exit 1
    fi
    if [ "$SEED_OPENMETADATA" = true ] || [ "$SEED_KEYCLOAK" = true ] || [ "$SEED_ALL" = true ]; then
      prepare_openmetadata_access_token || exit 1
    fi
    docker_compose --profile metadata run --rm openmetadata-configure || exit 1
  fi
fi

info "$my_name" "Smoke validation is separate: run ./scripts/smoke_stack.sh after startup if you need post-start smoke checks."

info "$my_name" "✓ Start containers script completed successfully"

exit 0
