# WF-7 Azure Container Apps Environment Deployment Implementation Plan

Status: Draft
Last updated: 2026-07-06

Feature reference: [WF_7_AZURE_CONTAINER_APPS_ENVIRONMENT_DEPLOYMENT.md](/docs/features/WF_7_AZURE_CONTAINER_APPS_ENVIRONMENT_DEPLOYMENT/)

## Purpose

Translate WF-7 feature scope into executable repository work for dev, test, and prod deployments to Azure Container Apps environments.

This plan is file-oriented and pipeline-oriented so each WF7 phase item maps to concrete repository touchpoints.

## Scope Guardrails

- Keep existing image build/publish ownership in repository scripts.
- Keep environment provisioning and per-app deployment as separate pipeline concerns.
- Keep environment selection explicit via dev/test/prod parameter contracts.
- Keep production secrets out of repository-tracked files.
- Keep Azure Container Apps deployment assets separate from Kubernetes deployment assets.

## Platform Separation Model

Use distinct deployment surfaces by platform:

- Azure Container Apps (WF7): own provisioning pipeline, own deploy pipeline/templates, own rollout validation scripts.
- Kubernetes/AKS (WF6): own manifest tree, own AKS pipeline/templates, own rollout validation scripts.

Allow reuse only through shared, platform-neutral templates/helpers:

- Shared pipeline templates for image variable resolution and evidence publishing.
- Shared shell helpers for environment validation and image tag resolution.

Do not route ACA deployments through AKS pipelines or AKS manifest paths.

## Pipeline Stage Contract (Mandatory)

All ACA deployment pipelines must implement these stages in order:

1. Build: build all selected runtime images.
2. Test: run validation and test gates against the build outputs.
3. Publish to Registry: push images only after test success.
4. Deploy: deploy by pulling published images from the configured registry.

Registry rules:

- Publish target must be explicit and environment-aware.
- Supported publish targets: Docker Hub (`docker.io`) or internal registry (for example Nexus).
- Deploy stages must pull from `docker.io` or the provided internal registry; no deploy stage may rely on locally built agent images.
- Registry hostname/namespace must be parameterized through pipeline variables or templates.

## Current Repository Anchors

Provisioning and deployment pipelines:

- `azure-pipelines/provision-container-app-environment.yml`
- `azure-pipelines/dq-made-easy-deploy-container-app.yml`
- `azure-pipelines/templates/dq-made-easy-container-app-deploy-tofu.yml`
- `azure-pipelines/parameters/dq-made-easy-dev.yml`
- `azure-pipelines/parameters/dq-made-easy-test.yml`
- `azure-pipelines/parameters/dq-made-easy-prod.yml`

OpenTofu modules:

- `infra/opentofu/container-app/main.tf`
- `infra/opentofu/container-app/variables.tf`
- `infra/opentofu/container-app/outputs.tf`
- `infra/opentofu/container-app/versions.tf`
- `infra/opentofu/container-app-environment/main.tf`
- `infra/opentofu/container-app-environment/variables.tf`
- `infra/opentofu/container-app-environment/outputs.tf`

Image build and tag sources:

- `scripts/build_and_push_all.sh`
- `scripts/build_and_push_one.sh`
- `scripts/pull_images.sh`
- `scripts/calculate_versions.sh`
- `VERSION_MANIFEST.json`

Validation and release evidence:

- `scripts/validate.sh`
- `scripts/validation/validate_env_file.sh`
- `scripts/validation/stack_smoke.sh`
- `docs/releases/*`

## New Repository Targets (to be created)

Azure deployment wrappers and validation:

- `scripts/azure/deploy_container_app.sh`
- `scripts/azure/promote_container_app.sh`
- `scripts/azure/rollback_container_app.sh`
- `scripts/validation/validate_aca_deploy_contract.sh`
- `scripts/validation/validate_aca_rollout_smoke.sh`

Pipeline templates and evidence output:

- `azure-pipelines/templates/dq-made-easy-container-app-smoke.yml`
- `azure-pipelines/templates/shared/resolve-image-vars.yml`
- `azure-pipelines/templates/shared/publish-deploy-evidence.yml`
- `tmp/release/aca-deploy-evidence/` (pipeline artifact output path)

