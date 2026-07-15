# DQ-20 Reusable DQ Engine Library — Pip-Installable, Offline-First

Status: Proposed

## Goal

Make the DQ Engine distributable as a `pip`-installable Python wheel that can be imported and used programmatically **without** Kong, Redis, OIDC, Kafka, or any external infrastructure. This enables the engine to be used:

- Directly from the **dq-cli** for local validation runs
- Inside **CI/CD pipelines** for pre-commit or gate-style validation
- As a **library dependency** in custom Python scripts, notebooks, or Airflow operators
- In **embedded** or edge environments where a full service mesh is unavailable

The existing infrastructure-bound dispatch flow (Kong → dq-api → Redis → dq-engine worker) remains **completely unchanged**. This feature adds a parallel, lightweight execution path.

## Why this feature matters

Today, running a DQ validation requires the full stack: Kong, dq-api, Redis, Spark, S3, OIDC, and the engine container. For lightweight use cases — a developer validating rules against a local CSV, a CI pipeline checking data quality before merge, or a notebook experiment — this is overkill.

By making the core execution logic available as a library, we lower the barrier to entry and give users a way to validate data quality at any scale: from a local file to a distributed warehouse.

## Scope

### In scope

- `pyproject.toml` for the `dq-engine` package with proper optional dependency groups
- Pure-Python execution entry points that accept rule payloads and data sources directly
- Optional/strategy-based reporting (no-op by default, pluggable callbacks)
- Optional Spark initialization (lazy-loaded only when needed)
- Optional Redis, Kafka, OIDC dependencies (all behind extras)
- CLI integration: `dq-cli` calls the engine library directly for local runs
- Unit tests for the pure-Python execution path
- Documentation for pip installation and programmatic usage

### Out of scope

- Replacing or modifying the existing Redis-based dispatch worker
- Replacing Kong, OIDC, or API-based reporting in the production flow
- Rewriting the rule model or introducing new rule syntax
- Adding new execution engines (that is DQ-19)
- Full Spark integration as a default (Spark remains optional)

## Current architecture (unchanged)

The existing flow must remain untouched:

```
dq-cli ──(HTTP/REST)──► Kong ──► dq-api ──(Redis queue)──► dq-engine worker
                                                               │
                                                           Spark + S3
                                                               │
                                                         Kafka (violations)
```

## New architecture (additive)

A parallel, infrastructure-free path:

```
dq-cli (or any Python code)
    │
    │  import dq_engine
    │  result = dq_engine.run_validation(rules, data_source)
    │
    ▼
dq-engine library (pure Python)
    │
    ├─── execute_engine_rule_payload()     ← already exists, already pure
    ├─── build_execution_report_summary()  ← already exists, already pure
    └─── build_execution_report_details()  ← already exists, already pure
```

## Existing code already supports this

The core execution function `execute_engine_rule_payload()` in `dq_plan_execution_orchestrator.py` is already a pure function:

```python
def execute_engine_rule_payload(
    *,
    engine_type: str,
    rule_payload: dict[str, Any],
    output_dir: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
```

It:
- Takes a rule dict and engine type
- Returns a result dict
- Does **not** call the API, Redis, Kafka, or OIDC

The reporting callbacks in `process_engine_dispatch_message()` are already parameterized:

```python
async def process_engine_dispatch_message(
    config: DqWorkerConfig,
    *,
    payload: dict[str, Any],
    run_id: str,
    correlation_id: str,
    requested_by: str | None,
    report_run_fn: ReportRunFn = report_run,
    report_progress_fn: ReportProgressFn | None = None,
    token_provider_factory: TokenProviderFactory = build_token_provider,
    execute_payload_fn: ExecutePayloadFn = execute_engine_rule_payload,
) -> dict[str, Any]:
```

This means the infrastructure coupling is already partially abstracted via strategy parameters.

## Proposed changes

### 1. Package manifest (`pyproject.toml`)

Create a proper buildable package with optional dependencies:

