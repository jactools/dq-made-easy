#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_NAME="local_pipeline.sh"

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
SERVICE_NAME=""
IMAGE_NAME=""
IMAGE_TAG="local"
TEST_COMMAND="./scripts/validate.sh"
SKIP_TESTS="false"
SKIP_MIGRATIONS="true"
SKIP_SEEDS="true"
SKIP_PREFLIGHT="true"
LOCAL_IMAGE_REF=""
DRY_RUN="false"

usage() {
  cat <<'EOF'
Usage: ./scripts/k8s/local_pipeline.sh --env dev|test|prod [OPTIONS]

Canonical env options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use explicit env file

Required options:
  --service-name NAME      Deployment + container name in Kubernetes (example: dq-api)
  --image-name NAME        Repository path (example: jacbeekers/dq-made-easy-api)

Optional options:
  --image-tag TAG          Image tag to build/load/deploy (default: local)
  --cloud-provider aks|eks|gke
                           Overlay/provider family for deploy.sh (default: aks)
  --cluster-runtime kind|minikube|auto
                           Runtime used for local image loading (default: auto)
  --local-image-ref REF    Fully qualified image reference to deploy; skip build mapping
  --test-command CMD       Test command for local Test stage (default: ./scripts/validate.sh)
  --skip-tests             Skip local Test stage
  --skip-migrations        Skip migration jobs in local Deploy stage
  --run-seeds              Run seed jobs (default is skip)
  --run-preflight          Run cluster preflight checks (default is skip)
  --dry-run                Preview stages and skip build/load/deploy mutations
  -h, --help               Show this help

Example:
  ./scripts/k8s/local_pipeline.sh --env dev \
    --service-name dq-api \
    --image-name jacbeekers/dq-made-easy-api \
    --image-tag local-dev \
    --cluster-runtime kind
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service-name)
      SERVICE_NAME="${2:-}"
      shift 2
      ;;
    --image-name)
      IMAGE_NAME="${2:-}"
      shift 2
      ;;
    --image-tag)
      IMAGE_TAG="${2:-}"
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
    --local-image-ref)
      LOCAL_IMAGE_REF="${2:-}"
      shift 2
      ;;
    --test-command)
      TEST_COMMAND="${2:-}"
      shift 2
      ;;
    --skip-tests)
      SKIP_TESTS="true"
      shift
      ;;
    --skip-migrations)
      SKIP_MIGRATIONS="true"
      shift
      ;;
    --run-seeds)
      SKIP_SEEDS="false"
      shift
      ;;
    --run-preflight)
      SKIP_PREFLIGHT="false"
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

if [[ -z "$SERVICE_NAME" ]]; then
  error "$SCRIPT_NAME" "--service-name is required"
  exit 1
fi

if [[ -z "$IMAGE_NAME" && -z "$LOCAL_IMAGE_REF" ]]; then
  error "$SCRIPT_NAME" "Either --image-name or --local-image-ref is required"
  exit 1
fi

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

if ! command -v kubectl >/dev/null 2>&1; then
  error "$SCRIPT_NAME" "kubectl is required"
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  error "$SCRIPT_NAME" "docker is required"
  exit 1
fi

map_build_target() {
  local image_name="$1"
  local repo_name="${image_name##*/}"
  case "$repo_name" in
    dq-made-easy-base) echo "dq-base" ;;
    dq-made-easy-api) echo "dq-api" ;;
    dq-made-easy-engine) echo "dq-engine" ;;
    dq-made-easy-profiling) echo "dq-profiling" ;;
    dq-made-easy-frontend) echo "dq-frontend" ;;
    dq-made-easy-kong) echo "dq-kong" ;;
    dq-made-easy-db) echo "dq-db" ;;
    dq-made-easy-keycloak) echo "dq-keycloak" ;;
    dq-made-easy-kafka) echo "dq-kafka" ;;
    dq-made-easy-kafka-consumer) echo "dq-kafka-consumer" ;;
    dq-made-easy-trino) echo "dq-trino" ;;
    dq-made-easy-edge) echo "dq-edge" ;;
    dq-made-easy-airflow) echo "dq-airflow" ;;
    dq-made-easy-llm) echo "dq-llm" ;;
    *) return 1 ;;
  esac
}

