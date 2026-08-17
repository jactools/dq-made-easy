#!/usr/bin/env bash
# scripts/run_validation_job.sh
#
# Purpose: Run a validation script as a K8s Job inside the Kind cluster.
#
# Usage:
#   scripts/run_validation_job.sh validate_user_login_end_to_end.sh [--env dev|test|prod]
#
# Requires:
# - kind and kubectl in PATH
# - Kind cluster running
# - dq-validation Job deployed via Flux

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="run_validation_job.sh"

print_usage() {
  cat <<'EOF'
Usage: scripts/run_validation_job.sh <validation_script> [--env dev|test|prod]

Runs a validation script as a K8s Job inside the Kind cluster.

Arguments:
  validation_script    Name of the validation script (e.g. validate_user_login_end_to_end.sh)

Options:
  --env dev|test|prod  Environment to use (default: dev)
  -h, --help           Show this help

Examples:
  scripts/run_validation_job.sh validate_user_login_end_to_end.sh
  scripts/run_validation_job.sh validate_user_login_end_to_end.sh --env test
EOF
}

main() {
  local script_name=""
  local env="dev"

  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    print_usage
    exit 0
  fi

  if [[ -z "${1:-}" ]]; then
    error "$my_name" "validation script name is required"
    print_usage >&2
    exit 2
  fi

  script_name="$1"
  shift

  # Parse options
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --env)
        env="$2"
        shift 2
        ;;
      *)
        error "$my_name" "Unknown option: $1"
        exit 2
        ;;
    esac
  done

  init_root_env_file "$ROOT_DIR"

  # Get Kind cluster name from env
  local cluster_name
  case "$env" in
    dev)  cluster_name="platform-dev" ;;
    test) cluster_name="platform-test" ;;
    prod) cluster_name="platform-prod" ;;
    *)    error "$my_name" "Unknown environment: $env"; exit 1 ;;
  esac

  local namespace="dq-${env}"
  # Replace underscores with dashes for valid K8s names
  local safe_name="${script_name//_/}"
  local job_name="validate-${safe_name%.sh}"

  # Get kubeconfig from Kind cluster
  local kubeconfig_path="/tmp/kind-${cluster_name}.conf"
  kind get kubeconfig --name "$cluster_name" > "$kubeconfig_path"

  # Run kubectl with cluster's kubeconfig
  _run_kubectl() {
    KUBECONFIG="$kubeconfig_path" kubectl "$@"
  }

  # Create env ConfigMap if not present
  local env_cm="dq-env-${env}"
  local env_file="$ROOT_DIR/.env.${env}.local"
  if [[ ! -f "$env_file" ]]; then
    error "$my_name" "Env file not found: $env_file"
    exit 1
  fi
  _run_kubectl create configmap "$env_cm" \
    --from-file=".env.${env}.local=$env_file" \
    -n "$namespace" --dry-run=client -o yaml | _run_kubectl apply -f -

  info "$my_name" "Running $script_name as Job $job_name in namespace $namespace"

  # Delete existing job if present
  _run_kubectl delete job "$job_name" -n "$namespace" --ignore-not-found=true 2>/dev/null || true
  sleep 1

  # Run the validation job (kustomize + sed to rename)
  local patched_yaml
  patched_yaml=$(mktemp)
  kubectl kustomize "$ROOT_DIR/infra/k8s/base/shared/jobs" 2>/dev/null | \
    sed "s|name: dq-validation|name: $job_name|g" > "$patched_yaml"
  _run_kubectl apply -n "$namespace" -f "$patched_yaml"
  rm -f "$patched_yaml"

  # Wait for completion
  info "$my_name" "Waiting for Job $job_name to complete..."
  if ! _run_kubectl wait "job/$job_name" --for=condition=complete -n "$namespace" --timeout=300s; then
    error "$my_name" "Job $job_name failed or timed out"
    local job_pod
    job_pod=$(_run_kubectl get pods -n "$namespace" -l job-name="$job_name" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
    if [[ -n "$job_pod" ]]; then
      _run_kubectl logs pod/"$job_pod" -n "$namespace"
    fi
    _run_kubectl delete job "$job_name" -n "$namespace" --ignore-not-found=true
    exit 1
  fi

  # Stream logs
  info "$my_name" "Validation completed successfully"
  local job_pod
  job_pod=$(_run_kubectl get pods -n "$namespace" -l job-name="$job_name" -o jsonpath='{.items[0].metadata.name}')
  _run_kubectl logs pod/"$job_pod" -n "$namespace"

  # Cleanup
  _run_kubectl delete job "$job_name" -n "$namespace" --ignore-not-found=true
}

main "$@"
