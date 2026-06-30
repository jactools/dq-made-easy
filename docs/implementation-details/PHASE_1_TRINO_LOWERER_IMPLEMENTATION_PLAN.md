# Phase 1 Implementation Plan: Trino Lowerer

**Status:** Phase 1 Complete  
**Owner:** [To Be Assigned]  
**Estimated Duration:** 2-3 weeks  
**Priority:** High

---

## Executive Summary

This plan details the implementation of the Trino lowerer to enable distributed SQL execution of Data Quality rules. The Trino lowerer will translate canonical DQ rule payloads into Trino-native SQL for execution against distributed data sources, enabling scalable validation across large datasets.

---

## Current State Analysis

### Existing Implementation

The Trino lowerer Phase 1 implementation is complete across `/dq-engine/runtime_lowerers.py`, `/dq-engine/trino_adapter.py`, `/dq-engine/trino_executor.py`, and `/dq-engine/trino_execution_pipeline.py`:

✅ **Already Implemented:**
- Basic row-level checks: `not_null`, `is_null`, `equals`, `not_equal`, `between`, `in`, `not_in`, `min`, `max`
- Basic aggregate checks: `count`, `sum`, `avg`, `min`, `max`, `distinct_count`
- Query-based validation patterns (`query` type)
- Trino connection/execution logic through the DBAPI client
- Bounded result sampling for large result sets
- Artifact persistence through the shared execution contract
- Structured error handling aligned with the shared reporting structures
- Performance metrics collection and Phase 1 benchmark evidence
- Failure envelope generation with proper error codes
- Engine type normalization and aliasing
- Integration with `compile_rule_payload`

⚠️ **Phase 1 Limitations:**
- Limited to basic constructs (no window functions, complex joins, etc.)
- No schema validation
- Query result caching is not implemented

---

## Implementation Goals

### Primary Goal
Enable end-to-end execution of Trino-backed data quality validations with:
1. SQL generation from canonical rules
2. Trino connection management
3. Query execution and result validation
4. Failure detection and reporting
5. Performance metrics collection

### Success Criteria
| Metric | Target |
|--------|--------|
| Supported row-level rules | 8/8 (100%) |
| Supported aggregate rules | 4/10 (40% - incrementally) |
| Query DQ support | Yes |
| Execution success rate (test suite) | ≥ 95% |
| End-to-end test coverage | ≥ 80% |
| Performance variance vs Spark | ≤ 20% for equivalent rules |

---

## Detailed Implementation Plan

### Phase 1.1: Trino Adapter Module (Week 1)

#### File: `/dq-engine/trino_adapter.py` (NEW)

**Purpose:** Centralize Trino-specific lowering logic and SQL generation

```python
# Key functions to implement:
1. lower_row_rule_to_trino(rule: dict) -> dict[str, Any]
2. lower_aggregate_rule_to_trino(rule: dict) -> dict[str, Any]
3. lower_query_rule_to_trino(rule: dict) -> dict[str, Any]
4. validate_trino_compatibility(rule: dict) -> list[str]
5. escape_trino_identifier(identifier: str) -> str
6. format_trino_literal(value: Any) -> str
```

**Deliverables:**
- ✅ Row-level rule lowering (already in progress)
- ⚠️ Aggregate rule lowering with proper Trino syntax
- ✅ Query rule lowering
- ✅ Schema validation (table/column existence)
- ✅ Identifier escaping for special characters

**Implementation Tasks:**

1. **Create `trino_adapter.py`**
   ```bash
   # Location: dq-engine/trino_adapter.py
   # Imports:
   - re: for identifier validation
   - typing: for type hints
   - runtime_lowerers: for shared utilities
   ```

2. **Implement identifier escaping**
   - Handle backticks, quotes, and special characters
   - Validate identifiers match Trino naming conventions
   ```python
   def escape_trino_identifier(identifier: str) -> str:
       # Trino identifiers are case-insensitive, use backticks
       return f"`{identifier}`"
   ```

