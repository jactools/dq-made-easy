# WF-8 Azure Pipeline Verification Harness

Goal: provide a local verification workflow that checks Azure DevOps pipeline logic before pipelines run in Azure DevOps, covering all current and future build/publish/deploy pipelines (ACA provisioning, ACA deploy/smoke, AKS/EKS/GKE deploy/smoke, image build/publish, validation-gates template).

Implementation status: not yet started.

## Principles

- Keep offline contract and syntax checks fast and credential-free so they run on every commit.
- Keep real infrastructure mutations opt-in behind an explicit sandbox flag.
- Reuse the exact shell script bodies that Azure DevOps executes so the local harness and the pipeline exercise the same code.
- Keep the sandbox path self-cleaning: every sandbox test that applies infrastructure must destroy it.
- Keep Python as the test runner and thin shell harnesses as the command wrappers.

## Scope

- Verify YAML syntax, template parameter contracts, required variable completeness, and stage output wiring for all azure-pipelines files.
- Verify OpenTofu module formatting and validate correctness for `infra/opentofu/container-app/` and `infra/opentofu/container-app-environment/`.
- Verify deploy input contracts (port range, ingress values, state key path shape, image reference shape) for dev/test/prod parameter files.
- Verify the command shape and argument order of every `az` and `tofu` invocation using stub binaries.
- Verify real deployment behavior with `tofu plan` against a pre-created sandbox resource group.
- Optionally verify full deploy and teardown with `tofu apply` + `az containerapp show` readbacks.
- Expose the offline checks as a `scripts/validate.sh` group so CI and local runs share one entrypoint.

## Out of Scope

- Replacing the Azure DevOps pipelines themselves.
- Verifying application-level correctness of deployed services (covered by post-deploy smoke tests in the pipelines).
- Managing the sandbox resource group lifecycle (assumed pre-created by platform operators).

## Verification Phases

### Phase 1 — Offline Contract and Syntax Checks

No Azure credentials required. Runs every commit.

**Step 1 — Extract inline pipeline scripts**
Extract the `inlineScript` bodies from all AzureCLI@2 tasks across all pipeline files into versioned shell harnesses under `scripts/azure/`. Pipeline YAML files reference them by path via `scriptLocation: filePath`. This makes the same code runnable outside Azure DevOps.

Files to extract from:
- [azure-pipelines.yml](../../azure-pipelines.yml)
- [azure-pipelines/provision-container-app-environment.yml](../../azure-pipelines/provision-container-app-environment.yml)
- [azure-pipelines/dq-made-easy-deploy-container-app.yml](../../azure-pipelines/dq-made-easy-deploy-container-app.yml)
- [azure-pipelines/templates/dq-made-easy-container-app-deploy-tofu.yml](../../azure-pipelines/templates/dq-made-easy-container-app-deploy-tofu.yml)
- [azure-pipelines/templates/dq-made-easy-container-app-smoke.yml](../../azure-pipelines/templates/dq-made-easy-container-app-smoke.yml)
- [azure-pipelines/templates/dq-made-easy-aks-deploy.yml](../../azure-pipelines/templates/dq-made-easy-aks-deploy.yml)

**Step 2 — Pipeline YAML syntax and template contract checker** (`tests/azure_pipelines/test_pipeline_yaml.py`)
- Parse all `azure-pipelines/**/*.yml` with PyYAML and assert valid structure.
- Walk `${{ parameters.* }}` references and assert every required parameter is defined in each caller.
- Assert all required pipeline variables from parameter files are present and non-empty.
- Assert stage output wiring is coherent (e.g. `stageDependencies.Publish.PublishToRegistry.outputs['PublishImage.DEPLOY_IMAGE_REF']`).

**Step 3 — OpenTofu module static validation** (`tests/azure_pipelines/test_tofu_modules.py`)
- Run `tofu fmt -check` on both OpenTofu modules and fail on drift.
- Run `tofu validate` with a conftest-managed temp `backend "local" {}` so `init` succeeds offline.
- Assert the modules parse correctly against their declared variables.

