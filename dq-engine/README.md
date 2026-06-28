DQ Execution Engine
===================

Overview
--------
This service exposes compile-time rule translation for dq-made-easy. It translates canonical rule payloads into Great Expectations expectations without executing them against source data.

Runtime execution is handled by the GX dispatch worker in `dq-engine/gx_dispatch_worker.py`, which runs suites on Spark and reports outcomes back through the main API.

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