3. **Implement literal formatting**
   - Support strings, numbers, booleans, NULL
   - Handle date/time literals
   ```python
   def format_trino_literal(value: Any) -> str:
       if isinstance(value, str):
           return f"'{value}'"
       if isinstance(value, bool):
           return "TRUE" if value else "FALSE"
       if value is None:
           return "NULL"
       # Handle dates
       if isinstance(value, datetime):
           return value.isoformat()
       return str(value)
   ```

4. **Implement row rule lowering**
   - `not_null`: `column IS NOT NULL`
   - `is_null`: `column IS NULL`
   - `equals`: `column = <literal>`
   - `not_equal`: `column != <literal>`
   - `between`: `column BETWEEN <min> AND <max>`
   - `in`: `column IN (<values>)`
   - `not_in`: `column NOT IN (<values>)`
   - `min`: `column >= <min>`
   - `max`: `column <= <max>`
    - Structured scalar filters use `params.where` before the scalar expectation
    - Raw SQL predicates remain unsupported; scalar filters use the same validated filter operators as aggregate filters

5. **Implement aggregate rule lowering**
   - `count`: `SELECT COUNT(*) FROM <table>`
   - `sum`: `SELECT SUM(column) FROM <table>`
   - `avg`: `SELECT AVG(column) FROM <table>`
   - `min`: `SELECT MIN(column) FROM <table>`
   - `max`: `SELECT MAX(column) FROM <table>`
   - `distinct_count`: `SELECT COUNT(DISTINCT column) FROM <table>`
    - Structured pre-aggregation filters use `params.where` as a filter dictionary or list of filter dictionaries
    - Structured post-aggregation filters use `params.having` against the aggregate expression
    - Raw SQL predicates remain unsupported; filter operators are explicit and validated before SQL generation

6. **Implement compatibility validation**
   ```python
   def validate_trino_compatibility(rule: dict) -> list[str]:
       """Return list of unsupported constructs or empty list if compatible"""
       unsupported = []
       
       # Check for unsupported params
       if rule.get("params", {}).get("expression"):
           unsupported.append("custom expression in params")
       
       if rule.get("params", {}).get("sql_predicate"):
           unsupported.append("SQL predicate in params")
       
       if rule.get("params", {}).get("window"):
           unsupported.append("window/analytic functions")
       
       if isinstance(rule.get("params", {}).get("columns"), list):
           unsupported.append("multi-column predicates")
       
       return unsupported
   ```

---

### Phase 1.2: Trino Execution Engine (Week 1-2)

#### File: `/dq-engine/trino_executor.py` (NEW)

**Purpose:** Execute Trino queries and collect results

```python
# Key functions to implement:
1. create_trino_connection(config: dict) -> trino.TrinoClient
2. execute_trino_query(client: TrinoClient, query: str) -> TrinoQueryResult
3. validate_query_result(result: TrinoQueryResult, expected: dict) -> dict[str, Any]
4. collect_query_metrics(client: TrinoClient, query: str) -> dict[str, Any]
5. handle_execution_error(error: Exception, query: str) -> dict[str, Any]
```

**Deliverables:**
- Trino connection pooling
- Query execution with timeout handling
- Result validation against expected values
- Error classification and reporting
- Metrics collection (execution time, rows processed, etc.)

**Implementation Tasks:**

1. **Create Trino client factory**
   ```python
   def create_trino_connection(config: dict[str, Any]) -> TrinoClient:
       """Create and configure Trino connection with pooling"""
       return TrinoClient(
           host=config.get("host", "localhost"),
           port=config.get("http_port", 8080),
           user=config.get("user", "user"),
           catalog=config.get("catalog", "memory"),
           schema=config.get("schema", "default"),
           session_properties={
               "query_max_runtime_ms": str(config.get("timeout_ms", 30000)),
               "memory_per_task": str(config.get("memory", "1GB")),
           },
           extra_credential_headers=config.get("auth_headers", {}),
       )
   ```

