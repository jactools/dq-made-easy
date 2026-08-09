#!/usr/bin/env bash
# ============================================================================
# sync_overlay_tags.sh — Update Kustomize overlay image tags from env file.
#
# Reads DQ_*_TAG values from .env.<env>.local, extracts base versions,
# and updates the overlay kustomization.yaml files with newTag.
#
# Usage: scripts/sync_overlay_tags.sh [--env dev|test|prod]
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV="${ENV:-dev}"

source "${ROOT_DIR}/.env.${ENV}.local"

# Extract base versions (strip commit hash: 0.10-7a9c018 -> 0.10)
get_base_tag() {
  local full_tag="${!1}"
  echo "${full_tag%%-*}"
}

API_TAG=$(get_base_tag DQ_API_TAG)
ENGINE_TAG=$(get_base_tag DQ_ENGINE_TAG)
FRONTEND_TAG=$(get_base_tag DQ_FRONTEND_TAG)
PROFILING_TAG=$(get_base_tag DQ_PROFILING_TAG)
BASE_TAG=$(get_base_tag DQ_BASE_TAG)
DB_TAG=$(get_base_tag DQ_DB_TAG 2>/dev/null || echo "$BASE_TAG")
METADATA_TAG=$(get_base_tag DQ_METADATA_CONFIGURE_TAG 2>/dev/null || echo "$BASE_TAG")
KEYCLOAK_TAG=$(get_base_tag DQ_KEYCLOAK_SEED_ARTIFACTS_TAG 2>/dev/null || echo "$BASE_TAG")
KAFKA_CONSUMER_TAG=$(get_base_tag DQ_KAFKA_CONSUMER_TAG 2>/dev/null || echo "$BASE_TAG")

overlay_dir="${ROOT_DIR}/infra/k8s/overlays"
updated=0

update_tag() {
  local file="$1"
  local image_name="$2"
  local tag="$3"
  if grep -q "$image_name" "$file" 2>/dev/null; then
    sed -i '' "/${image_name}/{n;s/newTag: \"[^\"]*\"/newTag: \"${tag}\"/}" "$file"
    updated=$((updated + 1))
    echo "  ${file##*/}: ${image_name} -> ${tag}"
  fi
}

echo "Syncing overlay tags for env=${ENV}..."
echo "  Base: api=${API_TAG} engine=${ENGINE_TAG} frontend=${FRONTEND_TAG} profiling=${PROFILING_TAG}"

echo "dev-api:"
update_tag "${overlay_dir}/dev-api/kustomization.yaml" "dq-made-easy-api" "$API_TAG"
update_tag "${overlay_dir}/dev-api/kustomization.yaml" "dq-made-easy-db" "${DB_TAG}"

echo "dev-engine:"
update_tag "${overlay_dir}/dev-engine/kustomization.yaml" "dq-made-easy-engine" "$ENGINE_TAG"
update_tag "${overlay_dir}/dev-engine/kustomization.yaml" "dq-made-easy-profiling" "$PROFILING_TAG"
update_tag "${overlay_dir}/dev-engine/kustomization.yaml" "dq-made-easy-llm" "$BASE_TAG"
update_tag "${overlay_dir}/dev-engine/kustomization.yaml" "dq-made-easy-kafka-consumer" "$KAFKA_CONSUMER_TAG"
update_tag "${overlay_dir}/dev-engine/kustomization.yaml" "dq-made-easy-openmetadata-db" "$BASE_TAG"
update_tag "${overlay_dir}/dev-engine/kustomization.yaml" "dq-made-easy-openmetadata" "$BASE_TAG"

echo "dev-ui:"
update_tag "${overlay_dir}/dev-ui/kustomization.yaml" "dq-made-easy-frontend" "$FRONTEND_TAG"

echo "shared-dev:"
update_tag "${overlay_dir}/shared-dev/kustomization.yaml" "dq-made-easy-api" "$API_TAG"
update_tag "${overlay_dir}/shared-dev/kustomization.yaml" "dq-made-easy-metadata-configure" "$METADATA_TAG"
update_tag "${overlay_dir}/shared-dev/kustomization.yaml" "dq-made-easy-keycloak-seed" "$KEYCLOAK_TAG"

echo ""
echo "Updated ${updated} image tags across overlays."
echo "Commit these changes before ArgoCD sync."
