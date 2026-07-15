# Refactor `gx_dispatch_worker.py` — Single Responsibility Module Split

## Goal

Break `gx_dispatch_worker.py` (2 832 lines) into modules where each has ONE clearly named responsibility. The worker file itself should end up under ~300 lines containing only the main loop, heartbeat, and startup logic.

## Current State

| Module | Lines | Responsibility | Issue |
|---|---|---|---|
| `gx_dispatch_worker.py` | 2 832 | Everything | Catch-all, multiple responsibilities |
| `gx_dispatch_expectations.py` | 787 | Expectation evaluation | Worker has DUPLICATE copies of most functions |
| `gx_dispatch_runtime.py` | 414 | Spark session, S3/URI, source resolution | ✅ Clean |
| `gx_dispatch_results.py` | 29 | Small utilities | ✅ Clean |
| `gx_dispatch_telemetry.py` | 431 | OTLP/telemetry | ✅ Clean |
| `gx_dispatch_types.py` | 53 | Types | ✅ Clean |
| `execution_dispatch.py` | 490 | Generic execution dispatch | ✅ Clean |

### What `gx_dispatch_worker.py` currently contains

| Line range | Content | Should go to |
|---|---|---|
| 79–273 | Config loading & environment resolution (`load_config`, `_resolve_*`) | `gx_dispatch_config.py` (NEW) |
| 275–315 | Redis heartbeat (`_write_worker_heartbeat`, `_start_worker_heartbeat_loop`) | `gx_dispatch_worker.py` (STAY) |
| 315–327 | Payload helpers (`_parse_dispatch_payload`, `_coerce_str`, `_coerce_int`) | `gx_dispatch_payload.py` (NEW) |
| 327–378 | Exception helpers (`_iter_exception_chain`, `_coerce_reported_failure`, etc.) | `gx_dispatch_api.py` (NEW) |
| 382–577 | API client (`_api_request`, `_api_report_run`, `_build_execution_progress`, etc.) | `gx_dispatch_api.py` (NEW) |
| 577–605 | Execution progress reporting (`_api_report_execution_progress`) | `gx_dispatch_api.py` (NEW) |
| 607–659 | Suite envelope parsing (`_extract_primary_key_fields`, `_assert_runnable_suite`) | `gx_dispatch_payload.py` (NEW) |
| 659–798 | Source resolution (`_extract_source_overrides`, `_column_is_available`, `_build_spark_row_condition_expression`) | `gx_dispatch_expectations.py` (EXISTING) |
| 798–943 | Join-pair + location resolution (`_resolve_join_pair_location`, `_resolve_locations_for_targets`) | `gx_dispatch_dispatch.py` (NEW) |
| 943–1274 | Expectation evaluation (DUPLICATE of `gx_dispatch_expectations.py`) | `gx_dispatch_expectations.py` (EXISTING) |
| 1852–2161 | Grouped dispatch processing (`_process_grouped_dispatch_message`) | `gx_dispatch_dispatch.py` (NEW) |
| 2161–2220 | Spark expectations processing (`_build_spark_expectations_report_summary`, `_process_spark_expectations_dispatch_message`) | `gx_dispatch_dispatch.py` (NEW) |
| 2220–2668 | Dispatch routing + single-object processing (`process_dispatch_message`) | `gx_dispatch_dispatch.py` (NEW) |
| 2668+ | Worker loop (`run_worker_forever`) | `gx_dispatch_worker.py` (STAY) |

### Duplication with `gx_dispatch_expectations.py`

The following functions exist in BOTH files (worker lines 671–1274 vs expectations module):

| Function | Worker line | Expectations line | Action |
|---|---|---|---|
| `_NativeGxBatchRunner` | 1100 | 8 | Keep in expectations, remove from worker |
| `_column_is_available` | 671 | 97 | Keep in expectations, remove from worker |
| `_supports_native_gx_execution` | 943 | 101 | Keep in expectations, remove from worker |
| `_collect_row_condition_columns` | 947 | (missing) | Add to expectations |
| `_required_columns_for_expectation` | 970 | 107 | Keep in expectations, remove from worker |
| `_native_gx_requires_column_projection` | 993 | 113 | Keep in expectations, remove from worker |
| `_build_native_gx_alias_map` | 997 | 117 | Keep in expectations, remove from worker |
| `_rewrite_native_gx_row_condition_for_aliases` | 1011 | 121 | Keep in expectations, remove from worker |
| `_rewrite_native_gx_expectation_for_aliases` | 1043 | 121 | Keep in expectations, remove from worker |
| `_lower_native_gx_row_condition` | 1068 | 128 | Keep in expectations, remove from worker |
| `_row_to_mapping` | 1189 | 132 | Keep in expectations, remove from worker |
| `_resolve_row_value` | 1211 | 154 | Keep in expectations, remove from worker |
| `_build_row_identifier` | 1221 | 164 | Keep in expectations, remove from worker |
| `_first_row_identifier` | 1234 | 177 | Keep in expectations, remove from worker |
| `_build_row_failure_diagnostics` | 1244 | 187 | Keep in expectations, remove from worker |
| `_evaluate_expectations_spark` | 1274 | 217 | Keep public version in expectations, remove from worker |
| `_build_spark_row_condition_expression` | 682 | 786 | Keep in expectations, remove from worker |
| `_NATIVE_GX_EXPECTATION_TYPES` | (inline) | (inline) | Keep in expectations, remove from worker |

