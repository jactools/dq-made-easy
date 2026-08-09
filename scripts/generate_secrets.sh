#!/usr/bin/env bash
# ============================================================================
# generate_secrets.sh — Generate secrets and configmaps for DQ services.
#
# Generates random passwords for all DQ service secrets, creates required
# configmaps with service URLs, applies everything to the Kubernetes cluster,
# and stores credentials in tmp/.credentials.
#
# Usage: scripts/generate_secrets.sh [options]
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

NAMESPACE="${NAMESPACE:-dq-made-easy-dev}"
CREDENTIALS_FILE="${REPO_ROOT}/tmp/.credentials"
APPLY_K8S="${APPLY_K8S:-true}"

usage() {
  cat <<'USAGE'
Usage: scripts/generate_secrets.sh [options]

Generate secrets and configmaps for all DQ services.

Options:
  --namespace NS      Target namespace (default: dq-made-easy-dev)
  --skip-k8s          Skip applying to cluster
  --help              Show this help

Secrets created:
  - dq-api-secrets              (DQ_DB_INTERNAL_URL, API_SECRET_PLACEHOLDER, APP_CONFIG_ENCRYPTION_KEY)
  - dq-db-secrets               (POSTGRES_PASSWORD)
  - dq-frontend-secrets         (FRONTEND_SECRET_PLACEHOLDER)
  - dq-engine-secrets           (ENGINE_SECRET_PLACEHOLDER)
  - dq-profiling-secrets        (PROFILING_SECRET_PLACEHOLDER)
  - dq-llm-secrets              (DQ_LLM_API_KEY)
  - dq-kafka-consumer-secrets   (KAFKA_CONSUMER_DB_URL)
  - dq-openmetadata-db-secrets  (POSTGRES_PASSWORD, POSTGRES_DB)
  - dq-openmetadata-server-secrets (OM_TOKEN)
  - dq-keycloak-secrets         (KEYCLOAK_ADMIN_PASSWORD)
  - dq-kong-secrets             (KONG_ADMIN_PASSWORD)

Configmaps created:
  - dq-api-config              (ENVIRONMENT)
  - dq-db-config               (ENVIRONMENT, POSTGRES_DB, POSTGRES_USER)
  - dq-frontend-config         (ENVIRONMENT, KONG_PUBLIC_URL)
  - dq-engine-config           (ENVIRONMENT)
  - dq-profiling-config        (ENVIRONMENT, KONG_INTERNAL_URL)
  - dq-llm-config              (ENVIRONMENT)
  - dq-kafka-consumer-config   (ENVIRONMENT, KAFKA_BOOTSTRAP_SERVERS)
  - dq-openmetadata-db-config  (ENVIRONMENT, POSTGRES_DB, POSTGRES_USER)
  - dq-openmetadata-server-config (ENVIRONMENT)
  - dq-keycloak-config         (ENVIRONMENT)
  - dq-kong-config             (ENVIRONMENT)

Credentials are stored in tmp/.credentials.
USAGE
}

log()  { printf '[dq-secrets] %s\n' "$*" >&2; }
info() { printf '[dq-secrets] ✓ %s\n' "$*" >&2; }
err()  { printf '[dq-secrets] ✗ %s\n' "$*" >&2; }
warn() { printf '[dq-secrets] ⚠ %s\n' "$*" >&2; }

generate_password() {
  openssl rand -base64 32 | tr -d '\n'
}

generate_fernet_key() {
  python3 -c "
import base64, os
print(base64.urlsafe_b64encode(os.urandom(32)).decode())
" 2>/dev/null || openssl rand -base64 32 | tr -d '\n'
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Missing required command: $1"
    exit 1
  fi
}

apply_secret() {
  local name="$1"
  shift
  local literals=("$@")

  if [[ "$APPLY_K8S" != "true" ]]; then
    log "Skipping K8s secret $name (--skip-k8s)"
    return 0
  fi

  local args=()
  for lit in "${literals[@]}"; do
    args+=(--from-literal="$lit")
  done

  kubectl create secret generic "$name" \
    "${args[@]}" \
    --dry-run=client -o yaml \
    | kubectl apply -f - -n "$NAMESPACE" 2>/dev/null && \
    info "Secret $name applied to $NAMESPACE" || \
    warn "Could not apply secret $name (cluster may not be running)"
}

