# Incident Runbook: Compile Failure Spike

**Alert:** `dq_compile_failure_spike`  
**Severity:** High  
**Service:** dq-engine (Python)  
**Correlation Field:** `correlationId`, `ruleId` in execution logs  

## Detection

Alert fires when rule compilation failure rate exceeds 10% over 5 minutes.

## Investigation Steps

1. **Access Engine Logs**
   ```bash
   # Check engine logs for compilation errors
   {job="dq-engine"} | json | event="compile_failure"
   # Group by failure type
   {job="dq-engine"} | json | event="compile_failure" | stats count by exception
   ```

2. **Identify Affected Rules**
   - Look for `ruleId` values in failed compilations
   - Check if failures are limited to specific rules or system-wide
   - Correlate rule changes in Git history

3. **Check Engine Health**
   ```bash
   # Verify engine is responsive
   curl http://dq-engine:8000/docs
   # Check resource usage
   docker stats dq-engine
   ```

4. **Check API Connectivity**
   - Verify engine can reach API service for rule retrieval
   - Check correlation propagation in logs (correlationId present)

5. **Validate Rule Syntax**
   - If specific rules fail consistently, download and test locally
   - Check for invalid rule definitions or schema mismatches

## Mitigation

- **Immediate:** Disable recently deployed rules if identified
  ```bash
  # Use API to pause rules with matching IDs
  curl -X PATCH http://api:4010/v1/rules/{ruleId}/status -d '{"status":"paused"}'
  ```
- **Short-term:** Rollback problematic rule definitions
- **Long-term:** Add pre-deployment rule validation in CI/CD

## Recovery

- Once underlying issue is fixed, resume disabled rules
- Monitor compilation success rate for 15 minutes
- Document root cause in incident ticket with failing rule details and correlation chains

## Escalation

- If > 50% of rules fail to compile, page on-call engineer
- If persists > 10 minutes, begin rule rollback procedure