detect_cluster_runtime() {
  local current_context
  current_context="$(kubectl config current-context 2>/dev/null || true)"

  if [[ "$CLUSTER_RUNTIME" != "auto" ]]; then
    echo "$CLUSTER_RUNTIME"
    return 0
  fi

  if [[ "$current_context" == kind-* ]]; then
    echo "kind"
    return 0
  fi

  if [[ "$current_context" == minikube* ]]; then
    echo "minikube"
    return 0
  fi

  return 1
}

resolve_namespace() {
  case "$DEPLOY_ENV" in
    dev) echo "dq-made-easy-dev" ;;
    test) echo "dq-made-easy-test" ;;
    prod) echo "dq-made-easy-prod" ;;
  esac
}

RUNTIME="$(detect_cluster_runtime || true)"
if [[ -z "$RUNTIME" ]]; then
  error "$SCRIPT_NAME" "Unable to detect cluster runtime from current context. Use --cluster-runtime kind|minikube."
  exit 1
fi

NAMESPACE="$(resolve_namespace)"

if [[ -z "$LOCAL_IMAGE_REF" ]]; then
  info "$SCRIPT_NAME" "Stage Build: building image via scripts/build_and_push_one.sh"

  BUILD_TARGET="$(map_build_target "$IMAGE_NAME" || true)"
  if [[ -z "$BUILD_TARGET" ]]; then
    error "$SCRIPT_NAME" "Cannot map image repository to build target: $IMAGE_NAME"
    exit 1
  fi

  if [[ "$DRY_RUN" == "true" ]]; then
    info "$SCRIPT_NAME" "Dry-run: would run build command for $BUILD_TARGET --env $DEPLOY_ENV --version $IMAGE_TAG"
  else
    "$ROOT_DIR/scripts/build_and_push_one.sh" "$BUILD_TARGET" --env "$DEPLOY_ENV" --no-push --version "$IMAGE_TAG"
  fi

  LOCAL_IMAGE_REF="docker.io/${IMAGE_NAME}:${IMAGE_TAG}"
fi

if [[ "$SKIP_TESTS" != "true" ]]; then
  info "$SCRIPT_NAME" "Stage Test: running local test command"
  bash -lc "$TEST_COMMAND"
else
  warning "$SCRIPT_NAME" "Stage Test skipped by --skip-tests"
fi

info "$SCRIPT_NAME" "Stage Publish(Local): loading image into $RUNTIME cluster"
case "$RUNTIME" in
  kind)
    if ! command -v kind >/dev/null 2>&1; then
      error "$SCRIPT_NAME" "kind CLI is required for --cluster-runtime kind"
      exit 1
    fi

    current_context="$(kubectl config current-context)"
    kind_cluster_name="${current_context#kind-}"
    if [[ -z "$kind_cluster_name" || "$kind_cluster_name" == "$current_context" ]]; then
      kind_cluster_name="kind"
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
      info "$SCRIPT_NAME" "Dry-run: would run kind load docker-image $LOCAL_IMAGE_REF --name $kind_cluster_name"
    else
      kind load docker-image "$LOCAL_IMAGE_REF" --name "$kind_cluster_name"
    fi
    ;;
  minikube)
    if ! command -v minikube >/dev/null 2>&1; then
      error "$SCRIPT_NAME" "minikube CLI is required for --cluster-runtime minikube"
      exit 1
    fi

    minikube_profile="$(minikube profile 2>/dev/null | awk '/\*/ {print $2; exit}')"
    if [[ -z "$minikube_profile" ]]; then
      minikube_profile="minikube"
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
      info "$SCRIPT_NAME" "Dry-run: would run minikube image load $LOCAL_IMAGE_REF --profile $minikube_profile"
    else
      minikube image load "$LOCAL_IMAGE_REF" --profile "$minikube_profile"
    fi
    ;;
