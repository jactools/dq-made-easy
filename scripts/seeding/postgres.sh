# Purpose: Dedicated seed block for the postgres profile.

seed_postgres_in_docker() {
  info "$my_name" "Reseeding Postgres in Docker (SQL generation, Alembic, Keycloak external-id mapping)..."

  # Only wipe the volume if it has existing data (warm restart reseed).
  # For a fresh init the volume is empty — no need to remove/recreate it.
  local pg_vol
  local prefix
  prefix="$(_get_project_prefix)"
  pg_vol="${prefix}_pgdata_v18"

  if docker volume ls -q --filter "name=${pg_vol}$" 2>/dev/null | grep -q .; then
    # Check if volume has data by inspecting its size
    local vol_size
    vol_size="$(docker inspect "$pg_vol" --format '{{.Size}}' 2>/dev/null || echo "unknown")"
    if [ "$vol_size" != "unknown" ] && [ "$vol_size" -gt 0 ] 2>/dev/null; then
      info "$my_name" "Postgres volume has data ($vol_size bytes); removing before reseed..."
      if ! remove_compose_postgres_volume; then
        error "$my_name" "Failed to remove the PostgreSQL data volume before reseeding"
        exit 34
      fi
    else
      info "$my_name" "Postgres volume is empty (fresh); skipping wipe"
    fi
  else
    info "$my_name" "Postgres volume does not exist (fresh start)"
  fi

  docker_compose up -d db keycloak || {
    error "$my_name" "Failed to start db/keycloak for Postgres seeding"
    exit 34
  }

  info "$my_name" "Waiting for Postgres to become healthy..."
  wait_for_compose_service_healthy db "Postgres database" 180 3 || {
    error "$my_name" "Postgres database did not become healthy before seeding"
    docker_compose logs --no-color --tail 80 db || true
    exit 34
  }

  info "$my_name" "Waiting for Keycloak to become healthy..."
  wait_for_compose_service_healthy keycloak "Keycloak" 180 3 || {
    error "$my_name" "Keycloak did not become healthy before seeding"
    docker_compose logs --no-color --tail 80 keycloak || true
    exit 34
  }

  info "$my_name" "Running db-seed container..."
  docker_compose --profile auth --profile seed run --rm db-seed || {
    error "$my_name" "Postgres Docker seed container failed"
    exit 34
  }

  info "$my_name" "✓ Postgres reseed completed via Docker Compose"
}

seed_stack_block_postgres() {
  if [ "$SEED_POSTGRES" != "true" ] && [ "$INIT_DB" != "true" ]; then
    return 0
  fi

  seed_postgres_in_docker
}