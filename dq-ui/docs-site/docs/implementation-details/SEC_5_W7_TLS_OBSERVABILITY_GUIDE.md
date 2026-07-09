# SEC-5 Workstream 7-03: TLS Failure Observability & Alerting

**Status**: Operational Guidance  
**Last Updated**: 2026-07-09  
**Audience**: DevOps, SRE, Operators  

---

## Overview

This document provides observability configuration and troubleshooting guides for TLS-related failures, listener mismatches, certificate issues, and proxy-routing regressions during SEC-5 compliance operations.

---

## Prometheus Alerts Configuration

Add these alert rules to `observability/prometheus/alerts.yml` to detect TLS failures:

### Alert 1: Certificate Expiry Warning (30 Days)

```yaml
- alert: SSLCertificateExpiringSoon
  expr: certifi_not_after - time() < 30 * 24 * 60 * 60
  for: 1h
  labels:
    severity: warning
  annotations:
    summary: "SSL Certificate expiring soon: {{ $labels.certificate }}"
    description: "Certificate {{ $labels.certificate }} will expire in {{ humanize ($value / 86400) }} days"
    runbook_url: "https://wiki.internal/runbooks/ssl-cert-expiry"
```

**Note**: Requires `certifi_exporter` or similar metrics source. Alternatively, use certificate monitoring:

```yaml
- alert: LocalCertificateExpiringSoon
  expr: |
    (time() - (1609459200 + (86400 * 365))) > (30 * 86400)
  for: 1h
  labels:
    severity: warning
  annotations:
    summary: "Generated certificates expiring in {{ humanize ((1609459200 + (86400 * 365) - time()) / 86400) }} days"
    description: "Regenerate certificates with ./scripts/create_certs.sh and restart services"
    service: "system"
```

### Alert 2: TLS Connection Failures

```yaml
- alert: TLSConnectionRefused
  expr: increase(http_requests_total{tls_error="connection_refused"}[5m]) > 0
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "TLS service refusing connections: {{ $labels.service }}"
    description: "Service {{ $labels.service }} on {{ $labels.endpoint }} is refusing TLS connections"
    runbook_url: "https://wiki.internal/runbooks/tls-connection-refused"

- alert: TLSCertificateVerificationFailures
  expr: increase(http_requests_total{tls_error="certificate_verify_failed"}[5m]) > 0
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Certificate verification failure: {{ $labels.service }}"
    description: "{{ $value }} certificate verification failures in past 5 minutes for {{ $labels.service }}"
    runbook_url: "https://wiki.internal/runbooks/tls-cert-verification-failed"
```

### Alert 3: TLS Handshake Timeout

```yaml
- alert: TLSHandshakeTimeout
  expr: increase(http_request_duration_seconds_bucket{le="+Inf", tls_handshake_timeout="true"}[5m]) > 5
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "TLS handshake timeouts: {{ $labels.service }}"
    description: "{{ $value }} TLS handshake timeouts in past 5 minutes for {{ $labels.service }}"
    runbook_url: "https://wiki.internal/runbooks/tls-handshake-timeout"
```

### Alert 4: Service Not Using TLS (Regression Detection)

```yaml
- alert: ServiceUsingPlaintextHttp
  expr: |
    count(http_requests_total{endpoint=~"127.0.0.1:.*", protocol="http"}) by (endpoint)
    unless
    count(http_requests_total{endpoint=~"127.0.0.1:.*", protocol="http", exception="true"}) by (endpoint)
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Service detected using plaintext HTTP (regression): {{ $labels.endpoint }}"
    description: "Service on {{ $labels.endpoint }} is accepting HTTP connections (should be HTTPS only)"
    runbook_url: "https://wiki.internal/runbooks/http-regression-detected"
```

### Alert 5: Healthcheck Latency Spike (TLS Overhead Baseline)

```yaml
- alert: HealthcheckLatencySpikeFromTLS
  expr: |
    rate(http_request_duration_seconds_sum{job="healthcheck", tls="true"}[5m])
    /
    rate(http_request_duration_seconds_count{job="healthcheck", tls="true"}[5m])
    > 0.05  # 50ms threshold for TLS overhead
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Healthcheck TLS latency spike: {{ $labels.service }}"
    description: "Healthcheck for {{ $labels.service }} taking {{ humanize $value }}s (expected: ~10-30ms)"
    runbook_url: "https://wiki.internal/runbooks/healthcheck-latency-spike"
```

---

## Loki Log Query Patterns

### Detect TLS Certificate Errors

```logql
{job="service"} | json | error =~ "certificate|verify|tls|ssl" | unwrap error_code | rate
```

### Detect HTTP Fallback Attempts

```logql
{job="edge"} | json | message =~ "http://" | stats count() by service
```

### Detect SNI Mismatch Errors

```logql
{job="edge"} | json | message =~ "sni|server_name|mismatch" | rate 5m
```

### Healthcheck TLS Verification Traces

