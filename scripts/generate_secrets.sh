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
ROTATE_PASSWORDS=false

usage() {
  cat <<'USAGE'
Usage: scripts/generate_secrets.sh [options]

Generate secrets and configmaps for all DQ services.

Options:
  --namespace NS      Target namespace (default: dq-made-easy-dev)
  --skip-k8s          Skip applying to cluster
  --rotate            Generate NEW passwords and rotate them in the database
  --help              Show this help

Behavior:
  By default, passwords are generated ONCE and reused on subsequent runs.
  Use --rotate to generate new passwords and update the running database.

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
# Password rotation
# ---------------------------------------------------------------------------

rotate_postgres_password() {
  local secret_name="$1"
  local new_password="$2"
  local user="$3"
  local db="$4"
  local host="$5"

  local old_password
  old_password="$(kubectl get secret "$secret_name" -n "$NAMESPACE" -o jsonpath='{.data.POSTGRES_PASSWORD}' 2>/dev/null | base64 -d || true)"

  if [ -z "$old_password" ]; then
    warn "Could not read old password from $secret_name; skipping rotation"
    return 0
  fi

  if [ "$old_password" = "$new_password" ]; then
    log "Password unchanged for $secret_name; skipping rotation"
    return 0
  fi

  log "Rotating password for $secret_name (user=$user, db=$db)"
  PGPASSWORD="$old_password" psql -h "$host" -U "$user" -d "$db" \
    -c "ALTER USER $user WITH PASSWORD '$new_password';" || \
    warn "Could not rotate password in database $host/$db (may not be running)"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
  require_cmd openssl
  mkdir -p "${REPO_ROOT}/tmp"

  # Parse arguments
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --namespace)
        NAMESPACE="$2"
        shift 2
        ;;
      --skip-k8s)
        APPLY_K8S=false
        shift
        ;;
      --rotate)
        ROTATE_PASSWORDS=true
        shift
        ;;
      --help)
        usage
        exit 0
        ;;
      *)
        warn "Unknown option: $1"
        usage
        exit 1
        ;;
    esac
  done

  # --- Generate all passwords ---
  # Preserve existing passwords unless --rotate is passed
  local api_secret
  api_secret="$(generate_password)"
  local api_encryption_key
  api_encryption_key="$(generate_fernet_key)"

  # DB passwords: preserve unless --rotate
  local db_password
  local existing_db_password
  existing_db_password="$(kubectl get secret dq-db-secrets -n "$NAMESPACE" -o jsonpath='{.data.POSTGRES_PASSWORD}' 2>/dev/null | base64 -d || true)"
  if [ "$ROTATE_PASSWORDS" = true ] || [ -z "$existing_db_password" ]; then
    db_password="$(generate_password)"
    log "${ROTATE_PASSWORDS:+Rotated} new DB password"
  else
    db_password="$existing_db_password"
    log "Reusing existing DB password (use --rotate to change)"
  fi

  local frontend_secret
  frontend_secret="$(generate_password)"

  local engine_secret
  engine_secret="$(generate_password)"

  local profiling_secret
  profiling_secret="$(generate_password)"

  local llm_api_key
  llm_api_key="$(generate_password)"

  # OpenMetadata DB password: preserve unless --rotate
  local om_db_password
  local existing_om_db_password
  existing_om_db_password="$(kubectl get secret dq-openmetadata-db-secrets -n "$NAMESPACE" -o jsonpath='{.data.POSTGRES_PASSWORD}' 2>/dev/null | base64 -d || true)"
  if [ "$ROTATE_PASSWORDS" = true ] || [ -z "$existing_om_db_password" ]; then
    om_db_password="$(generate_password)"
    log "${ROTATE_PASSWORDS:+Rotated} new OpenMetadata DB password"
  else
    om_db_password="$existing_om_db_password"
    log "Reusing existing OpenMetadata DB password (use --rotate to change)"
  fi

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
    "KONG_PUBLIC_URL=https://kong.dev.jac.dot:10443" \
    "KONG_SERVICE_FQDN=kong.dev.jac.dot" \
    "SSL_VERIFY=on"

  apply_configmap "dq-engine-config" \
    "ENVIRONMENT=dev"

  apply_configmap "dq-profiling-config" \
    "ENVIRONMENT=dev" \
    "KONG_INTERNAL_URL=http://kong.platform-kong.svc.cluster.local:8001"

  apply_configmap "dq-llm-config" \
    "ENVIRONMENT=dev"

  apply_configmap "dq-kafka-consumer-config" \
    "ENVIRONMENT=dev" \
    "KAFKA_BOOTSTRAP_SERVERS=kafka.platform-kafka.svc.cluster.local:9092" \
    "KAFKA_TOPIC=dq-made-easy.gx.violations"

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
    "KEYCLOAK_INTERNAL_URL=https://keycloak.platform-keycloak.svc.cluster.local:8443" \
    "KEYCLOAK_ADMIN_REALM=master"

  # Kong-bootstrap job connects to platform-foundation Kong
  apply_configmap "dq-kong-config" \
    "ENVIRONMENT=dev" \
    "KONG_ADMIN_INTERNAL_URL=https://kong-admin.platform-kong.svc.cluster.local:8444" \
    "DQ_API_INTERNAL_URL=https://dq-api.dev.jac.dot:10443" \
    "KEYCLOAK_REALM=dq-made-easy" \
    "KEYCLOAK_SYSTEM_ADMIN_USERNAME=admin" \
    "DQ_ENGINE_OIDC_CLIENT_ID=dq-engine" \
    "UI_VITE_LOCAL_URL=https://dq-frontend.dev.jac.dot:10443" \
    "UI_NGINX_LOCAL_URL=https://dq-frontend.dev.jac.dot:10443"

  # --- Rotate database passwords (if --rotate was passed) ---
  if [ "$ROTATE_PASSWORDS" = true ]; then
    log "Rotating database passwords..."
    rotate_postgres_password "dq-db-secrets" "$db_password" "postgres" "dq" "dq-db"
    rotate_postgres_password "dq-openmetadata-db-secrets" "$om_db_password" "openmetadata" "openmetadata" "dq-openmetadata-db"
    log "Password rotation complete"
  fi

  # --- Apply platform CA bundle ConfigMap ---
  local CA_BUNDLE_PATH="${REPO_ROOT}/../platform-foundation/tmp/certs/mkcert-rootCA.pem"
  if [ -f "$CA_BUNDLE_PATH" ]; then
    kubectl create configmap dq-platform-ca-bundle \
      --from-file=ca-bundle.pem="$CA_BUNDLE_PATH" \
      --dry-run=client -o yaml \
      | kubectl apply -f - -n "$NAMESPACE" 2>/dev/null && \
      info "ConfigMap dq-platform-ca-bundle applied to $NAMESPACE" || \
      warn "Could not apply configmap dq-platform-ca-bundle (cluster may not be running)"
  else
    warn "Platform CA bundle not found at $CA_BUNDLE_PATH; skipping"
  fi

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
