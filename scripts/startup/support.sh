# Purpose: Dedicated startup block for the support profile.

start_stack_block_support() {
  if [ "$START_PHASE" != "pre" ] || [ "$START_SUPPORT" != "true" ]; then
    return 0
  fi

  PROFILE_ARGS+=(--profile support)
  info "$my_name" "Support profile enabled"
}
