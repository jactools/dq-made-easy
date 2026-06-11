# EDR-006 [WRK]: GX Worker Spark Memory and Result-Size Guardrails

**Status**: Accepted
**Date**: 2026-04-19
**Tag**: WRK

## Context
Live GX validation exposed Spark JVM failures during heavier join-pair and transfer-match execution paths, including `OutOfMemoryError` during Spark broadcast and collect-style operations.

The GX worker previously relied on generic Spark defaults, which were too implicit for the repository's local and prototype execution patterns. In practice, this made worker behavior sensitive to runtime defaults and increased the chance of opaque Py4J-side failures surfacing only after Spark had already failed internally.

The repository needed a stable, explicit minimum Spark configuration for the GX worker, while still allowing targeted overrides when testing or running in other environments.

## Decision
Adopt explicit Spark guardrails for the GX dispatch worker:
- Configure worker Spark sessions with explicit defaults for:
  - `spark.driver.memory = 2g`
  - `spark.executor.memory = 2g`
  - `spark.driver.maxResultSize = 512m`
- Allow these values to be overridden through dedicated environment variables:
  - `DQ_SPARK_DRIVER_MEMORY`
  - `DQ_SPARK_EXECUTOR_MEMORY`
  - `DQ_SPARK_DRIVER_MAX_RESULT_SIZE`
- Apply these settings centrally when building worker Spark sessions rather than scattering per-call overrides.
- Propagate the same configuration surface through container runtime configuration so live workers and tests use the same contract.

## Rationale
- Explicit guardrails are more reviewable and predictable than relying on Spark defaults.
- A central builder configuration keeps runtime behavior consistent across execution shapes.
- Environment overrides preserve flexibility without forcing operators to edit code for sizing experiments.
- Result-size limits help surface unsafe collect-style execution characteristics earlier and more consistently.

## Scope Boundaries
This decision applies to Spark session configuration for the GX dispatch worker and related local/prototype runtime wiring.

It does not by itself define:
- optimal Spark sizing for production-scale deployments
- a general performance-tuning strategy for every Spark-backed component
- elimination of all possible JVM memory failures under arbitrary data sizes
- query-plan rewrites that avoid large collect/broadcast behavior entirely

## Consequences
**Positive**
- Worker Spark memory behavior is explicit and consistent.
- Local and prototype validation runs have a clearer minimum runtime contract.
- Operators can tune memory guardrails through environment configuration instead of code edits.
- Tests can assert the intended worker Spark configuration directly.

**Negative**
- Defaults that are safe for the prototype may be insufficient or oversized in other environments.
- Environment-driven overrides require operational discipline to remain consistent across services.
- Memory guardrails reduce ambiguity but do not replace execution-shape optimizations where needed.

## Implementation Guidance
- Keep Spark sizing in the shared GX worker Spark builder path.
- Prefer explicit worker-specific environment variables over hidden Spark defaults.
- Validate builder behavior with focused unit tests when defaults or override names change.
- Revisit the guardrails if data volume, join-pair materialization shape, or worker topology changes materially.

## Related Artifacts
- `dq-engine/gx_dispatch_worker.py`
- `dq-engine/tests/test_gx_dispatch_worker.py`
- `docker-compose.yml`
- `docs/engineering-decisions/EDR-003-WRK-gx-worker-fail-closed-on-fatal-spark-runtime-failures.md`
