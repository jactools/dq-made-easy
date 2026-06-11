# EDR-004 [VAL]: Validator Case Parallelism and Spark Queue Serialization

**Status**: Accepted
**Date**: 2026-04-19
**Tag**: VAL

## Context
The GX lifecycle validator was extended to run multiple cases concurrently in order to exercise queue behavior under bounded load.

That raised an operational question: should the validator expose one parallelism control for all work, or distinguish between case-level fan-out and Spark execution concurrency?

In the current prototype environment, Spark-backed work is not executed directly by the validator process. Instead, the validator enqueues work into Redis-backed worker services for:
- GX dispatch execution
- join-pair materialization
- test-data materialization

Those workers consume their queues serially in the current local topology. As a result, validator case fan-out and Spark runtime concurrency are not the same thing.

## Decision
Treat validator `--parallelism` as **case-level orchestration parallelism only**.

For the current prototype stack:
- Keep bounded validator case fan-out through `--parallelism`.
- Do not add a second validator-side Spark concurrency flag or lock.
- Rely on Redis-backed worker queues to serialize Spark-backed work in the current single-consumer topology.
- Document clearly in validator help and log output that extra Spark-backed requests wait in Redis rather than executing concurrently.

## Rationale
- Case orchestration and Spark runtime concurrency are separate concerns in the current architecture.
- Adding a second script-side Spark lock would duplicate queue backpressure that already exists in the worker layer.
- The queue-backed model is easier to explain operationally: the validator may fan out requests, but Spark-backed workers decide actual execution order.
- Keeping a single explicit `--parallelism` flag preserves CLI clarity while avoiding fake precision about runtime concurrency the script does not control directly.

## Scope Boundaries
This decision applies to the current prototype validator and current worker topology.

It does not by itself define:
- production worker replica counts or autoscaling policy
- queue concurrency for other services outside the validator flow
- future behavior if multiple Spark-capable worker replicas are introduced
- a guarantee that all Spark-backed operations will always remain single-consumer in every environment

## Consequences
**Positive**
- The validator remains simple to operate: one visible case-level concurrency control.
- Spark-backed work inherits queue backpressure from the worker layer rather than from shell-script coordination.
- Operational behavior is clearer: extra Spark-backed requests wait in Redis instead of running concurrently by accident.
- The concurrency model better matches how the live stack actually executes work.

**Negative**
- Validator wall-clock time can still grow significantly because Spark-backed work is serialized behind queues.
- Queue wait time is less obvious than direct in-process concurrency control.
- If worker topology changes later, the validator documentation and this EDR may need revision.

## Implementation Guidance
- Describe `--parallelism` explicitly as case-level orchestration parallelism in validator help text.
- Keep Spark-backed work routed through Redis-backed workers rather than adding script-side coordination.
- When demonstrating queue behavior, inspect worker queues and worker logs rather than assuming validator child count equals Spark concurrency.
- Revisit this decision if Spark-capable worker replica counts or worker concurrency semantics change.

## Related Artifacts
- `scripts/validate_rule_lifecycle_gx_supported.sh`
- `dq-engine/gx_dispatch_worker.py`
- `dq-engine/join_pair_materialization_worker.py`
- `dq-engine/test_data_materialization_worker.py`
- `validation-data/validate_rule_lifecycle_gx_supported_cases.json`
- `docs/engineering-decisions/EDR-002-VAL-gx-lifecycle-validator-parallelism-cli-control-and-external-case-catalog.md`