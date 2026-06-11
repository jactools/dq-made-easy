# Lightweight Observability Stack for DQ Rule Builder

**Status:** Complete  
**Last Updated:** 2026-03-22  
**Related Guides:**
- [OPENTELEMETRY_IMPLEMENTATION.md](./OPENTELEMETRY_IMPLEMENTATION.md) — Detailed instrumentation guide
- [OBSERVABILITY_QUICKSTART.md](./OBSERVABILITY_QUICKSTART.md) — Hands-on setup & implementation

## Architecture Overview

This design uses **Grafana Loki + Prometheus + Tempo + Grafana** — a minimal, open-source observability stack.

```
┌─────────────────────────────────────────────────────────┐
│ DQ Services (API, Engine, UI, etc.)                     │
│ └─ OpenTelemetry SDK instrumentation                    │
└──────────────┬──────────────────────────────────────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
    ▼          ▼          ▼
 Loki      Prometheus   Tempo        (Collectors)
(logs)      (metrics)    (traces)
    │          │          │
    └──────────┼──────────┘
               ▼
           Grafana       (Unified UI)
```

## Stack Components

| Component | Purpose | Containers | Resource Cost |
|-----------|---------|-----------|-----------------|
| **Loki** | Log aggregation & storage | 1 | ~50 MB RAM, minimal CPU |
| **Prometheus** | Metrics collection | 1 | ~100 MB RAM, minimal CPU |
| **Tempo** | Distributed tracing | 1 | ~50 MB RAM, minimal CPU |
| **Grafana** | Unified dashboards & UI | 1 | ~100 MB RAM, minimal CPU |
| **OpenTelemetry Collector** (optional) | Centralized instrumentation | 1 (optional) | ~100 MB RAM |
| **Total new containers** | | **4-5** | ~400-500 MB RAM |

## Why This Stack?

✅ **Minimal:** 4 containers vs. 10+ for ELK  
✅ **Lightweight:** ~400 MB total RAM overhead  
✅ **Open source:** No licensing  
✅ **Production-ready:** Used by thousands  
✅ **Easy to scale:** All components are horizontally scalable  
✅ **Native Kubernetes:** Designed for container environments  
✅ **90-day retention:** Built-in with local storage or S3-compatible backend  

---

## Storage Options

### Option 1: Local Filesystem (Recommended for 90-day @ light volume)

```yaml
volumes:
  loki_data: {}
  prometheus_data: {}
  tempo_data: {}
```

**Pros:** Zero external dependencies, simple setup  
**Cons:** Tied to single container host; loss of container = loss of data  
**Disk space needed:** ~20-30 GB for 90 days @ <100 MB/day logs + metrics + traces  

### Option 2: AIStor Free Edition (S3-compatible Object Storage)

```yaml
services:
  aistor:
    image: quay.io/minio/aistor/minio:latest
    environment:
      MINIO_ROOT_USER: ${AISTOR_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${AISTOR_ROOT_PASSWORD}
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - aistor_data:/mnt/data
      - ${AISTOR_LICENSE_FILE}:/minio.license:ro
    command: ["minio", "server", "/mnt/data", "--console-address", ":9001", "--license", "/minio.license"]
```

**Pros:** Scalable, cloud-native, persists across container restarts  
**Cons:** One additional container (~300 MB RAM)  

---

## Quick Start

### 1. Add to docker-compose.yml

See [`docker-compose-observability.yml`](./docker-compose-observability.yml) — merge this into your existing compose file (sections labeled `# OBSERVABILITY`).

### 2. Configuration Files

Create these directories:
```bash
mkdir -p observability/loki
mkdir -p observability/prometheus
mkdir -p observability/tempo
```

Copy configuration templates from sections below.

### 3. Start Stack

```bash
# Option A: Full stack with all services
docker-compose up -d db api dq-engine redis keycloak loki prometheus tempo grafana

# Option B: Add observability to running services
docker-compose up -d loki prometheus tempo grafana
```

### 4. Access Grafana

```
http://observability.local:3000
Username: admin
Password: changeme  (CHANGE THIS IN PRODUCTION!)
```

---

## Instrumentation (Code Changes)

### FastAPI (API, Engine)

Add to `main.py`:

```python
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
import structlog

# Configure Jaeger exporter for traces → Tempo
jaeger_exporter = JaegerExporter(
    agent_host_name="tempo",  # or "observability.local" if running on Docker host
    agent_port=6831,
)
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(jaeger_exporter)
)

# Auto-instrument FastAPI
FastAPIInstrumentor.instrument_app(app)

# Auto-instrument database and cache
SQLAlchemyInstrumentor().instrument(engine=engine)
RedisInstrumentor().instrument()

# Configure structured logging for Loki
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
```

### Python Generic (Engine, Profiling)

