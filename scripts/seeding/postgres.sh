# Purpose: Dedicated seed block for the postgres profile.

seed_postgres_in_docker() {
  info "$my_name" "Reseeding Postgres in Docker (SQL generation, Alembic, Keycloak external-id mapping)..."

  if ! remove_compose_postgres_volume; then
    error "$my_name" "Failed to remove the PostgreSQL data volume before reseeding"
    exit 34
  fi

  docker_compose up -d db keycloak || {
    error "$my_name" "Failed to start db/keycloak for Postgres seeding"
    exit 34
  }

  wait_for_compose_service_healthy db "Postgres database" 60 2 || {
    error "$my_name" "Postgres database did not become healthy before seeding"
    exit 34
  }

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