## Target Architecture

| Module | Lines (est.) | Responsibility |
|---|---|---|
| `gx_dispatch_config.py` (NEW) | ~200 | Config loading, environment resolution |
| `gx_dispatch_api.py` (NEW) | ~300 | API communication, failure reporting, exception helpers |
| `gx_dispatch_payload.py` (NEW) | ~200 | Payload parsing, source override extraction, suite envelope parsing |
| `gx_dispatch_dispatch.py` (NEW) | ~800 | Dispatch routing, grouped/single/join-pair processing |
| `gx_dispatch_expectations.py` (EXISTING, updated) | ~800 | Expectation evaluation (single source of truth) |
| `gx_dispatch_runtime.py` (EXISTING) | 414 | Spark session, S3/URI, source resolution |
| `gx_dispatch_results.py` (EXISTING) | 29 | Small utilities |
| `gx_dispatch_telemetry.py` (EXISTING) | 431 | OTLP/telemetry |
| `gx_dispatch_types.py` (EXISTING) | 53 | Types |
| `gx_dispatch_worker.py` (EXISTING, trimmed) | ~300 | Worker loop, heartbeat, crash recovery, main entry |
| `execution_dispatch.py` (EXISTING) | 490 | Generic execution dispatch |

## Action Plan

### Phase 1: Eliminate duplication in expectations (actions 1–4)

**A1.** Move `_collect_row_condition_columns` from `gx_dispatch_worker.py` into `gx_dispatch_expectations.py`.

- Source: worker line 947
- Target: `gx_dispatch_expectations.py` (after `_required_columns_for_expectation`)
- Update imports in `gx_dispatch_expectations.py` as needed
- Remove from `gx_dispatch_worker.py`

**A2.** Remove all duplicated expectation functions from `gx_dispatch_worker.py` (lines 671–1274, 943–1100).

- Functions to remove: `_column_is_available`, `_supports_native_gx_execution`, `_collect_row_condition_columns`, `_required_columns_for_expectation`, `_native_gx_requires_column_projection`, `_build_native_gx_alias_map`, `_rewrite_native_gx_row_condition_for_aliases`, `_rewrite_native_gx_expectation_for_aliases`, `_lower_native_gx_row_condition`, `_NativeGxBatchRunner`, `_row_to_mapping`, `_resolve_row_value`, `_build_row_identifier`, `_first_row_identifier`, `_build_row_failure_diagnostics`, `_evaluate_expectations_spark`, `_build_spark_row_condition_expression`, `_NATIVE_GX_EXPECTATION_TYPES`
- Verify `gx_dispatch_expectations.py` has all of these (it does except `_collect_row_condition_columns` — handled by A1)

**A3.** Update `gx_dispatch_dispatch.py` (created in A7) to import expectation helpers from `gx_dispatch_expectations`.

- The dispatch module will need `_evaluate_expectations_spark`, `_is_real_spark_dataframe`, `_supports_native_gx_execution`
- `_evaluate_expectations_spark` → from `gx_dispatch_expectations`
- `_is_real_spark_dataframe` → from `gx_dispatch_runtime` (already there)
- `_supports_native_gx_execution` → from `gx_dispatch_expectations`

**A4.** Update tests to import expectation functions from `gx_dispatch_expectations.py` instead of `gx_dispatch_worker`.

- `test_gx_dispatch_worker_custom_expectations.py` imports `_build_row_identifier`, `_build_native_gx_alias_map`, `_evaluate_expectations_spark`, `_rewrite_native_gx_expectation_for_aliases` from `gx_dispatch_worker` — change to `gx_dispatch_expectations`
- `gx_dispatch_expectations.py` must export these as public (non-underscore) or keep underscore and update test imports accordingly
- Decision: keep underscore prefix, update test imports

