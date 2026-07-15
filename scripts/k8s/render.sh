#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_NAME="render.sh"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/env/selection.sh"

set_log_level INFO
init_root_env_file "$ROOT_DIR"

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

RENDER_ENV=""
if [ -n "${ROOT_ENV_SELECTION_ENV:-}" ]; then
  RENDER_ENV="$ROOT_ENV_SELECTION_ENV"
elif [ -n "${ROOT_ENV_SELECTION_ENV_FILE:-}" ]; then
  case "$(basename "$ROOT_ENV_SELECTION_ENV_FILE")" in
    .env.dev.local) RENDER_ENV="dev" ;;
    .env.test.local) RENDER_ENV="test" ;;
    .env.prod.local) RENDER_ENV="prod" ;;
    *) RENDER_ENV="dev" ;;
  esac
else
  RENDER_ENV="dev"
fi

CLOUD_PROVIDER="aks"
OUTPUT_FILE=""

usage() {
  cat <<'EOF'
Usage: ./scripts/k8s/render.sh [--env dev|test|prod] [OPTIONS]

Canonical env options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use explicit env file for diagnostics/CI

Render options:
  --cloud-provider aks|eks|gke
                           Select provider overlay family (default: aks)
  --output PATH            Write rendered manifests to PATH (default: stdout)
  -h, --help               Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cloud-provider)
      CLOUD_PROVIDER="${2:-}"
      shift 2
      ;;
    --output)
      OUTPUT_FILE="${2:-}"
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

case "$RENDER_ENV" in
  dev|test|prod) ;;
  *)
    error "$SCRIPT_NAME" "Unsupported environment: $RENDER_ENV"
    exit 1
    ;;
esac

case "$CLOUD_PROVIDER" in
  aks|eks|gke) ;;
  *)
    error "$SCRIPT_NAME" "Unsupported --cloud-provider value: $CLOUD_PROVIDER"
    exit 1
    ;;
esac

if ! command -v kubectl >/dev/null 2>&1; then
  error "$SCRIPT_NAME" "kubectl is required"
  exit 1
fi

OVERLAY_DIR="$ROOT_DIR/infra/k8s/providers/$CLOUD_PROVIDER/$RENDER_ENV"
if [ ! -d "$OVERLAY_DIR" ]; then
  error "$SCRIPT_NAME" "Provider overlay not found: $OVERLAY_DIR"
  exit 1
fi

info "$SCRIPT_NAME" "Rendering manifests for env=$RENDER_ENV provider=$CLOUD_PROVIDER from $OVERLAY_DIR"

if [ -n "$OUTPUT_FILE" ]; then
  mkdir -p "$(dirname "$OUTPUT_FILE")"
  kubectl kustomize "$OVERLAY_DIR" > "$OUTPUT_FILE"
  info "$SCRIPT_NAME" "Wrote rendered manifests to $OUTPUT_FILE"
else
  kubectl kustomize "$OVERLAY_DIR"
fi
