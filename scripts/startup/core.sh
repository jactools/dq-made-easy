# Purpose: Dedicated startup block for the core profile.

start_stack_block_core() {
  if [ "$START_PHASE" != "pre" ] || [ "$START_CORE" != "true" ]; then
    return 0
  fi

  PROFILE_ARGS+=(--profile core)
  info "$my_name" "Core profile enabled"
}
