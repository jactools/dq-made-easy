DQ Execution Engine
===================

Overview
--------
This service exposes compile-time rule translation for dq-made-easy. It translates canonical rule payloads into Great Expectations expectations without executing them against source data.

Runtime execution is handled by the **GX dispatch worker**, which runs suites on Spark and reports outcomes back through the main API (Kong → FastAPI → DB).

### Module Architecture

The engine is split into focused modules following the Single Responsibility Principle:

| Module | Responsibility |
|---|---|
| `gx_dispatch_config.py` | Configuration loading, environment variable resolution |
| `gx_dispatch_api.py` | Kong API client, run reporting, failure handling |
| `gx_dispatch_payload.py` | Dispatch payload parsing, source override extraction |
| `gx_dispatch_dispatch.py` | Dispatch routing (grouped / single / join-pair / spark expectations) |
| `gx_dispatch_expectations.py` | Expectation evaluation engine — single source of truth |
| `gx_dispatch_runtime.py` | Spark session, S3/URI handling, source resolution |
| `gx_dispatch_telemetry.py` | OpenTelemetry instrumentation |
| `gx_dispatch_types.py` | Shared type definitions |
| `gx_dispatch_worker.py` | Main entry point — worker loop, heartbeat, crash recovery |
| `execution_dispatch.py` | Generic execution dispatch (non-GX engines) |

**Full module architecture:** [docs/technical/DQ_ENGINE_MODULE_ARCHITECTURE.md](../docs/technical/DQ_ENGINE_MODULE_ARCHITECTURE.md)

### Kafka Consumer

The **`dq-kafka-consumer`** is a separate, lightweight container that consumes violation records from Kafka and persists them to both the database and S3. See `dq-kafka-consumer/README.md` for details.

Quick start (local)
-------------------
- Configure env vars (example in `scripts/.env` or export in shell):

```bash
export DQ_LOG_LEVEL=INFO
```

- Build and run with Docker (from repository root):

```bash
docker build -t dq-engine ./dq-engine
docker run --rm -e DQ_LOG_LEVEL=$DQ_LOG_LEVEL -p 8003:8000 dq-engine
```

API
---
GET /health
- Returns `{"status": "ok"}`

GET /readiness
- Returns `{"status": "ready"}`

POST /compile
- JSON body: canonical rule translation payload

Example request body:

```json
{
  "id": 101,
  "table": "demo.orders",
  "column": "customer_id",
  "type": "not_null",
  "params": {}
}
```

Result format example:

```json
{
  "ok": true,
  "rule_id": 101,
  "expectation": "ExpectColumnValuesToNotBeNull",
  "kwargs": { "column": "customer_id" }
}
```

Notes
-----
- This is a minimal, opinionated implementation intended as a starting point. The `rule_translator.py` contains simple mapping from rule types to Great Expectations expectations and can be extended.
- Spark execution, dispatch, and result reporting live in the GX worker path rather than this FastAPI service.

Spark Expectations POC (SE-PLAN-002)
------------------------------------
- A small runnable POC is available at `dq-engine/scripts/spark_expectations_teller_machine_poc.py`.
- The POC reads teller_machine parquet staged in AIStor, validates one `row_dq` rule and one `agg_dq` rule through Spark Expectations validation utilities, and prints a JSON summary including quarantined-row samples.

Example run (from repository root):

```bash
export DQ_S3_ENDPOINT=http://localhost:9222
export DQ_S3_ACCESS_KEY=aistoradmin
export DQ_S3_SECRET_KEY=aistoradmin

python dq-engine/scripts/spark_expectations_teller_machine_poc.py \
  --input-uri "s3a://dq-landing-zone-retail-banking/gx/join-pairs/local-csv-staging/case_id=correct_atm_cash_movement_matches_customer_transaction_total/role=left/version_id=dov-9/format=parquet" \
  --row-expectation "transaction_id IS NOT NULL AND amount > 0" \
  --agg-expectation "count(*) > 0" \
  --fail-on-agg-failure
```
