#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_NAME="local_pipeline_batch.sh"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/env/selection.sh"

set_log_level INFO
init_root_env_file "$ROOT_DIR"

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

DEPLOY_ENV=""
if [ -n "${ROOT_ENV_SELECTION_ENV:-}" ]; then
  DEPLOY_ENV="$ROOT_ENV_SELECTION_ENV"
elif [ -n "${ROOT_ENV_SELECTION_ENV_FILE:-}" ]; then
  case "$(basename "$ROOT_ENV_SELECTION_ENV_FILE")" in
    .env.dev.local) DEPLOY_ENV="dev" ;;
    .env.test.local) DEPLOY_ENV="test" ;;
    .env.prod.local) DEPLOY_ENV="prod" ;;
    *) DEPLOY_ENV="dev" ;;
  esac
else
  DEPLOY_ENV="dev"
fi

CLOUD_PROVIDER="aks"
CLUSTER_RUNTIME="auto"
SERVICES_CSV="dq-api,dq-engine,dq-frontend"
ALL_SERVICES_CSV="dq-api,dq-engine,dq-frontend,dq-kong,dq-db,dq-keycloak,dq-profiling,dq-llm"
IMAGE_TAG_PREFIX="local"
IMAGE_TAG_OVERRIDE=""
TEST_COMMAND="./scripts/validate.sh"
SKIP_TESTS="true"
SKIP_MIGRATIONS="true"
RUN_SEEDS="false"
RUN_PREFLIGHT_FIRST="false"
DRY_RUN="false"
DEPLOY_ONLY="false"

usage() {
  cat <<'EOF'
Usage: ./scripts/k8s/local_pipeline_batch.sh --env dev|test|prod [OPTIONS]

Canonical env options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use explicit env file

Options:
  --services CSV|all       Comma-separated deploy service names or 'all'
                           (default: dq-api,dq-engine,dq-frontend)
  --image-tag TAG          Exact image tag used for every service in --deploy-only mode
  --image-tag-prefix TAG   Prefix used per service image tag in build mode (default: local)
  --cloud-provider aks|eks|gke
                           Overlay/provider family for deploy.sh (default: aks)
  --cluster-runtime kind|minikube|auto
                           Runtime used for local image loading (default: auto)
  --test-command CMD       Test command for local Test stage (default: ./scripts/validate.sh)
  --deploy-only            Skip local build for every service; prefer matching local Docker images and otherwise deploy env-configured registry images
  --run-tests              Run local Test stage for each service
  --run-migrations         Run migration jobs during deploy
  --run-seeds              Run seed jobs during deploy
  --run-preflight-first    Run preflight checks for first service only
  --dry-run                Preview all service stages without mutating cluster or images
  -h, --help               Show this help

Service aliases:
  dq-api        -> jacbeekers/dq-made-easy-api
  dq-engine     -> jacbeekers/dq-made-easy-engine
  dq-frontend   -> jacbeekers/dq-made-easy-frontend
  dq-kong       -> jacbeekers/dq-made-easy-kong
  dq-db         -> jacbeekers/dq-made-easy-db
  dq-keycloak   -> jacbeekers/dq-made-easy-keycloak
  dq-profiling  -> jacbeekers/dq-made-easy-profiling
  dq-llm        -> jacbeekers/dq-made-easy-llm

Example:
  ./scripts/k8s/local_pipeline_batch.sh --env dev \
    --cluster-runtime kind \
    --services dq-api,dq-engine,dq-frontend \
    --image-tag-prefix local-dev
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --services)
      SERVICES_CSV="${2:-}"
      shift 2
      ;;
    --image-tag-prefix)
      IMAGE_TAG_PREFIX="${2:-}"
      shift 2
      ;;
    --image-tag)
      IMAGE_TAG_OVERRIDE="${2:-}"
      shift 2
      ;;
    --cloud-provider)
      CLOUD_PROVIDER="${2:-}"
      shift 2
      ;;
    --cluster-runtime)
      CLUSTER_RUNTIME="${2:-}"
      shift 2
      ;;
    --test-command)
      TEST_COMMAND="${2:-}"
      shift 2
      ;;
    --deploy-only)
      DEPLOY_ONLY="true"
      shift
      ;;
    --run-tests)
      SKIP_TESTS="false"
      shift
      ;;
    --run-migrations)
      SKIP_MIGRATIONS="false"
      shift
      ;;
    --run-seeds)
      RUN_SEEDS="true"
      shift
      ;;
    --run-preflight-first)
      RUN_PREFLIGHT_FIRST="true"
      shift
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
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