2. **Implement query execution**
   ```python
   def execute_trino_query(client: TrinoClient, query: str) -> TrinoQueryResult:
       """Execute query with timeout, streaming fetches, and bounded result sampling"""
       try:
           cursor = client.cursor()
           cursor.execute(query)
           # Fetch in batches and retain only a bounded sample while counting all rows.
           return TrinoQueryResult(rows=sample_rows, row_count=row_count, truncated=truncated)
       except trino.exceptions.TrinoUserError as e:
           raise TrinoExecutionError(f"Trino query error: {e.message}", error_code="DQ_TRINO_QUERY_ERROR")
       except trino.exceptions.TrinoQueryException as e:
           raise TrinoExecutionError(f"Trino query exception: {e}", error_code="DQ_TRINO_QUERY_ERROR")
       except Exception as e:
           raise TrinoExecutionError(f"Query execution failed: {str(e)}", error_code="DQ_TRINO_EXECUTION_ERROR")
   ```

3. **Implement result validation**
   ```python
    def validate_query_result(result: TrinoQueryResult, expected: dict) -> dict:
       """Validate query results against expected values"""
       validation_result = {
           "passed": True,
           "actual_count": len(result),
           "expected_count": expected.get("expected_count"),
           "failed_rows": [],
           "details": {}
       }
       
       # Check count
       if expected.get("expected_count") is not None:
           if len(result) != expected["expected_count"]:
               validation_result["passed"] = False
               validation_result["details"]["count_mismatch"] = True
       
       # Check for failed rows
       if validation_result["passed"]:
           validation_result["failed_rows"] = []
       
       return validation_result
   ```

4. **Implement metrics collection**
   ```python
   def collect_query_metrics(client: TrinoClient, query: str) -> dict:
       """Collect query performance metrics"""
       metrics = {
           "query_id": None,
           "start_time": None,
           "end_time": None,
           "duration_ms": None,
           "rows_returned": 0,
           "plan_nodes": None,
           "warnings": [],
       }
       return metrics
   ```

---

### Phase 1.3: Configuration and Setup (Week 1)

#### File: `/dq-engine/trino_config.py` (NEW)

**Purpose:** Centralize Trino configuration and defaults

```python
# Key contents:
DEFAULT_TRINO_CONFIG = {
    "host": "localhost",
    "http_port": 8080,
    "user": "trino_user",
    "catalog": "hive",
    "schema": "default",
    "timeout_ms": 30000,
    "memory_per_task": "1GB",
}

# Environment variable mappings
TRINO_CONFIG_KEYS = {
    "DQ_TRINO_HOST": "host",
    "DQ_TRINO_PORT": "http_port",
    "DQ_TRINO_USER": "user",
    "DQ_TRINO_TIMEOUT": "timeout_ms",
    # ... etc
}
```

**Deliverables:**
- Default configuration
- Environment variable support
- Configuration validation
- Connection pool settings

---

### Phase 1.4: End-to-End Integration (Week 2)

#### File: `/dq-engine/trino_execution_pipeline.py` (NEW)

**Purpose:** Orchestrate the full execution pipeline

```python
# Key functions to implement:
1. create_trino_execution_plan(rule: dict, config: dict) -> ExecutionPlan
2. execute_trino_pipeline(plan: ExecutionPlan) -> ExecutionResult
3. persist_trino_artifacts(result: ExecutionResult, output_dir: str) -> None
```

**Deliverables:**
- Full execution pipeline
- Artifact persistence
- Error handling and recovery
- Result aggregation

---

### Phase 1.5: Testing and Validation (Week 2-3)

#### Test Files to Create/Update

1. **`/dq-engine/tests/test_trino_adapter.py`** (NEW)
   - Row-level rule lowering tests
   - Aggregate rule lowering tests
   - Query rule lowering tests
   - Identifier escaping tests
   - Literal formatting tests

