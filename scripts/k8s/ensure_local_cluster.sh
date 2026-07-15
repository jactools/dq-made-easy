#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_NAME="ensure_local_cluster.sh"

source "$ROOT_DIR/scripts/supporting/logging.sh"

set_log_level INFO

CLUSTER_RUNTIME="auto"
CLUSTER_NAME="dq-made-easy"
KIND_IMAGE=""
MINIKUBE_DRIVER=""
KUBERNETES_VERSION=""

usage() {
  cat <<'EOF'
Usage: ./scripts/k8s/ensure_local_cluster.sh [OPTIONS]

Ensure a local dq-made-easy Kubernetes cluster exists and is selected.

Options:
  --cluster-runtime kind|minikube|auto
                           Runtime to ensure (default: auto; prefers existing cluster,
                           otherwise prefers kind when available)
  --cluster-name NAME      Cluster/profile name to check or create (default: dq-made-easy)
  --kind-image IMAGE       Optional kind node image (example: kindest/node:v1.30.0)
  --driver DRIVER          Optional minikube driver
  --kubernetes-version V   Optional Kubernetes version for minikube (example: v1.30.0)
  -h, --help               Show this help

Examples:
  ./scripts/k8s/ensure_local_cluster.sh
  ./scripts/k8s/ensure_local_cluster.sh --cluster-runtime kind
  ./scripts/k8s/ensure_local_cluster.sh --cluster-runtime minikube --driver docker
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cluster-runtime)
      CLUSTER_RUNTIME="${2:-}"
      shift 2
      ;;
    --cluster-name)
      CLUSTER_NAME="${2:-}"
      shift 2
      ;;
    --kind-image)
      KIND_IMAGE="${2:-}"
      shift 2
      ;;
    --driver)
      MINIKUBE_DRIVER="${2:-}"
      shift 2
      ;;
    --kubernetes-version)
      KUBERNETES_VERSION="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      error "$SCRIPT_NAME" "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

case "$CLUSTER_RUNTIME" in
  auto|kind|minikube) ;;
  *)
    error "$SCRIPT_NAME" "Unsupported --cluster-runtime value: $CLUSTER_RUNTIME"
    exit 1
    ;;
esac

if [[ -z "$CLUSTER_NAME" ]]; then
  error "$SCRIPT_NAME" "--cluster-name cannot be empty"
  exit 1
fi

kind_cluster_exists() {
  command -v kind >/dev/null 2>&1 || return 1
  kind get clusters 2>/dev/null | grep -Fx "$CLUSTER_NAME" >/dev/null 2>&1
}

minikube_cluster_exists() {
  command -v minikube >/dev/null 2>&1 || return 1
  minikube status --profile "$CLUSTER_NAME" >/dev/null 2>&1
}

detect_runtime() {
  if [[ "$CLUSTER_RUNTIME" != "auto" ]]; then
    printf '%s' "$CLUSTER_RUNTIME"
    return 0
  fi

  if kind_cluster_exists; then
    printf '%s' "kind"
    return 0
  fi

  if minikube_cluster_exists; then
    printf '%s' "minikube"
    return 0
  fi

  if command -v kind >/dev/null 2>&1; then
    printf '%s' "kind"
    return 0
  fi

  if command -v minikube >/dev/null 2>&1; then
    printf '%s' "minikube"
    return 0
  fi

  return 1
}

ensure_kind_cluster() {
  local context_name="kind-${CLUSTER_NAME}"
  local create_args=(create cluster --name "$CLUSTER_NAME")

  if ! command -v kind >/dev/null 2>&1; then
    error "$SCRIPT_NAME" "kind CLI is required for --cluster-runtime kind"
    exit 1
  fi
  if ! command -v kubectl >/dev/null 2>&1; then
    error "$SCRIPT_NAME" "kubectl is required for kind cluster management"
    exit 1
  fi

  if kind_cluster_exists; then
    info "$SCRIPT_NAME" "kind cluster already exists: $CLUSTER_NAME"
  else
    if [[ -n "$KIND_IMAGE" ]]; then
      create_args+=(--image "$KIND_IMAGE")
    fi
    info "$SCRIPT_NAME" "Creating kind cluster: $CLUSTER_NAME"
    kind "${create_args[@]}"
  fi

  kubectl config use-context "$context_name" >/dev/null 2>&1 || true
  success "$SCRIPT_NAME" "kind cluster ready: $CLUSTER_NAME (context: $context_name)"
}

ensure_minikube_cluster() {
  local start_args=(start --profile "$CLUSTER_NAME")

  if ! command -v minikube >/dev/null 2>&1; then
    error "$SCRIPT_NAME" "minikube CLI is required for --cluster-runtime minikube"
    exit 1
  fi
  if ! command -v kubectl >/dev/null 2>&1; then
    error "$SCRIPT_NAME" "kubectl is required for minikube cluster management"
    exit 1
  fi

  if minikube_cluster_exists; then
    info "$SCRIPT_NAME" "minikube profile already exists: $CLUSTER_NAME"
  else
    if [[ -n "$MINIKUBE_DRIVER" ]]; then
      start_args+=(--driver "$MINIKUBE_DRIVER")
    fi
    if [[ -n "$KUBERNETES_VERSION" ]]; then
      start_args+=(--kubernetes-version "$KUBERNETES_VERSION")
    fi
    info "$SCRIPT_NAME" "Creating minikube profile: $CLUSTER_NAME"
    minikube "${start_args[@]}"
  fi

  kubectl config use-context "$CLUSTER_NAME" >/dev/null 2>&1 || true
  success "$SCRIPT_NAME" "minikube cluster ready: $CLUSTER_NAME (context: $CLUSTER_NAME)"
}

SELECTED_RUNTIME="$(detect_runtime || true)"
if [[ -z "$SELECTED_RUNTIME" ]]; then
  error "$SCRIPT_NAME" "Unable to detect a supported local runtime. Install kind or minikube, or pass --cluster-runtime explicitly."
  exit 1
fi

case "$SELECTED_RUNTIME" in
  kind)
    ensure_kind_cluster
    ;;
  minikube)
    ensure_minikube_cluster
    ;;
esac