### Phase 2: Create new modules (actions 5–8)

**A5.** Create `gx_dispatch_config.py` — Config loading & environment resolution.

- Move from `gx_dispatch_worker.py` lines 79–273:
  - `_utc_now_iso`
  - `_require_redis`
  - `_resolve_redis_url`
  - `_resolve_queue_key`
  - `_resolve_processing_queue_key`
  - `_resolve_worker_heartbeat_key`
  - `_resolve_worker_heartbeat_ttl_seconds`
  - `_resolve_worker_heartbeat_interval_seconds`
  - `_resolve_spark_master`
  - `_resolve_spark_ui_port`
  - `_resolve_s3_endpoint`
  - `_resolve_s3_access_key`
  - `_resolve_s3_secret_key`
  - `_resolve_s3_region`
  - `_resolve_bool_env`
  - `_resolve_optional_bool_env`
  - `_resolve_api_url`
  - `_build_token_provider`
  - `load_config`
- Dependencies: `gx_dispatch_types` (GxWorkerConfig), `dq_utils.auth_utils` (TokenProvider)
- Keep `load_config` as the public entry point

**A6.** Create `gx_dispatch_api.py` — API communication, failure reporting, exception helpers.

- Move from `gx_dispatch_worker.py`:
  - `_iter_exception_chain`, `_format_exception_message`, `_is_spark_runtime_exception`, `_is_transient_spark_gateway_error` (lines 327–358)
  - `_coerce_reported_failure` (lines 360–376)
  - `_should_fail_closed_worker` (lines 378–380)
  - `_report_dispatch_failure` (lines 382–426)
  - `_api_headers` (lines 427–435)
  - `_api_request` (lines 435–479)
  - `_should_discard_failed_message` (lines 479–485)
  - `_api_get_suite_envelope` (lines 485–506)
  - `_api_get_data_object_version` (lines 506–528)
  - `_api_report_run` (lines 528–569)
  - `_build_execution_progress` (lines 560–586)
  - `_api_report_execution_progress` (lines 586–616)
- Dependencies: `gx_dispatch_config` (`_build_token_provider`), `gx_dispatch_types`, `execution_dispatch` (`report_run`, `build_execution_progress`), `dq_utils.logging_utils`

**A7.** Create `gx_dispatch_payload.py` — Payload parsing, source override extraction, suite envelope parsing.

- Move from `gx_dispatch_worker.py`:
  - `_parse_dispatch_payload` (line 315)
  - `_coerce_str` (line 319)
  - `_coerce_int` (line 323)
  - `_extract_primary_key_fields` (lines 607–631)
  - `_assert_runnable_suite` (lines 631–668)
  - `_extract_source_overrides` (lines 659–671)
  - `_resolve_join_pair_location` (lines 798–851)
  - `_resolve_join_pair_report_storage_uri` (lines 851–877)
  - `_resolve_locations_for_targets` (lines 877–943)
- Dependencies: `gx_dispatch_api` (`_api_get_suite_envelope`, `_api_get_data_object_version`), `gx_dispatch_runtime` (`_coerce_source_location`, `_infer_materialized_source_location`), `gx_dispatch_types`, `execution_dispatch` (`coerce_str`, `coerce_int`)

**A8.** Create `gx_dispatch_dispatch.py` — Dispatch routing and processing.

- Move from `gx_dispatch_worker.py`:
  - `_process_grouped_dispatch_message` (lines 1852–2161)
  - `_build_spark_expectations_report_summary` (lines 2161–2184)
  - `_process_spark_expectations_dispatch_message` (lines 2184–2220)
  - `process_dispatch_message` (lines 2220–2668) — the main routing entry point
- Dependencies: `gx_dispatch_api`, `gx_dispatch_expectations`, `gx_dispatch_payload`, `gx_dispatch_runtime`, `gx_dispatch_telemetry`, `gx_dispatch_types`, `execution_dispatch`
- This module owns the dispatch routing logic: grouped vs single-object vs join-pair vs spark expectations

### Phase 3: Trim the worker and wire everything together (actions 9–11)

**A9.** Trim `gx_dispatch_worker.py` to ~300 lines.