2. **`/dq-engine/tests/test_trino_executor.py`** (NEW)
   - Connection creation tests
   - Query execution tests (mock)
   - Result validation tests
   - Error handling tests
   - Metrics collection tests

3. **`/dq-engine/tests/test_trino_integration.py`** (NEW)
   - End-to-end integration tests
   - Local Trino container tests
   - Performance benchmarks

4. **Update `/dq-engine/tests/test_runtime_lowerer_registry.py`**
   - Add Trino-specific test cases
   - Update existing tests to cover new functionality

**Test Coverage Targets:**
- Unit tests: 90%+ coverage
- Integration tests: All public APIs
- Performance tests: Baseline for each rule type

---

## File Structure

```
dq-engine/
├── trino_adapter.py              [NEW] - Core lowering logic
├── trino_executor.py             [NEW] - Query execution
├── trino_config.py               [NEW] - Configuration
├── trino_execution_pipeline.py   [NEW] - Orchestration
├── tests/
│   ├── test_trino_adapter.py        [NEW]
│   ├── test_trino_executor.py       [NEW]
│   ├── test_trino_integration.py    [NEW]
│   └── test_trino_performance.py    [NEW]
└── runtime_lowerers.py           [UPDATE] - Update get_runtime_lowerer
```

---

## Integration Points

### 1. Update `runtime_lowerers.py`

**Changes needed:**
- Move Trino-specific logic to `trino_adapter.py`
- Update `lower_rule_to_trino()` to delegate to new adapter
- Add configuration loading support

```python
# Before:
def lower_rule_to_trino(rule: dict[str, Any]) -> dict[str, Any]:
    # Direct implementation...

# After:
def lower_rule_to_trino(rule: dict[str, Any]) -> dict[str, Any]:
    from trino_adapter import lower_row_rule_to_trino, lower_aggregate_rule_to_trino
    
    # Delegate to appropriate lowerer...
```

### 2. Use the engine-neutral execution dispatch flow

**Changes needed:**
- Publish Trino execution outcomes through the shared run/report/result/error contract
- Reuse the existing reporting API that persists results/errors to Postgres and StorIO
- Keep execution dispatch internal instead of adding a Trino-specific public endpoint

```python
# Engine dispatch flow:
# execution_dispatch.process_engine_dispatch_message(..., engine_type="trino")
# -> /rulebuilder/v1/gx/runs/{run_id}/report compatibility contract
```

### 3. Update `docker-compose.yml`

**Changes needed:**
- Add Trino service
- Add configuration for Trino connection
- Add health checks

```yaml
# Add to docker-compose.yml:
trino:
    image: ${DQ_TRINO_REGISTRY:-}${DQ_TRINO_NAMESPACE:-}${DQ_TRINO_IMAGE:-dq-made-easy-trino}:${DQ_TRINO_TAG:-latest}
    build:
        context: ./dq-trino
        dockerfile: Dockerfile.trino
        args:
            TRINO_BASE_IMAGE: ${TRINO_BASE_IMAGE:-trinodb/trino:477}
  ports:
        - "${TRINO_HOST_BIND:-127.0.0.1}:${TRINO_HOST_PORT:-8084}:8080"
  # ... etc
```

---

## Milestones

### Milestone 1: Adapter Foundation (Week 1, Day 1-3)
- [x] Create `trino_adapter.py`
- [x] Implement identifier escaping
- [x] Implement literal formatting
- [x] Implement row rule lowering
- [x] Write unit tests (row rules)
- [x] **Acceptance:** All row-level rules generate correct Trino SQL
    - Evidence: [test-results/test-proof/0.11.5/api/dq-engine-trino-lowerer-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-lowerer-2026-06-30.json)
    - Scalar filter proof: [test-results/test-proof/0.11.5/api/dq-engine-trino-scalar-filters-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-scalar-filters-2026-06-30.json)

