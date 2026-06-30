#!/usr/bin/env bash
set -euo pipefail

# Purpose: Seed AIStor parquet catalog data required by Trino validation.
# What it does:
# - Reads dq-db/mock-data delivery/catalog CSV files through scripts/seed_delivery_objects.py.
# - Seeds the Currency v1 parquet delivery used by Trino AIStor validation by default.
# - Uses the existing delivery-seed Docker Compose service for real AIStor writes.
# - Requires the AIStor container to already be running for live seeding.
# - Supports dry-run planning without Docker or AIStor writes.
#
# Version: 1.0
# Last modified: 2026-06-30

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"

MY_NAME="seed_trino_aistor_catalogs.sh"
DEFAULT_TRINO_VALIDATION_DELIVERY_ID="019e0488-9a53-72c3-9444-dbd3c1a2baf7"
DEFAULT_TRINO_VALIDATION_URI="s3a://retail-banking/standardized/analytics/Currency/v1/LOAD_DTS=20260220T071500000Z"

print_usage() {
  cat <<'EOF'
Usage: scripts/seed_trino_aistor_catalogs.sh [OPTIONS]

Seeds the AIStor parquet delivery data needed by Trino validation. By default it
seeds the Currency v1 delivery used by tests/test_trino_real_aistor_parquet_validation.py.
The AIStor container must already be running; this script never starts or stops it.

Canonical env options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use an explicit env file

Seed options:
  --delivery-id ID         Seed an additional/alternate delivery id from dq-db/mock-data
  --all-trino-validation   Seed all delivery ids currently required by Trino validation
  --dry-run                Validate CSV inputs and print planned uploads without writing AIStor
  --purge-bucket           Purge target bucket(s) before seeding selected deliveries
  --force-build            Build delivery-seed image before seeding
  -h, --help               Show this help

Environment overrides:
  TRINO_AISTOR_SEED_S3_ENDPOINT       Default: http://aistor:9000
  TRINO_AISTOR_SEED_ACCESS_KEY        Default: AISTOR_ROOT_USER or aistoradmin
  TRINO_AISTOR_SEED_SECRET_KEY        Default: AISTOR_ROOT_PASSWORD or aistoradmin
  TRINO_AISTOR_SEED_REGION            Default: us-east-1
EOF
}

DRY_RUN=false
PURGE_BUCKET=false
FORCE_BUILD=false
DELIVERY_IDS=()

run_seed_delivery_objects_dry_run() {
  local python_bin
  if [[ -x "$ROOT_DIR/venv/bin/python" ]]; then
    python_bin="$ROOT_DIR/venv/bin/python"
  else
    python_bin="python3"
  fi

  "$python_bin" "$ROOT_DIR/scripts/seed_delivery_objects.py" --dry-run "$@"
}

require_aistor_container_live() {
  local container_name="dq-made-easy-aistor"
  local container_state
  local health_state

  container_state="$(docker inspect -f '{{.State.Status}}' "$container_name" 2>/dev/null || true)"
  if [[ "$container_state" != "running" ]]; then
    error "$MY_NAME" "AIStor container is not running. Start it first with: ./scripts/stack_ctl.sh start --profile aistor"
    exit 1
  fi

  health_state="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_name" 2>/dev/null || true)"
  if [[ "$health_state" != "healthy" && "$health_state" != "none" ]]; then
    error "$MY_NAME" "AIStor container is running but not healthy yet (health=$health_state). Start/wait for it through the stack scripts before seeding."
    exit 1
  fi
}

