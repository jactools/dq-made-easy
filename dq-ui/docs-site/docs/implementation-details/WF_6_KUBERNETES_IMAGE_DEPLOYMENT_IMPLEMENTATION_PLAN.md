# WF-6 Kubernetes Image Deployment Implementation Plan

Status: Draft
Last updated: 2026-07-06

Feature reference: [WF_6_KUBERNETES_IMAGE_DEPLOYMENT.md](/docs/features/WF_6_KUBERNETES_IMAGE_DEPLOYMENT/)

## Purpose

Translate WF-6 feature scope into executable repository work for dev, test, and prod Kubernetes deployments using immutable image promotion.

This plan is file-oriented and script-oriented so each WF6 phase item maps to concrete repository touchpoints.

## Scope Guardrails

- Keep image build and publish logic in existing image scripts; do not fork image pipelines for Kubernetes-only variants.
- Keep environment selection contract aligned with existing `--env dev\|test\|prod` conventions in stack scripts.
- Keep Compose-based local developer startup intact; Kubernetes rollout is additive.
- Keep production secrets out of tracked env files.
- Keep Kubernetes deployment assets separate from Azure Container Apps deployment assets.

## Platform Separation Model

Use distinct deployment surfaces by platform:

- Kubernetes (WF6): own manifest tree, own AKS pipelines, own validation scripts.
- Azure Container Apps (WF7): own OpenTofu modules, own ACA pipelines, own validation scripts.

Allow reuse only through shared templates/helpers that are platform-neutral:

- Shared pipeline template layer for variable normalization and evidence publishing.
- Shared shell helper layer for image-tag resolution and environment validation.

Do not use one platform's deployment pipeline, parameter files, or rollout scripts to deploy the other platform.

## Pipeline Stage Contract (Mandatory)

All AKS/Kubernetes deployment pipelines must implement these stages in order:

1. Build: build all selected runtime images.
2. Test: run validation and test gates against the build outputs.
3. Publish to Registry: push images only after test success.
4. Deploy: deploy by pulling published images from the configured registry.

Registry rules:

- Publish target must be explicit and environment-aware.
- Supported publish targets: Docker Hub (`docker.io`) or internal registry (for example Nexus).
- Deploy stages must never use local agent images; they must pull the published image references from `docker.io` or the provided internal registry.
- Registry hostname/namespace must be parameterized through pipeline variables or templates, not hardcoded per service.

## Current Repository Anchors

Existing files that WF6 implementation will extend:

- Image build/publish orchestrators:
  - `scripts/build_and_push_all.sh`
  - `scripts/build_and_push_one.sh`
  - `scripts/pull_images.sh`
  - `scripts/stack_ctl.sh`
- Version/digest coordination:
  - `scripts/calculate_versions.sh`
  - `VERSION_MANIFEST.json`
- Validation harness:
  - `scripts/validate.sh`
  - `scripts/validation/stack_smoke.sh`
  - `scripts/validation/validate_env_file.sh`
- Shared pipeline conventions only:
  - `azure-pipelines/parameters/dq-made-easy-dev.yml`
  - `azure-pipelines/parameters/dq-made-easy-test.yml`
  - `azure-pipelines/parameters/dq-made-easy-prod.yml`

## New Repository Targets (to be created)

Kubernetes manifests and overlays:

- `infra/k8s/base/namespace.yaml`
- `infra/k8s/base/config/`
- `infra/k8s/base/services/` (Deployment + Service per runtime component)
- `infra/k8s/base/jobs/` (migrations and one-shot seed jobs)
- `infra/k8s/base/policies/` (NetworkPolicy, PDB, optional HPA templates)
- `infra/k8s/overlays/dev/`
- `infra/k8s/overlays/test/`
- `infra/k8s/overlays/prod/`
- `infra/k8s/README.md`

Kubernetes deploy scripts:

- `scripts/k8s/deploy.sh`
- `scripts/k8s/rollback.sh`
- `scripts/k8s/render.sh`
- `scripts/k8s/smoke.sh`

Pipeline additions for Kubernetes:

- `azure-pipelines/dq-made-easy-deploy-aks.yml`
- `azure-pipelines/parameters/dq-made-easy-aks-dev.yml`
- `azure-pipelines/parameters/dq-made-easy-aks-test.yml`
- `azure-pipelines/parameters/dq-made-easy-aks-prod.yml`
- `azure-pipelines/templates/dq-made-easy-aks-deploy.yml`
- `azure-pipelines/templates/dq-made-easy-aks-smoke.yml`

Shared template additions (platform-neutral only):

- `azure-pipelines/templates/shared/resolve-image-vars.yml`
- `azure-pipelines/templates/shared/publish-deploy-evidence.yml`

Validation additions:

- `scripts/validation/validate_k8s_manifest_contract.sh`
- `scripts/validation/validate_k8s_rollout_smoke.sh`

## WF6 Work Item Mapping

### Phase 1: Baseline Kubernetes Contract