## WF7 Work Item Mapping

### Phase 1: Environment and Contract Baseline

- [x] WF7-F-P1-01 Define dev, test, and prod ACA environment contract and required variables.
  - Files: `azure-pipelines/parameters/dq-made-easy-dev.yml`, `azure-pipelines/parameters/dq-made-easy-test.yml`, `azure-pipelines/parameters/dq-made-easy-prod.yml`
  - Existing references: `scripts/supporting/env/selection.sh`, `docs/features/WF_5_DEDICATED_ENVIRONMENT_CONTRACT.md`
- [x] WF7-F-P1-02 Define per-service deployment inputs (image, container name, target port, ingress).
  - Files: `azure-pipelines/dq-made-easy-deploy-container-app.yml`, `azure-pipelines/templates/dq-made-easy-container-app-deploy-tofu.yml`
- [x] WF7-F-P1-03 Define naming conventions for resource groups, environment names, and state keys.
  - Files: `azure-pipelines/parameters/*.yml`, `provision-container-app-environment.yml`
  - OpenTofu state key references in deployment templates.
- [x] WF7-F-P1-04 Define environment provisioning behavior and idempotency expectations.
  - Files: `azure-pipelines/provision-container-app-environment.yml`, `infra/opentofu/container-app-environment/*`
- [x] WF7-F-P1-05 Define deployment evidence schema (image, ingress, revision, validation result).
  - Files: `azure-pipelines/templates/dq-made-easy-container-app-smoke.yml`, `tmp/release/aca-deploy-evidence/*`

### Phase 2: Deployment Automation

- [ ] WF7-F-P2-01 Implement environment-aware deploy pipeline for ACA app deployment.
  - Files: `azure-pipelines/dq-made-easy-deploy-container-app.yml`, `azure-pipelines/templates/dq-made-easy-container-app-deploy-tofu.yml`
  - Existing references: `azure-pipelines/templates/shared/resolve-image-vars.yml`
  - Stage contract: Build -> Test -> Publish -> Deploy
- [ ] WF7-F-P2-02 Implement fail-fast input validation and required variable checks.
  - Files: `azure-pipelines/templates/dq-made-easy-container-app-deploy-tofu.yml`
  - Existing guardrails already present should be extended, not duplicated.
- [ ] WF7-F-P2-03 Implement dev -> test promotion with immutable image tags.
  - Files: `scripts/azure/promote_container_app.sh`, `azure-pipelines/dq-made-easy-deploy-container-app.yml`
  - Image source: `scripts/build_and_push_all.sh` output tags and/or digest artifact.
- [ ] WF7-F-P2-04 Implement test -> prod promotion with explicit approval gate.
  - Files: `azure-pipelines/dq-made-easy-deploy-container-app.yml`
  - Pipeline environment approvals configured per prod stage.
- [ ] WF7-F-P2-05 Persist per-environment deployment evidence for audit and release notes.
  - Files: `azure-pipelines/templates/dq-made-easy-container-app-smoke.yml`, `azure-pipelines/templates/shared/publish-deploy-evidence.yml`, `docs/releases/*`

### Phase 3: Runtime Hardening

- [ ] WF7-F-P3-01 Define environment-specific ingress policy defaults.
  - Files: `azure-pipelines/dq-made-easy-deploy-container-app.yml`, `azure-pipelines/parameters/*.yml`
- [ ] WF7-F-P3-02 Define environment-specific scale and revision behavior.
  - Files: `infra/opentofu/container-app/variables.tf`, `infra/opentofu/container-app/main.tf`
- [ ] WF7-F-P3-03 Define secure registry-auth strategy per environment.
  - Files: `azure-pipelines/templates/dq-made-easy-container-app-deploy-tofu.yml`
  - Prefer managed identity where available; fallback to secure variables only.
- [ ] WF7-F-P3-04 Define secret-handling and rotation contract for ACA apps.
  - Files: `infra/opentofu/container-app/*`, `azure-pipelines/parameters/*.yml`