run_delivery_seed_container() {
  local seed_args
  local delivery_id
  seed_args=()

  for delivery_id in "${DELIVERY_IDS[@]}"; do
    seed_args+=(--delivery-id "$delivery_id")
  done

  if [[ "$PURGE_BUCKET" == "true" ]]; then
    seed_args+=(--purge-bucket)
  fi

  if [[ "$FORCE_BUILD" == "true" ]]; then
    info "$MY_NAME" "Building delivery-seed image before Trino AIStor seeding"
    docker_compose --profile seed --profile core --profile engine build delivery-seed
  fi

  require_aistor_container_live

  info "$MY_NAME" "Warming Spark jars for delivery seeding"
  docker_compose --profile core --profile engine run --rm --no-deps \
    -e DQ_SPARK_DRIVER_HOST=127.0.0.1 \
    -e DQ_SPARK_DRIVER_BIND_ADDRESS=0.0.0.0 \
    dq-made-easy-engine \
    python scripts/warmup_spark_jars.py --ivy-dir /home/appuser/.ivy2 --jar-dir /home/appuser/.dq-spark-jars

  info "$MY_NAME" "Seeding selected Trino AIStor catalog delivery object(s)"
  docker_compose --profile seed --profile core --profile engine run --rm --no-deps \
    -e DQ_S3_ENDPOINT="$TRINO_AISTOR_SEED_S3_ENDPOINT" \
    -e DQ_S3_ACCESS_KEY="$TRINO_AISTOR_SEED_ACCESS_KEY" \
    -e DQ_S3_SECRET_KEY="$TRINO_AISTOR_SEED_SECRET_KEY" \
    -e DQ_S3_REGION="$TRINO_AISTOR_SEED_REGION" \
    -e AWS_ACCESS_KEY_ID="$TRINO_AISTOR_SEED_ACCESS_KEY" \
    -e AWS_SECRET_ACCESS_KEY="$TRINO_AISTOR_SEED_SECRET_KEY" \
    -e AWS_REGION="$TRINO_AISTOR_SEED_REGION" \
    -e AWS_DEFAULT_REGION="$TRINO_AISTOR_SEED_REGION" \
    -e DQ_SPARK_DRIVER_HOST=127.0.0.1 \
    -e DQ_SPARK_DRIVER_BIND_ADDRESS=0.0.0.0 \
    delivery-seed "${seed_args[@]}"
}

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 2
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --delivery-id)
      if [[ -z "${2:-}" ]]; then
        error "$MY_NAME" "--delivery-id requires a value"
        print_usage
        exit 2
      fi
      DELIVERY_IDS+=("$2")
      shift 2
      ;;
    --all-trino-validation)
      DELIVERY_IDS+=("$DEFAULT_TRINO_VALIDATION_DELIVERY_ID")
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --purge-bucket)
      PURGE_BUCKET=true
      shift
      ;;
    --force-build)
      FORCE_BUILD=true
      shift
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      error "$MY_NAME" "Unknown argument: $1"
      print_usage
      exit 2
      ;;
  esac
done

if [[ ${#DELIVERY_IDS[@]} -eq 0 ]]; then
  DELIVERY_IDS+=("$DEFAULT_TRINO_VALIDATION_DELIVERY_ID")
fi

validate_selected_root_env_file "$ROOT_DIR" full

set -a
# shellcheck disable=SC1090
source "$ROOT_ENV_FILE"
set +a

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/setup_env.sh"

TRINO_AISTOR_SEED_S3_ENDPOINT="${TRINO_AISTOR_SEED_S3_ENDPOINT:-http://aistor:9000}"
TRINO_AISTOR_SEED_ACCESS_KEY="${TRINO_AISTOR_SEED_ACCESS_KEY:-${AISTOR_ROOT_USER:-aistoradmin}}"
TRINO_AISTOR_SEED_SECRET_KEY="${TRINO_AISTOR_SEED_SECRET_KEY:-${AISTOR_ROOT_PASSWORD:-aistoradmin}}"
TRINO_AISTOR_SEED_REGION="${TRINO_AISTOR_SEED_REGION:-${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}}"

info "$MY_NAME" "Environment selection: $(describe_root_env_file_selection "$ROOT_DIR" "$ROOT_ENV_FILE") -> $ROOT_ENV_FILE"
info "$MY_NAME" "Trino validation parquet target: $DEFAULT_TRINO_VALIDATION_URI"

seed_args=()
for delivery_id in "${DELIVERY_IDS[@]}"; do
  seed_args+=(--delivery-id "$delivery_id")
done
if [[ "$PURGE_BUCKET" == "true" ]]; then
  seed_args+=(--purge-bucket)
fi

if [[ "$DRY_RUN" == "true" ]]; then
  info "$MY_NAME" "Dry run: planning selected Trino AIStor seed deliveries"
  run_seed_delivery_objects_dry_run "${seed_args[@]}"
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  error "$MY_NAME" "docker is required for live Trino AIStor seeding"
  exit 2
fi

require_aistor_container_live

run_delivery_seed_container
info "$MY_NAME" "Trino AIStor catalog seed completed"
