# Purpose: Dedicated startup block for the metadata profile.

start_stack_block_metadata() {
  if [ "$START_PHASE" != "pre" ] || [ "$START_METADATA" != "true" ]; then
    return 0
  fi

  PROFILE_ARGS+=(--profile metadata)
  info "$my_name" "Metadata profile enabled: OpenMetadata services will be included"
}
