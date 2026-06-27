# Purpose: Legacy Spark cluster startup hook retained as a no-op.
#
# The repository now defaults to local Spark execution and no longer relies on
# the optional master/worker containers defined in docker-compose.yml.

start_stack_block_spark() {
  case "$START_PHASE" in
    pre)
      if [ "$START_SPARK" != "true" ]; then
        return 0
      fi

      info "$my_name" "Spark cluster profile is disabled; using local Spark by default"
      ;;
    post)
      if [ "$START_SPARK" != "true" ]; then
        info "$my_name" "Spark profile disabled: skipping Spark cluster readiness checks"
        return 0
      fi

      info "$my_name" "Spark cluster profile is disabled; local Spark remains the default runtime"
      ;;
  esac
}
