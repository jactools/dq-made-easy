# Purpose: Dedicated startup block for the workers profile.

start_stack_block_workers() {
  if [ "$START_PHASE" != "pre" ] || [ "$START_WORKERS" != "true" ]; then
    return 0
  fi

  PROFILE_ARGS+=(--profile workers)
  info "$my_name" "Workers profile enabled"
}
