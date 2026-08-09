#!/usr/bin/env bash
# ============================================================================
# generate_secrets.sh — Generate real secrets for DQ services.
#
# Generates random passwords for all DQ service secrets, applies them to
# the Kubernetes cluster, and stores credentials in tmp/.credentials.
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

Generate random passwords for all DQ service secrets.

Options:
  --namespace NS      Target namespace (default: dq-made-easy-dev)
  --skip-k8s          Skip applying secrets to cluster
  --force             Overwrite existing secrets (default: always generate new)
  --help              Show this help

Secrets created:
  - dq-api-secrets             (API_SECRET_PLACEHOLDER, APP_CONFIG_ENCRYPTION_KEY)
  - dq-db-secrets              (POSTGRES_PASSWORD)
  - dq-frontend-secrets        (FRONTEND_SECRET_PLACEHOLDER)
  - dq-engine-secrets          (ENGINE_SECRET_PLACEHOLDER)
  - dq-profiling-secrets       (PROFILING_SECRET_PLACEHOLDER)
  - dq-llm-secrets             (DQ_LLM_API_KEY)
  - dq-kafka-consumer-secrets  (KAFKA_CONSUMER_DB_URL)
  - dq-openmetadata-db-secrets (OM_DB_PASSWORD)
  - dq-openmetadata-server-secrets (OM_TOKEN)

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

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
  require_cmd openssl
  mkdir -p "${REPO_ROOT}/tmp"

  # --- Generate all passwords ---
  # API
  local api_secret
  api_secret="$(generate_password)"
  local api_encryption_key
  api_encryption_key="$(generate_fernet_key)"

  # Database
  local db_password
  db_password="$(generate_password)"

  # Frontend
  local frontend_secret
  frontend_secret="$(generate_password)"

  # Engine
  local engine_secret
  engine_secret="$(generate_password)"

  # Profiling
  local profiling_secret
  profiling_secret="$(generate_password)"

  # LLM
  local llm_api_key
  llm_api_key="$(generate_password)"

  # Kafka consumer (DB URL for consumer's own state DB)
  # This is a connection string, not a password — placeholder for now
  local kafka_consumer_db_url="postgresql://postgres:${db_password}@dq-db:5432/dq_consumer"

  # OpenMetadata DB
  local om_db_password
  om_db_password="$(generate_password)"

  # OpenMetadata Server
  local om_token
  om_token="$(generate_password)"

  # --- Apply secrets to cluster ---
  # API secrets + DB connection string
  local api_db_url="postgresql://postgres:${db_password}@dq-db:5432/dq"
  apply_secret "dq-api-secrets" \
    "API_SECRET_PLACEHOLDER=${api_secret}" \
    "APP_CONFIG_ENCRYPTION_KEY=${api_encryption_key}" \
    "DQ_DB_INTERNAL_URL=${api_db_url}"

  # Kafka consumer needs DB URL for its own state + bootstrap servers
  apply_secret "dq-kafka-consumer-secrets" \
    "KAFKA_CONSUMER_DB_URL=${kafka_consumer_db_url}" \
    "KAFKA_BOOTSTRAP_SERVERS=kafka.platform-kafka.svc.cluster.local:9092"

  # OpenMetadata DB also needs POSTGRES_PASSWORD for the postgres image
  apply_secret "dq-openmetadata-db-secrets" \
    "OM_DB_PASSWORD=${om_db_password}" \
    "POSTGRES_PASSWORD=${om_db_password}" \
    "POSTGRES_DB=openmetadata"

  # OpenMetadata server needs DB connection string
  local om_db_url="mysql://openmetadata:${om_db_password}@dq-openmetadata-db:3306/openmetadata"
  apply_secret "dq-openmetadata-server-secrets" \
    "OM_TOKEN=${om_token}" \
    "AM_DB_URL=${om_db_url}"

  apply_secret "dq-db-secrets" \
    "POSTGRES_PASSWORD=${db_password}"

  apply_secret "dq-frontend-secrets" \
    "FRONTEND_SECRET_PLACEHOLDER=${frontend_secret}"

  # Frontend also needs KONG_PUBLIC_URL (configmap-level, not secret)
  # Handled by deploy.sh or env file

  apply_secret "dq-engine-secrets" \
    "ENGINE_SECRET_PLACEHOLDER=${engine_secret}"

  apply_secret "dq-llm-secrets" \
    "DQ_LLM_API_KEY=${llm_api_key}"

  # --- Store credentials ---
  cat > "$CREDENTIALS_FILE" << EOF
# DQ Service Credentials
# Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
# Namespace: ${NAMESPACE}
# ⚠️  DO NOT COMMIT THIS FILE TO GIT

[API]
API_SECRET_PLACEHOLDER=${api_secret}
APP_CONFIG_ENCRYPTION_KEY=${api_encryption_key}

[Database]
POSTGRES_PASSWORD=${db_password}
connection_string=postgresql://postgres:${db_password}@dq-db.${NAMESPACE}.svc.cluster.local:5432/dq

[Frontend]
FRONTEND_SECRET_PLACEHOLDER=${frontend_secret}

[Engine]
ENGINE_SECRET_PLACEHOLDER=${engine_secret}

[Profiling]
PROFILING_SECRET_PLACEHOLDER=${profiling_secret}

[LLM]
DQ_LLM_API_KEY=${llm_api_key}

[Kafka Consumer]
KAFKA_CONSUMER_DB_URL=${kafka_consumer_db_url}

[OpenMetadata DB]
OM_DB_PASSWORD=${om_db_password}

[OpenMetadata Server]
OM_TOKEN=${om_token}
EOF

  chmod 600 "$CREDENTIALS_FILE"
  info "Credentials stored in $CREDENTIALS_FILE (mode 600)"
  echo ""
  info "All secrets generated successfully"
}

main "$@"
