# OBS-1 OTLP Metrics Streaming

Status: Proposed

## Goal

Switch service metrics from **pull-based** Prometheus scraping (15s interval) to **push-based** OTLP streaming (sub-second), so Grafana always reflects the latest data without waiting for the next scrape cycle.

Infrastructure metrics (postgres_exporter, redis_exporter, loki, tempo, container-metrics) remain pull-based via Prometheus scraping — these are external exporters that cannot emit OTLP.

## Current state

### Metrics pipeline

```
Prometheus ──scrape (15s)──► [dq-api, dq-engine, profiling-worker, ...]
Prometheus ──scrape (15s)──► [postgres_exporter, redis_exporter, loki, tempo, ...]
Prometheus ──────────────────► Grafana (query)
```

### OTLP pipeline (existing)

```
Services ──OTLP──► Otel Collector ──OTLP──► Tempo (traces)
Services ──OTLP──► Otel Collector ──debug──► stdout (logs)
Services ──OTLP──► Otel Collector ──prometheus exporter──► port 8889 (scraped by Prometheus)
```

Services already emit traces via OTLP. The collector exposes OTLP metrics on port 8889 in Prometheus format, but Prometheus still has to scrape them on a 15s cycle. **No remote write** exists.

### Service OTLP SDKs (already installed)

| Service | OTLP SDK | Already emits |
|---------|----------|---------------|
| dq-api (FastAPI) | `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, auto-instrumentation | Traces (HTTP, SQLAlchemy, Redis, HTTPX) |
| dq-engine | `opentelemetry-sdk`, `opentelemetry-exporter-otlp` | Traces |
| profiling-worker | `opentelemetry-sdk`, `opentelemetry-exporter-otlp` | Traces |
| dq-llm | `opentelemetry-sdk`, `opentelemetry-exporter-otlp` | Traces |

## Target state

```
Services ──OTLP push (sub-second)──► Otel Collector ──prometheusremotewrite──► Prometheus ──► Grafana
Prometheus ──scrape (15s)──► [postgres_exporter, redis_exporter, loki, tempo, container-metrics, aistor]
```

Services that have OTLP SDKs **push metrics in real-time**. Infrastructure exporters remain on pull-based scraping.

## Proposed changes

### 1. Collector: add prometheusremotewrite exporter

Add remote write exporter to `observability/otel-collector/config.yml`:

```yaml
exporters:
  # ... existing exporters ...

  prometheusremotewrite:
    endpoint: "http://prometheus:9090/api/v1/write"
    tls:
      insecure: true
    sending_queue:
      enabled: true
      num_consumers: 4
      queue_size: 5000
    resource_to_telemetry_conversion:
      enabled: true
```

### 2. Collector: update metrics pipeline

Route OTLP metrics through prometheusremotewrite:

```yaml
service:
  pipelines:
    metrics:
      receivers: [otlp, otlp/https]
      processors: [memory_limiter, batch]
      exporters: [prometheusremotewrite, prometheus, debug]
```

Keep the existing `prometheus` exporter (port 8889) as a fallback/debug surface. Prometheus still scrapes port 8889 for collector-internal metrics.

### 3. Prometheus: enable remote write acceptance

Add to `observability/prometheus/prometheus.yml`:

```yaml
# Accept remote write from OTLP Collector
# No auth for local dev; add TLS + auth for test/prod
# (Remote write is internal network only)
```

Prometheus v3 accepts remote write by default on port 9090. No config change needed for local dev. For test/prod, add TLS:

```yaml
# For test/prod: configure TLS on prometheus remote write endpoint
# (Handled by service-level TLS, not prometheus.yml)
```

### 4. Services: enable OTLP metric emission

Services already import the OTLP SDK. Add metric emission using OpenTelemetry metrics API.

**dq-api (FastAPI) — example:**

```python
# dq-api/fastapi/app/telemetry/metrics.py
from opentelemetry import metrics
from opentelemetry.metrics import Observation

