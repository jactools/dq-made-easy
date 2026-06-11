# Purpose: Dedicated seed block for the llm profile.

start_llm_in_docker() {
  info "$my_name" "Starting dq-llm in Docker Compose..."

  docker_compose --profile llm up -d dq-llm || {
    error "$my_name" "dq-llm start failed"
    exit 37
  }

  info "$my_name" "✓ dq-llm started via Docker Compose"
}

seed_stack_block_llm() {
  if [ "$START_LLM" != "true" ]; then
    return 0
  fi

  start_llm_in_docker
}