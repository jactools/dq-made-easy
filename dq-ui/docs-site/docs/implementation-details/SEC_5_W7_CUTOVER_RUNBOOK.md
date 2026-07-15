# SEC-5 Workstream 7-04: End-to-End Cutover Runbook

**Status**: Operational Guide  
**Last Updated**: 2026-07-09  
**Audience**: DevOps, Platform Engineering, Operators  

---

## Overview

This runbook provides the step-by-step procedure to complete the SEC-5 end-to-end no-HTTP TLS migration. It covers pre-cutover validation, per-service migration sequencing, and rollback procedures to ensure zero downtime and fast failure recovery.

## Pre-Cutover Validation Checklist

Before migrating any service to TLS-only mode:

- [ ] **W1-W5 Validation Complete**: Run `./scripts/validate_tls_backend_direct_routing.sh` — all tests pass
  - W6 verification: edge SNI passthrough works
  - W6 verification: backends are TLS-native
  - W6 verification: backend certs include user-facing SNI
  
- [ ] **Certificate Inventory**: Run `./scripts/validation/validate_tls_certificate_inventory.sh`
  - Mkcert root CA exists at `/tmp/certs/mkcert-rootCA.pem`
  - Every TLS listener has matching leaf cert + SAN set
  - No self-signed certs from prior builds
  
- [ ] **Trust Bundle**: Run `./scripts/validation/validate_tls_trust_bundle_conventions.sh`
  - Canonical bundle at `/tmp/certs/trust/internal-ca-bundle.pem`
  - All services mount correct bundle paths
  - No ad hoc cert paths
  
- [ ] **Smoke Tests Pass**: Run `./scripts/validate_tls_service_paths.sh`
  - Browser paths work over HTTPS
  - Service-to-service paths work over TLS
  - No HTTP fallback detected
  - Healthchecks verify TLS
  
- [ ] **Observability Ready**: Prometheus and Loki configured with:
  - TLS connection metrics baseline captured
  - Certificate expiry alerts active
  - Latency baseline for TLS handshake overhead recorded

---

## Service Migration Sequence

### Phase 1: LOCAL Mode (Development)

**Duration**: Immediate (already live after W6)

**Sequence**:
1. ✅ **Zammad Support Stack** (completed in W6)
   - Edge: SNI passthrough (no termination)
   - Rails server: native TLS port 3000
   - Websocket: native TLS port 6042
   - Healthchecks: TLS-verified
   
2. **Remaining LOCAL Services** (if applicable)
   - Airflow: host-bind exception (no migration required yet)
   - Any other direct-bind services

**Sign-Off**:
- [ ] Browser can reach support.jac.dot (healthcheck passes)
- [ ] Browser UI loads without SSL errors
- [ ] Healthcheck logs show TLS verification success

---

### Phase 2: PUBLIC Mode (Production Preparation)

**Duration**: TBD (requires SNI-based routing redesign)

**Sequence** (Future planning):

1. **Frontend**
   - Migrate to SNI-based hostname routing
   - Update public edge to route by SNI (not path)
   - Verify certificate matches public hostname
   
2. **API/Kong Gateway**
   - Convert Kong admin API from HTTP to TLS
   - Update consumer clients to use HTTPS
   - Verify service-to-service calls use TLS
   
3. **Keycloak**
   - Migrate Keycloak from HTTP to TLS
   - Update client redirect URIs
   - Verify federation over TLS
   
4. **OpenMetadata**
   - Already TLS-native (W4 complete)
   - Verify external ingestion uses HTTPS
   
5. **Metadata Services (Engine, Profiling, etc.)**
   - Migrate to TLS listeners
   - Update service discovery
   - Verify inter-service TLS

**Sign-Off** (per service):
- [ ] Service healthchecks pass over TLS
- [ ] Clients successfully connect with certificate validation
- [ ] No HTTP fallback paths remain
- [ ] Latency/performance acceptable with TLS overhead

---

## Migration Procedure (Per Service)

### Pre-Migration Steps (for any service)

```bash
# 1. Generate/verify TLS certificate for the service
export EDGE_LOCAL_SERVICE_HOST="service.jac.dot"  # or your local domain
./scripts/create_certs.sh

# 2. Verify certificate was created
ls -la tmp/certs/services/{service-name}/tls.*

# 3. Run service-specific validation
./scripts/validation/validate_tls_certificate_inventory.sh

# 4. Capture baseline metrics (latency, connection time)
# See "Observability" section below
```

### Migration Steps

1. **Update Service Configuration**
   ```yaml
   # docker-compose.yml
   service-name:
     command: [
       "start-service",
       "--tls-key=/etc/service/certs/tls.key",
       "--tls-cert=/etc/service/certs/tls.crt",
       "--port=3000"  # Change to TLS port
     ]
     volumes:
       - ./tmp/certs/services/service-name:/etc/service/certs:ro
     healthcheck:
       test: ["CMD-SHELL", 
              "curl -fsS --cacert /etc/service/certs/mkcert-rootCA.pem https://127.0.0.1:3000/health"]
   ```