apply_configmap() {
  local name="$1"
  shift
  local literals=("$@")

  if [[ "$APPLY_K8S" != "true" ]]; then
    log "Skipping K8s configmap $name (--skip-k8s)"
    return 0
  fi

  local args=()
  for lit in "${literals[@]}"; do
    args+=(--from-literal="$lit")
  done

  kubectl create configmap "$name" \
    "${args[@]}" \
    --dry-run=client -o yaml \
    | kubectl apply -f - -n "$NAMESPACE" 2>/dev/null && \
    info "ConfigMap $name applied to $NAMESPACE" || \
    warn "Could not apply configmap $name (cluster may not be running)"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
  require_cmd openssl
  mkdir -p "${REPO_ROOT}/tmp"

  # --- Generate all passwords ---
  local api_secret
  api_secret="$(generate_password)"
  local api_encryption_key
  api_encryption_key="$(generate_fernet_key)"

  local db_password
  db_password="$(generate_password)"

  local frontend_secret
  frontend_secret="$(generate_password)"

  local engine_secret
  engine_secret="$(generate_password)"

  local profiling_secret
  profiling_secret="$(generate_password)"

  local llm_api_key
  llm_api_key="$(generate_password)"

  local om_db_password
  om_db_password="$(generate_password)"

  local om_token
  om_token="$(generate_password)"

  local keycloak_admin_password
  keycloak_admin_password="$(generate_password)"

  local kong_admin_password
  kong_admin_password="$(generate_password)"

  # --- Build connection strings ---
  local api_db_url="postgresql://postgres:${db_password}@dq-db:5432/dq"
  local kafka_consumer_db_url="postgresql://postgres:${db_password}@dq-db:5432/dq_consumer"
  local om_db_url="postgresql://openmetadata:${om_db_password}@dq-openmetadata-db:5432/openmetadata"

  # --- Apply secrets ---
  apply_secret "dq-api-secrets" \
    "DQ_DB_INTERNAL_URL=${api_db_url}" \
    "API_SECRET_PLACEHOLDER=${api_secret}" \
    "APP_CONFIG_ENCRYPTION_KEY=${api_encryption_key}"

  apply_secret "dq-db-secrets" \
    "POSTGRES_PASSWORD=${db_password}"

  apply_secret "dq-frontend-secrets" \
    "FRONTEND_SECRET_PLACEHOLDER=${frontend_secret}"

  apply_secret "dq-engine-secrets" \
    "ENGINE_SECRET_PLACEHOLDER=${engine_secret}"

  apply_secret "dq-profiling-secrets" \
    "PROFILING_SECRET_PLACEHOLDER=${profiling_secret}"

  apply_secret "dq-llm-secrets" \
    "DQ_LLM_API_KEY=${llm_api_key}"

  apply_secret "dq-kafka-consumer-secrets" \
    "KAFKA_CONSUMER_DB_URL=${kafka_consumer_db_url}"

  apply_secret "dq-openmetadata-db-secrets" \
    "POSTGRES_PASSWORD=${om_db_password}" \
    "POSTGRES_DB=openmetadata"

  # OpenMetadata server needs DB_USER_PASSWORD (same as OM_DB_PASSWORD)
  apply_secret "dq-openmetadata-server-secrets" \
    "OM_TOKEN=${om_token}" \
    "AM_DB_URL=${om_db_url}" \
    "DB_USER_PASSWORD=${om_db_password}"

  apply_secret "dq-keycloak-secrets" \
    "KEYCLOAK_ADMIN_PASSWORD=${keycloak_admin_password}"

  apply_secret "dq-kong-secrets" \
    "KONG_ADMIN_PASSWORD=${kong_admin_password}"

  # --- Apply configmaps ---
  apply_configmap "dq-api-config" \
    "ENVIRONMENT=dev"

  apply_configmap "dq-db-config" \
    "ENVIRONMENT=dev" \
    "POSTGRES_DB=dq" \
    "POSTGRES_USER=postgres"

  apply_configmap "dq-frontend-config" \
    "ENVIRONMENT=dev" \
    "KONG_PUBLIC_URL=https://kong.dev.jac.dot:10443"

  apply_configmap "dq-engine-config" \
    "ENVIRONMENT=dev"

  apply_configmap "dq-profiling-config" \
    "ENVIRONMENT=dev" \
    "KONG_INTERNAL_URL=http://kong.platform-kong.svc.cluster.local:8001"

  apply_configmap "dq-llm-config" \
    "ENVIRONMENT=dev"

  apply_configmap "dq-kafka-consumer-config" \
    "ENVIRONMENT=dev" \
    "KAFKA_BOOTSTRAP_SERVERS=kafka.platform-kafka.svc.cluster.local:9092"

  apply_configmap "dq-openmetadata-db-config" \
    "ENVIRONMENT=dev" \
    "POSTGRES_DB=openmetadata" \
    "POSTGRES_USER=openmetadata"

  # OpenMetadata server needs PostgreSQL DB connection settings
  apply_configmap "dq-openmetadata-server-config" \
    "ENVIRONMENT=dev" \
    "DB_DRIVER_CLASS=org.postgresql.Driver" \
    "DB_SCHEME=postgresql" \
    "DB_HOST=dq-openmetadata-db" \
    "DB_PORT=5432" \
    "OM_DATABASE=openmetadata" \
    "DB_USER=openmetadata"

  # Keycloak-seed job connects to platform-foundation Keycloak
  apply_configmap "dq-keycloak-config" \
    "ENVIRONMENT=dev" \
    "KEYCLOAK_INTERNAL_URL=https://keycloak.dev.jac.dot:10443" \
    "KEYCLOAK_ADMIN_REALM=master"

  # Kong-bootstrap job connects to platform-foundation Kong
  apply_configmap "dq-kong-config" \
    "ENVIRONMENT=dev" \
    "KONG_ADMIN_INTERNAL_URL=https://kong-admin.dev.jac.dot:10443" \
    "DQ_API_INTERNAL_URL=https://dq-api.dev.jac.dot:10443" \
    "KEYCLOAK_REALM=dq-made-easy" \
    "KEYCLOAK_SYSTEM_ADMIN_USERNAME=admin" \
    "DQ_ENGINE_OIDC_CLIENT_ID=dq-engine" \
    "UI_VITE_LOCAL_URL=https://dq-frontend.dev.jac.dot:10443" \
    "UI_NGINX_LOCAL_URL=https://dq-frontend.dev.jac.dot:10443"

  # --- Store credentials ---
  cat > "$CREDENTIALS_FILE" << EOF
# DQ Service Credentials
# Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
# Namespace: ${NAMESPACE}
# ⚠️  DO NOT COMMIT THIS FILE TO GIT

[API]
API_SECRET_PLACEHOLDER=${api_secret}
APP_CONFIG_ENCRYPTION_KEY=${api_encryption_key}
DQ_DB_INTERNAL_URL=${api_db_url}

[Database]
POSTGRES_PASSWORD=${db_password}

[Frontend]
FRONTEND_SECRET_PLACEHOLDER=${frontend_secret}
KONG_PUBLIC_URL=https://kong.dev.jac.dot:10443

[Engine]
ENGINE_SECRET_PLACEHOLDER=${engine_secret}

[Profiling]
PROFILING_SECRET_PLACEHOLDER=${profiling_secret}
KONG_INTERNAL_URL=http://kong.platform-kong.svc.cluster.local:8001

[LLM]
DQ_LLM_API_KEY=${llm_api_key}

[Kafka Consumer]
KAFKA_BOOTSTRAP_SERVERS=kafka.platform-kafka.svc.cluster.local:9092
KAFKA_CONSUMER_DB_URL=${kafka_consumer_db_url}

[OpenMetadata DB]
POSTGRES_PASSWORD=${om_db_password}
POSTGRES_DB=openmetadata

[OpenMetadata Server]
OM_TOKEN=${om_token}
AM_DB_URL=${om_db_url}

[Keycloak Seed]
KEYCLOAK_ADMIN_PASSWORD=${keycloak_admin_password}

[Kong Bootstrap]
KONG_ADMIN_PASSWORD=${kong_admin_password}
EOF

  chmod 600 "$CREDENTIALS_FILE"
  info "Credentials stored in $CREDENTIALS_FILE (mode 600)"
  echo ""
  info "All secrets and configmaps generated successfully"
}

main "$@"
