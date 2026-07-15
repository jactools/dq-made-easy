# Purpose: Dedicated seed block for the metadata profile.

source "$ROOT_DIR/scripts/supporting/openmetadata.sh"

seed_openmetadata_in_docker() {
  info "$my_name" "Seeding OpenMetadata in Docker (auth configuration, users, catalog sync, contracts)..."

  if [ "$SEED_KEYCLOAK" = "false" ]; then
    info "$my_name" "--seed-openmetadata requested without --seed-keycloak; reseeding Keycloak first so the live realm matches the generated credentials"
    seed_keycloak_in_docker || {
      error "$my_name" "Keycloak reseed failed before OpenMetadata seeding"
      exit 35
    }
    # Keycloak seeding starts keycloak + openmetadata services
  else
    # Keycloak was already seeded; only start OpenMetadata services.
    # Do NOT start keycloak here — its dependency on keycloak-seed-artifacts
    # would regenerate random passwords that are not yet applied to the live
    # Keycloak, causing the openmetadata-configure password grant to fail.
    docker_compose up -d openmetadata-server openmetadata-ingestion || {
      error "$my_name" "Failed to start OpenMetadata services for seeding"
      exit 35
    }
  fi

  if ! dq_source_seeded_user_credentials --quiet; then
    error "$my_name" "Unable to load seeded Keycloak credentials for OpenMetadata seeding"
    exit 35
  fi

  prepare_openmetadata_access_token || {
    error "$my_name" "Unable to prepare OM_TOKEN for OpenMetadata seeding"
    exit 35
  }

  docker_compose --profile metadata --profile auth run --rm openmetadata-configure --seed-all || {
    error "$my_name" "OpenMetadata Docker seed container failed"
    exit 35
  }

  info "$my_name" "✓ OpenMetadata seeding complete via Docker Compose"
}

seed_stack_block_openmetadata() {
  if [ "$SEED_OPENMETADATA" != "true" ]; then
    return 0
  fi

  seed_openmetadata_in_docker
}