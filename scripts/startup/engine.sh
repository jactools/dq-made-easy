# Purpose: Dedicated startup block for the engine profile.

start_stack_block_engine() {
  case "$START_PHASE" in
    pre)
      if [ "$START_ENGINE" != "true" ]; then
        return 0
      fi

      PROFILE_ARGS+=(--profile engine)
      info "$my_name" "Engine profile enabled"
      ;;
    post)
      if [ "$START_ENGINE" != "true" ]; then
        info "$my_name" "Engine profile disabled: skipping dq-engine readiness checks"
        return 0
      fi

      DQ_ENGINE_READY_URL="${DQ_ENGINE_LOCAL_URL:?DQ_ENGINE_LOCAL_URL is required when --with-engine is enabled}"
      info "$my_name" "Waiting for dq-engine ($DQ_ENGINE_READY_URL) to become available..."
      ENGINE_MAX=30
      engine_ok=0
      for i in $(seq 1 $ENGINE_MAX); do
        eng_code=$(curl --max-time 2 -s -o /dev/null -w "%{http_code}" "${DQ_ENGINE_READY_URL}/docs" || true)
        eng_code="${eng_code:-000}"
        if [[ "$eng_code" != "000" ]]; then
          info "$my_name" "dq-engine responded with HTTP $eng_code"
          engine_ok=1
          break
        fi

        sleep 1
      done

      if [[ "$engine_ok" -ne 1 ]]; then
        warning "$my_name" "dq-engine did not respond after $ENGINE_MAX seconds"
        exit 22
      else
        info "$my_name" "dq-engine is up at $DQ_ENGINE_READY_URL"
      fi
      ;;
  esac
}
