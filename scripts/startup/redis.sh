# Purpose: Dedicated startup block for the redis profile.

start_stack_block_redis() {
  if [ "$START_PHASE" != "pre" ] || [ "$START_REDIS" != "true" ]; then
    return 0
  fi

  PROFILE_ARGS+=(--profile redis)
  info "$my_name" "Redis profile enabled"
}
