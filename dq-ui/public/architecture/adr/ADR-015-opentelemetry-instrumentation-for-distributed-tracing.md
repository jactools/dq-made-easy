# ADR-015: OpenTelemetry Instrumentation for Distributed Tracing & Observability

**Status**: Proposed  
**Date**: 2026-03-22  
**Related**: [DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS](../../docs/implementation-details/DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md), [OBSERVABILITY_SETUP](../../docs/implementation-details/OBSERVABILITY_SETUP.md), [OPENTELEMETRY_IMPLEMENTATION](../../docs/implementation-details/OPENTELEMETRY_IMPLEMENTATION.md)

---

## Context

### Problem Statement

As the DQ Rule Builder system grows to support **multi-service execution** (API → Compiler → Engine → Profiling → Exception Store), teams have limited visibility into:

1. **Request flows**: Which services are involved in a user action? What's the latency breakdown?
2. **Error diagnosis**: When a rule fails, what happened at each stage? Which service is the bottleneck?
3. **Performance tracking**: Are rule executions meeting SLOs? Is compilation slowing down?
4. **Operational metrics**: What's the system's current load? Are there anomalies?

Current state:
- ❌ No distributed tracing across services
- ❌ Logs scattered across containers (no central aggregation)
- ❌ No metrics collection for SLO tracking
- ❌ Manual correlation of issues across service boundaries
- ❌ No vendor integration (hard to migrate if needed)

### Observability Requirements

From **DQ-7.4 Orchestration** design:
- ✅ Structured logging (correlationId, runId, dataObjectVersionId)
- ✅ Suite compilation & execution metrics
- ✅ Exception store write monitoring
- ✅ End-to-end trace visibility
- ✅ Correlation across async operations
- ✅ 90+ day data retention for compliance

---

## Decision

**Implement OpenTelemetry (OTel) with Grafana Loki + Prometheus + Tempo + Grafana** as the unified observability platform.

### Why OpenTelemetry?

| Criterion | OTel | Jaeger | Datadog | Splunk |
|-----------|------|--------|--------|--------|
| Vendor-neutral | ✅ | ⚠️ | ❌ | ❌ |
| Open source | ✅ | ✅ | ❌ | ❌ |
| Multi-backend export | ✅ | ❌ | ❌ | ❌ |
| Auto-instrumentation | ✅ | ❌ | ✅ | ✅ |
| No lock-in | ✅ | ⚠️ | ❌ | ❌ |
| Cost (self-hosted) | Free | Free | Paid | Paid |
| Maintained by CNCF | ✅ | ✅ | N/A | N/A |

### Why This Stack?

```
Services (API, Engine, Jobs)
    ↓↓↓ OpenTelemetry SDKs
    ├─ Jaeger Exporter → Tempo (traces)
    ├─ Prometheus Exporter → Prometheus (metrics)
    └─ structlog → JSON logs for Loki
    ↓↓↓
Grafana (single pane of glass)
    ├─ Explore logs (Loki)
    ├─ View metrics (Prometheus)
    ├─ Follow traces (Tempo)
    └─ Build dashboards + alerts
```

**Stack selection rationale**:
- **Loki**: Log aggregation (lightweight, label-based, &lt;$0 cost)
- **Prometheus**: Industry-standard metrics (pull-based, efficient)
- **Tempo**: Trace backend (designed for high volume, minimal storage cost)
- **Grafana**: Unified UI (supports all three + custom dashboards)
- **Total overhead**: 4 containers, ~300 MB RAM (vs 10+ for ELK)

---

## Implementation

### Architecture

```
┌──────────────────────────────────────────┐
│ DQ Services (API v6+, Engine, Jobs)      │
│ ├─ OpenTelemetry SDK (installed)         │
│ ├─ Jaeger exporter (UDP 6831)            │
│ ├─ Prometheus client (/metrics endpoint) │
│ └─ structlog (JSON logging)              │
└────────┬──────────────────────────────────┘
         │
    ┌────┴─────┬──────────┬─────────┐
    │           │          │         │
    ▼           ▼          ▼         ▼
  Tempo    Prometheus   Loki     [Collector]
 (traces)   (metrics)   (logs)    (optional)
    │           │          │         │
    └───────────┴──────────┴─────────┘
                 ▼
            Grafana 3000
         (unified dashboards)
```