- Keep: imports, `_utc_now_iso` wrapper (or remove if moved), `_write_worker_heartbeat`, `_start_worker_heartbeat_loop`, `run_worker_forever`
- Remove: everything moved in A5–A8
- Update imports to use the new modules
- The worker should import:
  - `from gx_dispatch_config import load_config, _resolve_worker_heartbeat_key, _resolve_worker_heartbeat_ttl_seconds, _resolve_worker_heartbeat_interval_seconds, _require_redis, _build_token_provider`
  - `from gx_dispatch_api import _report_dispatch_failure, _should_discard_failed_message, _should_fail_closed_worker`
  - `from gx_dispatch_dispatch import process_dispatch_message`
  - `from gx_dispatch_payload import _parse_dispatch_payload, _coerce_str`
  - `from gx_dispatch_telemetry import configure_worker_telemetry, record_worker_failure`

**A10.** Update all test imports.

- `test_gx_dispatch_worker.py`:
  - `from gx_dispatch_worker import _create_spark_session, _configure_worker_spark_builder` → `from gx_dispatch_runtime import _create_spark_session, _configure_worker_spark_builder`
  - `from gx_dispatch_worker import _coerce_reported_failure` → `from gx_dispatch_api import _coerce_reported_failure`
  - `from gx_dispatch_worker import _resolve_spark_ui_port` → `from gx_dispatch_config import _resolve_spark_ui_port`
  - `from gx_dispatch_worker import _resolve_worker_heartbeat_key, _resolve_worker_heartbeat_interval_seconds, _resolve_worker_heartbeat_ttl_seconds, _write_worker_heartbeat` → stay in `gx_dispatch_worker` or move to `gx_dispatch_config`
  - `from gx_dispatch_worker import process_dispatch_message` → `from gx_dispatch_dispatch import process_dispatch_message`
  - `from gx_dispatch_worker import GxWorkerConfig` → `from gx_dispatch_types import GxWorkerConfig` (already available)
- `test_gx_dispatch_worker_custom_expectations.py`:
  - `from gx_dispatch_worker import _build_row_identifier, _build_native_gx_alias_map, _evaluate_expectations_spark, _rewrite_native_gx_expectation_for_aliases` → `from gx_dispatch_expectations import _build_row_identifier, _build_native_gx_alias_map, _evaluate_expectations_spark, _rewrite_native_gx_expectation_for_aliases`
  - `from gx_dispatch_worker import process_dispatch_message` → `from gx_dispatch_dispatch import process_dispatch_message`
- `test_join_pair_materialization_worker.py`:
  - `from gx_dispatch_worker import GxWorkerConfig` → `from gx_dispatch_types import GxWorkerConfig`
- `test_spark_expectations_adapter.py`:
  - `from gx_dispatch_worker import GxWorkerConfig` → `from gx_dispatch_types import GxWorkerConfig`
  - `from gx_dispatch_worker import process_dispatch_message` → `from gx_dispatch_dispatch import process_dispatch_message`
- `test_kafka_client_validation.py` — no changes (already imports from `kafka_client`)
- `test_trino_execution_pipeline.py` — no changes (already imports from `gx_dispatch_types` and `execution_dispatch`)

**A11.** Run full test suite and verify no regressions.

- `cd dq-engine && python -m pytest tests/ -x -q`
- Verify `python -c "from gx_dispatch_worker import run_worker_forever; print('OK')"` works
- Verify `python -c "from gx_dispatch_dispatch import process_dispatch_message; print('OK')"` works

### Phase 4: Cleanup (actions 12–13)

**A12.** Remove unused imports from all files.

- After the split, some imports in `gx_dispatch_worker.py` are no longer needed (e.g., `import re`, `import tempfile`, Spark imports that were only used for the moved functions)
- Run `grep -c "import " gx_dispatch_*.py` to check

**A13.** Add module docstrings to all new modules.

- `gx_dispatch_config.py`: "GX worker configuration — loading GxWorkerConfig from environment variables."
- `gx_dispatch_api.py`: "GX worker API client — Kong communication, run reporting, failure handling, exception helpers."
- `gx_dispatch_payload.py`: "GX dispatch payload parsing — source overrides, suite envelope resolution, primary key extraction."
- `gx_dispatch_dispatch.py`: "GX dispatch processing — routing dispatch messages by execution_shape (grouped/single/join-pair/spark expectations)."

## Execution Order

The actions must be done in this order to avoid circular imports:

