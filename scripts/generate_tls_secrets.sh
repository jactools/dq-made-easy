#!/usr/bin/env bash
# ============================================================================
# generate_tls_secrets.sh — Generate TLS certificates and K8s secrets for DQ.
#
# Generates self-signed TLS certificates for DQ Ingress hostnames using the
# platform's shared root CA, then creates Kubernetes TLS Secrets in the
# target namespace.
#
# Usage: scripts/generate_tls_secrets.sh [options]
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Paths to platform root CA (shared across all tenants)
PLATFORM_ROOT="${PLATFORM_ROOT:-/Users/jacbeekers/gitrepos/platform-foundation}"
CA_KEY="${PLATFORM_ROOT}/certs/mkcert-rootCA-key.pem"
CA_CERT="${PLATFORM_ROOT}/certs/mkcert-rootCA.pem"

# DQ certificate output
CERTS_DIR="${REPO_ROOT}/certs"
NAMESPACE="${NAMESPACE:-dq-made-easy-dev}"
APPLY_K8S="${APPLY_K8S:-true}"

# DNS names → secret name mapping
# Format: "dns_name:secret_name"
# Note: keycloak.dev.jac.dot is owned by the platform — DQ accesses it via
# internal service name or Kong routes, not its own Ingress.
declare -a TLS_ENTRIES=(
  "dq-made-easy.dev.jac.dot:dq-dev-tls-cert"
  "openmetadata.dev.jac.dot:dq-dev-openmetadata-tls-cert"
)

usage() {
  cat <<'USAGE'
Usage: scripts/generate_tls_secrets.sh [options]

Generate TLS certificates and Kubernetes secrets for DQ Ingresses.

Options:
  --namespace NS       Target namespace (default: dq-made-easy-dev)
  --platform-root PATH Path to platform-foundation root (for shared CA)
  --skip-k8s           Skip applying secrets to cluster
  --force              Regenerate all certificates
  --help               Show this help

Secrets created in namespace:
  - dq-dev-tls-cert             (dq-made-easy.dev.jac.dot)
  - dq-dev-openmetadata-tls-cert (openmetadata.dev.jac.dot)

Note: keycloak.dev.jac.dot is a platform-owned hostname — the platform
manages its TLS secret (platform-keycloak-tls in platform-keycloak ns).
USAGE
}

log()  { printf '[dq-tls] %s\n' "$*" >&2; }
info() { printf '[dq-tls] ✓ %s\n' "$*" >&2; }
err()  { printf '[dq-tls] ✗ %s\n' "$*" >&2; }
warn() { printf '[dq-tls] ⚠ %s\n' "$*" >&2; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Missing required command: $1"
    exit 1
  fi
}

get_kind_node_ip() {
  if command -v kind >/dev/null 2>&1 && command -v docker >/dev/null 2>&1; then
    local cluster_name="${KIND_CLUSTER_NAME:-platform-dev}"
    local container_name="${cluster_name}-control-plane"
    docker inspect --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$container_name" 2>/dev/null || echo ""
  else
    echo ""
  fi
}

generate_cert() {
  local dns_name="$1"
  local cert_file="${CERTS_DIR}/${dns_name}.pem"
  local key_file="${CERTS_DIR}/${dns_name}-key.pem"

  if [[ -f "$cert_file" && -f "$key_file" ]]; then
    info "Certificate for $dns_name already exists (use --force to regenerate)"
    return 0
  fi

  local kind_ip
  kind_ip="$(get_kind_node_ip)"

  # Build SAN list: DNS name + localhost + kind node IP
  local sans="DNS:${dns_name},DNS:localhost,IP:127.0.0.1"
  if [[ -n "$kind_ip" ]]; then
    sans="${sans},IP:${kind_ip}"
  fi

  log "Generating certificate for $dns_name..."

  openssl genrsa -out "$key_file" 2048 2>/dev/null

  openssl req -new \
    -key "$key_file" \
    -out "${CERTS_DIR}/${dns_name}.csr" \
    -subj "/C=NL/ST=North Holland/O=Platform Foundation/CN=${dns_name}" \
    -addext "subjectAltName=${sans}" \
    2>/dev/null

  openssl x509 -req \
    -in "${CERTS_DIR}/${dns_name}.csr" \
    -CA "$CA_CERT" \
    -CAkey "$CA_KEY" \
    -CAcreateserial \
    -out "$cert_file" \
    -days 730 \
    -copy_extensions copyall \
    2>/dev/null

  rm -f "${CERTS_DIR}/${dns_name}.csr"
  info "Certificate generated for $dns_name"
}

create_tls_secret() {
  local dns_name="$1"
  local secret_name="$2"
  local cert_file="${CERTS_DIR}/${dns_name}.pem"
  local key_file="${CERTS_DIR}/${dns_name}-key.pem"

  if [[ ! -f "$cert_file" || ! -f "$key_file" ]]; then
    err "Certificate files not found for $dns_name — skipping secret creation"
    return 1
  fi

  if [[ "$APPLY_K8S" != "true" ]]; then
    log "Skipping K8s secret creation for $secret_name (--skip-k8s)"
    return 0
  fi

  kubectl create secret tls "$secret_name" \
    --cert="$cert_file" \
    --key="$key_file" \
    -n "$NAMESPACE" \
    --dry-run=client -o yaml \
    | kubectl apply -f - 2>/dev/null && \
    info "TLS secret $secret_name created in $NAMESPACE" || \
    warn "Could not create TLS secret $secret_name (cluster may not be running)"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
  local force=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --namespace)
        if [[ -z "${2:-}" ]]; then err "--namespace requires a value"; exit 2; fi
        NAMESPACE="$2"; shift 2 ;;
      --platform-root)
        if [[ -z "${2:-}" ]]; then err "--platform-root requires a path"; exit 2; fi
        PLATFORM_ROOT="$2"
        CA_KEY="${PLATFORM_ROOT}/certs/mkcert-rootCA-key.pem"
        CA_CERT="${PLATFORM_ROOT}/certs/mkcert-rootCA.pem"
        shift 2 ;;
      --skip-k8s) APPLY_K8S=false; shift ;;
      --force) force=true; shift ;;
      --help) usage; exit 0 ;;
      *) err "Unknown option: $1"; usage; exit 2 ;;
    esac
  done

  require_cmd openssl
  mkdir -p "$CERTS_DIR"

  # Verify root CA exists
  if [[ ! -f "$CA_KEY" || ! -f "$CA_CERT" ]]; then
    err "Platform root CA not found at $PLATFORM_ROOT/certs/"
    err "Run 'scripts/generate_dev_certs.sh' in platform-foundation first."
    exit 1
  fi

  # Generate certificates for each DNS name
  for entry in "${TLS_ENTRIES[@]}"; do
    local dns_name="${entry%%:*}"
    local secret_name="${entry##*:}"

    if [[ "$force" == true ]]; then
      rm -f "${CERTS_DIR}/${dns_name}.pem" "${CERTS_DIR}/${dns_name}-key.pem"
    fi

    generate_cert "$dns_name"
    create_tls_secret "$dns_name" "$secret_name"
  done

  echo ""
  info "All TLS certificates generated in $CERTS_DIR"
  echo ""
  log "To trust the root CA locally:"
  echo "  $PLATFORM_ROOT/certs/mkcert-rootCA.pem"
}

main "$@"