### Key Components

#### 1. OpenTelemetry SDK (In-Process)

**Location**: `dq-api/`, `dq-engine/`, batch jobs  
**Config file**: None (programmatic setup in `main.py`)  
**Dependencies**:
```bash
pip install \
  opentelemetry-api==1.21.0 \
  opentelemetry-sdk==1.21.0 \
  opentelemetry-exporter-jaeger-thrift==1.21.0 \
  opentelemetry-instrumentation-fastapi==0.42b0 \
  opentelemetry-instrumentation-sqlalchemy==0.42b0 \
  prometheus-client==0.19.0 \
  structlog==23.2.0
```

#### 2. Backend Stack (Docker)

**Location**: `docker-compose-observability.yml`  
**Services**:
- `dq-loki:3100` — Log aggregation (no auth)
- `dq-prometheus:9090` — Metrics storage
- `dq-otel-collector:4317/4318` — Host-facing OTLP ingress (also Jaeger 14250, Zipkin 9411)
- `dq-tempo:3200` — Internal trace backend and query API
- `dq-grafana:3000` — Dashboards (admin/changeme)

**Configuration**:
- `observability/loki/loki-config.yml` — 90-day retention, filesystem storage
- `observability/prometheus/prometheus.yml` — Scrape dq-api, dq-engine, databases
- `observability/prometheus/alerts.yml` — Pre-configured SLOs (5xx errors, latency p95/p99)
- `observability/otel-collector/config.yml` — OTLP/Jaeger/Zipkin ingress, forwarding to Tempo
- `observability/tempo/tempo-config.yml` — Internal OTLP receiver, local WAL, query API

#### 3. Service Instrumentation

**Pattern**: Add 30-50 lines to each service's `main.py`:

```python
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
import structlog

# 1. Configure Jaeger exporter (traces → Tempo)
jaeger_exporter = JaegerExporter(
    agent_host_name=os.getenv("JAEGER_AGENT_HOST", "tempo"),
    agent_port=6831,
)
trace_provider = TracerProvider()
trace_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
trace.set_tracer_provider(trace_provider)

# 2. Auto-instrument FastAPI
FastAPIInstrumentor.instrument_app(app)

# 3. Configure structured logging
structlog.configure(processors=[...JSON...])
log = structlog.get_logger(__name__)

# 4. Create custom spans/metrics in endpoints
@app.post("/rules/{rule_id}/activate")
async def activate_rule(rule_id: str):
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("activate_rule") as span:
        span.set_attribute("rule_id", rule_id)
        log.info("rule_activated", rule_id=rule_id)
```

**Service-specific instrumentation**:

| Service | Scope | Instrumentation |
|---------|-------|-----------------|
| **dq-api** | HTTP requests, rule compilation, GX suite publish | FastAPI auto-instrumentation + custom spans for compiler/publisher |
| **dq-engine** | Rule execution, GX suite evaluation, result writing | Custom spans for suite execution, exception store writes |
| **Batch jobs** (seed, profiling) | Job start/end, per-item processing | SimpleSpanProcessor (no batching for quick scripts) |
| **dq-db** | SQL performance (optional) | SQLAlchemy instrumentation if using sync driver |
| **dq-redis** | Cache hit/miss, connection pool | RedisInstrumentor |

#### 4. Correlation & Context

**Mandatory implementation**:
- W3C TraceContext headers propagate automatically via OTel
- Custom X-Correlation-Id header extracted in middleware
- structlog context variables (correlation_id, user_id, request_path, trace_id)
- Baggage for cross-service attributes (user_tier, data_product_id)

**Example middleware**:
```python
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-Id", str(uuid.uuid4()))
    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        trace_id=get_trace_id(),
    )
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id
    return response
```