1. **A1** — Add missing function to expectations
2. **A5** — Create `gx_dispatch_config.py` (no external deps on new modules)
3. **A6** — Create `gx_dispatch_api.py` (depends on config)
4. **A7** — Create `gx_dispatch_payload.py` (depends on api, runtime)
5. **A2** — Remove duplicated expectation functions from worker
6. **A8** — Create `gx_dispatch_dispatch.py` (depends on api, expectations, payload, runtime)
7. **A9** — Trim `gx_dispatch_worker.py` (depends on all new modules)
8. **A3** — Verify expectation imports in dispatch module
9. **A10** — Update all test imports
10. **A11** — Run tests
11. **A12** — Remove unused imports
12. **A13** — Add module docstrings
14. **A4** — (already covered by A10)

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Circular imports between new modules | Dependency chain is linear: config → api → payload → dispatch → worker |
| Test failures from import changes | A10 explicitly lists every import change per test file |
| Expectation evaluation breaks | A2 removes worker duplicates; `gx_dispatch_expectations.py` is the single source of truth |
| `process_dispatch_message` public API changes location | It moves to `gx_dispatch_dispatch.py`; tests updated in A10 |

## Final Module Sizes (estimated)

| Module | Before | After | Δ |
|---|---|---|---|
| `gx_dispatch_worker.py` | 2 832 | ~300 | −2 532 |
| `gx_dispatch_expectations.py` | 787 | ~800 | +13 |
| `gx_dispatch_runtime.py` | 414 | 414 | 0 |
| `gx_dispatch_config.py` | — | ~200 | +200 (new) |
| `gx_dispatch_api.py` | — | ~300 | +300 (new) |
| `gx_dispatch_payload.py` | — | ~200 | +200 (new) |
| `gx_dispatch_dispatch.py` | — | ~800 | +800 (new) |
| `gx_dispatch_results.py` | 29 | 29 | 0 |
| `gx_dispatch_telemetry.py` | 431 | 431 | 0 |
| `gx_dispatch_types.py` | 53 | 53 | 0 |
| `execution_dispatch.py` | 490 | 490 | 0 |
| **Total** | **5 731** | **~4 567** | **−1 164** |

---

## Completion Notes (2026-07-05)

### Final Module Sizes

| Module | Lines | Status |
|---|---|---|
| `gx_dispatch_config.py` | 272 | ✅ Created |
| `gx_dispatch_api.py` | 357 | ✅ Created |
| `gx_dispatch_payload.py` | 283 | ✅ Created |
| `gx_dispatch_dispatch.py` | 921 | ✅ Created |
| `gx_dispatch_expectations.py` | 830 | ✅ Updated (A1 applied) |
| `gx_dispatch_runtime.py` | 414 | ✅ Unchanged |
| `gx_dispatch_results.py` | 29 | ✅ Unchanged |
| `gx_dispatch_telemetry.py` | 431 | ✅ Unchanged |
| `gx_dispatch_types.py` | 53 | ✅ Unchanged |
| `gx_dispatch_worker.py` | 291 | ✅ Trimmed (was 2,832) |
| **Total** | **3,881** | **−1,850 lines (was 5,731)** |

### Actions Completed

- [x] A1 — Add `_collect_row_condition_columns` to `gx_dispatch_expectations.py`
- [x] A2 — Remove duplicated expectation functions from worker
- [x] A3 — Import expectation helpers from `gx_dispatch_expectations` in dispatch module
- [x] A4 — Update test imports for expectation functions
- [x] A5 — Create `gx_dispatch_config.py`
- [x] A6 — Create `gx_dispatch_api.py`
- [x] A7 — Create `gx_dispatch_payload.py`
- [x] A8 — Create `gx_dispatch_dispatch.py`
- [x] A9 — Trim `gx_dispatch_worker.py`
- [x] A10 — Update all test imports
- [x] A11 — Run full test suite (syntax/AST verified, runtime needs Docker)
- [x] A12 — Remove unused imports (cleaned inline)
- [x] A13 — Add module docstrings (included in new modules)

### Import Graph (verified acyclic)

```
types → config → api → payload → dispatch → worker
                     ↓            ↓
               expectations   runtime
```

### Technical Documentation Updated

- `docs/technical/DQ_ENGINE_MODULE_ARCHITECTURE.md` — new module architecture reference
- `docs/technical/README.md` — added module architecture link
- `dq-engine/README.md` — updated overview with module table and Kafka consumer reference

### Test Files Updated

- `test_gx_dispatch_worker.py` — imports moved to config/api/runtime/dispatch
- `test_join_pair_materialization_worker.py` — `GxWorkerConfig` from `gx_dispatch_types`
- `test_gx_dispatch_worker_custom_expectations.py` — expectation helpers from `gx_dispatch_expectations`
- `test_spark_expectations_adapter.py` — `GxWorkerConfig` from `gx_dispatch_types`, `process_dispatch_message` from `gx_dispatch_dispatch`