esac

info "$SCRIPT_NAME" "Stage Deploy: applying overlay and running local deployment workflow"

DEPLOY_ARGS=("--env" "$DEPLOY_ENV" "--cloud-provider" "$CLOUD_PROVIDER" "--no-rollout-wait")

if [[ "$SKIP_MIGRATIONS" == "true" ]]; then
  DEPLOY_ARGS+=("--skip-migrations")
fi
if [[ "$SKIP_SEEDS" == "true" ]]; then
  DEPLOY_ARGS+=("--seed-mode" "never")
fi
if [[ "$SKIP_PREFLIGHT" == "true" ]]; then
  DEPLOY_ARGS+=("--skip-preflight")
fi
if [[ "$DRY_RUN" == "true" ]]; then
  DEPLOY_ARGS+=("--dry-run")
fi

"$ROOT_DIR/scripts/k8s/deploy.sh" "${DEPLOY_ARGS[@]}"

if [[ "$DRY_RUN" == "true" ]]; then
  info "$SCRIPT_NAME" "Dry-run: would run kubectl set image deployment/${SERVICE_NAME} ${SERVICE_NAME}=${LOCAL_IMAGE_REF}"
  info "$SCRIPT_NAME" "Dry-run: would patch imagePullPolicy=IfNotPresent on deployment/${SERVICE_NAME}"
  info "$SCRIPT_NAME" "Dry-run: skipping smoke rollout/image/pod checks"
  success "$SCRIPT_NAME" "Dry-run completed for ${SERVICE_NAME} with planned image ${LOCAL_IMAGE_REF}"
  exit 0
fi

kubectl -n "$NAMESPACE" set image "deployment/${SERVICE_NAME}" "${SERVICE_NAME}=${LOCAL_IMAGE_REF}"
kubectl -n "$NAMESPACE" patch deployment "$SERVICE_NAME" --type strategic -p "{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"${SERVICE_NAME}\",\"imagePullPolicy\":\"IfNotPresent\"}]}}}}"

info "$SCRIPT_NAME" "Stage Smoke: validating rollout and image"
kubectl -n "$NAMESPACE" rollout status "deployment/${SERVICE_NAME}" --timeout=300s

current_image="$(kubectl -n "$NAMESPACE" get deployment "$SERVICE_NAME" -o jsonpath='{.spec.template.spec.containers[0].image}')"
if [[ "$current_image" != "$LOCAL_IMAGE_REF" ]]; then
  error "$SCRIPT_NAME" "Deployed image mismatch: expected $LOCAL_IMAGE_REF got $current_image"
  exit 1
fi

running_count="$(kubectl -n "$NAMESPACE" get pods -l "app.kubernetes.io/name=${SERVICE_NAME}" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d '[:space:]')"
if [[ "$running_count" == "0" ]]; then
  warning "$SCRIPT_NAME" "No running pods found with app.kubernetes.io/name=${SERVICE_NAME}; trying app=${SERVICE_NAME}"
  running_count="$(kubectl -n "$NAMESPACE" get pods -l "app=${SERVICE_NAME}" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d '[:space:]')"
fi

if [[ "$running_count" == "0" ]]; then
  error "$SCRIPT_NAME" "No running pods found for service $SERVICE_NAME in namespace $NAMESPACE"
  kubectl -n "$NAMESPACE" get pods -o wide || true
  exit 1
fi

success "$SCRIPT_NAME" "Local Build/Test/Publish/Deploy/Smoke completed for ${SERVICE_NAME} with image ${LOCAL_IMAGE_REF}"