- [x] WF6-F-P1-01 Define base Kubernetes resource templates for each repo-managed runtime service.
  - Files: `infra/k8s/base/services/*`, `infra/k8s/base/config/*`, `infra/k8s/base/README.md`
  - Existing references: `docker-compose.yml`, `scripts/stack_catalog.sh`
- [x] WF6-F-P1-02 Define dev, test, and prod overlays with environment-specific config boundaries.
  - Files: `infra/k8s/overlays/dev/*`, `infra/k8s/overlays/test/*`, `infra/k8s/overlays/prod/*`
  - Existing references: `.env.dev.local`, `.env.test.local`, `.env.prod.local`, `scripts/supporting/env/selection.sh`
- [x] WF6-F-P1-03 Define namespace and ingress hostname conventions for all environments.
  - Files: `infra/k8s/base/namespace.yaml`, `infra/k8s/base/ingress/*`, `infra/k8s/README.md`
  - Existing references: `docs/features/WF_5_DEDICATED_ENVIRONMENT_CONTRACT.md`, `docs/technical/KONG_DEPLOYMENT.md`
- [x] WF6-F-P1-04 Define migration and seed job lifecycle behavior per environment.
  - Files: `infra/k8s/base/jobs/*`, `scripts/k8s/deploy.sh`
  - Existing references: `scripts/start-containers.sh`, `scripts/seed_stack.sh`, `scripts/start_stack.sh`
- [x] WF6-F-P1-05 Define required labels and annotations for traceability.
  - Files: `infra/k8s/base/metadata/labels.yaml`, `infra/k8s/base/services/*`
  - Existing references: `VERSION_MANIFEST.json`

### Phase 2: Pipeline and Promotion Automation

- [ ] WF6-F-P2-01 Publish build artifact containing image tags and digests for all deployable services.
  - Files: `scripts/build_and_push_all.sh`, `scripts/calculate_versions.sh`, `VERSION_MANIFEST.json`
  - Output artifact: `tmp/release/image-digests.json` (or pipeline artifact equivalent)
- [ ] WF6-F-P2-02 Implement deploy pipeline step for dev overlay with validation gate.
  - Files: `azure-pipelines/dq-made-easy-deploy-aks.yml`, `azure-pipelines/templates/dq-made-easy-aks-deploy.yml`
  - Existing references: `azure-pipelines/templates/shared/resolve-image-vars.yml`
  - Stage contract: Build -> Test -> Publish -> Deploy
- [ ] WF6-F-P2-03 Implement promotion pipeline step from dev to test using identical digests.
  - Files: `azure-pipelines/dq-made-easy-deploy-aks.yml`, `azure-pipelines/templates/dq-made-easy-aks-deploy.yml`
  - Artifact dependency: digest file from WF6-F-P2-01
- [ ] WF6-F-P2-04 Implement gated promotion pipeline step from test to prod.
  - Files: `azure-pipelines/dq-made-easy-deploy-aks.yml`
  - Existing references: environment parameter pattern in `azure-pipelines/parameters/dq-made-easy-aks-*.yml`
- [ ] WF6-F-P2-05 Persist deployment evidence per environment for audit and release notes.
  - Files: `azure-pipelines/templates/dq-made-easy-aks-smoke.yml`, `docs/releases/*` (release evidence entries)
- [ ] WF6-F-P2-06 Add cloud-specific environment parameter templates and enforce non-placeholder cluster context values.
  - Files: `azure-pipelines/parameters/dq-made-easy-eks-*.yml`, `azure-pipelines/parameters/dq-made-easy-gke-*.yml`, `azure-pipelines/dq-made-easy-deploy-aks.yml`
  - Validation: fail pipeline when placeholder `kubeContext` or cluster identifiers are detected.
- [ ] WF6-F-P2-07 Implement native cluster credential acquisition for EKS and GKE in deploy/smoke templates.
  - Files: `azure-pipelines/templates/dq-made-easy-aks-deploy.yml`, `azure-pipelines/templates/dq-made-easy-aks-smoke.yml`
  - Existing references: EKS (`aws eks update-kubeconfig`) and GKE (`gcloud container clusters get-credentials`) auth patterns.
- [ ] WF6-F-P2-08 Add provider-aware render and preflight checks to CI validation gates.
  - Files: `scripts/k8s/render.sh`, `scripts/validation/validate_k8s_cluster_capabilities.sh`, `azure-pipelines/dq-made-easy-deploy-aks.yml`
  - Validation: render matrix for `aks\|eks\|gke` and preflight capability checks per target provider.

### Phase 3: Runtime Hardening

- [ ] WF6-F-P3-01 Add readiness, liveness, and startup probes for all long-running services.
  - Files: `infra/k8s/base/services/*`
  - Existing references: health endpoints in `docker-compose.yml` service contracts
- [ ] WF6-F-P3-02 Add resource requests and limits with environment-specific defaults.
  - Files: `infra/k8s/base/services/*`, `infra/k8s/overlays/dev/*`, `infra/k8s/overlays/test/*`, `infra/k8s/overlays/prod/*`
