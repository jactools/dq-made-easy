#!/usr/bin/env bash
# ============================================================================
# deploy.sh — Deploy DQ Made Easy to Kubernetes.
#
# Renders and applies the 4 overlays (shared-dev, dev-api, dev-ui, dev-engine),
# generates secrets and TLS certs, then waits for rollout.
#
# Usage: scripts/k8s/deploy.sh [options]
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPT_NAME="deploy.sh"

NAMESPACE="${NAMESPACE:-dq-made-easy-dev}"
SKIP_SECRETS="${SKIP_SECRETS:-false}"
SKIP_TLS="${SKIP_TLS:-false}"
SKIP_RENDER="${SKIP_RENDER:-false}"
SKIP_ROLLOUT="${SKIP_ROLLOUT:-false}"
DRY_RUN="${DRY_RUN:-false}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-300}"

OVERLAYS=(
  "shared-dev"
  "dev-api"
  "dev-ui"
  "dev-engine"
)

usage() {
  cat <<'EOF'
Usage: ./scripts/k8s/deploy.sh [OPTIONS]

Deploy DQ Made Easy services to Kubernetes.

Options:
  --namespace NS           Target namespace (default: dq-made-easy-dev)
  --skip-secrets           Skip generating service secrets
  --skip-tls               Skip generating TLS secrets
  --skip-render            Skip rendering validation (assumes valid overlays)
  --skip-rollout           Apply without waiting for rollout
  --rollout-timeout N      Rollout timeout in seconds (default: 300)
  --dry-run                Preview only (validate + render, no apply)
  -h, --help               Show this help

Steps:
  1. Validate overlays render (kubectl kustomize)
  2. Generate TLS certs and secrets
  3. Generate service secrets
  4. Apply all overlays via kubectl apply -k
  5. Wait for rollout to complete
EOF
}

