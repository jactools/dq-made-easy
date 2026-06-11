# Purpose: Dedicated startup block for the llm profile.

start_stack_block_llm() {
  if [ "$START_PHASE" != "pre" ] || [ "$START_LLM" != "true" ]; then
    return 0
  fi

  PROFILE_ARGS+=(--profile llm)
  info "$my_name" "LLM profile enabled"
}