meter = metrics.get_meter("dq-api")

# Request counter
http_request_counter = meter.create_counter(
    "http.server.request.count",
    unit="1",
    description="Total HTTP server requests",
)

# Request duration histogram
http_request_duration = meter.create_histogram(
    "http.server.request.duration",
    unit="s",
    description="HTTP server request duration",
)

# Active connections gauge
http_active_connections = meter.create_up_down_counter(
    "http.server.active.connections",
    unit="1",
    description="Active HTTP server connections",
)
```

Use FastAPI middleware or the existing auto-instrumentation to record metrics on each request.

**dq-engine — example:**

```python
# dq-engine/telemetry/metrics.py
from opentelemetry import metrics

meter = metrics.get_meter("dq-engine")

# Rule execution counter
rule_execution_counter = meter.create_counter(
    "dq.engine.rule.execution.count",
    unit="1",
    description="Total rule executions",
)

# Rule execution duration
rule_execution_duration = meter.create_histogram(
    "dq.engine.rule.execution.duration",
    unit="s",
    description="Rule execution duration",
)

# Active workers gauge
active_workers_gauge = meter.create_gauge(
    "dq.engine.active.workers",
    unit="1",
    description="Currently active workers",
)
```

### 5. Reduce Prometheus scrape interval for remaining targets

Services that switch to OTLP push can be removed from Prometheus scrape configs. Infrastructure exporters remain but with reduced interval:

```yaml
# prometheus.yml
global:
  scrape_interval: 15s  # unchanged for infrastructure

# Remove or reduce scrape for services now pushing via OTLP:
# - job_name: "dq-api"          → removed (pushing via OTLP)
# - job_name: "dq-engine"        → removed (pushing via OTLP)
# - job_name: "dq-profiling"     → removed (pushing via OTLP)
# - job_name: "dq-llm"           → removed (pushing via OTLP)

# Keep (infrastructure exporters cannot emit OTLP):
- job_name: "postgres"           → 15s
- job_name: "redis"              → 15s
- job_name: "loki"               → 15s
- job_name: "tempo"              → 15s
- job_name: "container-metrics"  → 15s
- job_name: "aistor"             → 15s
- job_name: "grafana"            → 15s
```

### 6. Grafana dashboard updates

No change needed for existing Grafana dashboards. Prometheus serves all metrics (scraped + remote write) through the same API. Dashboards continue to query `Prometheus` data source.

Optional: add `OTLP` label filter in dashboards to distinguish push vs pull metrics.

## Scope

### In scope

- Collector: add `prometheusremotewrite` exporter
- Collector: update metrics pipeline to include remote write
- Prometheus: accept remote write (local dev: no config change; test/prod: TLS)
- Services: add OTLP metric emission (dq-api, dq-engine, profiling-worker, dq-llm)
- Prometheus: remove scrape jobs for services now pushing via OTLP
- Grafana: verify dashboards work with remote write metrics

### Out of scope

- Adding new Grafana dashboards
- Alert rules for OTLP metrics
- Service-level OTLP configuration (services already have SDKs)
- Changing trace or log pipeline

## Acceptance criteria

- [ ] Otel Collector accepts OTLP metrics and pushes to Prometheus via remote write
- [ ] Prometheus serves OTLP-pushed metrics through its API
- [ ] Grafana dashboards show real-time service metrics (sub-second latency)
- [ ] dq-api emits HTTP request count, duration, and active connection metrics via OTLP
- [ ] dq-engine emits rule execution count, duration, and active worker metrics via OTLP
- [ ] Infrastructure metrics (postgres, redis, loki, tempo, etc.) still work via Prometheus scrape
- [ ] Collector health check passes
- [ ] Prometheus health check passes
- [ ] `docker compose up` starts without errors

## Architecture

### Metrics flow (OTLP push)

```
Service (Python OTLP SDK)
    │
    │  metric.record(value, attributes)
    │
    ▼
Otel Collector (OTLP receiver :4318)
    │
    │  batch processor (10s timeout)
    │
    ▼