case "$DEPLOY_ENV" in
  dev|test|prod) ;;
  *)
    error "$SCRIPT_NAME" "Unsupported environment: $DEPLOY_ENV"
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

case "$CLUSTER_RUNTIME" in
  auto|kind|minikube) ;;
  *)
    error "$SCRIPT_NAME" "Unsupported --cluster-runtime value: $CLUSTER_RUNTIME"
    exit 1
    ;;
esac

if [[ -z "$SERVICES_CSV" ]]; then
  error "$SCRIPT_NAME" "--services cannot be empty"
  exit 1
fi

if [[ "$DEPLOY_ONLY" == "true" && -z "$IMAGE_TAG_OVERRIDE" ]]; then
  error "$SCRIPT_NAME" "--image-tag is required with --deploy-only"
  exit 1
fi

if [[ "$SERVICES_CSV" == "all" ]]; then
  SERVICES_CSV="$ALL_SERVICES_CSV"
fi

map_image_name() {
  local service_name="$1"
  case "$service_name" in
    dq-api) echo "jacbeekers/dq-made-easy-api" ;;
    dq-engine) echo "jacbeekers/dq-made-easy-engine" ;;
    dq-frontend) echo "jacbeekers/dq-made-easy-frontend" ;;
    dq-kong) echo "jacbeekers/dq-made-easy-kong" ;;
    dq-db) echo "jacbeekers/dq-made-easy-db" ;;
    dq-keycloak) echo "jacbeekers/dq-made-easy-keycloak" ;;
    dq-profiling) echo "jacbeekers/dq-made-easy-profiling" ;;
    dq-llm) echo "jacbeekers/dq-made-easy-llm" ;;
    *) return 1 ;;
  esac
}

IFS=',' read -r -a services <<< "$SERVICES_CSV"
if [[ "${#services[@]}" -eq 0 ]]; then
  error "$SCRIPT_NAME" "No services were parsed from --services"
  exit 1
fi

local_pipeline_script="$ROOT_DIR/scripts/k8s/local_pipeline.sh"
if [[ ! -x "$local_pipeline_script" ]]; then
  error "$SCRIPT_NAME" "Required script missing or not executable: $local_pipeline_script"
  exit 1
fi

for idx in "${!services[@]}"; do
  service_name="$(echo "${services[$idx]}" | awk '{$1=$1; print}')"
  if [[ -z "$service_name" ]]; then
    continue
  fi

  image_name="$(map_image_name "$service_name" || true)"
  if [[ -z "$image_name" ]]; then
    error "$SCRIPT_NAME" "Unknown service alias in --services: $service_name"
    exit 1
  fi

  image_tag="${IMAGE_TAG_PREFIX}-${service_name}"
  if [[ "$DEPLOY_ONLY" == "true" ]]; then
    image_tag="$IMAGE_TAG_OVERRIDE"
  fi

  info "$SCRIPT_NAME" "Running local pipeline for service=$service_name image=$image_name tag=$image_tag"

  args=(
    "--env" "$DEPLOY_ENV"
    "--service-name" "$service_name"
    "--image-name" "$image_name"
    "--image-tag" "$image_tag"
    "--cloud-provider" "$CLOUD_PROVIDER"
    "--cluster-runtime" "$CLUSTER_RUNTIME"
    "--test-command" "$TEST_COMMAND"
  )

  if [[ "$SKIP_TESTS" == "true" ]]; then
    args+=("--skip-tests")
  fi

  if [[ "$SKIP_MIGRATIONS" == "true" ]]; then
    args+=("--skip-migrations")
  fi

  if [[ "$RUN_SEEDS" == "true" ]]; then
    args+=("--run-seeds")
  fi

  if [[ "$RUN_PREFLIGHT_FIRST" == "true" ]]; then
    if [[ "$idx" == "0" ]]; then
      args+=("--run-preflight")
    fi
  fi

  if [[ "$DRY_RUN" == "true" ]]; then
    args+=("--dry-run")
  fi

  if [[ "$DEPLOY_ONLY" == "true" ]]; then
    args+=("--deploy-only")
  fi

  "$local_pipeline_script" "${args[@]}"
done

success "$SCRIPT_NAME" "Completed local pipeline batch for services: $SERVICES_CSV"