```python
import logging
import structlog
import json

# Structured logging setup
logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=logging.INFO,
)
log = structlog.get_logger(__name__)

# Log with context
log.info(
    "rule_executed",
    ruleId="rule_123",
    dataObjectVersionId="dov_456",
    status="passed",
    duration_ms=1234,
    correlation_id="req_xyz",
)
```

### React/Node.js Frontend

```javascript
import * as Sentry from "@sentry/react";

Sentry.init({
  dsn: "http://observability.local:3000/sentry",  // or use error tracking endpoint
  tracesSampleRate: 1.0,
  integrations: [
    new Sentry.Replay({
      maskAllText: true,
      blockAllMedia: true,
    }),
  ],
});

// Or use OpenTelemetry JS
import { WebTracerProvider } from "@opentelemetry/sdk-trace-web";
import { JaegerExporter } from "@opentelemetry/exporter-jaeger";

const provider = new WebTracerProvider();
provider.addSpanProcessor(
  new BatchSpanProcessor(
    new JaegerExporter({
      endpoint: "http://observability.local:14268/api/traces",
    })
  )
);
```

---

## Configuration Files

### Loki Configuration

File: `observability/loki/loki-config.yml`

```yaml
auth_enabled: false

ingester:
  chunk_idle_period: 3m
  max_chunk_age: 1h
  max_streams_per_user: 10000
  chunk_retain_period: 1m

limits_config:
  enforce_metric_name: false
  reject_old_samples: true
  reject_old_samples_max_age: 168h  # 7 days
  retention_period: 2160h  # 90 days

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

storage_config:
  filesystem:
    directory: /loki/chunks
  boltdb_shipper:
    active_index_directory: /loki/boltdb-shipper-active
    shared_store: filesystem
    cache_location: /loki/boltdb-shipper-cache

server:
  http_listen_port: 3100
  log_level: info

query_scheduler:
  max_outstanding_requests_per_tenant: 256

querier:
  query_timeout: 5m
```

### Prometheus Configuration

File: `observability/prometheus/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: dq-rulebuilder
    environment: dev

alerting:
  alertmanagers:
    - static_configs:
        - targets: []

rule_files: []

scrape_configs:
  - job_name: "prometheus"
    static_configs:
      - targets: ["observability.local:9090"]

  - job_name: "dq-api"
    static_configs:
      - targets: ["api:4001"]
    metrics_path: "/metrics"
    scrape_interval: 5s

  - job_name: "dq-engine"
    static_configs:
      - targets: ["dq-engine:8000"]
    metrics_path: "/metrics"

  - job_name: "postgres"
    static_configs:
      - targets: ["db:5432"]
    # Requires postgres_exporter sidecar

  - job_name: "redis"
    static_configs:
      - targets: ["redis:6379"]
    # Requires redis_exporter sidecar
```

### Tempo Configuration

File: `observability/tempo/tempo-config.yml`

```yaml
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317

querier:
  frontend_worker:
    frontend_address: observability.local:3200

storage:
  trace:
    backend: local
    local:
      path: /var/tempo
    blocklist_poll: 5m
    wal:
      path: /var/tempo/wal
      checkpoint_duration: 5m

metrics_generator:
  registry:
    external_labels:
      cluster: dq-rulebuilder
  storage:
    path: /var/tempo/metrics-generator
    remote_write:
      - url: http://prometheus:9090/api/v1/write
```

    Tempo keeps its OTLP receivers enabled for internal traffic from `otel-collector`, but only the query API on port `3200` is published on the host. Host-facing OTLP (`4317`/`4318`), Jaeger (`14250`), and Zipkin (`9411`) ingress belong to `otel-collector` to avoid port collisions.

---

## Dashboards

Grafana comes pre-loaded with dashboards for:

- **Logs:** Loki log browser
- **Metrics:** Prometheus scrape targets, node exporter
- **Traces:** Tempo service graph, latency analysis

### Create Custom Dashboards

1. **Login:** http://observability.local:3000 (admin/changeme)
2. **Create Dashboard** → Add Panel
3. **Data Source:** Select "Prometheus", "Loki", or "Tempo"
4. **Example Queries:**
   - **Logs:** `{job="dq-api"} | json | duration_ms > 1000`
   - **Metrics:** `rate(http_requests_total[5m])`
   - **Traces:** Service = `dq-engine`, Status = `error`

---

## Alerts

Example alert rules (Prometheus):

File: `observability/prometheus/alerts.yml`

```yaml
groups:
  - name: dq_alerts
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        annotations:
          summary: "High error rate detected"

      - alert: RuleExecutionTimeout
        expr: histogram_quantile(0.95, rate(rule_execution_duration_ms[5m])) > 30000
        for: 10m
        annotations:
          summary: "Rule execution p95 latency > 30s"

      - alert: ExceptionStoreWriteFailure
        expr: increase(exception_store_write_errors_total[5m]) > 0
        for: 1m
        annotations:
          summary: "Exception store write failures"
```

