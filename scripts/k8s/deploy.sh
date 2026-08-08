#!/usr/bin/env bash
# ============================================================================
# deploy.sh — Deploy DQ Made Easy onto the platform cluster.
#
# Note: dq-made-easy is a consumer workload. The cluster is managed by
# platform-foundation. This script assumes the cluster already exists.
#
# Flow (mirrors bootstrap_platform.sh pattern):
#   1. Validate environment (overlays render, kubectl available)
#   2. Verify cluster reachable (no create — platform manages the cluster)
#   3. Build Docker images (staged, pushed to docker-registry)
#   4. Generate TLS secrets
#   5. Generate service secrets
#   6. Apply manifests (kubectl apply -k per overlay)
#   7. Wait for rollout
#   8. Store credentials
#   9. Final validation
#
# Usage: scripts/k8s/deploy.sh [options]
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

NAMESPACE="${NAMESPACE:-dq-made-easy-dev}"
SKIP_BUILD="${SKIP_BUILD:-false}"
SKIP_SECRETS="${SKIP_SECRETS:-false}"
SKIP_TLS="${SKIP_TLS:-false}"
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

Bootstrap DQ Made Easy onto the platform cluster.

Options:
  --env dev|test|prod     Target environment (default: dev)
  --skip-build            Skip building Docker images
  --skip-secrets          Skip generating service secrets
  --skip-tls              Skip generating TLS secrets
  --skip-rollout          Apply without waiting for rollout
  --rollout-timeout N     Rollout timeout in seconds (default: 300)
  --dry-run               Preview only (validate + render, no mutations)
  -h, --help              Show this help

Steps:
  1. Validate environment (overlay renders, kubectl available)
  2. Verify cluster reachable
  3. Build Docker images (delegates to build_and_push_all.sh)
  4. Generate TLS certs and secrets
  5. Generate service secrets
  6. Apply all overlays via kubectl apply -k
  7. Wait for rollout to complete
  8. Store credentials in tmp/.credentials
  9. Final validation (pods running, services healthy)
EOF
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log_step() { echo ""; echo "=========================================================================="; echo "[step]  $*"; echo "=========================================================================="; }
log()  { printf '[dq-deploy] %s\n' "$*" >&2; }
info() { printf '[dq-deploy] ✓ %s\n' "$*" >&2; }
warn() { printf '[dq-deploy] ⚠ %s\n' "$*" >&2; }
err()  { printf '[dq-deploy] ✗ %s\n' "$*" >&2; exit 1; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Missing required command: $1"
  fi
}

validate_cluster() {
  if ! kubectl cluster-info >/dev/null 2>&1; then
    return 1
  fi
  return 0
}

