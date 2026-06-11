# Purpose: Dedicated startup block for the metadata-ingestion profile.

start_stack_block_metadata_ingestion() {
  if [ "$START_PHASE" != "pre" ] || [ "$START_METADATA_INGESTION" != "true" ]; then
    return 0
  fi

  PROFILE_ARGS+=(--profile metadata-ingestion)
  info "$my_name" "Metadata ingestion profile enabled"
}
