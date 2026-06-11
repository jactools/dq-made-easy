# Purpose: Dedicated seed block for the zammad profile.

seed_zammad_in_docker() {
  info "$my_name" "Seeding Zammad in Docker (auto wizard, organizations, user import, support token persistence)..."

  docker_compose up -d db zammad-railsserver || {
    error "$my_name" "Failed to start db and Zammad support services"
    exit 36
  }

  docker_compose --profile support run --rm zammad-seed || {
    error "$my_name" "Zammad Docker seed container failed"
    exit 36
  }

  info "$my_name" "✓ Zammad reseed completed via Docker Compose"
}

seed_stack_block_zammad() {
  if [ "$SEED_ZAMMAD" != "true" ]; then
    return 0
  fi

  seed_zammad_in_docker
}