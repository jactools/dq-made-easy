# Purpose: Dedicated startup block for the edge profile.

start_stack_block_edge() {
  if [ "$START_PHASE" != "pre" ] || [ "$START_EDGE" != "true" ]; then
    return 0
  fi

  PROFILE_ARGS+=(--profile edge)
  info "$my_name" "Edge profile enabled"
}
