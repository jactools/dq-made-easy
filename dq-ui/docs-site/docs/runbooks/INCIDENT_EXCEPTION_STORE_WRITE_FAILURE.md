# Incident Runbook: Exception Store Write Failure

**Alert:** `dq_exception_store_write_failure`  
**Severity:** Critical  
**Service:** dq-engine (Python) + Database (PostgreSQL)  
**Correlation Field:** `correlationId`, `runId` in logs  

## Detection

Alert fires when exception-store write operations fail for > 5 minutes or drop rate across 10+ consecutive attempts.

## Investigation Steps

1. **Access Engine Exception Logs**
   ```bash
   # Check engine logs for write failures
   {job="dq-engine"} | json | event="exception_write_failure"
   # Extract error messages
   {job="dq-engine"} | json | event="exception_write_failure" | stats count by exception
   ```

2. **Verify Database Connectivity**
   ```bash
   # Test database connection and schema
   docker exec <db-container> psql -U postgres -d dq -c "SELECT COUNT(*) FROM exceptions;"
   # Check exception table exists and has proper schema
   docker exec <db-container> psql -U postgres -d dq -c "\d exceptions"
   ```

3. **Check Database Disk Space**
   ```bash
   # Check disk availability
   docker exec <db-container> df -h /var/lib/postgresql/data
   # Check table size
   docker exec <db-container> psql -U postgres -d dq -c "SELECT pg_size_pretty(pg_total_relation_size('exceptions'));"
   ```

4. **Check Database Performance**
   ```bash
   # Verify database is responding
   docker exec <db-container> psql -U postgres -d dq -c "SELECT NOW();"
   # Check for slow/blocking queries
   docker exec <db-container> psql -U postgres -d dq -c "SELECT * FROM pg_stat_activity WHERE state != 'idle';"
   ```

5. **Verify Exception Table Permissions**
   ```bash
   # Verify application user has INSERT permission
   docker exec <db-container> psql -U postgres -d dq -c "GRANT INSERT ON exceptions TO postgres;"
   ```

## Mitigation

- **Immediate:** Restart database service to reset connections
  ```bash
  docker-compose restart db
  ```
- **Short-term:** Clear old exceptions to free space if disk pressure
  ```sql
  DELETE FROM exceptions WHERE created_at < NOW() - INTERVAL '30 days';
  VACUUM ANALYZE exceptions;
  ```
- **Long-term:** Implement retention policy with automated cleanup

## Recovery

- Verify exception writes succeed post-recovery
- Reprocess any exceptions that failed to write (check correlation IDs)
- Monitor exception store write latency for 15 minutes
- Create incident ticket with failed write correlation IDs for audit trail

## Escalation

- If database is unresponsive, page on-call DBA
- If disk is full, activate emergency cleanup and request capacity increase
- If > 1000 exceptions fail to write, declare severity-0 incident (data loss risk)
