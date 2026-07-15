# ADR-005: Health and Readiness Endpoints

**Status**: Implemented  
**Date**: 2026-03-02

### Context
Running behind a gateway and Kubernetes requires standard health endpoints for load balancer configuration and orchestration.

### Decision
Implement health endpoints following Kubernetes conventions:
- `/v1/health` - Overall health with component checks (database, redis)
- `/v1/ready` - Readiness probe (can accept traffic)
- `/v1/live` - Liveness probe (process is alive)
- `/v1/info` - Service metadata and API discovery

**Implementation**:
- Created `health.controller.ts` with all 4 endpoints
- Database connectivity check with response time
- Returns structured health status

### Consequences
**Positive**:
- Gateway/load balancer can route traffic based on health
- Kubernetes can auto-restart unhealthy pods
- Monitoring systems can scrape health endpoint
- `/info` enables API version discovery

**Negative**:
- Health checks add database load (negligible with simple SELECT 1)

---

