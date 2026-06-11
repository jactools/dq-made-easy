# Purpose: Dedicated startup block for the base profile.

start_stack_block_base() {
  if [ "$START_PHASE" != "pre" ] || [ "$START_BASE" != "true" ]; then
    return 0
  fi

  PROFILE_ARGS+=(--profile base)
  info "$my_name" "Base profile enabled"
}
