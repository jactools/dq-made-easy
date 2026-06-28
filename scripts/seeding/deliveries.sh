# Purpose: Dedicated seed block for delivery objects.

prepare_delivery_seed_runtime() {
  if [ "${FORCE_BUILD:-false}" = "true" ]; then
    info "$my_name" "Building delivery-seed image before delivery seeding so Spark/Delta runtime changes are used"
    docker_compose --profile seed --profile core --profile engine build delivery-seed || {
      error "$my_name" "Failed to build delivery-seed image"
      exit 36
    }
  fi

  info "$my_name" "Warming Spark jars for delivery seeding..."
  docker_compose --profile core --profile engine run --rm --no-deps -e DQ_SPARK_DRIVER_HOST=127.0.0.1 -e DQ_SPARK_DRIVER_BIND_ADDRESS=0.0.0.0 dq-made-easy-engine python scripts/warmup_spark_jars.py --ivy-dir /home/appuser/.ivy2 --jar-dir /home/appuser/.dq-spark-jars || {
    error "$my_name" "Spark jar warm-up failed before delivery seeding"
    exit 36
  }
}

seed_delivery_objects_in_docker() {
  local delivery_args
  delivery_args=()

  if [ "$PURGE_BUCKET" = "true" ]; then
    delivery_args+=(--purge-bucket)
  fi

  if [ "$WIPE_AISTOR" = "true" ]; then
    delivery_args+=(--wipe-aistor)
  fi

  info "$my_name" "Seeding delivery objects in Docker (AIStor materialization via one-shot engine service)..."

  docker_compose up -d aistor || {
    error "$my_name" "Failed to start AIStor for delivery seeding"
    exit 36
  }

  prepare_delivery_seed_runtime

  if [ "${#delivery_args[@]}" -gt 0 ]; then
    docker_compose --profile seed --profile core --profile engine run --rm --no-deps -e DQ_SPARK_DRIVER_HOST=127.0.0.1 -e DQ_SPARK_DRIVER_BIND_ADDRESS=0.0.0.0 delivery-seed "${delivery_args[@]}" || {
      error "$my_name" "Delivery Docker seed container failed"
      exit 36
    }
  else
    docker_compose --profile seed --profile core --profile engine run --rm --no-deps -e DQ_SPARK_DRIVER_HOST=127.0.0.1 -e DQ_SPARK_DRIVER_BIND_ADDRESS=0.0.0.0 delivery-seed || {
      error "$my_name" "Delivery Docker seed container failed"
      exit 36
    }
  fi

  info "$my_name" "✓ AIStor delivery objects seeded via Docker Compose"
}

seed_stack_block_deliveries() {
  if [ "$SEED_DELIVERIES" != "true" ] && [ "$WIPE_AISTOR" != "true" ]; then
    return 0
  fi

  seed_delivery_objects_in_docker
}