```logql
{job="docker"} | json | ("healthcheck" in message or "tls" in message) | __error__ =""
```

---

## Manual Troubleshooting Guide

### Symptom: Certificate Verification Failed

**Error Example**:
```
curl: (60) SSL certificate problem: self signed certificate
ERROR: certificate verify failed (_ssl.c:997)
```

**Diagnosis Steps**:

```bash
# 1. Verify CA bundle exists and is readable
ls -la tmp/certs/mkcert-rootCA.pem
cat tmp/certs/mkcert-rootCA.pem | head -3

# 2. Inspect the service certificate
openssl x509 -in tmp/certs/services/service-name/tls.crt -noout -text

# 3. Check certificate chain
openssl s_client -connect service-name:3000 -showcerts 2>/dev/null | \
  openssl x509 -noout -text | grep -A5 "Subject:"

# 4. Verify certificate is signed by CA
openssl verify -CAfile tmp/certs/mkcert-rootCA.pem \
  tmp/certs/services/service-name/tls.crt

# 5. Test TLS connection with correct CA
openssl s_client -connect 127.0.0.1:3000 \
  -CAfile tmp/certs/mkcert-rootCA.pem \
  -servername service-name < /dev/null
```

**Fix**:

```bash
# Regenerate certificates if mkcert CA changed
./scripts/create_certs.sh

# Verify new certs
ls -la tmp/certs/services/service-name/tls.*

# Restart service
docker-compose restart service-name

# Test again
docker exec edge-container curl -v \
  --cacert /etc/nginx/certs/mkcert-rootCA.pem \
  https://service-name:3000/health
```

---

### Symptom: Connection Refused

**Error Example**:
```
curl: (7) Failed to connect to service-name port 3000: Connection refused
ECONNREFUSED: Connection refused
```

**Diagnosis Steps**:

```bash
# 1. Check if service is running
docker-compose ps service-name

# 2. Check if port is actually listening
docker exec service-name netstat -tlnp | grep 3000
docker exec service-name ss -tlnp | grep 3000

# 3. Check service logs for startup errors
docker logs service-name | tail -30 | grep -i "error\|fail\|tls\|ssl"

# 4. Check if firewall/network policy is blocking
docker exec service-name curl -v http://localhost:3000/health 2>&1 | head -20

# 5. Check service configuration for port binding
docker inspect service-name | grep -A20 "Ports\|ExposedPorts"
```

**Fix**:

```bash
# Check configuration file
grep -A10 "service-name:" docker-compose.yml | grep -E "ports:|listen|:3000"

# Ensure TLS port is correctly bound
# Example for Puma: -b ssl://[::]:3000?key=...&cert=...

# Restart service with debug logging
docker-compose logs -f service-name &
docker-compose restart service-name

# Wait for healthcheck to pass
sleep 10
docker-compose ps service-name
```

---

### Symptom: SNI Hostname Mismatch

**Error Example**:
```
openssl: Received alert: (119) unrecognized_name
Curl error: (51) Peer certificate cannot be authenticated with given CA certificates
```

**Diagnosis Steps**:

```bash
# 1. Get the certificate's Subject Alternative Names (SANs)
openssl x509 -in tmp/certs/services/service-name/tls.crt \
  -noout -text | grep -A2 "Subject Alternative Name"

# 2. Test TLS connection with SNI
openssl s_client -connect 127.0.0.1:3000 \
  -servername service-name \
  -CAfile tmp/certs/mkcert-rootCA.pem < /dev/null

# 3. Check what SNI name the edge is sending
# (requires debug logging or packet capture)

# 4. Verify certificate CN and SAN match expected hostname
openssl x509 -in tmp/certs/services/service-name/tls.crt \
  -noout -subject -text | grep -E "Subject:|DNS:"
```

**Fix**:

```bash
# Regenerate certificate with correct hostname
export EDGE_LOCAL_SERVICE_HOST="service.jac.dot"
./scripts/create_certs.sh

# Restart service
docker-compose restart service-name

# Verify new cert has correct SAN
openssl x509 -in tmp/certs/services/service-name/tls.crt \
  -noout -text | grep -A2 "Subject Alternative Name"
```

---

### Symptom: Healthcheck Latency Spike

**Observed**: Healthcheck latency increases from 10ms to 100ms+ after TLS migration

**Diagnosis Steps**:

```bash
# 1. Baseline: Test HTTP response time
for i in {1..10}; do
  time curl http://localhost:3000/health 2>&1 | tail -2
done

# 2. With TLS: Test HTTPS response time
for i in {1..10}; do
  time curl --cacert tmp/certs/mkcert-rootCA.pem https://localhost:3000/health 2>&1 | tail -2
done

# 3. Measure TLS handshake time only
time echo "" | openssl s_client -connect localhost:3000 2>/dev/null

# 4. Check service CPU/memory during healthcheck
docker stats service-name --no-stream

# 5. Check if persistent TLS session reuse is working
# (subsequent requests should be faster than first)
```

