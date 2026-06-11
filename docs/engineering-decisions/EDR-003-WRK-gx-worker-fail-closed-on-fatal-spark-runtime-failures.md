# EDR-003 [WRK]: GX Worker Fail-Closed on Fatal Spark Runtime Failures

**Status**: Accepted
**Date**: 2026-04-19
**Tag**: WRK

## Context
The GX dispatch worker runs Spark-backed execution from a Redis queue. During live validation, fatal Spark JVM and Py4J failures were observed where the worker process stayed alive after the underlying Spark gateway had already become unusable.

In that state, the worker could continue consuming queued dispatch messages, but each subsequent run would fail immediately with follow-on gateway errors such as `ConnectionRefusedError` rather than an isolated failure for the original broken run.

This created two engineering risks:
- one real Spark failure could cascade into many misleading queue failures
- subsequent runs could be consumed and marked failed by a poisoned process instead of being retried by clean worker startup recovery

The repository already uses a Redis processing queue and startup recovery path for the GX worker, so the missing piece was deciding how the worker should behave after a fatal Spark runtime failure.

## Decision
Adopt a fail-closed worker policy for fatal Spark runtime failures in `dq-engine/gx_dispatch_worker.py`:
- Treat exceptions rooted in `pyspark` or `py4j` as worker-fatal runtime failures.
- Preserve and report the underlying Spark or Py4J error for the current run as `GX_WORKER_EXECUTION_ERROR`.
- After reporting the current run failure, re-raise the fatal exception so the worker process terminates instead of continuing to drain the queue.
- Rely on container restart and existing processing-queue recovery to requeue any remaining in-flight messages for later handling by a clean worker process.

## Rationale
- A poisoned Spark gateway is not a local, recoverable per-run error. Continuing in-process turns one runtime failure into a queue-wide failure burst.
- Restart-based recovery is simpler and more reliable than trying to reconstruct a healthy Spark runtime inside the same Python worker process.
- The repository already has crash-recovery semantics through the processing queue and compose restart policy, so fail-closed behavior fits the existing operational model.
- This follows the repository fail-fast policy: do not silently substitute degraded behavior after a required runtime has become unavailable.

## Scope Boundaries
This decision applies to the GX dispatch worker runtime in `dq-engine/gx_dispatch_worker.py`.

It does not by itself define:
- retry policy for failed GX runs at the API level
- queue semantics for non-GX workers unless they independently adopt the same rule
- horizontal scaling or replica-count policy for worker services
- the Spark memory sizing policy that may still be needed to prevent JVM failures in the first place

## Consequences
**Positive**
- One fatal Spark failure no longer cascades into many misleading follow-on queue failures.
- Remaining queued work is left for clean-worker recovery rather than being consumed by a broken process.
- Reported run failures preserve the underlying Spark or Py4J cause instead of being masked by teardown noise.
- The worker behavior aligns with repository fail-fast and no-fallback guidance.

**Negative**
- Fatal Spark failures now deliberately terminate the worker process, which produces restarts during bad runtime conditions.
- Some queue latency is shifted to worker restart and recovery time.
- This policy depends on container restart configuration and processing-queue recovery continuing to work correctly.

## Implementation Guidance
- Use exception-chain inspection to detect fatal Spark runtime failures (`py4j` and `pyspark` roots).
- Report the current run failure before terminating the worker process.
- Do not try to keep consuming queued work after a fatal Spark gateway failure.
- Keep startup recovery logic intact so messages left in the processing queue are requeued on worker restart.
- Preserve the original Spark failure message when Spark session shutdown also fails.

## Related Artifacts
- `dq-engine/gx_dispatch_worker.py`
- `dq-engine/tests/test_gx_dispatch_worker.py`
- `docker-compose.yml`
- `docs/engineering-decisions/EDR-004-VAL-validator-case-parallelism-and-spark-queue-serialization.md`
