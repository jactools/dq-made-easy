# Incident Runbook: API 5xx Error Spike

**Alert:** `dq_api_5xx_spike`  
**Severity:** Critical  
**Service:** dq-api (FastAPI)  
**Correlation Field:** `correlationId` from request logs  

## Detection

Alert fires when HTTP 5xx error rate exceeds 1% over 5 minutes.

## Investigation Steps

1. **Access Logs**
   ```bash
   # Check API logs in Loki or ELK for correlation IDs of failed requests
   {job="dq-api"} | json | level="ERROR" | http_status >= 500
   ```

2. **Identify Root Cause**
   - Check `msg` field for exception type (DB connection, validation, auth failure)
   - Check `correlationId` for cross-service trace across engine/worker
   - Check API resource usage (CPU, memory) via Prometheus

3. **Check Database Connection**
   ```bash
   # Verify database health
   docker exec <db-container> psql -U postgres -d dq -c "\dt"
   # Check connection pool status in logs
   ```

4. **Check Redis Cache**
   ```bash
   # Verify Redis is responding
   redis-cli ping
   # Check memory usage
   redis-cli info memory
   ```

5. **Check Recent Deployments**
   - Verify no code changes causing panics
   - Check environment variable misconfigurations (database URL, auth settings)

## Mitigation

- **Immediate:** Restart API service to reset connection pools
  ```bash
  docker-compose restart api
  ```
- **Short-term:** Scale API horizontally if load is high
- **Long-term:** Add circuit breakers for downstream service failures

## Recovery

- Once API service recovers, monitor error rate normalization
- Ensure correlation IDs are properly logged for root cause analysis
- Create incident ticket with sampled 5xx logs and correlation chains

## Escalation

- If error rate persists > 5 minutes, page on-call SRE
- If API is completely down, activate disaster recovery runbook