2. **Update Clients/Callers**
   ```bash
   # Update any service that calls this service
   OLD: http://service-name:3000
   NEW: https://service-name:3000
   
   # Ensure TLS verification is enabled
   --cacert /path/to/mkcert-rootCA.pem
   ```

3. **Update Edge Routing** (if applicable)
   ```bash
   # For LOCAL mode SNI passthrough:
   ${service_host} service-name:3000  # No intermediate proxy
   ```

4. **Restart Service**
   ```bash
   docker-compose up -d service-name
   ```

5. **Verify Healthcheck**
   ```bash
   # Wait for healthcheck to pass
   sleep 5
   docker-compose ps | grep service-name  # Should show "healthy"
   ```

### Post-Migration Verification

```bash
# Test TLS connection from host
openssl s_client -connect 127.0.0.1:3000 \
  -CAfile tmp/certs/mkcert-rootCA.pem \
  -servername service.jac.dot

# Verify certificate has correct SAN
openssl s_client -connect 127.0.0.1:3000 \
  -servername service.jac.dot 2>/dev/null | \
  openssl x509 -noout -text | grep -A1 "Subject Alternative Name"

# Test from another container
docker exec edge-container openssl s_client \
  -connect service-name:3000 \
  -CAfile /etc/nginx/certs/mkcert-rootCA.pem
```

---

## Rollback Procedure

If a service migration fails or causes issues:

### Immediate Rollback (< 5 minutes)

```bash
# 1. Revert docker-compose.yml changes
git checkout docker-compose.yml

# 2. Restart service with previous config
docker-compose up -d service-name

# 3. Revert any client configuration changes
git checkout dq-api/config.yaml  # or relevant config files

# 4. Restart all dependent services
docker-compose restart dq-api  # or affected services

# 5. Verify healthchecks pass
docker-compose ps
```

### Root Cause Analysis

```bash
# 1. Check service logs for TLS errors
docker logs service-name | tail -50

# 2. Verify certificate is valid
openssl x509 -in tmp/certs/services/service-name/tls.crt -noout -text

# 3. Check if CA bundle is accessible
docker exec service-name cat /etc/service/certs/mkcert-rootCA.pem

# 4. Verify DNS/hostname resolution
docker exec service-name getent hosts service-name

# 5. Test TLS connection manually
docker exec service-name \
  curl -v --cacert /etc/service/certs/mkcert-rootCA.pem \
  https://localhost:3000/health
```

---

## Observability During Cutover

### Baseline Metrics (Before Migration)

Capture these metrics before any service migration:

```bash
# Connection time
time curl http://service-name:3000/health

# TLS handshake time (post-migration)
time curl https://service-name:3000/health --cacert ...

# Error rate from client application
curl http://service-name:3000/health -w "%{http_code}\n" -o /dev/null

# Certificate verification time (not applicable for HTTP, but shows TLS overhead)
time openssl s_client -connect service-name:3000 </dev/null 2>/dev/null
```

### Real-Time Monitoring During Cutover

**Watch logs for TLS errors**:
```bash
# Container logs
docker logs -f service-name | grep -i "tls\|ssl\|cert\|verify"

# Application logs (if structured)
docker exec service-name tail -f /var/log/service/error.log
```

**Monitor connection failures**:
```bash
# Check Prometheus alerts
# - `TLSConnectionErrors` > 0
# - `CertificateVerificationFailures` > 0
# - `ServiceHealthcheckFailures` > 0
```

**Latency overhead tracking**:
```bash
# Compare metrics before/after
# If TLS adds > 50ms per request, investigate:
#   - Certificate generation quality
#   - TLS version (use 1.3 when possible)
#   - Hardware acceleration availability
```

### Post-Cutover Validation

After each service migration, verify:

```bash
# 1. Service health
docker-compose ps | grep service-name

# 2. Certificate expiry not imminent
openssl x509 -in tmp/certs/services/service-name/tls.crt \
  -noout -dates

# 3. No HTTP fallback in logs
docker logs service-name | grep -i "http://" | wc -l  # Should be 0

# 4. TLS verification working
docker exec dependent-service \
  curl --cacert /etc/certs/mkcert-rootCA.pem \
  https://service-name:3000/health

# 5. Run smoke test
./scripts/sec5-w7-tls-smoke-tests.sh
```

---

## Communication Template

### Pre-Cutover Announcement

