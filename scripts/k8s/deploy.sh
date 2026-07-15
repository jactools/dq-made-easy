#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_NAME="deploy.sh"

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

SEED_MODE="auto"
ALLOW_PROD_SEED="false"
SKIP_MIGRATIONS="false"
JOB_TIMEOUT_SECONDS="600"
WAIT_ROLLOUT="true"
CLOUD_PROVIDER="aks"
SKIP_PREFLIGHT="false"
DRY_RUN="false"

usage() {
  cat <<'EOF'
Usage: ./scripts/k8s/deploy.sh [--env dev|test|prod] [OPTIONS]

Canonical env options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use explicit env file for diagnostics/CI

Lifecycle options:
  --cloud-provider aks|eks|gke
                           Select provider-specific overlay and preflight checks (default: aks)
  --seed-mode auto|always|never
                           auto: run seed jobs in dev/test, skip in prod
                           always: run seed jobs in all envs (requires --allow-prod-seed for prod)
                           never: never run seed jobs
  --skip-preflight         Skip provider capability preflight validation
  --dry-run                Preview deploy actions and run kubectl server-side validation only
  --allow-prod-seed        Required to run seed jobs in prod
  --skip-migrations        Skip migration jobs
  --job-timeout-seconds N  Timeout for each migration/seed job wait (default: 600)
  --no-rollout-wait        Apply manifests without waiting for deployment rollout
  -h, --help               Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cloud-provider)
      CLOUD_PROVIDER="${2:-}"
      shift 2
      ;;
    --seed-mode)
      SEED_MODE="${2:-}"
      shift 2
      ;;
    --skip-preflight)
      SKIP_PREFLIGHT="true"
      shift
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    --allow-prod-seed)
      ALLOW_PROD_SEED="true"
      shift
      ;;
    --skip-migrations)
      SKIP_MIGRATIONS="true"
      shift
      ;;
    --job-timeout-seconds)
      JOB_TIMEOUT_SECONDS="${2:-}"
      shift 2
      ;;
    --no-rollout-wait)
      WAIT_ROLLOUT="false"
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

case "$SEED_MODE" in
  auto|always|never) ;;
  *)
    error "$SCRIPT_NAME" "Invalid --seed-mode: $SEED_MODE"
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

PROVIDER_OVERLAY_DIR="$ROOT_DIR/infra/k8s/providers/$CLOUD_PROVIDER/$DEPLOY_ENV"
if [ -d "$PROVIDER_OVERLAY_DIR" ]; then
  OVERLAY_DIR="$PROVIDER_OVERLAY_DIR"
else
  OVERLAY_DIR="$ROOT_DIR/infra/k8s/overlays/$DEPLOY_ENV"
fi

if [ ! -d "$OVERLAY_DIR" ]; then
  error "$SCRIPT_NAME" "Overlay directory not found: $OVERLAY_DIR"
  exit 1
fi

NAMESPACE="dq-made-easy-$DEPLOY_ENV"
if [ "$DEPLOY_ENV" = "prod" ]; then
  NAMESPACE="dq-made-easy-prod"
fi

if ! command -v kubectl >/dev/null 2>&1; then
  error "$SCRIPT_NAME" "kubectl is required"
  exit 1
fi

MIGRATION_JOBS=(
  "api-migrate.yaml:dq-job-api-migrate"
  "kong-migrate.yaml:dq-job-kong-migrate"
)
SEED_JOBS=(
  "openmetadata-seed.yaml:dq-job-openmetadata-seed"
)

run_job_manifest() {
  local manifest_file="$1"
  local job_name="$2"

  info "$SCRIPT_NAME" "Running job $job_name in namespace $NAMESPACE"
  kubectl -n "$NAMESPACE" delete job "$job_name" --ignore-not-found >/dev/null 2>&1 || true
  kubectl -n "$NAMESPACE" apply -f "$ROOT_DIR/infra/k8s/base/jobs/$manifest_file" >/dev/null
  kubectl -n "$NAMESPACE" wait --for=condition=complete --timeout="${JOB_TIMEOUT_SECONDS}s" "job/$job_name"
}

should_run_seed_jobs() {
  case "$SEED_MODE" in
    never)
      return 1
      ;;
    always)
      if [ "$DEPLOY_ENV" = "prod" ] && [ "$ALLOW_PROD_SEED" != "true" ]; then
        error "$SCRIPT_NAME" "Refusing to run seed jobs in prod without --allow-prod-seed"
        exit 1
      fi
      return 0
      ;;
    auto)
      if [ "$DEPLOY_ENV" = "prod" ]; then
        return 1
      fi
      return 0
      ;;
  esac
}

info "$SCRIPT_NAME" "Deploying WF6 overlay: env=$DEPLOY_ENV namespace=$NAMESPACE seed_mode=$SEED_MODE dry_run=$DRY_RUN"

if [ "$SKIP_PREFLIGHT" != "true" ]; then
  preflight_script="$ROOT_DIR/scripts/validation/validate_k8s_cluster_capabilities.sh"
  if [ -x "$preflight_script" ]; then
    "$preflight_script" --provider "$CLOUD_PROVIDER" --namespace "$NAMESPACE"
  else
    warning "$SCRIPT_NAME" "Preflight script not executable or missing: $preflight_script"
  fi
else
  warning "$SCRIPT_NAME" "Skipping preflight validation due to --skip-preflight"
fi

info "$SCRIPT_NAME" "Using overlay path: $OVERLAY_DIR"

if [ "$DRY_RUN" = "true" ]; then
  info "$SCRIPT_NAME" "Dry-run: validating overlay with server-side apply"
  kubectl apply --dry-run=server -k "$OVERLAY_DIR"
else
  kubectl apply -k "$OVERLAY_DIR"
fi

if [ "$DRY_RUN" = "true" ]; then
  info "$SCRIPT_NAME" "Dry-run: skipping migration and seed job execution"
elif [ "$SKIP_MIGRATIONS" != "true" ]; then
  for job_spec in "${MIGRATION_JOBS[@]}"; do
    manifest_file="${job_spec%%:*}"
    job_name="${job_spec##*:}"
    run_job_manifest "$manifest_file" "$job_name"
  done
else
  warning "$SCRIPT_NAME" "Skipping migration jobs due to --skip-migrations"
fi

if [ "$DRY_RUN" = "true" ]; then
  :
elif should_run_seed_jobs; then
  for job_spec in "${SEED_JOBS[@]}"; do
    manifest_file="${job_spec%%:*}"
    job_name="${job_spec##*:}"
    run_job_manifest "$manifest_file" "$job_name"
  done
else
  info "$SCRIPT_NAME" "Seed jobs not scheduled for env=$DEPLOY_ENV with seed_mode=$SEED_MODE"
fi

if [ "$DRY_RUN" = "true" ]; then
  info "$SCRIPT_NAME" "Dry-run: skipping rollout status checks"
elif [ "$WAIT_ROLLOUT" = "true" ]; then
  info "$SCRIPT_NAME" "Waiting for workload rollout"
  kubectl -n "$NAMESPACE" rollout status deployment/dq-api --timeout=300s
  kubectl -n "$NAMESPACE" rollout status deployment/dq-kong --timeout=300s
  kubectl -n "$NAMESPACE" rollout status deployment/dq-frontend --timeout=300s
fi

info "$SCRIPT_NAME" "Deployment flow completed for env=$DEPLOY_ENV"
