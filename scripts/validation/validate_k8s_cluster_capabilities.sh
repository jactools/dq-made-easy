#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="validate_k8s_cluster_capabilities.sh"

usage() {
  cat <<'EOF'
Usage: ./scripts/validation/validate_k8s_cluster_capabilities.sh --provider aks|eks|gke --namespace NAMESPACE

Options:
  --provider aks|eks|gke   Target cloud provider
  --namespace NAME         Target namespace for deploy permission checks
  -h, --help               Show this help
EOF
}

PROVIDER=""
NAMESPACE=""
EXPECTED_INGRESS_CLASS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider)
      PROVIDER="${2:-}"
      shift 2
      ;;
    --namespace)
      NAMESPACE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[$SCRIPT_NAME] Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$PROVIDER" || -z "$NAMESPACE" ]]; then
  echo "[$SCRIPT_NAME] --provider and --namespace are required" >&2
  usage
  exit 1
fi

case "$PROVIDER" in
  aks)
    EXPECTED_INGRESS_CLASS="nginx"
    ;;
  eks)
    EXPECTED_INGRESS_CLASS="alb"
    ;;
  gke)
    EXPECTED_INGRESS_CLASS="gce"
    ;;
  *)
    echo "[$SCRIPT_NAME] Unsupported provider: $PROVIDER" >&2
    exit 1
    ;;
esac

if ! command -v kubectl >/dev/null 2>&1; then
  echo "[$SCRIPT_NAME] kubectl is required" >&2
  exit 1
fi

kubectl cluster-info >/dev/null

if ! kubectl api-resources --verbs=list --namespaced -o name | grep -qx 'ingresses.networking.k8s.io'; then
  echo "[$SCRIPT_NAME] Cluster does not expose networking.k8s.io Ingress API" >&2
  exit 1
fi

if ! kubectl auth can-i create deployments.apps -n "$NAMESPACE" >/dev/null; then
  echo "[$SCRIPT_NAME] Missing permission: create deployments.apps in namespace $NAMESPACE" >&2
  exit 1
fi

if ! kubectl auth can-i create jobs.batch -n "$NAMESPACE" >/dev/null; then
  echo "[$SCRIPT_NAME] Missing permission: create jobs.batch in namespace $NAMESPACE" >&2
  exit 1
fi

if ! kubectl auth can-i create ingresses.networking.k8s.io -n "$NAMESPACE" >/dev/null; then
  echo "[$SCRIPT_NAME] Missing permission: create ingresses.networking.k8s.io in namespace $NAMESPACE" >&2
  exit 1
fi

if kubectl get ingressclass "$EXPECTED_INGRESS_CLASS" >/dev/null 2>&1; then
  echo "[$SCRIPT_NAME] Found expected ingress class: $EXPECTED_INGRESS_CLASS"
else
  echo "[$SCRIPT_NAME] Expected ingress class not found: $EXPECTED_INGRESS_CLASS" >&2
  echo "[$SCRIPT_NAME] Ensure the cluster has the provider ingress controller installed before deploy." >&2
  exit 1
fi

echo "[$SCRIPT_NAME] Preflight passed for provider=$PROVIDER namespace=$NAMESPACE"