```
Subject: SEC-5 TLS Migration: [Service Name] - [Date] [Time-Window]

The [Service Name] will be migrated to TLS-only communication on [Date] 
from [Start-Time] to [End-Time] UTC.

Expected Impact:
- Brief service restart (< 1 minute)
- No data loss
- Brief latency increase from TLS handshake (~10-50ms)

Rollback Plan:
- If issues detected, automatic rollback in < 5 minutes
- All tests pass before cutover

Please monitor [dashboard URL] during the window.
Contact [ops-team] for issues.
```

### Post-Cutover Confirmation

```
✅ [Service Name] successfully migrated to TLS-only.

Verification:
- Healthchecks passing
- Zero HTTP connections detected
- Certificate verification working
- Smoke tests passing

Next Service: [Service Name] on [Date]
```

---

## Success Criteria Per Service

For each migrated service, confirm:

1. **TLS Listener Active**
   - Service listens on correct TLS port
   - Certificate is valid and not expired
   - SAN includes service hostname
   
2. **Certificate Verification Working**
   - Healthchecks verify TLS
   - External callers verify certificate
   - No certificate verification failures in logs
   
3. **No HTTP Fallback**
   - Zero HTTP requests/connections detected
   - Logs show no http:// URLs
   - Configuration has no HTTP fallback paths
   
4. **Performance Acceptable**
   - TLS overhead < 50ms per request
   - No connection timeouts
   - Healthcheck latency baseline established
   
5. **Observability Ready**
   - Certificate expiry alert configured
   - TLS error metrics collected
   - Logs parseable for TLS issues

---

## Full Cutover Readiness Checklist

When all services are TLS-native:

- [ ] **Configuration Audit**: No http:// URLs remain in compose, env, or code
  - Run: `grep -r "http://" . --exclude-dir=.git \| grep -v "http_proxy\\|HTTP_PROXY" \| wc -l` → 0
  
- [ ] **Certificate Lifecycle**: Automation in place for renewal
  - Mkcert CA will be refreshed periodically
  - Service certs will be regenerated at startup
  - Rotation tested for production readiness
  
- [ ] **Documentation Updated**: All runbooks reference HTTPS
  - API documentation shows HTTPS examples
  - Configuration guides use https:// URLs
  - Troubleshooting docs mention TLS issues
  
- [ ] **Exception Registry Current**: ARCH-EXC-0001 reflects reality
  - All exceptions listed with owner and retirement date
  - No undocumented HTTP services
  
- [ ] **Smoke Tests Passing**: Full W7 suite passes
  - W6 tests: SNI passthrough, backend TLS nativity ✅
  - W7-02 tests: Browser, healthcheck, service paths ✅
  - W7-01 validation: No HTTP regressions ✅

---

## Incident Response: TLS-Related Issues

### Certificate Verification Failures

**Symptom**: Logs show "certificate verify failed" or "CERTIFICATE_VERIFY_FAILED"

**Diagnosis**:
```bash
# 1. Check if CA bundle is correct
openssl x509 -in tmp/certs/mkcert-rootCA.pem -noout -text

# 2. Verify certificate chain
openssl s_client -connect service-name:3000 \
  -showcerts 2>/dev/null | openssl x509 -noout -text

# 3. Check hostname mismatch
openssl x509 -in tmp/certs/services/service-name/tls.crt \
  -noout -text | grep -A1 "Subject Alternative Name"
```

**Fix**:
- Regenerate certificates: `./scripts/create_certs.sh`
- Restart service: `docker-compose restart service-name`
- Verify: `docker-compose ps`

### Connection Refused

**Symptom**: TLS services refuse connections on specified port

**Diagnosis**:
```bash
# Check if service is actually listening
docker exec service-name netstat -tlnp | grep 3000

# Check service startup logs
docker logs service-name | tail -20
```

**Fix**:
- Verify port binding in config
- Check firewall/network policy
- Restart service with verbose logging

### Timeout Connecting to TLS Service

**Symptom**: Connections hang or timeout

**Diagnosis**:
```bash
# Check latency
time curl --cacert ... https://service-name:3000

# Check TLS handshake time
echo "" | openssl s_client -connect service-name:3000 -connect_timeout 5

# Check service load
docker stats service-name
```

**Fix**:
- Increase timeout if handshake overhead acceptable
- Reduce load on service if CPU/memory exhausted
- Check network latency

---

## Related Documents

- [SEC_5_END_TO_END_NO_HTTP_TLS_IMPLEMENTATION_PLAN.md](/docs/implementation-details/SEC_5_END_TO_END_NO_HTTP_TLS_IMPLEMENTATION_PLAN/)
- [SEC_5_W6_IMPLEMENTATION_STRATEGY.md](/docs/implementation-details/SEC_5_W6_IMPLEMENTATION_STRATEGY/)
- [SEC_5_NO_HTTP_CONTRACT_AND_EXCEPTION_BOUNDARY.md](/docs/implementation-details/SEC_5_NO_HTTP_CONTRACT_AND_EXCEPTION_BOUNDARY/)
- [ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md](/docs/architecture/ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS/)
