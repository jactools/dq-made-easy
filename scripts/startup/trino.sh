# Purpose: Dedicated startup block for the trino profile.

start_stack_block_trino() {
  if [ "$START_PHASE" != "pre" ] || [ "$START_TRINO" != "true" ]; then
    return 0
  fi

  PROFILE_ARGS+=(--profile trino)
  info "$my_name" "Trino profile enabled"
}