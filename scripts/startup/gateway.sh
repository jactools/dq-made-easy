# Purpose: Dedicated startup block for the gateway profile.
#
# Kong image and container lifecycle are managed by platform-foundation.
# This script retains the bootstrap_kong.sh deployment logic for
# deploying routes, services, consumers, and ACLs to Kong.

refresh_existing_kong_after_keycloak_seed_if_needed() {
  if [ "$SEED_KEYCLOAK" != "true" ] && [ "$SEED_ALL" != "true" ]; then
    return 0
  fi

  local keycloak_local_base="${KEYCLOAK_LOCAL_URL:-${KEYCLOAK_PUBLIC_URL:-https://${KEYCLOAK_PUBLIC_HOSTNAME:-keycloak.jac.dot}:9444}}"
  local keycloak_ready_url="${keycloak_local_base}"
  local bootstrap_src="$ROOT_DIR/dq-kong/scripts/bootstrap_kong.sh"

  info "$my_name" "Checking Keycloak readiness before Kong refresh..."
  if ! wait_for_keycloak_ready "$keycloak_ready_url" "Keycloak"; then
    warning "$my_name" "Keycloak reseed detected, but Keycloak is not ready yet; skipping Kong refresh"
    return 0
  fi

  if [ ! -f "$bootstrap_src" ]; then
    warning "$my_name" "Kong bootstrap source script not found at $bootstrap_src; skipping Kong refresh"
    return 0
  fi

  # Kong container is managed by platform-foundation; bootstrap runs externally
  info "$my_name" "Keycloak reseed detected -> run bootstrap_kong.sh to refresh Kong routes/plugins/JWT credentials"
  info "$my_name" "  Bootstrap script: $bootstrap_src"
  info "$my_name" "  (Kong container lifecycle managed by platform-foundation)"
}

start_stack_block_gateway() {
  case "$START_PHASE" in
    pre)
      if [ "$START_GATEWAY" != "true" ]; then
        return 0
      fi

      # Gateway profile (edge only) — Kong containers managed by platform-foundation
      PROFILE_ARGS+=(--profile gateway)
      info "$my_name" "Gateway profile enabled (edge service; Kong managed by platform-foundation)"
      ;;
    post)
      if [ "$START_GATEWAY" != "true" ]; then
        info "$my_name" "Gateway profile disabled"
        return 0
      fi

      local bootstrap_src="$ROOT_DIR/dq-kong/scripts/bootstrap_kong.sh"

      if [ ! -f "$bootstrap_src" ]; then
        warning "$my_name" "Kong bootstrap script not found at $bootstrap_src"
        return 0
      fi

      info "$my_name" "Kong bootstrap script available: $bootstrap_src"
      info "$my_name" "Kong container lifecycle is managed by platform-foundation."
      info "$my_name" "Deploy routes/ACLs by running bootstrap_kong.sh against the Kong Admin API."
      echo ""

      if [ "$SKIP_POST_STACK_KONG_REFRESH" != "true" ]; then
        refresh_existing_kong_after_keycloak_seed_if_needed
      fi
      ;;
  esac
}
