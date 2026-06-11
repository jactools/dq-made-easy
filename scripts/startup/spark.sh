# Purpose: Dedicated startup block for the Spark cluster profile.
#
# Version: 1.0
# Last modified: 2026-06-02

start_stack_block_spark() {
  case "$START_PHASE" in
    pre)
      if [ "$START_SPARK" != "true" ]; then
        return 0
      fi

      PROFILE_ARGS+=(--profile spark)
      DQ_SPARK_MASTER="${DQ_SPARK_MASTER:-spark://spark-master:7077}"
      export DQ_SPARK_MASTER
      info "$my_name" "Spark profile enabled"
      info "$my_name" "Spark master set to ${DQ_SPARK_MASTER}"
      ;;
    post)
      if [ "$START_SPARK" != "true" ]; then
        info "$my_name" "Spark profile disabled: skipping Spark cluster readiness checks"
        return 0
      fi

      info "$my_name" "Spark cluster requested; waiting is handled by the Spark services themselves"
      ;;
  esac
}