- [ ] WF7-F-P3-05 Define monitoring and alerting contract for deployment failures.
  - Files: `AZURE_DEPLOYMENT.md`, `docs/implementation-details/OBSERVABILITY_SETUP.md`

### Phase 4: Validation and Recovery

- [ ] WF7-F-P4-01 Add post-deploy smoke validation for each environment.
  - Files: `scripts/validation/validate_aca_rollout_smoke.sh`, `azure-pipelines/templates/dq-made-easy-container-app-smoke.yml`
- [ ] WF7-F-P4-02 Add rollout failure detection and pipeline fail-fast behavior.
  - Files: `azure-pipelines/templates/dq-made-easy-container-app-deploy-tofu.yml`
- [ ] WF7-F-P4-03 Add rollback workflow to previous known-good image tag.
  - Files: `scripts/azure/rollback_container_app.sh`, `azure-pipelines/dq-made-easy-deploy-container-app.yml`
- [ ] WF7-F-P4-04 Add operator runbook for failed ACA deployments.
  - Files: `AZURE_DEPLOYMENT.md`
- [ ] WF7-F-P4-05 Add release health summary for deployment status and rollbacks.
  - Files: `docs/releases/*`, `tmp/release/aca-deploy-evidence/*`

## Implementation Order (Concrete)

1. Normalize dev/test/prod parameter contracts in `azure-pipelines/parameters/*.yml`.
2. Add ACA pipeline stages with mandatory order: Build, Test, Publish-to-registry, Deploy.
3. Parameterize registry target (`docker.io` or internal registry such as Nexus) and enforce deploy-time pulls from published image references.
4. Add evidence output block and smoke hook template for ACA deployment pipeline.
5. Add `scripts/validation/validate_aca_deploy_contract.sh` and wire into `scripts/validate.sh`.
6. Add promotion helper script to enforce immutable tag reuse across environments.
7. Add rollback helper script and pipeline wiring for failure paths.
8. Update `AZURE_DEPLOYMENT.md` with operator runbook aligned to pipeline behavior.

## Validation Gates

Minimum command contract for WF7 rollout:

```bash
./scripts/validation/validate_env_file.sh --env dev
./scripts/validation/validate_env_file.sh --env test
./scripts/validation/validate_env_file.sh --env prod
./scripts/validation/validate_aca_deploy_contract.sh --env dev
./scripts/validation/validate_aca_deploy_contract.sh --env test
./scripts/validation/validate_aca_deploy_contract.sh --env prod
./scripts/validation/validate_aca_rollout_smoke.sh --env test
./scripts/validation/validate_aca_rollout_smoke.sh --env prod
```

## Acceptance Evidence Mapping

- WF7-F-AC-01: deployment history proves same immutable image tag promoted dev -> test -> prod.
- WF7-F-AC-02: parameter/template diffs prove isolated per-environment ingress and secret scope.
- WF7-F-AC-03: validation logs show fail-fast behavior for missing deploy inputs.
- WF7-F-AC-04: post-deploy checks confirm deployed image and target port match requested values.
- WF7-F-AC-05: rollback transcript and redeploy evidence to known-good tag.
- WF7-F-AC-06: prod approval log and deployment evidence artifact linked in release notes.

## Related Documents

- [WF_7_AZURE_CONTAINER_APPS_ENVIRONMENT_DEPLOYMENT.md](/docs/features/WF_7_AZURE_CONTAINER_APPS_ENVIRONMENT_DEPLOYMENT/)
- [AZURE_CONTAINER_APPS_TO_AKS_DEPLOYMENT_PLAN.md](/docs/implementation-details/AZURE_CONTAINER_APPS_TO_AKS_DEPLOYMENT_PLAN/)
- [AZURE_DEPLOYMENT.md](https://github.com/jactools/dq-rulebuilder/blob/main/AZURE_DEPLOYMENT.md)
- [WF_6_KUBERNETES_IMAGE_DEPLOYMENT_IMPLEMENTATION_PLAN.md](/docs/implementation-details/WF_6_KUBERNETES_IMAGE_DEPLOYMENT_IMPLEMENTATION_PLAN/)
