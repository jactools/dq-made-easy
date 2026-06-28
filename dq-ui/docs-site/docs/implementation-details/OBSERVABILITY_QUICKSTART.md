# Observability Stack - Quick Start Guide

**Status:** Complete  
**Last Updated:** 2026-03-22  
**Related Guides:**
- [OBSERVABILITY_SETUP.md](/docs/implementation-details/OBSERVABILITY_SETUP/) — Detailed architecture & design
- [OPENTELEMETRY_IMPLEMENTATION.md](/docs/implementation-details/OPENTELEMETRY_IMPLEMENTATION/) — In-depth instrumentation patterns

## 5-Minute Setup

### 1. Start Observability Stack

```bash
# Observability stack with the profiling worker and its runtime dependencies
docker-compose --profile observability up -d

# Verify all containers are running
docker-compose ps | grep -E "loki|prometheus|tempo|grafana|profiling-worker|redis-exporter"
```

Expected output:
```
dq-loki        grafana/loki:2.9.3       Up (healthy)
dq-prometheus  prom/prometheus:v2.48.0  Up (healthy)
dq-tempo       grafana/tempo:2.3.0      Up (healthy)
dq-grafana     grafana/grafana:10.2.0   Up (healthy)
```

### 2. Access Grafana UI

```
URL: http://observability.jac.dot:3000
Username: admin
Password: changeme
```

**First time?** Change password immediately (Settings → Server Admin → Edit Profile).

### 3. Verify Data Sources

1. Go to Configuration → Data Sources
2. You should see:
   - ✅ **Prometheus** (green, "Data source is working")
   - ✅ **Loki** (green)
   - ✅ **Tempo** (green)
    - ✅ **Profiling worker metrics** available through Prometheus as `dq_profiling_request_count_total`
    - ✅ **Redis exporter metrics** available through Prometheus as `redis_commands_processed_total`

---

## Instrument Your Services (15 min)

### Option A: FastAPI (dq-api, dq-engine)

#### 1. Install Dependencies

```bash
cd dq-api
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-jaeger \
            opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy \
            opentelemetry-instrumentation-redis opentelemetry-instrumentation-httpx \
            structlog prometheus-client
```

#### 2. Add to `main.py` (after imports)

```python
import os
import sys
import structlog
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from prometheus_client import Counter, Histogram, make_asgi_app

# ========================================================================
# Configure Structured Logging (JSON → Loki)
# ========================================================================
timestamper = structlog.processors.TimeStamper(fmt="iso")

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=logging.INFO,
)

log = structlog.get_logger(__name__)

# ========================================================================
# Configure Distributed Tracing (Jaeger → Tempo)
# ========================================================================
jaeger_exporter = JaegerExporter(
    agent_host_name=os.getenv("JAEGER_AGENT_HOST", "observability.local"),
    agent_port=int(os.getenv("JAEGER_AGENT_PORT", 6831)),
)

trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(jaeger_exporter)
)

# ========================================================================
# Configure Prometheus Metrics
# ========================================================================
rule_execution_duration = Histogram(
    "rule_execution_duration_ms",
    "Rule execution time in milliseconds",
    buckets=(100, 500, 1000, 5000, 10000, 30000, 60000),
    labelnames=["rule_id", "status"],
)

rule_results = Counter(
    "rule_results_total",
    "Total rule executions",
    labelnames=["status", "rule_id"],
)

exception_store_writes = Counter(
    "exception_store_write_errors_total",
    "Exception store write failures",
)

# ========================================================================
# FastAPI App Setup (existing code...)
# ========================================================================
app = FastAPI()

# Add Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Auto-instrument FastAPI
FastAPIInstrumentor.instrument_app(app)

# Auto-instrument database (if using SQLAlchemy)
# SQLAlchemyInstrumentor().instrument(engine=engine)

# Auto-instrument Redis (if using)
# RedisInstrumentor().instrument()

# ========================================================================
# Example: Middleware to add correlation ID
# ========================================================================
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    import uuid
    
    correlation_id = request.headers.get(
        "X-Correlation-Id", 
        str(uuid.uuid4())
    )
    
    # Add to structlog context
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        request_path=request.url.path,
    )
    
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id
    return response

# ========================================================================
# Example: Instrumented Endpoint
# ========================================================================
@app.post("/rules/{rule_id}/activate")
async def activate_rule(rule_id: str, request: RuleActivationRequest):
    import time
    
    start = time.time()
    tracer = trace.get_tracer(__name__)
    
    with tracer.start_as_current_span("activate_rule") as span:
        span.set_attribute("rule_id", rule_id)
        
        try:
            # Your business logic here
            result = await compile_and_activate_rule(rule_id, request)
            
            duration_ms = (time.time() - start) * 1000
            rule_execution_duration.labels(
                rule_id=rule_id,
                status="success"
            ).observe(duration_ms)
            rule_results.labels(status="success", rule_id=rule_id).inc()
            
            log.info(
                "rule_activated",
                rule_id=rule_id,
                duration_ms=int(duration_ms),
                status="success",
            )
            
            return result
            
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            rule_execution_duration.labels(
                rule_id=rule_id,
                status="error"
            ).observe(duration_ms)
            rule_results.labels(status="error", rule_id=rule_id).inc()
            
            log.error(
                "rule_activation_failed",
                rule_id=rule_id,
                error=str(e),
                duration_ms=int(duration_ms),
            )
            
            raise
```

#### 3. Set Environment Variables

```bash
# In your .env file or docker-compose
export JAEGER_AGENT_HOST=observability.local  # or "tempo" if in Docker
export JAEGER_AGENT_PORT=6831
```

#### 4. Restart Service

```bash
docker-compose restart api dq-engine
```