**Step 4 — Deploy input contract checker** (`tests/azure_pipelines/test_deploy_inputs.py`)
- Load each parameter file (dev/test/prod) and assert every pipeline-referenced variable is present, non-empty, and well-formed.
- Assert `targetPort` is a valid TCP port, `ingress` is `internal|external`, state key paths follow `dq-made-easy/aca/<env>/<kind>`, image references match `<registry>/<namespace>/<image>:<tag>`.

### Phase 2 — Mocked Command Execution

No Azure credentials required. Proves command shape and argument contract.

**Step 5 — az/tofu stub harness** (`tests/azure_pipelines/conftest.py` + `tests/azure_pipelines/stubs/`)
- Install thin `az` and `tofu` stub scripts on PATH for test duration.
- Each stub logs its arguments to a temp JSONL file and returns configurable mock output.

**Step 6 — Pipeline script execution tests** (`tests/azure_pipelines/test_script_execution.py`)
- Call each extracted shell harness from Step 1 with all required env vars set and stubs on PATH.
- Assert the exact `az containerapp show --query` expressions, `tofu init -backend-config` arguments, and `tofu apply -var` flags match the parameter file values.
- Assert the required-variable check scripts produce the expected error messages for missing inputs.

### Phase 3 — Sandbox Execution

Requires Azure credentials and pre-created resource group. Opt-in.

**Step 7 — Sandbox configuration** (`tests/azure_pipelines/sandbox.env.example`)
Required vars: `SANDBOX_RESOURCE_GROUP`, `SANDBOX_REGION`, `SANDBOX_SUBSCRIPTION_ID`, `SANDBOX_STATE_STORAGE_ACCOUNT`, `SANDBOX_STATE_CONTAINER`, `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET`, `ARM_TENANT_ID`. Tests skip gracefully when `SANDBOX_RESOURCE_GROUP` is unset.

**Step 8 — Real tofu plan test** (`tests/azure_pipelines/test_tofu_sandbox.py`)
- Run `tofu init` with real backend targeting the sandbox storage account.
- Run `tofu plan` (never `apply`) for both modules with known dev parameter values.
- Assert the plan produces only expected additions/changes and no unexpected destroys.
- Clean up local `.terraform` cache after the test.

**Step 9 — Full sandbox apply-and-teardown** (`tests/azure_pipelines/test_sandbox_deploy.py`, marked `@pytest.mark.sandbox_apply`)
- Provision a minimal ACA environment and one container app using the same `tofu apply` path as the pipeline.
- Run the same `az containerapp show` readbacks the smoke template runs and assert them.
- Destroy with `tofu destroy` after assertions pass.
- Assert the sandbox resource group is clean after teardown.
- Run with: `pytest -m sandbox_apply`.

### Phase 4 — Integration

**Step 10 — Wire into `scripts/validate.sh`**
Add a new validation group `azure-pipelines` that runs Phases 1 and 2 via `venv/bin/python -m pytest tests/azure_pipelines/ -m "not sandbox"`. Sandbox tests remain separate and opt-in.

## Environment Contract

- Pre-created sandbox resource group with contributor access for the service principal.
- State storage account and container created within the sandbox resource group.
- `sandbox.env` gitignored; `sandbox.env.example` committed.
- All offline tests runnable with no Azure credentials.

## Further Considerations

- Steps 1 and 2 can start in parallel; Step 6 blocks on both Steps 1 and 5.
- The `scripts/azure/` harnesses should source the same env contract as the start-stack path so variable resolution is consistent.
- AKS, EKS, and GKE deploy templates share a `cloudProvider` parameter and a common kubeconfig step — the contract checker and stub harness must cover all three providers so new k8s pipeline additions are automatically gated.
- The sandbox apply test is the only step that can prove the command set truly deploys what we expect.