#### 5. Metrics & SLOs

**Standard metrics** (auto-instrumented by OTel):
- HTTP request duration, status codes, count
- Database query latency
- Redis operation latency

**Custom DQ metrics**:
```python
meter = metrics.get_meter(__name__)

rule_execution_total = meter.create_counter(
    "rule_execution_total",
    description="Total rule executions",
    unit="1",
)
rule_execution_total.add(1, {"status": "success", "rule_id": rule_id})

rule_execution_duration = meter.create_histogram(
    "rule_execution_duration_ms",
    description="Rule execution time",
    unit="ms",
)
rule_execution_duration.record(1234, {"rule_id": rule_id})
```

**Pre-configured alerts** (in `prometheus/alerts.yml`):
- ✅ High HTTP error rate (>5% for 5 min) → warning
- ✅ Rule execution p95 latency >30s → warning
- ✅ Rule execution p99 latency >60s → critical
- ✅ Exception store write failures → critical
- ✅ Service down (api, engine, db, redis) >2 min → critical
- ✅ Database connection pool >80% → warning
- ✅ Disk space &lt;10% → critical

---

### Deployment & Lifecycle

#### Start Stack
```bash
scripts/observability.sh start
# or
docker-compose --profile observability up -d
```

#### Verify
```bash
curl http://observability.local:3100/ready         # Loki
curl http://observability.local:9090/-/healthy     # Prometheus
curl http://observability.local:3200/ready         # Tempo
curl http://observability.local:3000/api/health    # Grafana
```

#### Access
- **Grafana**: http://observability.local:3000 (admin/changeme)
- **Prometheus**: http://observability.local:9090
- **Tempo**: http://observability.local:3200/search
- **Loki**: Via Grafana Explore

#### Stop
```bash
scripts/observability.sh stop
```

---

## Consequences

### Positive

1. **Comprehensive observability**
   - ✅ Distributed tracing end-to-end (user → API → compiler → engine → results)
   - ✅ Centralized logging with correlation IDs
   - ✅ Metrics for SLO tracking and alerting
   - ✅ Unified Grafana dashboard (logs + metrics + traces)

2. **Vendor independence**
   - ✅ No proprietary SDKs or lock-in
   - ✅ Can export to multiple backends simultaneously (Datadog, Lightstep, etc.)
   - ✅ Easy migration path (change exporter, keep instrumentation)

3. **Operational efficiency**
   - ✅ Debug production issues quickly (follow trace from logs)
   - ✅ Identify bottlenecks (compilation vs execution vs storage)
   - ✅ Proactive alerting on SLO violations
   - ✅ Historical analysis (90-day retention)

4. **Compliance & auditing**
   - ✅ Structured logs with context (user_id, data_product_id)
   - ✅ Immutable trace records for audit trail
   - ✅ 90+ day retention meets data governance requirements

5. **Development experience**
   - ✅ Simple API (no custom instrumentation boilerplate)
   - ✅ Auto-instrumentation reduces integration effort
   - ✅ testable (in-memory exporters for unit tests)

### Negative

1. **Operational overhead**
   - ⚠️ 4 additional containers (~300-500 MB RAM)
   - ⚠️ Monitoring the monitors (need to track Loki/Prometheus/Tempo health)
   - ⚠️ Storage growth (20-30 GB for 90 days @ light volume)
   - **Mitigation**: Use AIStor or cloud storage backend for production

2. **Development overhead**
   - ⚠️ 15-30 min per service to add instrumentation
   - ⚠️ New testing requirements (span assertions)
   - ⚠️ Performance tuning (sampling rates, cardinality)
   - **Mitigation**: Copy-paste FastAPI example from OPENTELEMETRY_IMPLEMENTATION.md

3. **Operational complexity**
   - ⚠️ Must configure sampling (too high = storage blow-up, too low = missing issues)
   - ⚠️ Metric cardinality can cause Prometheus memory issues
   - ⚠️ Debugging distributor/exporter issues requires OTEL knowledge
   - **Mitigation**: Start with defaults (10% sampling, proven cardinality limits)