### Milestone 2: Aggregate Rules (Week 1, Day 4-6)
- [x] Implement aggregate rule lowering
- [x] Add DISTINCT support
- [x] Add aggregate function aliases
- [x] Add WHERE filters before aggregation
- [x] Add HAVING filters after aggregation
- [x] Write unit tests (aggregate rules)
- [x] **Acceptance:** All aggregate rules generate correct Trino SQL
    - Evidence: [test-results/test-proof/0.11.5/api/dq-engine-trino-aggregate-lowerer-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-aggregate-lowerer-2026-06-30.json)

### Milestone 3: Execution Engine (Week 2, Day 1-4)
- [x] Create `trino_executor.py`
- [x] Implement connection factory
- [x] Implement query execution
- [x] Implement result validation
- [x] Write unit tests (executor)
- [x] **Acceptance:** Queries execute successfully against Trino
    - Evidence: [test-results/test-proof/0.11.5/api/dq-engine-trino-executor-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-executor-2026-06-30.json)

### Milestone 4: Integration (Week 2, Day 5-7)
- [x] Create `trino_execution_pipeline.py`
- [x] Implement end-to-end flow
- [x] Add artifact persistence
- [x] Update `runtime_lowerers.py`
- [x] Write integration tests
- [x] **Acceptance:** Full rule execution works end-to-end
    - Evidence: [test-results/test-proof/0.11.5/api/dq-engine-trino-integration-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-integration-2026-06-30.json)

### Milestone 5: Testing & Performance (Week 3)
- [x] Complete test coverage
- [x] Performance benchmarks
- [x] Error handling validation
- [x] Documentation
- [x] **Acceptance:** All tests pass, performance within bounds
    - Evidence: [test-results/test-proof/0.11.5/api/dq-engine-trino-milestone-5-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-milestone-5-2026-06-30.json)

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Trino connection issues | Medium | Use connection pooling, add retry logic |
| SQL dialect differences | Medium | Start with simple rules, document unsupported features |
| Performance overhead | Medium | Benchmark against Spark, optimize hot paths |
| Large result sets | Medium | Implement streaming, add pagination |
| Security vulnerabilities | High | Validate SQL injection, use parameterized queries |
| Configuration complexity | Low | Use sensible defaults, add validation |

---

## Testing Strategy

### Unit Tests
- Test SQL generation for each rule type
- Test identifier escaping
- Test literal formatting
- Test error cases

### Integration Tests
- Test with local Trino container
- Test with different data sources
- Test with large datasets
- Test error scenarios

### Performance Tests
- Benchmark query execution time
- Test memory usage
- Test throughput
- Validate Trino Phase 1 lowering throughput, in-process execution throughput, and bounded large-result sampling with `scripts/validation/benchmark_trino_phase1.py`

---

## Acceptance Criteria

### Must Have
- [x] All row-level rules (not_null, equals, not_equal, between, in, not_in, min, max) generate valid Trino SQL
    - Evidence: [test-results/test-proof/0.11.5/api/dq-engine-trino-lowerer-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-lowerer-2026-06-30.json)
    - Scalar filter proof: [test-results/test-proof/0.11.5/api/dq-engine-trino-scalar-filters-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-scalar-filters-2026-06-30.json)
- [x] Basic aggregate rules (count, sum, avg, min, max) generate valid Trino SQL
    - Evidence: [test-results/test-proof/0.11.5/api/dq-engine-trino-lowerer-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-lowerer-2026-06-30.json)
    - Milestone 2 proof: [test-results/test-proof/0.11.5/api/dq-engine-trino-aggregate-lowerer-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-aggregate-lowerer-2026-06-30.json)