- [ ] WF6-F-P3-03 Add network policies for service-to-service communication boundaries.
  - Files: `infra/k8s/base/policies/networkpolicy-*.yaml`
  - Existing references: `docs/features/SEC_4_CONTROLLED_CONTAINER_EGRESS_AND_APPROVED_EXTERNAL_DESTINATIONS.md`
- [ ] WF6-F-P3-04 Add pod disruption budgets for critical services.
  - Files: `infra/k8s/base/policies/pdb-*.yaml`
- [ ] WF6-F-P3-05 Add autoscaling policy where runtime behavior supports it.
  - Files: `infra/k8s/base/policies/hpa-*.yaml`, overlay tuning in `infra/k8s/overlays/*`

### Phase 4: Rollout Safety and Recovery

- [ ] WF6-F-P4-01 Define per-service rollout strategy and rollback policy.
  - Files: `infra/k8s/base/services/*`, `scripts/k8s/rollback.sh`, `infra/k8s/README.md`
- [ ] WF6-F-P4-02 Implement automated post-deploy smoke validation execution.
  - Files: `scripts/k8s/smoke.sh`, `scripts/validation/validate_k8s_rollout_smoke.sh`, `azure-pipelines/templates/dq-made-easy-aks-smoke.yml`
  - Existing references: `scripts/validation/stack_smoke.sh`
- [ ] WF6-F-P4-03 Implement rollback on critical smoke failures in non-dev environments.
  - Files: `scripts/k8s/rollback.sh`, `azure-pipelines/dq-made-easy-deploy-aks.yml`
- [ ] WF6-F-P4-04 Define and document manual recovery runbook for failed deployments.
  - Files: `docs/technical/KONG_DEPLOYMENT.md`, `docs/technical/DEPLOYMENT.md` (new Kubernetes sections)
- [ ] WF6-F-P4-05 Add release-health dashboard inputs for deployment status and rollback events.
  - Files: `observability/*` (deployment event ingestion docs/config), `docs/implementation-details/OBSERVABILITY_SETUP.md`

## Implementation Order (Concrete)

1. Create `infra/k8s/base` and `infra/k8s/overlays/{dev,test,prod}` skeletons.
2. Implement `scripts/k8s/render.sh` for deterministic manifest rendering by environment.
3. Implement `scripts/k8s/deploy.sh` for apply + rollout wait + evidence output.
4. Add `scripts/validation/validate_k8s_manifest_contract.sh` and wire it into `scripts/validate.sh`.
5. Add AKS pipeline stages with mandatory order: Build, Test, Publish-to-registry, Deploy.
6. Parameterize registry target (`docker.io` or internal registry such as Nexus) and ensure deploy pulls from published registry references.
7. Add Azure pipeline AKS deployment YAML using the existing dev/test/prod parameter pattern.
8. Add `scripts/k8s/smoke.sh` and `scripts/k8s/rollback.sh` and connect them to pipeline gates.
9. Add release evidence output and documentation updates.

## Validation Gates

Minimum command contract for WF6 rollout:

```bash
./scripts/validation/validate_env_file.sh --env dev
./scripts/validation/validate_env_file.sh --env test
./scripts/validation/validate_env_file.sh --env prod
./scripts/validation/validate_k8s_manifest_contract.sh --env dev
./scripts/validation/validate_k8s_manifest_contract.sh --env test
./scripts/validation/validate_k8s_manifest_contract.sh --env prod
./scripts/validation/validate_k8s_rollout_smoke.sh --env test
./scripts/validation/validate_k8s_rollout_smoke.sh --env prod
```

## Acceptance Evidence Mapping

- WF6-F-AC-01: pipeline artifact with identical digest set promoted dev -> test -> prod.
- WF6-F-AC-02: overlay diff report for hostnames, secrets, and replica settings.
- WF6-F-AC-03: failing validation run logs for missing config/secret/policy.
- WF6-F-AC-04: successful rollback transcript from `scripts/k8s/rollback.sh` in test.
- WF6-F-AC-05: smoke output artifacts from `scripts/k8s/smoke.sh` and validation wrappers.
- WF6-F-AC-06: pipeline approval logs and release note references.

## Related Documents

- [WF_6_KUBERNETES_IMAGE_DEPLOYMENT.md](/docs/features/WF_6_KUBERNETES_IMAGE_DEPLOYMENT/)
- [AZURE_CONTAINER_APPS_TO_AKS_DEPLOYMENT_PLAN.md](/docs/implementation-details/AZURE_CONTAINER_APPS_TO_AKS_DEPLOYMENT_PLAN/)
- [STACK_SCRIPT_CONTRACT.md](/docs/implementation-details/STACK_SCRIPT_CONTRACT/)
- [WF_5_DEDICATED_ENVIRONMENT_CONTRACT.md](/docs/features/WF_5_DEDICATED_ENVIRONMENT_CONTRACT/)
