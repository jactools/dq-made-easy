# Incident Runbook: Executor Timeout Spike

**Alert:** `dq_executor_timeout_spike`  
**Severity:** High  
**Service:** dq-engine (Python) + dq-profiling (Node.js worker)  
**Correlation Field:** `correlationId`, `runId` in execution logs  

## Detection

Alert fires when rule execution timeout rate exceeds 5% over 5 minutes.

## Investigation Steps

1. **Access Execution Logs**
   ```bash
   # Check engine logs for timeout events
   {job="dq-engine"} | json | event="execution_timeout"
   # Check worker logs for job timeouts
   {job="dq-profiling-worker"} | json | event="job_timeout"
   ```

2. **Identify Affected Rules**
   - Extract `ruleId` and `runId` from timeout events
   - Check if timeouts are rule-specific or data-volume related
   - Correlate `dataObjectId` to identify problematic datasets

3. **Check System Resources**
   ```bash
   # Check worker queue depth
   redis-cli LLEN "bull:dq-profiling-worker:active"
   redis-cli LLEN "bull:dq-profiling-worker:wait"
   # Check CPU and memory on engine/worker containers
   docker stats dq-engine dq-profiling-worker
   ```

4. **Check Database Performance**
   - Verify database is not slow/unresponsive
   - Check for long-running queries blocking rule execution
   ```sql
   SELECT pid, query, query_start FROM pg_stat_activity 
   WHERE state = 'active' ORDER BY query_start;
   ```

5. **Analyze Rule Complexity**
   - Check timeout rules for high JOIN complexity
   - Verify data object row counts are within expected range

## Mitigation

- **Immediate:** Increase executor timeout threshold temporarily
  ```bash
  # Update engine config
  docker-compose restart dq-engine -e DQ_EXECUTION_TIMEOUT_SECONDS=120
  ```
- **Short-term:** Disable heavy rules or reduce data volume scope
- **Long-term:** Optimize slow-executing rules or add database indexes

## Recovery

- Once timeouts normalize, gradually reduce timeout threshold back to baseline
- Monitor individual rule execution times to identify optimization opportunities
- Document timeout-prone rules for future optimization planning

## Escalation

- If > 100 concurrent timeouts, page on-call database team
- If persists > 15 minutes, consider disabling user-initiated rule executions