- [x] Query DQ rules execute correctly and results are persisted
    - Evidence: `cd dq-engine && /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_executor.py tests/test_trino_execution_pipeline.py tests/test_trino_adapter.py tests/test_runtime_lowerer_registry.py -q`
    - Milestone 4 proof: [test-results/test-proof/0.11.5/api/dq-engine-trino-integration-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-integration-2026-06-30.json)
    - Dispatch evidence: `cd dq-engine && /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_spark_expectations_adapter.py::test_process_dispatch_message_routes_spark_expectations_payload tests/test_spark_expectations_adapter.py::test_process_dispatch_message_reports_structured_spark_expectations_failure tests/test_spark_expectations_adapter.py::test_process_dispatch_message_routes_sql_engine_through_shared_reporting tests/test_trino_execution_pipeline.py::test_query_rule_execution_persists_bounded_results_and_query_artifact -q`
    - Live container evidence: with Trino already running via `./scripts/stack_ctl.sh start --profile trino`, run `scripts/validation/validate_trino_live_container.sh` (`2 passed` live; broader Trino/dispatch suite with live tests: `49 passed`).
- [x] Connection management works reliably
    - Evidence: `cd dq-engine && /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_executor.py tests/test_trino_execution_pipeline.py -q`
    - Milestone 3 proof: [test-results/test-proof/0.11.5/api/dq-engine-trino-executor-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-executor-2026-06-30.json)
- [x] Error handling produces meaningful messages and is aligned with the existing error reporting structures, persisted and available through the reporting APIs
    - Evidence: `cd dq-engine && /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_execution_pipeline.py tests/test_spark_expectations_adapter.py::test_process_dispatch_message_reports_structured_spark_expectations_failure -q`
    - Trino-specific proof: structured `failure_code`, `failure_message`, `failed_check`, `failure_metrics`, `trace`, and `error_management` fields are persisted to `trino_execution.json`/`trino_errors.json` and propagated through the generic run reporting flow.
- [x] All Trino related tests pass (≥90% coverage)
    - Evidence: `cd dq-engine && DQ_TRINO_HOST=127.0.0.1 DQ_TRINO_PORT=8084 DQ_TRINO_CATALOG=memory DQ_TRINO_SCHEMA=default /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_adapter.py tests/test_trino_executor.py tests/test_trino_execution_pipeline.py tests/test_runtime_lowerer_registry.py tests/test_trino_live_container.py --cov=trino_adapter --cov=trino_config --cov=trino_executor --cov=trino_execution_pipeline --cov-report=term-missing --cov-fail-under=90 -q -rs`
    - Result: `90 passed in 1.05s`; coverage gate reached with total coverage `95.24%` (`trino_adapter.py` 96%, `trino_config.py` 93%, `trino_execution_pipeline.py` 95%, `trino_executor.py` 96%).
    - Proof: [test-results/test-proof/0.11.5/api/dq-engine-trino-coverage-gate-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-coverage-gate-2026-06-30.json)
    - Milestone 5 proof: [test-results/test-proof/0.11.5/api/dq-engine-trino-milestone-5-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-milestone-5-2026-06-30.json)
    - Raw evidence: [test-results/evidence/0.11.5/api/20260630T150000Z-dq-engine-trino-coverage-gate](../../test-results/evidence/0.11.5/api/20260630T150000Z-dq-engine-trino-coverage-gate)
    - Latest raw evidence: [test-results/evidence/0.11.5/api/20260630T172000Z-dq-engine-trino-milestone-5](../../test-results/evidence/0.11.5/api/20260630T172000Z-dq-engine-trino-milestone-5)

### Should Have
- [ ] Performance metrics collection through the existing APIs and persistence
- [ ] Schema validation
- [ ] Query result caching
- [ ] Streaming for large results, where aggregated results are stored in postgres and large detailed results on AIStor, the same way as for other lowerers
- [ ] Comprehensive documentation

### Nice to Have
- [ ] Window function support
- [ ] Complex joins
- [ ] Subquery support
- [ ] CTE support
- [ ] Automatic optimization hints