**Expected**: TLS handshake adds 10-30ms, but should be amortized with keep-alive  
**Acceptable Threshold**: < 50ms TLS overhead per request

**Fix** (if spike is excessive):

```bash
# 1. Use TLS 1.3 (faster than 1.2)
# In docker-compose: ssl_protocols TLSv1.3

# 2. Enable session reuse
# Ensure curl/client uses Keep-Alive

# 3. Check if hardware acceleration is available
# openssl speed  (shows if AES-NI available)

# 4. Reduce certificate size if using very long chains
```

---

### Symptom: HTTP Regression Detected

**Error Example**: Configuration audit finds `http://` URL in production service

**Diagnosis Steps**:

```bash
# 1. Find all HTTP references
grep -r "http://" docker-compose.yml dq-api/ scripts/ --exclude-dir=.git | \
  grep -v "http_proxy\|HTTP_PROXY\|http://" | head -20

# 2. Identify which service still uses HTTP
grep "http://" docker-compose.yml | grep -v "#"

# 3. Check if it's a documented exception
grep -r "ARCH-EXC" . | grep -i "http"

# 4. Check git history for when it was introduced
git log -p --all -S 'http://' -- docker-compose.yml | head -100
```

**Fix**:

```bash
# 1. If not documented exception: convert to HTTPS
# Update: http://service-name:8000 → https://service-name:443

# 2. If documented exception: verify owner and retirement date
# Update ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md

# 3. Run validation to confirm fix
./scripts/sec5-w6-smoke-tests.sh
./scripts/sec5-w7-tls-smoke-tests.sh
```

---

## Metrics Configuration Examples

### For Prometheus via curl wrapper

Add to services that need TLS instrumentation:

```yaml
# Pseudo-metric collection (requires custom exporter or script)
tls_certificate_expiry_timestamp_seconds{service="service-name"}
tls_connection_errors_total{service="service-name", error_type="verify_failed"}
tls_handshake_duration_seconds{service="service-name"}
http_requests_total{service="service-name", protocol="https"}
```

### For Docker healthcheck logs

Parse Docker healthcheck output for timing:

```bash
# Extract healthcheck duration
docker inspect container-name | jq '.State.Health.Log[-1]' | grep -o "duration: [0-9]*ms"
```

---

## Dashboards & Visualization

### Grafana Dashboard for SEC-5 TLS Health

Create a dashboard with:

1. **Certificate Expiry Countdown**
   - Shows days until certificate expiration
   - Red when < 7 days, yellow when < 30 days

2. **TLS Connection Status**
   - Services using TLS vs. HTTP
   - Connection success rate
   - Failures by type (verify, timeout, refused)

3. **Healthcheck Latency Baseline**
   - TLS handshake time
   - Request latency with/without TLS
   - Timeout rate

4. **HTTP Regression Detection**
   - Count of HTTP connections over time
   - Alert when HTTP detected

5. **SNI/Certificate Mismatch Rate**
   - Failed SNI negotiations
   - Certificate hostname mismatches

---

## Runbook References

Link to incident response playbooks:

- [TLS Certificate Verification Failed](/docs/implementation-details/SEC_5_W7_CUTOVER_RUNBOOK/#certificate-verification-failures)
- [Connection Refused on TLS Port](/docs/implementation-details/SEC_5_W7_CUTOVER_RUNBOOK/#connection-refused)
- [Healthcheck Latency Spike](/docs/implementation-details/SEC_5_W7_CUTOVER_RUNBOOK/#timeout-connecting-to-tls-service)
- [HTTP Regression Detected](/docs/implementation-details/SEC_5_W7_CUTOVER_RUNBOOK/#incident-response-tls-related-issues)

---

## Integration with Existing Observability

### Fluent Bit / Logstash Configuration

Add parsing for TLS errors:

```
<match service-tls-errors>
  @type forward
  <buffer>
    @type file
    path /var/log/fluentd/tls-errors.buffer
  </buffer>
  <server>
    host loki
    port 3100
  </server>
</match>
```

### Alert Manager Routing

Ensure TLS-related alerts route to correct team:

```yaml
route:
  - match:
      severity: critical
      category: tls
    receiver: platform-engineering
    repeat_interval: 5m
  - match:
      severity: warning
      category: tls
    receiver: devops
    repeat_interval: 30m
```

---

## References

- [SEC_5_END_TO_END_NO_HTTP_TLS_IMPLEMENTATION_PLAN.md](/docs/implementation-details/SEC_5_END_TO_END_NO_HTTP_TLS_IMPLEMENTATION_PLAN/)
- [SEC_5_W7_CUTOVER_RUNBOOK.md](/docs/implementation-details/SEC_5_W7_CUTOVER_RUNBOOK/)
- [RFC 6234: US Secure Hash and Digital Signature Algorithm](https://tools.ietf.org/html/rfc6234)