---

## Retention & Data Management

### Loki Retention

- **Default:** 90 days (configurable via `retention_period`)
- **Storage:** ~300-400 MB per 30 days @ <100 MB/day logs
- **Cleanup:** Automatic; Loki deletes chunks older than retention period

### Prometheus Retention

- **Default:** 15 days (configurable via `--storage.tsdb.retention.time`)
- **Storage:** ~100-150 MB per 30 days @ light volume
- **Samples kept:** ~1 million active series

### Tempo Retention

- **Default:** 48 hours in local backend, 24h in object storage
- **Storage:** ~50-100 MB per 30 days @ light volume
- **Traces:** ~100k traces per day

### Upgrade Retention: Modify docker-compose

```yaml
services:
  prometheus:
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.retention.time=365d"  # 1 year

  loki:
    environment:
      - RETENTION_PERIOD=2160h  # 90 days
```

---

## Monitoring the Monitors

### Health Checks

```bash
# Loki health
curl http://localhost:3100/ready

# Prometheus health
curl http://localhost:9090/-/healthy

# Tempo health
curl http://localhost:3200/ready

# Grafana health
curl http://localhost:3000/api/health
```

### Key Metrics to Monitor

| Metric | What it means | Alert threshold |
|--------|---------------|-----------------|
| `loki_ingester_chunks_created_total` | Chunks being written | Spike = potential issue |
| `prometheus_tsdb_symbol_table_size_bytes` | DB size | > 1 GB = consider retention |
| `tempo_distributor_spans_received_total` | Traces flowing | 0 = check instrumentation |
| `up{job="..."}` | Scrape target health | 0 = target down |

---

## Best Practices

### 1. **Structured Logging**
Always log as JSON with structured fields:
```python
log.info("rule_executed", ruleId="r1", status="passed", duration_ms=100)
```
NOT: `log.info(f"Rule {rule_id} passed in {duration}ms")`

### 2. **Correlation IDs**
Pass `X-Correlation-Id` through all requests:
```python
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-Id", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id
    return response
```

### 3. **Sample Rates**
For high-volume services, sample traces (10-50%):
```python
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(exporter, schedule_delay_millis=5000)
)
```

### 4. **Retention Strategy**
- **Logs:** 90 days (compliance, debugging)
- **Metrics:** 30-90 days (trends, capacity planning)
- **Traces:** 7-48 hours (real-time debugging)

### 5. **Privacy & Security**
- Mask PII in logs:
  ```python
  log.info("user_login", user_id="***", email="***@***.com")
  ```
- Don't log passwords, API keys, tokens
- Consider encryption at rest if on shared infrastructure

---

## Troubleshooting

### Issue: No Logs in Loki

```bash
# Check Loki is receiving data
curl 'http://observability.local:3100/api/prom/query?query={job="dq-api"}'

# Check ingestion rate
curl 'http://observability.local:3100/api/prom/query?query=rate(loki_ingester_entries_limit_bytes[5m])'
```

**Solution:** Verify services are logging JSON and `promtail` (if using) is running.

### Issue: Traces Not Appearing

```bash
# Check collector and Tempo are both listening
docker logs <otel-collector-container> | grep -i "listening\|otlp"
docker logs <tempo-container> | grep -i "listening\|otlp"

# Verify host OTLP endpoint (collector ingress)
curl http://observability.local:4317  # Should fail gracefully, not hang
```

**Solution:** Ensure host-based clients send traces to `observability.local:4317` or `observability.local:4318`, and containerized services send traces to `otel-collector:4317` or `otel-collector:4318`. `tempo:4317` is internal to the observability network and should not be exposed on the host.

### Issue: High Memory Usage

```bash
# Check Prometheus targets
curl http://observability.local:9090/api/v1/targets

# Reduce scrape targets or increase retention
docker-compose down loki prometheus
# Edit configs, reduce intervals
docker-compose up -d loki prometheus
```

---

## Next Steps

1. **[Complete Setup]** Merge `docker-compose-observability.yml` → `docker-compose.yml`
2. **[Instrument Services]** Add OpenTelemetry to FastAPI, Engine, UI
3. **[Create Dashboards]** Custom business KPI dashboards in Grafana
4. **[Set Alerts]** Alert on critical paths (rule failures, execution timeouts)
5. **[Document SLOs]** Define Service Level Objectives (e.g., "99% rules execute < 5s")

---

## References

- **Loki:** https://grafana.com/docs/loki/latest/
- **Prometheus:** https://prometheus.io/docs/
- **Tempo:** https://grafana.com/docs/tempo/latest/
- **OpenTelemetry:** https://opentelemetry.io/docs/
- **Grafana:** https://grafana.com/docs/grafana/latest/
