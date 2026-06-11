# Purpose: Dedicated startup block for the profiling profile.

start_stack_block_profiling() {
  if [ "$START_PHASE" != "pre" ] || [ "$START_PROFILING" != "true" ]; then
    return 0
  fi

  PROFILE_ARGS+=(--profile profiling)
  info "$my_name" "Profiling profile enabled"
}
