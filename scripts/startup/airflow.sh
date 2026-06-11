# Purpose: Dedicated startup block for the Airflow profile.

start_stack_block_airflow() {
  if [ "$START_PHASE" != "pre" ] || [ "$START_AIRFLOW" != "true" ]; then
    return 0
  fi

  PROFILE_ARGS+=(--profile airflow)
  info "$my_name" "Airflow profile enabled"
}