---

### Option B: Python Batch Job (dq-profiling, seed generators, etc.)

For non-FastAPI async jobs:

```python
import logging
import time
import structlog
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

# Configure logging
logging.basicConfig(
    format="%(message)s",
    level=logging.INFO,
)
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)
log = structlog.get_logger(__name__)

# Configure tracing
jaeger_exporter = JaegerExporter(
    agent_host_name="observability.local",
    agent_port=6831,
)
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    SimpleSpanProcessor(jaeger_exporter)
)

# Your batch job
def run_seed_generator():
    tracer = trace.get_tracer(__name__)
    
    with tracer.start_as_current_span("seed_generation") as span:
        span.set_attribute("job", "seed_generator")
        
        log.info("seed_generation_started")
        
        try:
            # Your work here
            time.sleep(1)
            log.info("seed_generation_completed", records=100)
        except Exception as e:
            log.error("seed_generation_failed", error=str(e))
            raise

if __name__ == "__main__":
    run_seed_generator()
```

---

## Querying Data

### 1. View Logs (Loki)

In Grafana, go to **Explore** → Select **Loki**:

```logql
# All logs from dq-api
{job="dq-api"}

# Errors only
{job="dq-api"} |= "ERROR"

# Parse JSON and filter
{job="dq-api"} | json | duration_ms > 1000

# Logs with specific correlation ID
{job="dq-api"} | json | correlation_id="abc-123"
```

### 2. View Metrics (Prometheus)

In Grafana, go to **Explore** → Select **Prometheus**:

```promql
# HTTP request rate
rate(http_requests_total[5m])

# Error rate
rate(http_requests_total{status=~"5.."}[5m])

# Rule execution p95 latency
histogram_quantile(0.95, rate(rule_execution_duration_ms[5m]))

# Current errors
rate(rule_results_total{status="error"}[5m])
```

### 3. View Traces (Tempo)

In Grafana, go to **Explore** → Select **Tempo**:

1. **Service Graph:** Shows dependencies between services
2. **Search:** Find traces by:
   - Service name: `dq-api`
   - Duration: `> 500ms`
   - Error: `error=true`
   - Tags: `rule_id=rule_123`

---

## Create Alerts

### 1. Example: Alert on High Error Rate

1. Go to Alerting → Alert rules
2. Click **New alert rule**
3. Name: `HighHTTPErrorRate`
4. Condition: `rate(http_requests_total{status=~"5.."}[5m]) > 0.05`
5. For: `5m`
6. Save

### 2. Silence Alerts

If alert is noisy:

1. Alerting → Alert rules → find rule
2. Click **Silence** → Set duration → Confirm

---

## Common Patterns

### Pattern 1: Correlation IDs Across Requests

```python
# In middleware or request handler
import uuid
correlation_id = request.headers.get("X-Correlation-Id", str(uuid.uuid4()))
structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

# Then logs/spans automatically include it
log.info("event")  # Includes correlation_id in JSON
```

### Pattern 2: Measure Execution Time

```python
import time
import structlog

log = structlog.get_logger(__name__)

start = time.time()
try:
    result = execute_rule(rule_id)
    duration_ms = (time.time() - start) * 1000
    log.info("rule_executed", rule_id=rule_id, duration_ms=int(duration_ms), status="success")
except Exception as e:
    duration_ms = (time.time() - start) * 1000
    log.error("rule_failed", rule_id=rule_id, duration_ms=int(duration_ms), error=str(e))
    raise
```

### Pattern 3: Batch Operation Logging

```python
import structlog

log = structlog.get_logger(__name__)

def batch_execute_rules(rules: List[Rule]):
    results = {"success": 0, "failed": 0}
    
    for rule in rules:
        try:
            execute_rule(rule.id)
            results["success"] += 1
        except Exception as e:
            log.error("rule_failed", rule_id=rule.id, error=str(e))
            results["failed"] += 1
    
    log.info("batch_execution_completed", **results)
```

---

## Troubleshooting

### No data appearing?

```bash
# Check services are healthy
docker-compose ps | grep observability

# Check Loki is receiving logs
curl 'http://observability.local:3100/api/prom/query?query={job="dq-api"}'

# Check Prometheus is scraping
curl http://observability.local:9090/api/v1/targets | jq '.data.activeTargets[]'

# Check Tempo is receiving traces
curl http://observability.local:3200/api/traces?limit=1
```

### Memory usage too high?

Edit `docker-compose-observability.yml`:

```yaml
loki:
  environment:
    - LOKI_CONFIG_FILE=/etc/loki/local-config.yml
    - GOMAXPROCS=2  # Limit CPU cores

prometheus:
  command:
    - "--storage.tsdb.max-block-duration=1h"
    - "--query.max-samples=10000000"  # Reduce memory
```

### Want to keep more data?

Edit `observability/prometheus/prometheus.yml`:

```yaml
global:
  # Increase from 15s if you want finer granularity
  scrape_interval: 30s
```

Edit `observability/loki/loki-config.yml`:

```yaml
limits_config:
  # Change from 2160h (90 days) to whatever you need
  retention_period: 4320h  # 180 days
```

---

## Next Steps

1. ✅ Stack running → Check health endpoints
2. ✅ Instruments services → Verify metrics/logs/traces flowing
3. ✅ Create custom dashboards → Add business KPIs
4. ✅ Set up alerts → Define SLOs for critical paths
5. ✅ Document runbooks → Team knows how to respond

---

## Further Reading

- [Grafana Observability Stack](https://grafana.com/docs/grafana/latest/getting-started/getting-started-with-grafana/)
- [Loki Best Practices](https://grafana.com/docs/loki/latest/operations/)
- [Prometheus Alerting](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
