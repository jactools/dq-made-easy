# EDR-022 [WRK]: Profiling Worker Status Transitions and Queue Lifecycle Rules

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: WRK

## Context
Profiling requests move through a queued worker lifecycle. Earlier failures showed that processing could succeed or fail without the durable request record reflecting accurate started/completed status, making the system look idle or stuck even when work had run.

## Decision
- The profiling worker owns request lifecycle status transitions for queued jobs.
- Worker processing must set started state before ETL work and completed or failed state after processing ends.
- API-side enqueue paths must not pretend to own worker-side runtime status updates once a job has been accepted by the queue.
- Validation of profiling worker lifecycle should exercise both success and failure transitions as a single coherent path.

## Rationale
- Worker-owned status transitions reflect the component that actually observes job execution.
- Explicit started/completed/failed timestamps make queued request state inspectable and testable.
- API enqueue and worker execution are different lifecycle phases and should not blur responsibility.

## Scope Boundaries
This decision covers profiling-worker request lifecycle semantics.

It does not by itself define:
- retry/backoff policies
- stale-message recovery
- queue infrastructure design outside profiling lifecycle state

## Consequences
**Positive**
- Profiling request state is more accurate and observable.
- Success and failure paths are validated consistently.

**Negative**
- Worker implementation must remain responsible for DB-backed status mutation.

## Implementation Guidance
- Set `started_at` before ETL begins.
- Set `completed_at` and final status on both success and failure.
- Test lifecycle state transitions end to end, including failure paths.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-profiling-worker-status-transition-note.md`
- `/memories/repo/dq-rulebuilder-profiling-worker-lifecycle-validation-wrapper-note.md`