```toml
[project]
name = "dq-engine"
dynamic = ["version"]
dependencies = [
    "requests>=2.31",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
redis = ["redis>=5.0"]
kafka = ["kafka-python>=2.0"]
spark = ["pyspark>=4.0", "delta-spark>=4.0", "boto3>=1.30"]
gx = ["great-expectations>=1.18"]
soda = []
trino = ["trino>=0.326"]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"
```

### 2. Optional config fields

Make `DqWorkerConfig` fields optional for local execution:

```python
@dataclass(frozen=True)
class DqWorkerConfig:
    # Infrastructure fields — None means "not used"
    redis_url: str | None = None
    queue_key: str | None = None
    processing_queue_key: str | None = None
    heartbeat_key: str | None = None
    heartbeat_ttl_seconds: int | None = None
    heartbeat_interval_seconds: int | None = None
    api_url: str | None = None

    # Execution fields
    max_rows: int = 100000
    spark_master: str | None = None
    spark_ui_port: int | None = None

    # S3 fields
    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str | None = None
    s3_path_style_access: bool = True
    s3_ssl_enabled: bool | None = None
```

Add a factory for minimal configs:

```python
@dataclass(frozen=True)
class DqWorkerConfig:
    @classmethod
    def for_local_execution(
        cls,
        *,
        max_rows: int = 100000,
        spark_master: str | None = None,
    ) -> "DqWorkerConfig":
        """Build a config suitable for offline/local execution."""
        return cls(
            max_rows=max_rows,
            spark_master=spark_master,
        )
```

### 3. Public library API

Add a `dq_engine/__init__.py` (or `dq_engine/execution.py`) with the primary entry points:

```python
"""DQ Engine — reusable validation execution library.

Usage (no infrastructure required):
    from dq_engine import run_validation, SourceLocation, ExecutionResult

    result = run_validation(
        rules=[...],
        data_source=SourceLocation(uri="file:///data/input.parquet", format="parquet"),
        engine_type="spark_expectations",
    )
    print(result.summary)
"""

def run_validation(
    rules: list[dict[str, Any]],
    *,
    engine_type: str = "spark_expectations",
    output_dir: str | None = None,
    config: dict[str, Any] | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
    on_complete: Callable[[ExecutionResult], None] | None = None,
) -> ExecutionResult:
    """Execute validation rules against data without Redis, Kong, or OIDC.

    This is the primary entry point for CLI, CI/CD, and library usage.
    Returns immediately with results. No external services are contacted.
    """
    ...

def execute_rule(
    *,
    engine_type: str,
    rule_payload: dict[str, Any],
    output_dir: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a single rule payload. Thin wrapper around the core executor."""
    ...
```

### 4. Lazy Spark initialization

Make Spark session creation lazy so it only starts when actually needed:

```python
def _create_spark_session(config: DqWorkerConfig, enable_delta: bool = False):
    if config.spark_master is None:
        # Auto-detect or use local mode
        spark_master = os.getenv("SPARK_MASTER", "local[*]")
    else:
        spark_master = config.spark_master
    ...
```

### 5. No-op reporting callbacks

Provide built-in no-op callbacks for offline execution:

```python
def _no_op_report_run(*args, **kwargs) -> None:
    """No-op callback — does not contact any API."""
    pass

def _no_op_report_progress(*args, **kwargs) -> None:
    """No-op callback — does not contact any API."""
    pass
```

### 6. CLI integration

Add a local execution command to `dq-cli` that calls the library directly:

```bash
dq-run-plan execute --engine spark_expectations --rules rules.json --data /path/to/data.parquet
```

This bypasses Kong entirely and calls `dq_engine.run_validation()` directly.

### 7. Remove FastAPI from default behavior

Make `main.py` the FastAPI server opt-in (e.g., behind a CLI flag or separate entry point), not the default package behavior. The library should be importable without side effects.

### 8. Lazy optional dependency imports

Wrap all optional imports so they fail gracefully:

```python
# Instead of:
import redis  # fails if not installed

# Use:
try:
    import redis
    _REDIS_AVAILABLE = True
except ImportError:
    redis = None
    _REDIS_AVAILABLE = False
```

This already exists in some modules (`gx_queue_service.py`, `kafka_client.py`). Extend it to all optional infrastructure.

## Acceptance criteria

