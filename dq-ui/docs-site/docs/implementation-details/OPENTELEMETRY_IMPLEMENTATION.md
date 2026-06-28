# OpenTelemetry Implementation for DQ Rule Builder

**Status:** Complete instrumentation guide  
**Last Updated:** 2026-03-23  
**Related:** [OBSERVABILITY_SETUP.md](/docs/implementation-details/OBSERVABILITY_SETUP/), [OBSERVABILITY_QUICKSTART.md](/docs/implementation-details/OBSERVABILITY_QUICKSTART/)

---

## Table of Contents

1. [Telemetry Conventions](#telemetry-conventions)
2. [Overview](#overview)
3. [Architecture](#architecture)
4. [Core Concepts](#core-concepts)
5. [Installation & Setup](#installation--setup)
6. [FastAPI Instrumentation](#fastapi-instrumentation)
7. [Python Batch Jobs](#python-batch-jobs)
8. [Span Enrichment & Context](#span-enrichment--context)
9. [Custom Metrics](#custom-metrics)
10. [Trace Propagation](#trace-propagation)
11. [Testing & Validation](#testing--validation)
12. [Performance Tuning](#performance-tuning)
13. [Troubleshooting](#troubleshooting)

---

## Telemetry Conventions

Approved: 2026-03-23

### Service Names

Every service that emits telemetry MUST set `OTEL_SERVICE_NAME` to its canonical name.
Do not use the docker-compose service key directly; use the values below.

| docker-compose key   | OTEL_SERVICE_NAME |
|----------------------|-------------------|
| `api`                | `dq-api`          |
| `frontend`           | `dq-ui`           |
| `dq-engine`          | `dq-engine`       |
| `profiling-worker`   | `dq-profiling`    |
| `kong`               | `dq-kong`         |
| `openmetadata-server`| `dq-openmetadata` |
| `openmetadata-ingestion` | `dq-openmetadata-ingestion` |

### Environment Labels

The `environment` attribute is set via the `ENVIRONMENT` env var (default: `dev`).
Use exactly these values — no free-form strings.

| Deployment context        | `ENVIRONMENT` value |
|---------------------------|---------------------|
| Local development / dev   | `dev`               |
| CI / integration testing  | `test`              |
| Production                | `prod`              |

The API reads this from `Settings.environment` (set by env var `ENVIRONMENT`).
The UI reads it from `VITE_ENVIRONMENT` at build time.

### Mandatory Span and Log Attributes

Every span and every structured log line MUST carry these fields:

| Attribute             | Source                               | Note |
|-----------------------|--------------------------------------|------|
| `correlation_id`      | `X-Correlation-ID` request header   | Generated as UUID-4 by `CorrelationIdMiddleware` if absent. Already implemented. |
| `user_id`             | Authenticated user sub / `anonymous` | Use `anonymous` for unauthenticated requests. Do NOT log email or display name. |
| `route`               | `http.route` (OTel semconv / FastAPI) | Normalised path pattern, e.g. `/api/v1/rules/&#123;rule_id&#125;`, not raw URL. |
| `environment`         | `Settings.environment`               | One of `dev`, `test`, `prod`. |
| `service.name`        | `OTEL_SERVICE_NAME`                  | OTel standard resource attribute. |
| `service.version`     | `OTEL_SERVICE_VERSION`               | Set at container build or deploy time. |

Optional but strongly recommended when available:

| Attribute           | When to include |
|---------------------|-----------------|
| `tenant_id`         | When a rule or data object belongs to a specific org/tenant |
| `rule_id`           | Spans touching a rule resource |
| `trace_id`          | Included in structured logs for Loki ↔ Tempo cross-linking |

### Cardinality Rules

- **Never** use raw user email, raw URL path (use normalised route), or uncapped free-form IDs as metric label values.
- **Always** use low-cardinality labels on metrics: `status` (`success`/`error`), `endpoint_group` (e.g. `rules`, `auth`, `health`), `method` (`GET`/`POST`/…).
- Trace attributes may carry high-cardinality values (e.g. `rule_id`) because traces are sampled.

### Sampling Policy

| Environment | `OTEL_TRACES_SAMPLER`               | `OTEL_TRACES_SAMPLER_ARG` |
|-------------|--------------------------------------|---------------------------|
| `dev`       | `parentbased_traceidratio`           | `0.1` (10%)               |
| `test`      | `parentbased_traceidratio`           | `0.1` (10%)               |
| `prod`      | `parentbased_traceidratio`           | `0.01` (1%)               |

Sampled child spans always follow the decision of the parent span (W3C `traceparent` sampled flag).

### Existing Infrastructure: Correlation ID

The API already has a working correlation ID implementation — do not replace it, extend it:

- Middleware: `dq-api/fastapi/app/middleware/correlation_id.py` (`CorrelationIdMiddleware`)
- Header: `X-Correlation-ID` (read/write)
- Async propagation: `dq-api/fastapi/app/core/request_context.py` (`get_correlation_id()` / `set_correlation_id()`)

When OTel spans are created, attach `correlation_id` from `get_correlation_id()` as a span attribute so traces and logs are joinable.

### Existing Infrastructure: Structured Logging

The API already uses a custom JSON formatter (`_JsonFormatter` in `dq-api/fastapi/app/core/logging_config.py`).
Do not replace it; add the mandatory `trace_id`, `correlation_id`, and `environment` keys to every log record via a logging filter during Phase 3 OTel wiring.

Required JSON log fields after instrumentation:

```json
{
  "ts": "2026-03-23T10:00:00Z",
  "level": "INFO",
  "logger": "app.routers.rules",
  "msg": "rule_activated",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "trace_id": "abc123def456abc123def456abc123de",
  "environment": "dev",
  "service_name": "dq-api"
}
```

---

## Overview

**OpenTelemetry (OTel)** is a vendor-neutral standard for collecting telemetry data (traces, metrics, logs). It provides:

- **Automatic instrumentation** of popular libraries (FastAPI, SQLAlchemy, Redis, etc.)
- **Exporting** to multiple backends (Tempo, Prometheus, Loki, Jaeger, etc.)
- **Vendor independence** — no vendor lock-in
- **Minimal overhead** — configurable sampling, batching, and filtering

### Why OpenTelemetry?

| Feature | OTel | Jaeger | Datadog SDK | Splunk SDK |
|---------|------|--------|-------------|-----------|
| Vendor-neutral | ✅ | ⚠️ | ❌ | ❌ |
| Open source | ✅ | ✅ | ❌ | ❌ |
| Multiple exporters | ✅ | ❌ | ❌ | ❌ |
| Automatic instrumentation | ✅ | ❌ | ✅ | ✅ |
| Cost (self-hosted) | Free | Free | Paid | Paid |

---

## Architecture

### OpenTelemetry Flow

```
┌────────────────────────────────────────────────────────┐
│ DQ Services (API, Engine, Jobs)                        │
│ └─ OpenTelemetry SDK                                   │
│    ├─ Auto-instrumentation                            │
│    ├─ Custom spans & metrics                          │
│    └─ Context propagation (W3C TraceContext)          │
└───────────────────┬────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
        [Jaeger]  [Prometheus] [OTLP gRPC/HTTP]
        Exporter   Exporter      Exporter
        │           │           │
        └───────────┼───────────┘
                    │
        ┌───────────┼───────────────┐
        │           │               │
        ▼           ▼               ▼
     OTel Collector Prometheus    Loki (OTLP/logs)
     (Ingress)      (Metrics)    (Logs)
                │
                ▼
            Tempo
        (Traces)
        │           │               │
        └───────────┼───────────────┘
                    │
                    ▼
                 Grafana
              (Dashboard UI)
```

### Component Responsibilities

| Component | Purpose | Protocol |
|-----------|---------|----------|
| **OpenTelemetry SDK** | Instrument code, collect signals | In-process APIs |
| **Jaeger Exporter** | Send traces to collector/ingress | Thrift/gRPC (port 6831) |
| **Prometheus Exporter** | Expose metrics for scraping | HTTP (port 8000) |
| **OTLP Exporter** | Send traces/logs/metrics to collector | gRPC/HTTP (4317/4318) |
| **OpenTelemetry Collector** | Host-facing telemetry ingress; forwards traces to Tempo | OTLP, Zipkin, Jaeger APIs |
| **Tempo** | Store and index traces behind the collector | Internal OTLP receiver + query API |
| **Prometheus** | Scrape metrics from exporters | HTTP (9090) |
| **Loki** | Ingest and store logs | OTLP, Promtail, Syslog |

---

## Core Concepts

### 1. Spans

A **span** is a single operation within a trace. Each span has:

```python
# Span attributes
span.set_attribute("rule_id", "rule_123")
span.set_attribute("user_id", "user_456")
span.set_attribute("duration_ms", 1234)
span.set_attribute("status", "success")

# Span events (for notable moments)
span.add_event("rule_validation_passed")
span.add_event("exception_store_write_started")

# Span status
span.set_status(Status(StatusCode.OK))
span.set_status(Status(StatusCode.ERROR, "Database error"))
```

### 2. Traces

A **trace** is a sequence of spans that follows a request through the system:

```
User Request
  └─ api-gateway (span)
      ├─ rule-compiler (span)
      ├─ database-write (span)
      └─ gx-suite-publish (span)
```

### 3. Context Propagation

**Context** travels with requests using W3C TraceContext headers:

```http
POST /api/rulebuilder/v1/rules/rule_123/activate HTTP/1.1
traceparent: 00-<trace_id>-<span_id>-<flags>
tracestate: dd=s:1; ...
X-Correlation-Id: req_abc123
```

### 4. Meters & Metrics

**Metrics** track numerical observations over time:

```python
# Counter (always increases)
rule_execution_counter.add(1, {"rule_id": "r1", "status": "success"})

# Histogram (measures distribution)
rule_execution_duration.record(1234, {"rule_id": "r1"})

# Gauge (current value)
active_rule_count.observe(42)
```

---

## Installation & Setup

### Step 1: Install Dependencies

```bash
# Latest stable baseline (selected 2026-03-23)
pip install \
  opentelemetry-api==1.40.0 \
  opentelemetry-sdk==1.40.0 \
  opentelemetry-exporter-otlp==1.40.0 \
  prometheus-client==0.19.0 \
  structlog==23.2.0

# Optional auto-instrumentation (pre-release at time of writing; requires explicit approval)
# pip install \
#   opentelemetry-instrumentation==0.61b0 \
#   opentelemetry-instrumentation-fastapi==0.61b0 \
#   opentelemetry-instrumentation-sqlalchemy==0.61b0 \
#   opentelemetry-instrumentation-redis==0.61b0 \
#   opentelemetry-instrumentation-httpx==0.61b0 \
#   opentelemetry-instrumentation-logging==0.61b0
```

**Version note:** Keep `opentelemetry-api`, `opentelemetry-sdk`, and `opentelemetry-exporter-otlp` on matching latest stable versions.

### Step 2: Environment Variables

```bash
# Jaeger exporter (traces → collector ingress)
export JAEGER_AGENT_HOST=observability.local  # "tempo" in Docker
export JAEGER_AGENT_PORT=6831

# OTLP exporter (collector ingress)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://observability.local:4317
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc

# Service identification
export OTEL_SERVICE_NAME=dq-api
export OTEL_SERVICE_VERSION=1.0.0

# Sampling (0.0-1.0; start with 0.1 for high-volume)
export OTEL_TRACES_SAMPLER=parentbased_traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1
```

---

## FastAPI Instrumentation

### Complete Example: `dq-api/fastapi/main.py`

```python
"""
DQ Rule Builder API - with full OpenTelemetry instrumentation
"""
import os
import sys
import uuid
import logging
from typing import Optional
from contextvars import ContextVar

import structlog
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, Gauge, make_asgi_app

# OpenTelemetry imports
from opentelemetry import trace, metrics, context, baggage
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ParentBased
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.semantic_conventions.resource import ResourceAttributes
from opentelemetry.sdk.resources import Resource

# ============================================================================
# 1. RESOURCE DEFINITION (identify this service)
# ============================================================================

resource = Resource.create({
    ResourceAttributes.SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "dq-api"),
    ResourceAttributes.SERVICE_VERSION: os.getenv("OTEL_SERVICE_VERSION", "1.0.0"),
    "environment": os.getenv("ENVIRONMENT", "dev"),
    "region": os.getenv("REGION", "local"),
})

# ============================================================================
# 2. TRACE EXPORTER & PROVIDER (Tempo via Jaeger)
# ============================================================================

jaeger_exporter = JaegerExporter(
    agent_host_name=os.getenv("JAEGER_AGENT_HOST", "localhost"),
    agent_port=int(os.getenv("JAEGER_AGENT_PORT", 6831)),
    # Max packet size for UDP (Jaeger protocol)
    max_tag_value_length=256,
)

trace_provider = TracerProvider(
    resource=resource,
    # Sampling: keep N% of traces (0.1 = 10%)
    sampler=ParentBased(
        TraceIdRatioBased(
            float(os.getenv("OTEL_TRACES_SAMPLER_ARG", 0.1))
        )
    ),
)
trace_provider.add_span_processor(
    BatchSpanProcessor(
        jaeger_exporter,
        max_queue_size=2048,
        max_export_batch_size=512,
        schedule_delay_millis=5000,
    )
)
trace.set_tracer_provider(trace_provider)

# ============================================================================
# 3. METRICS EXPORTER & PROVIDER (Prometheus)
# ============================================================================

prometheus_reader = PrometheusMetricReader()

metrics_provider = MeterProvider(
    resource=resource,
    metric_readers=[prometheus_reader],
)
metrics.set_meter_provider(metrics_provider)

# ============================================================================
# 4. STRUCTURED LOGGING (JSON → Loki)
# ============================================================================

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

# Instrument Python logging to send to OpenTelemetry
LoggingInstrumentor().instrument(set_logging_format=True)

# ============================================================================
# 5. CUSTOM METRICS (DQ-specific)
# ============================================================================

meter = metrics.get_meter(__name__)

# Counters
rule_execution_total = meter.create_counter(
    name="rule_execution_total",
    description="Total number of rule executions",
    unit="1",
)

rule_compilation_failures = meter.create_counter(
    name="rule_compilation_failures_total",
    description="Total rule compilation failures",
    unit="1",
)

exception_store_writes = meter.create_counter(
    name="exception_store_write_total",
    description="Total exception store writes",
    unit="1",
)

# Histograms
rule_execution_duration = meter.create_histogram(
    name="rule_execution_duration_ms",
    description="Rule execution time in milliseconds",
    unit="ms",
)

compilation_duration = meter.create_histogram(
    name="compilation_duration_ms",
    description="Rule compilation time in milliseconds",
    unit="ms",
)

# Gauges
active_batches = meter.create_observable_gauge(
    name="active_batches",
    description="Number of active execution batches",
    unit="1",
    callbacks=[lambda opts: [(0, {})]],  # Placeholder
)

# ============================================================================
# 6. FASTAPI SETUP
# ============================================================================

app = FastAPI(
    title="DQ Rule Builder API",
    version=os.getenv("OTEL_SERVICE_VERSION", "1.0.0"),
)

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app(registry=prometheus_reader._registry)
app.mount("/metrics", metrics_app)

# Auto-instrument FastAPI
FastAPIInstrumentor.instrument_app(
    app,
    server_request_hook=lambda span, request: server_request_hook(span, request),
    client_request_hook=lambda span, request: client_request_hook(span, request),
)

# ============================================================================
# 7. CONTEXT & CORRELATION TRACKING
# ============================================================================

# Context variables
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
request_path_var: ContextVar[str] = ContextVar("request_path", default="")

def get_correlation_id() -> str:
    """Retrieve current correlation ID from context."""
    return correlation_id_var.get()

def get_trace_id() -> str:
    """Get current trace ID from OpenTelemetry context."""
    span = trace.get_current_span()
    context_obj = span.get_span_context()
    return format(context_obj.trace_id, "032x")

# ============================================================================
# 8. INSTRUMENTATION HOOKS
# ============================================================================

def server_request_hook(span, request: Request):
    """Hook: enrich span with request details."""
    span.set_attribute("request_path", request.url.path)
    span.set_attribute("request_method", request.method)
    span.set_attribute("request_headers_user_agent", 
                       request.headers.get("user-agent", "unknown"))
    
    # Extract correlation ID from request
    correlation_id = request.headers.get(
        "X-Correlation-Id", 
        str(uuid.uuid4())
    )
    span.set_attribute("correlation_id", correlation_id)
    correlation_id_var.set(correlation_id)

def client_request_hook(span, request):
    """Hook: enrich span for outgoing HTTP requests."""
    span.set_attribute("http.request.body.size", 
                       len(request.content) if hasattr(request, 'content') else 0)

# ============================================================================
# 9. MIDDLEWARE: Add correlation ID to all requests
# ============================================================================

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Extract/generate correlation ID and add to context."""
    correlation_id = request.headers.get("X-Correlation-Id", str(uuid.uuid4()))
    user_id = request.headers.get("X-User-Id", "anonymous")
    
    # Set context variables
    correlation_id_var.set(correlation_id)
    user_id_var.set(user_id)
    request_path_var.set(request.url.path)
    
    # Add to structlog context
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        user_id=user_id,
        request_path=request.url.path,
        trace_id=get_trace_id(),
    )
    
    # Process request
    response = await call_next(request)
    
    # Add correlation ID to response
    response.headers["X-Correlation-Id"] = correlation_id
    response.headers["X-Trace-Id"] = get_trace_id()
    
    return response

# ============================================================================
# 10. EXAMPLE: INSTRUMENTED ENDPOINT
# ============================================================================

@app.post("/api/v1/rules/{rule_id}/activate")
async def activate_rule(
    rule_id: str,
    background_tasks=None,
):
    """
    Activate a rule and compile to GX suite.
    
    :param rule_id: Rule ID to activate
    :param background_tasks: FastAPI background tasks
    """
    import time
    
    tracer = trace.get_tracer(__name__)
    start_time = time.time()
    
    # Create a new span for this operation
    with tracer.start_as_current_span("activate_rule") as span:
        # Set span attributes
        span.set_attribute("rule_id", rule_id)
        span.set_attribute("user_id", user_id_var.get())
        span.set_attribute("correlation_id", correlation_id_var.get())
        
        try:
            log.info(
                "rule_activation_started",
                rule_id=rule_id,
                event="activation_request",
            )
            
            # Step 1: Validate rule
            with tracer.start_as_current_span("validate_rule") as validate_span:
                validate_span.set_attribute("rule_id", rule_id)
                # await validate_rule(rule_id)
                log.info("rule_validated", rule_id=rule_id)
            
            # Step 2: Compile rule
            with tracer.start_as_current_span("compile_rule") as compile_span:
                compile_span.set_attribute("rule_id", rule_id)
                
                compile_start = time.time()
                # compiled_rule = await compile_rule(rule_id)
                compile_duration = (time.time() - compile_start) * 1000
                
                compile_span.set_attribute("duration_ms", int(compile_duration))
                compilation_duration.record(compile_duration, {"rule_id": rule_id})
                
                log.info(
                    "rule_compiled",
                    rule_id=rule_id,
                    duration_ms=int(compile_duration),
                )
            
            # Step 3: Publish GX suite
            with tracer.start_as_current_span("publish_gx_suite") as publish_span:
                publish_span.set_attribute("rule_id", rule_id)
                # gx_suite = await publish_suite(rule_id, compiled_rule)
                log.info("gx_suite_published", rule_id=rule_id)
            
            # Record metrics
            duration_ms = (time.time() - start_time) * 1000
            rule_execution_total.add(1, {"status": "success", "rule_id": rule_id})
            rule_execution_duration.record(duration_ms, {"rule_id": rule_id})
            
            span.set_status(trace.Status(trace.StatusCode.OK))
            log.info(
                "rule_activated_success",
                rule_id=rule_id,
                duration_ms=int(duration_ms),
                status="success",
            )
            
            return {
                "rule_id": rule_id,
                "status": "activated",
                "trace_id": get_trace_id(),
                "correlation_id": correlation_id_var.get(),
            }
            
        except Exception as e:
            # Record error metrics
            rule_execution_total.add(1, {"status": "error", "rule_id": rule_id})
            duration_ms = (time.time() - start_time) * 1000
            
            # Set span error status
            span.set_status(
                trace.Status(trace.StatusCode.ERROR, description=str(e))
            )
            span.record_exception(e)
            
            log.error(
                "rule_activation_failed",
                rule_id=rule_id,
                error=str(e),
                error_type=type(e).__name__,
                duration_ms=int(duration_ms),
            )
            
            raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# 11. DATABASE & CACHE INSTRUMENTATION
# ============================================================================

# Auto-instrument SQLAlchemy (if using)
# SQLAlchemyInstrumentor().instrument(engine=engine)

# Auto-instrument Redis (if using)
# RedisInstrumentor().instrument()

# ============================================================================
# 12. STARTUP & SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Log service startup with version info."""
    log.info(
        "api_startup",
        service="dq-api",
        version=os.getenv("OTEL_SERVICE_VERSION", "unknown"),
        environment=os.getenv("ENVIRONMENT", "unknown"),
    )

@app.on_event("shutdown")
async def shutdown_event():
    """Flush any pending spans before shutdown."""
    log.info("api_shutdown")
    trace_provider.force_flush(timeout_millis=30000)
    metrics_provider.force_flush(timeout_millis=30000)

# ============================================================================
# 13. ERROR HANDLERS
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all exceptions and record in OpenTelemetry."""
    span = trace.get_current_span()
    span.record_exception(exc)
    span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
    
    log.error(
        "unhandled_exception",
        error=str(exc),
        error_type=type(exc).__name__,
        path=request.url.path,
        trace_id=get_trace_id(),
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "trace_id": get_trace_id(),
            "correlation_id": correlation_id_var.get(),
        },
    )

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=4001,
        reload=os.getenv("ENV", "prod") != "prod",
        log_config=None,  # Use structlog
    )
```

---

## Python Batch Jobs

### Example: Seed Generator with Tracing

```python
"""
Seed data generator - with OpenTelemetry tracing
"""
import os
import time
import structlog
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.semantic_conventions.resource import ResourceAttributes

# Configure tracing for batch job
resource = Resource.create({
    ResourceAttributes.SERVICE_NAME: "seed-generator",
    "job_type": "seed",
})

jaeger_exporter = JaegerExporter(
    agent_host_name=os.getenv("JAEGER_AGENT_HOST", "observability.local"),
    agent_port=int(os.getenv("JAEGER_AGENT_PORT", 6831)),
)

trace_provider = TracerProvider(resource=resource)
trace_provider.add_span_processor(SimpleSpanProcessor(jaeger_exporter))
trace.set_tracer_provider(trace_provider)

# Structured logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)

log = structlog.get_logger(__name__)

# ========================================================================
# Main Job
# ========================================================================

def run_seed_generator():
    """Generate seed data for all data objects."""
    tracer = trace.get_tracer(__name__)
    start_time = time.time()
    
    with tracer.start_as_current_span("seed_generation_job") as span:
        span.set_attribute("job_type", "seed")
        
        try:
            log.info("seed_generation_started")
            
            # Seed data objects
            with tracer.start_as_current_span("seed_data_objects") as do_span:
                do_span.set_attribute("count", 10)
                log.info("seeding_data_objects", count=10)
                # ... seed logic ...
                time.sleep(1)
            
            # Seed assignments
            with tracer.start_as_current_span("seed_assignments") as assign_span:
                assign_span.set_attribute("count", 25)
                log.info("seeding_assignments", count=25)
                # ... seed logic ...
                time.sleep(1)
            
            duration_ms = (time.time() - start_time) * 1000
            span.set_status(trace.Status(trace.StatusCode.OK))
            span.set_attribute("duration_ms", int(duration_ms))
            
            log.info(
                "seed_generation_completed",
                duration_ms=int(duration_ms),
                status="success",
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            
            log.error(
                "seed_generation_failed",
                error=str(e),
                duration_ms=int(duration_ms),
            )
            raise
        
        finally:
            # Flush spans before exit
            trace_provider.force_flush(timeout_millis=5000)

if __name__ == "__main__":
    run_seed_generator()
```

---

## Span Enrichment & Context

### Baggage (Cross-Cutting Attributes)

Use **baggage** to propagate context-specific information across service boundaries:

```python
from opentelemetry import baggage, context

# Set baggage (persists across spans)
ctx = baggage.set_baggage("user_tier", "premium")
ctx = baggage.set_baggage("data_product_id", "odcs.dp.sales", ctx)

# Read baggage in any span
user_tier = baggage.get_baggage("user_tier")

# Baggage automatically includes in TraceContext header
# X-Trace-State: user_tier=premium; data_product_id=odcs.dp.sales
```

### Custom Attributes

Add domain-specific attributes to spans:

```python
span.set_attribute("rule_config.check_type", "completeness")
span.set_attribute("rule_config.data_types", ["int", "string"])
span.set_attribute("assignment.data_object_id", "do_123")
span.set_attribute("execution.status", "passed")
span.set_attribute("execution.record_count", 1000)
span.set_attribute("execution.violation_count", 3)
```

### Linked Spans

Link related spans (e.g., async tasks):

```python
# Parent span
with tracer.start_as_current_span("parent_operation") as parent_span:
    # Queue an async task
    task_future = background_tasks.add_task(async_task)
    
# Later, in async task, link to parent
async def async_task():
    parent_context = trace.get_current_span().get_span_context()
    link = trace.Link(parent_context)
    
    with tracer.start_as_current_span("async_task", links=[link]):
        # Work...
        pass
```

---

## Custom Metrics

### Patterns

```python
from opentelemetry import metrics

meter = metrics.get_meter(__name__)

# 1. Counter (monotonically increasing)
request_count = meter.create_counter(
    name="http_requests_total",
    description="Total HTTP requests processed",
    unit="1",
)
request_count.add(1, {"method": "POST", "endpoint": "/rules"})

# 2. Histogram (distribution of values)
response_time = meter.create_histogram(
    name="http_response_time_ms",
    description="HTTP response time in milliseconds",
    unit="ms",
)
response_time.record(125, {"endpoint": "/rules"})

# 3. Observable Gauge (current snapshot)
def get_queue_size():
    return [(123, {})]  # Size as attribute

queue_size = meter.create_observable_gauge(
    name="async_queue_size",
    description="Number of items in async queue",
    unit="1",
    callbacks=[get_queue_size],
)

# 4. UpDownCounter (can increase or decrease)
active_connections = meter.create_up_down_counter(
    name="active_connections",
    description="Number of active WebSocket connections",
    unit="1"
)
active_connections.add(1)  # Connection opened
active_connections.add(-1)  # Connection closed
```

---

## Trace Propagation

### W3C TraceContext Header

OpenTelemetry automatically sends these headers:

```http
traceparent: 00-trace_id-span_id-sampled
00                              # Version
─ trace_id                      # 32 hex chars (128-bit)
    ─ span_id                   # 16 hex chars (64-bit)
         ─ sampled              # 01=sampled, 00=not sampled
```

### Extracting Trace Info in Downstream Services

```python
from opentelemetry.propagate import extract

@app.middleware("http")
async def extract_trace_context(request: Request, call_next):
    # Extract trace context from incoming headers
    ctx = extract(request.headers)
    
    with trace.use_span(trace.get_current_span(ctx)):
        response = await call_next(request)
    
    return response
```

### Multi-Service Example

```
User Request
    │
    ├─ Header: traceparent=00-abc123-def456-01
    ▼
[API Service]
    ├─ Span: POST /activate
    ├─ Creates child span: compile_rule
    └─ Forwards traceparent header downstream
        │
        ├─ Header: traceparent=00-abc123-ghi789-01
        ▼
    [Engine Service]
        └─ Span: execute_engine (linked to parent trace)

All spans in same trace (abc123) in Grafana:
  trace/abc123
    ├─ api.POST.activate (api service)
    │  └─ compile_rule (api service)
    └─ engine.execute (engine service)
```

---

## Testing & Validation

### Unit Test: Span Creation

```python
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

def test_rule_activation_creates_span():
    """Verify spans are created for rule activation."""
    
    # Setup test tracer with in-memory exporter
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter
    )
    
    memory_exporter = InMemorySpanExporter()
    trace_provider = TracerProvider()
    trace_provider.add_span_processor(SimpleSpanProcessor(memory_exporter))
    trace.set_tracer_provider(trace_provider)
    
    # Execute function
    activate_rule("rule_123")
    
    # Assert spans were created
    spans = memory_exporter.get_finished_spans()
    assert len(spans) >= 3  # activate, validate, compile, publish
    assert spans[0].name == "activate_rule"
    assert spans[0].attributes["rule_id"] == "rule_123"

def test_span_attributes():
    """Verify span attributes are set correctly."""
    
    tracer = trace.get_tracer(__name__)
    
    with tracer.start_as_current_span("test_span") as span:
        span.set_attribute("test_key", "test_value")
        
        # In real test, use exporter to verify
        assert span.is_recording()
```

### Integration Test: Trace Propagation

```python
def test_trace_propagation_across_services():
    """Verify trace context propagates via headers."""
    
    # Simulate incoming request with trace context
    headers = {
        "traceparent": "00-abc123def456abc123def456abc123de-def456abc123def4-01"
    }
    
    # Make request to API
    response = client.post(
        "/api/v1/rules/rule_123/activate",
        headers=headers,
    )
    
    # Verify response includes trace
    assert "X-Trace-Id" in response.headers
    assert "X-Correlation-Id" in response.headers
```

---

## Performance Tuning

### 1. Sampling Strategy

**Adaptive Sampling** — lower sample rate under load:

```python
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ParentBased

# 10% of root traces, 100% of child traces
sampler = ParentBased(
    root=TraceIdRatioBased(0.1),  # 10% of new traces
    remote_parent_sampled=AlwaysOn(),  # 100% if parent sampled
    remote_parent_not_sampled=AlwaysOff(),
)
```

### 2. Batch Processing

Configure batch exporter for throughput:

```python
BatchSpanProcessor(
    jaeger_exporter,
    max_queue_size=2048,        # Buffer size
    max_export_batch_size=512,  # Batch size
    schedule_delay_millis=5000, # Flush interval
)
```

### 3. Attribute Limits

```python
SpanLimits(
    max_num_attributes=128,
    max_num_events=128,
    max_num_links=32,
    max_event_attributes=32,
    max_link_attributes=32,
)
```

### 4. Metrics Aggregation

```python
PeriodicExportingMetricReader(
    exporter,
    interval_millis=60000,  # Export every 60s
)
```

---

## Troubleshooting

### Issue: Spans not appearing in Tempo

**Symptoms:** No traces in Grafana, but service is running.

**Debug steps:**

```bash
# Check Jaeger connectivity
curl -v http://localhost:6831  # Should fail gracefully (UDP)

# Check Tempo is receiving
curl http://observability.local:3200/api/traces?limit=1

# Enable debug logging
export OTEL_SDK_DISABLED=false
export OTEL_LOG_LEVEL=debug
```

### Issue: High memory usage

**Symptoms:** Service memory grows over time.

**Solutions:**

1. Reduce sampling rate:
   ```python
   OTEL_TRACES_SAMPLER_ARG=0.01  # 1% instead of 10%
   ```

2. Reduce batch size:
   ```python
   max_queue_size=512
   ```

3. Limit attributes:
   ```python
   max_num_attributes=64
   ```

### Issue: Slow Prometheus queries

**Symptoms:** Grafana queries timeout.

**Solutions:**

1. Increase Prometheus memory:
   ```yaml
   prometheus:
     deploy:
       resources:
         requests:
           memory: 512Mi
   ```

2. Reduce cardinality (unique metric series):
   ```python
   # BAD: creates new series for every user ID
   request_counter.add(1, {"user_id": user_id})
   
   # GOOD: tag only high-cardinality dimensions
   request_counter.add(1, {"endpoint": "/rules"})
   ```

### Issue: Correlation IDs not propagating

**Symptoms:** Different trace IDs in logs and traces.

**Solution:** Ensure middleware sets both OTel context AND structlog:

```python
@app.middleware("http")
async def middleware(request, call_next):
    correlation_id = request.headers.get("X-Correlation-Id")
    
    # Set BOTH
    correlation_id_var.set(correlation_id)
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
    
    response = await call_next(request)
    return response
```

---

## References

- **OpenTelemetry Python:** https://opentelemetry.io/docs/instrumentation/python/
- **Jaeger Export:** https://github.com/open-telemetry/opentelemetry-python/tree/main/exporter/opentelemetry-exporter-jaeger
- **Semantic Conventions:** https://opentelemetry.io/docs/reference/specification/protocol/exporter/
- **W3C TraceContext:** https://www.w3.org/TR/trace-context/
- **OTEL Best Practices:** https://opentelemetry.io/docs/reference/specification/protocol/