4. **Dependency management**
   - ⚠️ OpenTelemetry SDK + instrumenters must be kept in sync
   - ⚠️ Breaking changes in instrumentation APIs (versioned but not always smooth)
   - **Mitigation**: Pin versions in requirements.txt, test upgrades thoroughly

5. **Learning curve**
   - ⚠️ W3C TraceContext headers, baggage semantics, sampler strategies
   - ⚠️ Span naming conventions, attribute cardinality
   - **Mitigation**: Clear documentation + training examples provided

---

## Alternatives Considered

### 1. **ELK Stack** (Elasticsearch, Logstash, Kibana)
- ❌ Heavy (7+ containers, 2+ GB RAM)
- ❌ Overkill for current volume
- ❌ Expensive at scale
- ❌ No native tracing support (must bolt on Jaeger)
- ✅ Most flexible for complex log queries

### 2. **Datadog / New Relic / Lightstep**
- ❌ Expensive (~$100+/month for current volume)
- ❌ Vendor lock-in
- ✅ Full-featured, SaaS convenience
- ✅ Built-in APM

### 3. **Jaeger only** (without Prometheus + Loki)
- ❌ Traces only (missing logs + metrics)
- ❌ Higher operational complexity (Jaeger + Elasticsearch backend)
- ✅ Mature for tracing use case

### 4. **Manual logging** (structured logs to files)
- ❌ No real-time search or alerting
- ❌ No correlation across services
- ❌ No metrics for SLOs
- ✓ Zero operational overhead

**Chosen solution** balances observability needs with operational simplicity and cost.

---

## Implementation Plan

### Phase A: Infrastructure Setup (1-2 days)
- [x] Design & document stack (this ADR + guides)
- [ ] Deploy observability containers (Loki, Prometheus, Tempo, Grafana)
- [ ] Create base configuration files
- [ ] Verify health checks

### Phase B: Service Instrumentation (3-5 days)
- [ ] Instrument dq-api (FastAPI auto-instrumentation + custom spans)
- [ ] Instrument dq-engine (custom spans for execution)
- [ ] Instrument batch jobs (seed-generator, profiling-worker)
- [ ] Test correlation IDs flowing through traces

### Phase C: Testing & Validation (2-3 days)
- [ ] Unit tests for span creation
- [ ] Integration tests for trace propagation
- [ ] Load testing (verify sampling doesn't lose important traces)
- [ ] Validate 90-day retention
- [ ] Test alert rules

### Phase D: Rollout & Training (2 days)
- [ ] Deploy to dev environment
- [ ] Create runbooks (troubleshoot high latency, missing traces, etc.)
- [ ] Train team on Grafana usage
- [ ] Migrate on-call alerts to OTel-based rules

---

## Next Steps

1. **Review & Approval**: This ADR
2. **Setup Infrastructure**: Deploy docker-compose-observability.yml
3. **Instrument Services**: Add OTel SDKs to FastAPI apps (copy from OPENTELEMETRY_IMPLEMENTATION.md)
4. **Create Dashboards**: Business KPIs (rule execution trends, compilation latency, exception volume)
5. **Define SLOs**: Document performance targets (e.g., "99% of rules execute &lt;5s")
6. **Automation**: Auto-publish metrics to alerting system

---

## References

- **OpenTelemetry Python**: https://opentelemetry.io/docs/instrumentation/python/
- **Temporal Implementation Guide**: docs/implementation-details/OPENTELEMETRY_IMPLEMENTATION.md
- **Setup Documentation**: docs/implementation-details/OBSERVABILITY_SETUP.md
- **Quick Start**: docs/implementation-details/OBSERVABILITY_QUICKSTART.md
- **W3C TraceContext**: https://www.w3.org/TR/trace-context/
- **Grafana Docs**: https://grafana.com/docs/grafana/latest/
- **Tempo Docs**: https://grafana.com/docs/tempo/latest/
- **Prometheus Best Practices**: https://prometheus.io/docs/practices/