- `pip install dq-engine` succeeds without Redis, Spark, Kafka, or OIDC packages
- `from dq_engine import run_validation` imports without side effects
- `run_validation()` executes rules and returns results without contacting any external service
- The existing worker loop (`gx_dispatch_worker.py`) continues to work unchanged with Redis/Kong/OIDC
- The FastAPI server (`main.py`) starts unchanged when run as a service
- `dq-cli` can use the library path for local execution
- Unit tests cover the pure-Python execution path
- All existing tests continue to pass

## Proposed workstreams

### 1. Package foundation
- Create `pyproject.toml` with optional dependency groups
- Add `__init__.py` with public API surface
- Add lazy import guards for all optional dependencies
- [ ] `DQ-20.1` Package manifest and build system
- [ ] `DQ-20.2` Lazy import guards for redis, kafka, spark, trino, gx

### 2. Config decoupling
- Make `DqWorkerConfig` fields optional with defaults
- Add `DqWorkerConfig.for_local_execution()` factory
- Make `_resolve_spark_master()` return `None` when unavailable
- Make `_resolve_api_url()` return `None` when unavailable
- [ ] `DQ-20.3` Optional DqWorkerConfig fields
- [ ] `DQ-20.4` Local execution config factory
- [ ] `DQ-20.5` Lazy Spark master resolution

### 3. Public API surface
- Implement `run_validation()` entry point
- Implement `execute_rule()` single-rule entry point
- Define `ExecutionResult` dataclass
- Provide no-op reporting callbacks
- [ ] `DQ-20.6` run_validation() entry point
- [ ] `DQ-20.7` ExecutionResult dataclass
- [ ] `DQ-20.8` No-op reporting callbacks

### 4. CLI integration
- Add `dq-run-plan execute` command for local validation
- Wire `dq-cli` to call `dq_engine.run_validation()` directly
- Support `--data`, `--rules`, `--engine` flags
- [ ] `DQ-20.9` CLI execute command
- [ ] `DQ-20.10` CLI flag definitions

### 5. Testing
- Unit tests for `run_validation()` with mock rules
- Unit tests for `execute_engine_rule_payload()` isolation
- Integration test: `pip install dq-engine` + basic execution
- Regression test: existing worker flow unchanged
- [ ] `DQ-20.11` Unit tests for pure execution path
- [ ] `DQ-20.12` Integration test for pip installation
- [ ] `DQ-20.13` Regression test for existing worker

### 6. Documentation
- Add usage examples for CLI, CI/CD, and library modes
- Document optional dependency installation matrix
- Add migration guide for users coming from full-stack deployment
- [ ] `DQ-20.14` Library usage documentation
- [ ] `DQ-20.15` CI/CD integration examples
- [ ] `DQ-20.16` Optional dependency matrix

## Risk assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Breaking existing worker by making config optional | Low | Backward-compat aliases already exist; add validation in `load_config()` for worker mode |
| Spark dependency too heavy for pip install | Medium | Spark is an optional extra; `pip install dq-engine[spark]` |
| GX dependency too heavy | Medium | GX is an optional extra; `pip install dq-engine[gx]` |
| Tests assume Redis/OIDC availability | Medium | Split tests into `core/` (no infra) and `infrastructure/` (needs stack) |

## Success criteria

- A developer can `pip install dq-engine`, import the library, and run a validation against a local file in under 30 seconds without any infrastructure setup.
- The existing production dispatch flow (Redis → worker → Spark → API reporting) is demonstrably unchanged and fully tested.
- The `dq-cli` supports both the existing API-gateway mode and the new local-execution mode.

## Related references

- [ABS_1_EXECUTION_ABSTRACTION.md](/docs/features/ABS_1_EXECUTION_ABSTRACTION/) — execution abstraction foundation
- [DQ_19_MULTI_RUNTIME_LOWERERS.md](/docs/features/DQ_19_MULTI_RUNTIME_LOWERERS/) — multi-runtime lowerers (complementary)
- [DQ-7 Executable Rule Transformation](/docs/features/DQ-7_EXECUTABLE_RULE_TRANSFORMATION/) — rule execution foundation
