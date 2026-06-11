# EDR-002 [VAL]: GX Lifecycle Validator Parallelism, CLI Control, and External Case Catalog

**Status**: Accepted
**Date**: 2026-04-19
**Tag**: VAL

## Context
The GX lifecycle regression validator needed to exercise queueing behavior by running multiple cases concurrently, but without becoming an unbounded load generator.

At the same time, the validator had two maintainability problems:
- The supported case catalog was embedded directly in the shell script as a large JSON blob.
- Parallelism behavior was initially controlled through an environment variable, which made invocation less explicit and less auditable from shell history.

These choices made the validator harder to review, harder to evolve, and less explicit operationally.

## Decision
Adopt the following validator design for `scripts/validate_rule_lifecycle_gx_supported.sh`:
- Use **bounded parallel child execution** to run selected cases concurrently.
- Control concurrency through an explicit **`--parallelism` CLI option**.
- Keep case selection explicit through CLI filters such as **`--case-ids`**, `--rule-kinds`, and `--dimensions`.
- Store the supported case catalog in a dedicated JSON file at **`validation-data/validate_rule_lifecycle_gx_supported_cases.json`**.
- Keep child case executions isolated by recursively invoking the validator with `--parallelism 1` for a single selected case.

## Rationale
- Bounded parallelism demonstrates queue behavior without overwhelming the engine.
- CLI options make operational intent explicit and visible in shell history.
- An external JSON case catalog is easier to review and maintain than an embedded shell heredoc.
- Child-process isolation avoids making the shell script's mutable global state concurrency-safe within one process.
- Explicit case filters support targeted reruns without hidden environment-driven behavior.

## Scope Boundaries
This decision applies to the GX lifecycle validator and its case-catalog organization.

It does not by itself define:
- The default parallelism value for all other validators
- Global validation-runner argument forwarding in `scripts/validate.sh`
- Engine queueing semantics or worker scheduling policies

## Consequences
**Positive**
- The validator is clearer to operate and easier to extend.
- Case data is separated cleanly from orchestration logic.
- Parallel execution remains bounded and explicit.
- Targeted reruns are more deterministic and discoverable.

**Negative**
- Parallel execution introduces more child processes and log fan-out.
- The validator now depends on an external data file that must be kept in sync.
- Parent-run output becomes sparser between child completions because logs are emitted on reap boundaries.

## Implementation Guidance
- Maintain the supported cases in `validation-data/validate_rule_lifecycle_gx_supported_cases.json`.
- Add new filters and execution controls as CLI options rather than environment variables when they affect validator behavior.
- Keep child runs isolated by invoking the validator recursively with a single selected case.
- Use small, bounded concurrency values when validating queue behavior against a live stack.

## Related Artifacts
- `scripts/validate_rule_lifecycle_gx_supported.sh`
- `validation-data/validate_rule_lifecycle_gx_supported_cases.json`
- `scripts/validate.sh`