prometheusremotewrite exporter
    │
    │  HTTP POST /api/v1/write
    │
    ▼
Prometheus (port 9090)
    │
    ▼
Grafana (query Prometheus)
```

### Metrics flow (Prometheus scrape — infrastructure)

```
Prometheus ──scrape (15s)──► postgres_exporter:9187
Prometheus ──scrape (15s)──► redis_exporter:9121
Prometheus ──scrape (15s)──► loki:3100/metrics
Prometheus ──scrape (15s)──► tempo:3200/metrics
Prometheus ──scrape (15s)──► container-metrics:8000/metrics
Prometheus ──scrape (15s)──► aistor:9000/metrics
```

### Collector config diff

**Before:**
```yaml
exporters:
  prometheus:
    endpoint: 0.0.0.0:8889

service:
  pipelines:
    metrics:
      receivers: [otlp, otlp/https, prometheus]
      processors: [memory_limiter, batch]
      exporters: [prometheus, debug]
```

**After:**
```yaml
exporters:
  prometheus:
    endpoint: 0.0.0.0:8889

  prometheusremotewrite:
    endpoint: "http://prometheus:9090/api/v1/write"
    tls:
      insecure: true
    sending_queue:
      enabled: true
      num_consumers: 4
      queue_size: 5000
    resource_to_telemetry_conversion:
      enabled: true

service:
  pipelines:
    metrics:
      receivers: [otlp, otlp/https]
      processors: [memory_limiter, batch]
      exporters: [prometheusremotewrite, prometheus, debug]

    metrics/internal:
      receivers: [prometheus]
      processors: [memory_limiter, batch]
      exporters: [prometheus, debug]
```

## Security considerations

| Concern | Mitigation |
|---------|-----------|
| Remote write is unauthenticated (local dev) | Internal Docker network only; add TLS + mTLS for test/prod |
| Collector batch size | 10s timeout + 1024 batch size balances latency vs throughput |
| Prometheus remote write flood | Sending queue (5000 items) + 4 consumers backpressure |
| Service OTLP endpoint is HTTPS | Already enforced via `otlp/https` receiver with TLS |

## Risk assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Collector becomes bottleneck for metrics | Low | Batch processor + sending queue handles load |
| Prometheus storage grows faster | Medium | Same data, just pushed instead of scraped; storage unchanged |
| Breaking existing dashboards | Low | Prometheus serves all metrics through same API |
| Services fail to emit metrics | Low | OTLP exporter is already installed; add metric recording |

## Proposed workstreams

### 1. Collector configuration
- [ ] `OBS-1.1` Add `prometheusremotewrite` exporter to collector config
- [ ] `OBS-1.2` Update metrics pipeline to include remote write
- [ ] `OBS-1.3` Split internal metrics (prometheus receiver) into separate pipeline
- [ ] `OBS-1.4` Verify collector config is valid (`otelcol --config-validate`)

### 2. Service metric emission
- [ ] `OBS-1.5` Add HTTP metrics to dq-api (request count, duration, active connections)
- [ ] `OBS-1.6` Add execution metrics to dq-engine (rule count, duration, workers)
- [ ] `OBS-1.7` Add metrics to profiling-worker (profile count, duration)
- [ ] `OBS-1.8` Add metrics to dq-llm (request count, duration, token usage)

### 3. Prometheus cleanup
- [ ] `OBS-1.9` Remove scrape jobs for services now pushing via OTLP
- [ ] `OBS-1.10` Verify Prometheus accepts remote write
- [ ] `OBS-1.11` Verify Grafana dashboards show new metrics

### 4. Test/prod readiness
- [ ] `OBS-1.12` Add TLS for prometheusremotewrite endpoint (test/prod)
- [ ] `OBS-1.13` Document OTLP metrics flow in observability guide

## Related references

- [OBS_1_OTLP_METRICS_STREAMING.md](./OBS_1_OTLP_METRICS_STREAMING.md) — this document
