# EDR-016 [ENG]: Shared Spark Runtime Coordination

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: ENG

## Context
Spark execution in this repository is no longer confined to one worker. The GX worker, join-pair materialization worker, test-data materialization worker, seeded-delivery scripts, staging helpers, and FastAPI-side PySpark execution all need a consistent runtime model.

Several failures showed that this runtime needs explicit coordination rules:

- Spark builder helpers duplicated at the repo root drifted across entry points and made container/runtime behavior inconsistent.
- Runtime dependency resolution through Maven or pip-based Delta helpers was too fragile for containerized workers and prototype environments.
- mismatched Iceberg runtime coordinates could break Docker warm-up and leave different Spark entry points using different connector assumptions.
- default Spark UI port collisions created noisy local behavior unless the repository standardized a non-default starting port.

These are shared Spark runtime rules, not single-worker implementation details.

## Decision
Adopt the following shared Spark runtime rules:

- Shared Spark builder and Spark-jar helper logic must live in the packaged `dq_utils.spark_runtime` and `dq_utils.spark_jars` modules, not in repo-root helper files.
- All Spark entry points in the repository should import those packaged helpers so runtime behavior is coordinated across workers, API helpers, and scripts.
- Runtime Spark sessions in containerized execution paths must use image-baked offline jars from `DQ_SPARK_JAR_DIR` rather than resolving packages dynamically at runtime.
- Do not use `configure_spark_with_delta_pip` or `spark.jars.packages` at runtime in repository Spark execution paths.
- The repository must keep the Iceberg runtime coordinate aligned across engine and seed/runtime entry points.
- Spark entry points should default `spark.ui.port` from `DQ_SPARK_UI_PORT`, falling back to `4044` rather than Spark's default `4040`.
- Container rebuild/restart is required when packaged Spark runtime helpers change, because long-running runtime paths depend on the installed `dq-utils` package inside the image.

## Rationale
- One packaged runtime helper surface is easier to keep consistent than several repo-local copies.
- Offline jars eliminate network-time dependency resolution and reduce runtime fragility in containerized workers.
- Coordinated Iceberg coordinates prevent warm-up/build drift across engine and seed paths.
- A shared non-default UI port reduces local contention with ad hoc Spark usage while still allowing Spark's normal incremental fallback behavior when the port is occupied.
- Rebuild/restart requirements need to be explicit because installed package code inside containers does not update automatically with source-only edits.

## Scope Boundaries
This decision applies to shared Spark runtime helper code, runtime dependency loading, connector coordinate alignment, and default Spark UI behavior across repository Spark entry points.

It does not by itself define:
- Spark memory sizing and result-size guardrails for individual workers
- queueing or fail-closed behavior for workers
- every connector used by every future Spark workload
- local Python environment repair outside the Spark runtime packaging model

## Consequences
**Positive**
- Spark behavior is more consistent across workers, scripts, and API helpers.
- Runtime paths are less dependent on live package downloads.
- Docker builds and warm-ups are easier to keep aligned across Spark-enabled images.
- Local Spark UI behavior is more predictable across multiple repository entry points.

**Negative**
- Dependency updates now require image rebuilds rather than ad hoc runtime package resolution.
- Helper changes must be coordinated through the shared `dq-utils` package, which raises the bar for casual local-only tweaks.
- Connector/version drift is more visible and must be resolved deliberately.

## Implementation Guidance
- Import Spark builder and jar configuration helpers only from `dq_utils.spark_runtime` and `dq_utils.spark_jars`.
- Bake Spark jars into the image and load them from `DQ_SPARK_JAR_DIR` during runtime session setup.
- Keep engine Dockerfiles, seed/runtime scripts, and other Spark warm-up paths aligned on the same Iceberg coordinate.
- Default Spark UI startup to `4044` via the shared resolution helper, while allowing Spark's normal incremental fallback if the port is occupied.
- Rebuild and restart Spark-enabled containers after changing packaged Spark runtime helpers.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-shared-spark-runtime-note.md`
- `/memories/repo/dq-rulebuilder-dq-engine-offline-spark-jars-note.md`
- `/memories/repo/dq-rulebuilder-iceberg-spark-runtime-coordinate-note.md`
- `/memories/repo/dq-rulebuilder-spark-ui-default-port-note.md`
- `dq-utils/src/dq_utils/spark_runtime.py`
- `dq-utils/src/dq_utils/spark_jars.py`
- `dq-engine/Dockerfile.engine`