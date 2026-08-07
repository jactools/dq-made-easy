#!/usr/bin/env bash
# ============================================================================
# render.sh — Render DQ Made Easy K8s manifests without applying.
#
# Usage: scripts/k8s/render.sh [options]
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPT_NAME="render.sh"

OVERLAYS=(
  "shared-dev"
  "dev-api"
  "dev-ui"
  "dev-engine"
)

OUTPUT_FILE=""
FILTER=""

usage() {
  cat <<'EOF'
Usage: ./scripts/k8s/render.sh [OPTIONS]

Render K8s manifests from overlays without applying to cluster.

Options:
  --output PATH            Write rendered manifests to PATH (default: stdout)
  --filter KIND            Filter by resource kind (e.g. Deployment, Job, Secret)
  --overlay NAME           Render specific overlay (default: all)
  -h, --help               Show this help

Examples:
  ./scripts/k8s/render.sh
  ./scripts/k8s/render.sh --output /tmp/manifests.yaml
  ./scripts/k8s/render.sh --overlay shared-dev
  ./scripts/k8s/render.sh --filter Deployment
EOF
}

log()  { printf '[render] %s\n' "$*" >&2; }
info() { printf '[render] ✓ %s\n' "$*" >&2; }
err()  { printf '[render] ✗ %s\n' "$*" >&2; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Missing required command: $1"
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      if [[ -z "${2:-}" ]]; then err "--output requires a path"; exit 2; fi
      OUTPUT_FILE="$2"; shift 2 ;;
    --filter)
      if [[ -z "${2:-}" ]]; then err "--filter requires a kind"; exit 2; fi
      FILTER="$2"; shift 2 ;;
    --overlay)
      if [[ -z "${2:-}" ]]; then err "--overlay requires a name"; exit 2; fi
      OVERLAYS=("$2"); shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) err "Unknown option: $1"; usage; exit 2 ;;
  esac
done

require_cmd kubectl

render_overlay() {
  local overlay="$1"
  local overlay_dir="${ROOT_DIR}/infra/k8s/overlays/${overlay}"

  if [[ ! -d "$overlay_dir" ]]; then
    err "Overlay directory not found: $overlay_dir"
    return 1
  fi

  if ! kubectl kustomize "$overlay_dir" >/dev/null 2>&1; then
    err "Overlay $overlay failed to render"
    kubectl kustomize "$overlay_dir" 2>&1
    return 1
  fi

  local output
  output=$(kubectl kustomize "$overlay_dir")

  if [[ -n "$FILTER" ]]; then
    output=$(echo "$output" | python3 -c "
import sys, yaml
docs = list(yaml.safe_load_all(sys.stdin))
yaml.dump_all([d for d in docs if d and d.get('kind') == '$FILTER'], sys.stdout, default_flow_style=False, sort_keys=False)
" 2>/dev/null || echo "$output")
  fi

  echo "$output"
}

# Render all overlays
rendered=""
for overlay in "${OVERLAYS[@]}"; do
  result=$(render_overlay "$overlay")
  if [[ -z "$rendered" ]]; then
    rendered="$result"
  else
    rendered="$rendered
---
$result"
  fi
done

if [[ -n "$OUTPUT_FILE" ]]; then
  mkdir -p "$(dirname "$OUTPUT_FILE")"
  echo "$rendered" > "$OUTPUT_FILE"
  info "Wrote rendered manifests to $OUTPUT_FILE"
else
  echo "$rendered"
fi

info "Render complete"