### Milestone 1 Evidence
- Raw evidence: [test-results/evidence/0.11.5/api/20260630T135805Z-dq-engine-trino-lowerer](../../test-results/evidence/0.11.5/api/20260630T135805Z-dq-engine-trino-lowerer)
- Scalar filter raw evidence: [test-results/evidence/0.11.5/api/20260630T163000Z-dq-engine-trino-scalar-filters](../../test-results/evidence/0.11.5/api/20260630T163000Z-dq-engine-trino-scalar-filters)
- Curated proof: [test-results/test-proof/0.11.5/api/dq-engine-trino-lowerer-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-lowerer-2026-06-30.json)
- Scalar filter proof: [test-results/test-proof/0.11.5/api/dq-engine-trino-scalar-filters-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-scalar-filters-2026-06-30.json)
- Focused test command: `cd dq-engine && /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_adapter.py tests/test_runtime_lowerer_registry.py -q`

### Milestone 2 Evidence
- Raw evidence: [test-results/evidence/0.11.5/api/20260630T161500Z-dq-engine-trino-aggregate-lowerer](../../test-results/evidence/0.11.5/api/20260630T161500Z-dq-engine-trino-aggregate-lowerer)
- Curated proof: [test-results/test-proof/0.11.5/api/dq-engine-trino-aggregate-lowerer-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-aggregate-lowerer-2026-06-30.json)
- Focused test command: `cd dq-engine && /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_adapter.py tests/test_runtime_lowerer_registry.py -q`

### Milestone 3 Evidence
- Raw evidence: [test-results/evidence/0.11.5/api/20260630T164500Z-dq-engine-trino-executor](../../test-results/evidence/0.11.5/api/20260630T164500Z-dq-engine-trino-executor)
- Curated proof: [test-results/test-proof/0.11.5/api/dq-engine-trino-executor-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-executor-2026-06-30.json)
- Focused test command: `cd dq-engine && /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_executor.py -q`

### Milestone 4 Evidence
- Raw evidence: [test-results/evidence/0.11.5/api/20260630T170000Z-dq-engine-trino-integration](../../test-results/evidence/0.11.5/api/20260630T170000Z-dq-engine-trino-integration)
- Curated proof: [test-results/test-proof/0.11.5/api/dq-engine-trino-integration-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-integration-2026-06-30.json)
- Focused test command: `cd dq-engine && /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_execution_pipeline.py tests/test_runtime_lowerer_registry.py -q`

### Milestone 5 Evidence
- Test and coverage raw evidence: [test-results/evidence/0.11.5/api/20260630T172000Z-dq-engine-trino-milestone-5](../../test-results/evidence/0.11.5/api/20260630T172000Z-dq-engine-trino-milestone-5)
- Benchmark raw evidence: [test-results/evidence/0.11.5/api/20260630T171500Z-dq-engine-trino-phase1-benchmark](../../test-results/evidence/0.11.5/api/20260630T171500Z-dq-engine-trino-phase1-benchmark)
- Curated proof: [test-results/test-proof/0.11.5/api/dq-engine-trino-milestone-5-2026-06-30.json](../../test-results/test-proof/0.11.5/api/dq-engine-trino-milestone-5-2026-06-30.json)
- Coverage command: `cd dq-engine && DQ_TRINO_HOST=127.0.0.1 DQ_TRINO_PORT=8084 DQ_TRINO_CATALOG=memory DQ_TRINO_SCHEMA=default /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_adapter.py tests/test_trino_executor.py tests/test_trino_execution_pipeline.py tests/test_runtime_lowerer_registry.py tests/test_trino_live_container.py --cov=trino_adapter --cov=trino_config --cov=trino_executor --cov=trino_execution_pipeline --cov-report=term-missing --cov-fail-under=90 -q -rs`
- Benchmark command: `cd /Users/Jac.Beekers/gitrepos/dq-made-easy && /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python scripts/validation/benchmark_trino_phase1.py --output test-results/evidence/0.11.5/api/20260630T171500Z-dq-engine-trino-phase1-benchmark/benchmark.json`

