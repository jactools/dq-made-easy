# EDR-007 [WRK]: GX Worker Processing-Queue Recovery and Stale-Message Handling

**Status**: Accepted
**Date**: 2026-04-19
**Tag**: WRK

## Context
The GX dispatch worker uses a Redis ready queue and a Redis processing queue. When the worker crashes mid-execution, messages can remain stranded in the processing queue.

Without explicit recovery, this creates two problems:
- queued work can become permanently stuck after worker death
- later operational investigation is harder because the queue no longer reflects what is actually retryable

At the same time, a recovery mechanism must not silently discard messages or assume success when the worker died before completing run reporting.

## Decision
Adopt startup recovery and explicit processing-queue handling for the GX dispatch worker:
- Use `brpoplpush` from the ready queue into a dedicated processing queue while work is in flight.
- On worker startup, move any remaining processing-queue messages back to the ready queue before consuming new work.
- Remove a message from the processing queue only after successful completion or after explicit failure reporting for the current run.
- Log recovery activity so operators can see when stale processing messages were requeued.
- Treat stranded processing-queue messages as retryable work, not as silently lost or implicitly successful work.

## Rationale
- A separate processing queue makes in-flight work visible and recoverable.
- Startup requeue is a simple, deterministic crash-recovery mechanism.
- Explicit cleanup after success or reportable failure preserves fail-fast behavior without silently dropping work.
- Recovery logging gives operators concrete evidence when worker restarts had to reclaim stale processing messages.

## Scope Boundaries
This decision applies to the GX dispatch worker queue-consumption model.

It does not by itself define:
- cross-service deduplication of retried GX runs
- API-level reconciliation of orphaned historical runs that no longer exist
- queue-recovery semantics for every other worker unless they independently adopt the same pattern
- permanent retention or audit strategy for stale queue payloads

## Consequences
**Positive**
- In-flight work is recoverable after worker crashes.
- The worker does not silently lose claimed queue messages.
- Operators can observe recovery behavior through queue and log signals.
- The queue model supports fail-closed worker termination without abandoning later work.

**Negative**
- Old or malformed payloads can be replayed on startup and may still fail again if the underlying run no longer exists.
- Recovery can temporarily surface stale historical work after long-lived failures or manual intervention.
- Queue semantics become more complex than a single ready list.

## Implementation Guidance
- Keep processing-queue recovery early in worker startup before new work is consumed.
- Only acknowledge processing messages after success or after an explicit failure-report path completes.
- Log `recoveredCount` and related queue names whenever stale processing messages are requeued.
- Investigate malformed or unreportable recovered payloads separately rather than disabling recovery.

## Related Artifacts
- `dq-engine/gx_dispatch_worker.py`
- `dq-engine/tests/test_gx_dispatch_worker.py`
- `docs/engineering-decisions/EDR-003-WRK-gx-worker-fail-closed-on-fatal-spark-runtime-failures.md`