log()  { printf '[deploy] %s\n' "$*" >&2; }
info() { printf '[deploy] ✓ %s\n' "$*" >&2; }
warn() { printf '[deploy] ⚠ %s\n' "$*" >&2; }
err()  { printf '[deploy] ✗ %s\n' "$*" >&2; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Missing required command: $1"
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Step 1: Validate overlays render
# ---------------------------------------------------------------------------

validate_overlays() {
  log "Step 1/5: Validating overlays..."
  for overlay in "${OVERLAYS[@]}"; do
    local overlay_dir="${ROOT_DIR}/infra/k8s/overlays/${overlay}"
    if [[ ! -d "$overlay_dir" ]]; then
      err "Overlay directory not found: $overlay_dir"
      exit 1
    fi
    if kubectl kustomize "$overlay_dir" >/dev/null 2>&1; then
      info "Overlay $overlay renders OK"
    else
      err "Overlay $overlay failed to render"
      kubectl kustomize "$overlay_dir" 2>&1
      exit 1
    fi
  done
}

# ---------------------------------------------------------------------------
# Step 2: Generate TLS secrets
# ---------------------------------------------------------------------------

generate_tls() {
  if [[ "$SKIP_TLS" == "true" ]]; then
    log "Step 2/5: Skipping TLS generation (--skip-tls)"
    return 0
  fi

  log "Step 2/5: Generating TLS secrets..."
  local tls_script="${ROOT_DIR}/scripts/generate_tls_secrets.sh"
  if [[ -x "$tls_script" ]]; then
    "$tls_script" --namespace "$NAMESPACE" --force
    info "TLS secrets generated"
  else
    warn "TLS script not found or not executable: $tls_script"
    warn "TLS secrets must be created manually"
  fi
}

# ---------------------------------------------------------------------------
# Step 3: Generate service secrets
# ---------------------------------------------------------------------------

generate_secrets() {
  if [[ "$SKIP_SECRETS" == "true" ]]; then
    log "Step 3/5: Skipping secrets generation (--skip-secrets)"
    return 0
  fi

  log "Step 3/5: Generating service secrets..."
  local secrets_script="${ROOT_DIR}/scripts/generate_secrets.sh"
  if [[ -x "$secrets_script" ]]; then
    "$secrets_script" --namespace "$NAMESPACE" --force
    info "Service secrets generated"
  else
    warn "Secrets script not found or not executable: $secrets_script"
    warn "Secrets must be created manually"
  fi
}

# ---------------------------------------------------------------------------
# Step 4: Apply overlays
# ---------------------------------------------------------------------------

apply_overlays() {
  log "Step 4/5: Applying overlays..."

  if [[ "$DRY_RUN" == "true" ]]; then
    log "Dry-run: previewing manifests..."
    for overlay in "${OVERLAYS[@]}"; do
      local overlay_dir="${ROOT_DIR}/infra/k8s/overlays/${overlay}"
      info "=== $overlay ==="
      kubectl kustomize "$overlay_dir"
    done
    info "Dry-run complete (no changes applied)"
    return 0
  fi

  # Create namespace if needed
  kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true
  info "Namespace $NAMESPACE ready"

  # Apply each overlay
  for overlay in "${OVERLAYS[@]}"; do
    local overlay_dir="${ROOT_DIR}/infra/k8s/overlays/${overlay}"
    if kubectl apply -k "$overlay_dir" 2>/dev/null; then
      info "Overlay $overlay applied"
    else
      err "Overlay $overlay failed to apply"
      exit 1
    fi
  done
}

# ---------------------------------------------------------------------------
# Step 5: Wait for rollout
# ---------------------------------------------------------------------------

wait_for_rollout() {
  if [[ "$SKIP_ROLLOUT" == "true" || "$DRY_RUN" == "true" ]]; then
    log "Step 5/5: Skipping rollout wait"
    return 0
  fi

  log "Step 5/5: Waiting for rollout..."

  local deployments=(
    "dq-api"
    "dq-db"
    "dq-frontend"
    "dq-engine"
    "dq-profiling"
    "dq-llm"
    "dq-kafka-consumer"
    "dq-openmetadata-db"
    "dq-openmetadata-server"
  )

  local failed=false
  for deploy in "${deployments[@]}"; do
    if kubectl rollout status "deployment/$deploy" -n "$NAMESPACE" --timeout="${ROLLOUT_TIMEOUT}s" >/dev/null 2>&1; then
      info "Deployment $deploy rolled out successfully"
    else
      warn "Deployment $deploy failed or timed out (check with kubectl get pods -n $NAMESPACE)"
      failed=true
    fi
  done

  if [[ "$failed" == "true" ]]; then
    warn "Some deployments did not roll out successfully"
    log "Pod status:"
    kubectl get pods -n "$NAMESPACE" 2>/dev/null || true
    return 1
  fi

  info "All deployments rolled out successfully"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --namespace)
        if [[ -z "${2:-}" ]]; then err "--namespace requires a value"; exit 2; fi
        NAMESPACE="$2"; shift 2 ;;
      --skip-secrets) SKIP_SECRETS=true; shift ;;
      --skip-tls) SKIP_TLS=true; shift ;;
      --skip-render) SKIP_RENDER=true; shift ;;
      --skip-rollout) SKIP_ROLLOUT=true; shift ;;
      --rollout-timeout)
        if [[ -z "${2:-}" ]]; then err "--rollout-timeout requires a value"; exit 2; fi
        ROLLOUT_TIMEOUT="$2"; shift 2 ;;
      --dry-run) DRY_RUN=true; shift ;;
      -h|--help) usage; exit 0 ;;
      *) err "Unknown option: $1"; usage; exit 2 ;;
    esac
  done

  require_cmd kubectl
  require_cmd openssl

  echo ""
  info "Deploying DQ Made Easy to namespace $NAMESPACE"
  echo ""

  if [[ "$SKIP_RENDER" != "true" ]]; then
    validate_overlays
  fi
  generate_tls
  generate_secrets
  apply_overlays
  wait_for_rollout

  echo ""
  info "Deployment complete!"
  log "Namespace: $NAMESPACE"
  log "To check status: kubectl get all -n $NAMESPACE"
}

main "$@"
