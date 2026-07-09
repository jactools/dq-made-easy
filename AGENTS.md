# Agent Instructions

This file is for AI coding assistants (Copilot, Claude, Cursor, etc.).

## Where to find the rules

Read `.github/copilot/01-general.md` for the authoritative repository rules:
- Python file size limit (< 1000 lines)
- Module naming conventions
- Dependency layering (no upward imports)
- Test-proof file layout

Additional instruction files (if they exist):
- `.github/copilot/02-fastapi-sqlalchemy.md` — FastAPI + SQLAlchemy
- `.github/copilot/03-testing.md` — Testing conventions; Python tests must use `<repo-root>/venv` and `scripts/python_arm64.sh`
- `.github/copilot/04-database.md` — Database migrations
- `.github/copilot/05-versioning.md` — Versioning rules
- `.github/copilot/06-internal-service-contracts.md` — Internal env, URL, and trust-bundle contracts
- `.github/copilot/07-tls-transport-enforcement.md` — No-HTTP rule, edge routing model, certificate generation, healthcheck and exception registry conventions
- `.github/instructions/python-test-module-boundary.instructions.md` — Every Python production module must have its own dedicated unit test module
- `.github/instructions/commit-validation-gate.instructions.md` — All commits must pass relevant build/test validation before being created; if a script can't be run, the commit is blocked

## Error handling and validation rules

**NEVER disable, suppress, or work around errors to make them go away.** Errors are signals that indicate:
- Configuration or structural problems that need fixing
- Invalid assumptions about code or data
- Broken contracts or dependencies

**When an error appears:**
1. **Analyze** — Understand the root cause. Is it a missing file? Invalid configuration? Broken link? Logic error?
2. **Fix** — Address the underlying issue, not the symptom. For example:
   - If a build system reports broken links, find and fix the links (don't change error level to 'warn')
   - If validation fails, correct the invalid state (don't skip the validation)
   - If a dependency is missing, install it (don't remove the dependency declaration)
3. **Verify** — Re-run the tool/test/build to confirm the fix works

**Exception:** Only suppress or work around errors if you've **explicitly asked the user** and received **explicit approval** for that approach. Document the decision and the justification in code comments or commit messages.

## When you are about to create or modify a Python file

1. Check if the file already exists and how many lines it has.
2. If it will exceed 800 lines, plan the split **before** writing code.
3. If modifying an existing file over 1000 lines, extract new logic into a new module rather than adding to the large file.
4. Run the validation script through `scripts/python_arm64.sh --python-bin ./venv/bin/python` (see `.github/copilot/03-testing.md`) when done to verify.

## Repository workflow notes

Startup and image refresh:
- `scripts/common_startup.sh` and `scripts/start-containers.sh` honor `ROOT_ENV_FILE`, but the normal startup path uses `docker compose up -d --no-build` and does not pull updated images.
- When current registry contents matter, use `scripts/pull_images.sh` or `scripts/start_stack_pull.sh` instead of assuming startup will refresh images.

WF6 Kubernetes notes:
- Base WF6 manifests live under `infra/k8s/base`; overlays own namespace assignment and patch the `Namespace` object name for `dev`, `test`, and `prod`.
- Kustomize patch matching is strict. When patching namespaced base resources, include the correct namespace or use explicit patch target selectors.
- Keep overlay/provider patch files inside the overlay directory tree; parent-directory patch references can fail under default kustomize security restrictions.
- Local Kubernetes bootstrap lives at `scripts/k8s/ensure_local_cluster.sh`; default local cluster/profile name is `dq-made-easy`, and auto runtime selection prefers `kind` over `minikube`.
- WF6 deploy lifecycle policy: migration jobs run in all environments; seed jobs follow mode semantics (`auto` = dev/test, `always` = all with explicit prod allowance, `never` = disabled).

WF7 Azure Container Apps notes:
- ACA env parameter contracts include `environmentName`, `deploymentPlatform`, `resourceNamePrefix`, `stateKeyPrefixEnvironment`, `stateKeyPrefixApp`, `acaIngressDefault`, and `acaEvidencePath`.
- ACA environment provisioning uses `stateKeyPrefixEnvironment` for `environment.tfstate`; per-app deployment uses `stateKeyPrefixApp` for individual app state.
- ACA deploy pipelines publish smoke/evidence output through `azure-pipelines/templates/dq-made-easy-container-app-smoke.yml` into `tmp/release/aca-deploy-evidence/<env>`.

## Conflict resolution

If a rule conflicts with an explicit developer or system instruction, raise the conflict to the user. Do not silently override.
