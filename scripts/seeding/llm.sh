# Purpose: Dedicated seed block for the llm profile.
# Version: 1.0
# Last modified: 2026-07-01

start_llm_in_docker() {
  info "$my_name" "Starting dq-made-easy-llm in Docker Compose..."

  docker_compose --profile llm up -d dq-made-easy-llm || {
    error "$my_name" "dq-made-easy-llm start failed"
    exit 37
  }

  info "$my_name" "✓ dq-made-easy-llm started via Docker Compose"
}

seed_stack_block_llm() {
  if [ "$START_LLM" != "true" ]; then
    return 0
  fi

  start_llm_in_docker
}