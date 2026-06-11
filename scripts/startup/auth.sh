# Purpose: Dedicated startup block for the auth profile.

start_stack_block_auth() {
  if [ "$START_PHASE" != "pre" ] || [ "$START_AUTH" != "true" ]; then
    return 0
  fi

  PROFILE_ARGS+=(--profile auth)
  info "$my_name" "Auth profile enabled"
}
