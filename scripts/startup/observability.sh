# Purpose: Dedicated startup block for the observability profile.

start_stack_block_observability() {
  if [ "$START_PHASE" != "pre" ] || [ "$START_OBSERVABILITY" != "true" ]; then
    return 0
  fi

  PROFILE_ARGS+=(--profile observability)
  info "$my_name" "Observability profile enabled"
}