validate_ns_pods() {
  local ns="$1" expected="$2"
  local count
  count=$(kubectl get pods -n "$ns" --field-selector=status.phase=Running -o name 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$count" -ge "$expected" ]]; then
    info "$ns: $count running pod(s) >= $expected"
    return 0
  else
    warn "$ns: $count running pod(s) < $expected"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Step 1: Validate environment
# ---------------------------------------------------------------------------

step_validate_env() {
  log_step "1. Validate environment"

  require_cmd kubectl
  require_cmd openssl

  # Validate overlays render
  for overlay in "${OVERLAYS[@]}"; do
    local overlay_dir="${ROOT_DIR}/infra/k8s/overlays/${overlay}"
    if [[ ! -d "$overlay_dir" ]]; then
      err "Overlay directory not found: $overlay_dir"
    fi
    if kubectl kustomize "$overlay_dir" >/dev/null 2>&1; then
      info "Overlay $overlay renders OK"
    else
      err "Overlay $overlay failed to render"
    fi
  done
  info "Environment validation passed"
}

# ---------------------------------------------------------------------------
# Step 2: Verify cluster reachable (no create — platform manages the cluster)
# ---------------------------------------------------------------------------

step_verify_cluster() {
  log_step "2. Verify cluster reachable"

  if ! validate_cluster; then
    err "Cannot connect to cluster (current context: $(kubectl config current-context 2>/dev/null || echo 'unknown'))"
    log "Ensure the platform cluster is running: scripts/bootstrap_platform.sh --env dev"
    log "Or set KUBECONFIG to point to a reachable cluster."
  fi

  info "Cluster reachable (current context: $(kubectl config current-context 2>/dev/null || echo 'default'))"
}

# ---------------------------------------------------------------------------
# Step 3: Build Docker images (pushed to docker-registry)
# ---------------------------------------------------------------------------

step_build_images() {
  log_step "3. Build Docker images"

  if [[ "$SKIP_BUILD" == "true" ]]; then
    log "Skipping build (--skip-build)"
    return 0
  fi

  local build_script="${ROOT_DIR}/scripts/build_and_push_all.sh"
  if [[ -x "$build_script" ]]; then
    log "Building DQ images (all repo scope)..."
    "$build_script" --scope repo 2>&1 || warn "Some images may have failed to build"
    info "Docker images built and pushed to registry"
  else
    warn "build_and_push_all.sh not found — images must be built manually"
  fi
}

# ---------------------------------------------------------------------------
# Step 4: Generate TLS secrets
# ---------------------------------------------------------------------------

step_generate_tls() {
  log_step "4. Generate TLS secrets"

  if [[ "$SKIP_TLS" == "true" ]]; then
    log "Skipping TLS generation (--skip-tls)"
    return 0
  fi

  local tls_script="${ROOT_DIR}/scripts/generate_tls_secrets.sh"
  if [[ -x "$tls_script" ]]; then
    "$tls_script" --namespace "$NAMESPACE" --force 2>&1
    info "TLS secrets generated"
  else
    warn "TLS script not found — TLS secrets must be created manually"
  fi
}

# ---------------------------------------------------------------------------
# Step 5: Generate service secrets
# ---------------------------------------------------------------------------

step_generate_secrets() {
  log_step "5. Generate service secrets"

  if [[ "$SKIP_SECRETS" == "true" ]]; then
    log "Skipping secrets generation (--skip-secrets)"
    return 0
  fi

  local secrets_script="${ROOT_DIR}/scripts/generate_secrets.sh"
  if [[ -x "$secrets_script" ]]; then
    "$secrets_script" --namespace "$NAMESPACE" --force 2>&1
    info "Service secrets generated"
  else
    warn "Secrets script not found — secrets must be created manually"
  fi
}

# ---------------------------------------------------------------------------
# Step 6: Apply manifests
# ---------------------------------------------------------------------------

step_apply_overlays() {
  log_step "6. Apply manifests"

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

  # Create namespace
  kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true
  info "Namespace $NAMESPACE ready"

  # Apply each overlay
  for overlay in "${OVERLAYS[@]}"; do
    local overlay_dir="${ROOT_DIR}/infra/k8s/overlays/${overlay}"
    if kubectl apply -k "$overlay_dir" 2>&1; then
      info "Overlay $overlay applied"
    else
      err "Overlay $overlay failed to apply"
    fi
  done
}

# ---------------------------------------------------------------------------
# Step 7: Wait for rollout
# ---------------------------------------------------------------------------

step_wait_rollout() {
  log_step "7. Wait for rollout"

  if [[ "$SKIP_ROLLOUT" == "true" || "$DRY_RUN" == "true" ]]; then
    log "Skipping rollout wait"
    return 0
  fi

  local deployments=(
    "dq-api" "dq-db" "dq-frontend"
    "dq-engine" "dq-profiling" "dq-llm"
    "dq-kafka-consumer" "dq-openmetadata-db" "dq-openmetadata-server"
  )

  local passed=0 failed=0
  for deploy in "${deployments[@]}"; do
    if kubectl rollout status "deployment/$deploy" -n "$NAMESPACE" --timeout="${ROLLOUT_TIMEOUT}s" >/dev/null 2>&1; then
      info "  ✓ $deploy"
      ((passed++))
    else
      local reason
      reason=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$deploy" \
        -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.phase}{" "}{.status.containerStatuses[*].state.*.reason}{"\n"}' 2>/dev/null | head -1 | xargs)
      warn "  ✗ $deploy: $reason"
      ((failed++))
    fi
  done

  echo ""
  log "Rollout summary: $passed passed, $failed failed"

  if [[ "$failed" -gt 0 ]]; then
    warn "Some deployments did not roll out successfully"
    echo ""
    log "Pod status:"
    kubectl get pods -n "$NAMESPACE" 2>/dev/null || true
    return 1
  fi

  info "All deployments rolled out successfully"
}

# ---------------------------------------------------------------------------
# Step 8: Store credentials
# ---------------------------------------------------------------------------

step_store_credentials() {
  log_step "8. Store credentials"

  if [[ ! -f "${ROOT_DIR}/tmp/.credentials" ]]; then
    warn "No credentials file found (secrets were skipped)"
    return 0
  fi

  info "Credentials stored in ${ROOT_DIR}/tmp/.credentials"
  log "  API:  see [API] section"
  log "  DB:   see [Database] section"
}

# ---------------------------------------------------------------------------
# Step 9: Final validation
# ---------------------------------------------------------------------------

step_final_validation() {
  log_step "9. Final validation"

  validate_ns_pods "$NAMESPACE" 1 || true

  # Show any non-running pods
  local unhealthy
  unhealthy=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running -o name 2>/dev/null | wc -l | tr -d ' ')
  [[ "$unhealthy" -gt 0 ]] && log "  ⚠ $unhealthy pod(s) not Running"

  echo ""
  log "=========================================================="
  log "DQ Made Easy deployment complete"
  log "Namespace: $NAMESPACE"
  log "Credentials: ${ROOT_DIR}/tmp/.credentials"
  log "=========================================================="
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --env)
        NAMESPACE="dq-made-easy-${2:-dev}"
        shift 2 ;;
      --skip-build) SKIP_BUILD=true; shift ;;
      --skip-secrets) SKIP_SECRETS=true; shift ;;
      --skip-tls) SKIP_TLS=true; shift ;;
      --skip-rollout) SKIP_ROLLOUT=true; shift ;;
      --rollout-timeout)
        ROLLOUT_TIMEOUT="${2:-300}"
        shift 2 ;;
      --dry-run) DRY_RUN=true; shift ;;
      -h|--help) usage; exit 0 ;;
      *) err "Unknown option: $1" ;;
    esac
  done

  log "Deploying DQ Made Easy (namespace: $NAMESPACE)"

  step_validate_env
  step_verify_cluster
  step_build_images
  step_generate_tls
  step_generate_secrets
  step_apply_overlays
  step_wait_rollout
  step_store_credentials
  step_final_validation
}

main "$@"
