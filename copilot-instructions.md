# Copilot / Agent Instruction: No-Fallbacks (Fail-Fast Policy)

Purpose
-------
This instruction makes the repository-wide rule explicit for Copilot/assistant-generated code and for human contributors: fail fast when a required API, service, or script is unavailable. Do not silently substitute behavior or return implicit default values that hide errors.

Policy (single line)
--------------------
No fallbacks: fail fast when a required API or script is unavailable. Do not silently substitute behavior.

Legacy / compatibility policy (single line)
-------------------------------------------
No legacy names and no compatibility code: use canonical contracts only, and update all repo-controlled callers instead of adding shims, aliases, dual-read paths, or translation layers.

Scope
-----
- Applies to: backend services (API endpoints), background workers, scripts and CLI tools, and any automated glue code produced by agents.
- Frontend UX may show cached/stale views only when explicitly labelled stale; functional behavior must still fail-fast on required service errors.
- Exceptions must be explicit, justified in a PR, and include tests and a feature-flagged opt-in.

Agent guidance (how the assistant should behave)
-----------------------------------------------
- When asked to generate code that depends on another service or script, produce fail-fast handling by default.
- Do not invent or add silent fallback branches (for example: returning cached/stubbed data, substituting a different service without explicit instruction, or swallowing exceptions and returning defaults).
- Do not preserve or introduce legacy env vars, legacy payload shapes, legacy route names, or compatibility readers/writers alongside canonical ones.
- When a contract changes, update every repo-controlled caller to the canonical contract instead of adding alias support, compatibility branches, or adapter glue.
- If the user requests an alternative fallback behaviour, ask a clarifying question about scope, tolerance, and desired signalling (logs, metrics, response fields).

Canonical contract enforcement
------------------------------
- Legacy is forbidden in repo-controlled code at all times.
- Compatibility code is forbidden in repo-controlled code at all times.
- "Compatibility code" includes alias env lookups, dual reads/writes, shim fields, translation layers kept only to support old repo-owned callers, and any branch that preserves obsolete naming after a canonical contract exists.
- If a repo-owned script, service, test, or compose block still uses an obsolete contract, change that caller. Do not add a bridge.
- The only acceptable exception is a third-party or externally owned interface that cannot be changed here; document that case explicitly and keep the compatibility boundary as small as possible.

Concrete recommendations by surface
---------------------------------

APIs (FastAPI / HTTP services)
- On downstream/service unavailability return clear, machine-readable error responses and appropriate 5xx status codes (503/502/504) rather than returning proxied stale data.
- Include a `correlation_id` and an `error` code in JSON responses. Example response body shape:

```json
{
  "error": "downstream_unavailable",
  "service": "dataset-service",
  "message": "dataset-service is unreachable",
  "correlation_id": "<uuid>"
}
```

Python/FastAPI example
```py
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

def call_downstream():
    try:
        return do_remote_call()
    except Exception as exc:
        logger.exception("downstream dataset-service failed")
        raise HTTPException(status_code=503, detail={
            "error": "downstream_unavailable",
            "service": "dataset-service",
            "message": "dataset-service is unavailable"
        })
```

Shell scripts and CLI tools
- Scripts MUST use strict failure flags and exit non-zero on missing dependencies or failing steps. Example header:

```bash
#!/usr/bin/env bash
set -euo pipefail

if ! ./required-script.sh; then
  echo "required-script.sh failed" >&2
  exit 1
fi
```

Spark Expectations and pySpark test execution
- When running Spark Expectations tests, always use `scripts/run_spark_expectations_container_tests.sh` and the dedicated dq-engine test container.
- When running pySpark tests, use the same containerized dq-engine test environment; do not rely on the host Java runtime or host PySpark installation.
- If the containerized test path is unavailable, fail fast and report the blocker instead of falling back to host execution.

Background workers / queues
- Mark the job as failed in the status store, record the cause and correlation id, emit a metric/alert; do not silently drop or mark succeeded with a substituted payload.

Tests and verification
- Unit tests should assert that dependency failures result in explicit error propagation (exceptions or HTTP 5xx), not silent success.
- Integration/smoke tests should include a dependency-failure scenario to confirm fail-fast behaviour.

Enforcement suggestions
-----------------------
- Add a lightweight static check (semgrep rule or grep-based CI check) that flags obvious "swallowing exceptions" patterns and returning default values when calling external services.
- Add a CI job `no-fallbacks` that runs the pattern checks and fails the build on matches; require an explicit PR justification to bypass.
- Add a reviewer checklist item: "Does this change introduce silent fallback behavior?" and require a rationale if yes.

How to request an exception
---------------------------
- Requests for allowed fallback behaviour must include:
  - Rationale (why fail-fast is unacceptable in this specific case)
  - A migration/rollback plan
  - Tests that demonstrate the intended behavior and clearly surface stale/approximate results
  - An explicit opt-in feature flag or config guard

Ambiguities / Questions for maintainers
--------------------------------------
1. Confirm scope: should this rule apply to all front-end UX tolerances (e.g., read-only cached fallbacks), or only to server-side functional correctness? (I recommend allowing only labelled stale UI fallbacks; server APIs must fail-fast.)
2. Do you want an automated semgrep rule added in this change, or would you prefer we open a separate PR to add CI enforcement?

Examples prompts for testing the instruction
-------------------------------------------
- "Generate a FastAPI endpoint that calls dataset-service; on dataset-service failure return a 503 with a correlation id and no cached fallback." 
- "Create a bash wrapper for the existing seed script that fails fast if the seed script exits non-zero."

Next steps I can take
---------------------
- Add a repository semgrep rule and a CI job to enforce this policy.
- Add example unit/integration tests that show the fail-fast behavior patterns.

When in doubt, ask the maintainers before introducing any behaviour that relaxes this rule.