---

## Rollout Plan

### Phase 1: Internal Testing (Week 4)
- Deploy to staging environment
- Run internal test suite
- Validate with sample data

### Phase 2: Pilot (Week 5-6)
- Enable for internal users
- Collect feedback
- Monitor performance

### Phase 3: Production (Week 7+)
- Gradual rollout
- Feature flag for Trino backend
- Full documentation

---

## Dependencies

### External Dependencies
- Trino server (latest stable version)
- Python Trino client (`trino` package)

### Internal Dependencies
- Existing `runtime_lowerers.py` infrastructure
- `compile_rule_payload` API
- Failure envelope system
- Configuration management

---

## Timeline

```
Week 1: Adapter Foundation
├─ Day 1-2: trino_adapter.py creation
├─ Day 3-4: Row rule implementation
├─ Day 5: Aggregate rules
└─ Day 6-7: Testing

Week 2: Execution Engine
├─ Day 1-2: trino_executor.py creation
├─ Day 3-4: Connection management
├─ Day 5-6: Query execution
└─ Day 7: Integration

Week 3: Testing & Polish
├─ Day 1-2: Full test suite
├─ Day 3-4: Performance testing
├─ Day 5: Documentation
└─ Day 6-7: Review and deployment
```

---

## Appendix A: Supported Rule Types Matrix

| Rule Type | Supported | SQL Example | Notes |
|-----------|-----------|-------------|-------|
| `not_null` | ✅ | `column IS NOT NULL` | - |
| `is_null` | ✅ | `column IS NULL` | - |
| `equals` | ✅ | `column = 'value'` | - |
| `not_equal` | ✅ | `column != 'value'` | - |
| `between` | ✅ | `column BETWEEN a AND b` | - |
| `in` | ✅ | `column IN ('a', 'b')` | - |
| `not_in` | ✅ | `column NOT IN ('a', 'b')` | - |
| `min` | ✅ | `column >= <min>` | Row-level |
| `max` | ✅ | `column <= <max>` | Row-level |
| `count` | ✅ | `SELECT COUNT(*)` | Aggregate |
| `sum` | ✅ | `SELECT SUM(column)` | Aggregate |
| `avg` | ✅ | `SELECT AVG(column)` | Aggregate |
| `distinct_count` | ✅ | `SELECT COUNT(DISTINCT column)` | Aggregate |

---

## Appendix B: Unsupported Constructs

The following constructs are **NOT supported** in Phase 1 and must be rejected:

1. Custom expressions in `params.expression`
2. SQL predicates in `params.sql_predicate`
3. Window/analytic functions in `params.window`
4. Multi-column predicates
5. Nested queries
6. JOIN operations
7. UNION/INTERSECT/EXCEPT
8. Complex subqueries
9. Stored procedure calls

These should be documented and rejected with clear error messages.

---

## Appendix C: Error Codes Reference

| Code | Description | Trigger |
|------|-------------|---------|
| `DQ_TRINO_CONNECTION_FAILED` | Unable to establish Trino connection | Connection error |
| `DQ_TRINO_QUERY_ERROR` | SQL query execution failed | Trino error |
| `DQ_TRINO_RESULT_MISMATCH` | Query results don't match expectations | Validation |
| `DQ_TRINO_UNSUPPORTED_RULE` | Rule type not supported | Compatibility check |
| `DQ_TRINO_INVALID_IDENTIFIER` | Invalid column/table name | Validation |
| `DQ_TRINO_INVALID_LITERALS` | Invalid literal values | Validation |

---

## Contact & Support

**Questions:** Contact the implementation team  
**Documentation:** See `docs/implementation-details/`  
**Support:** #dq-engine Slack channel  

---

*Last Updated: 2026-06-29*  
*Version: 1.0*
