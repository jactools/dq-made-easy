# WF-7 Azure Container Apps Environment Deployment for Dev, Test, and Prod

Goal: define a single deployment feature that promotes repository-managed Docker images to Azure Container Apps environments in dev, test, and prod with repeatable rollout, validation, and rollback behavior.

Implementation plan: [WF_7_AZURE_CONTAINER_APPS_ENVIRONMENT_DEPLOYMENT_IMPLEMENTATION_PLAN.md](../implementation-details/WF_7_AZURE_CONTAINER_APPS_ENVIRONMENT_DEPLOYMENT_IMPLEMENTATION_PLAN.md)

## Principles

- Keep one environment contract across dev, test, and prod.
- Promote immutable image tags across environments; do not rebuild per environment.
- Separate environment provisioning from per-app image deployment.
- Keep fail-fast validation before apply and post-deploy validation after rollout.
- Keep secrets out of repository-tracked env files.
- Keep deployment evidence traceable to image tag, environment, and pipeline run.
- Keep Azure Container Apps deployment files and pipelines separate from Kubernetes deployment files and pipelines.

## Platform Separation

- Azure Container Apps deployment assets (OpenTofu modules, ACA deploy/provision pipelines, ACA parameter files) are WF-7 owned.
- Kubernetes deployment assets (manifests, AKS deploy pipelines, AKS parameter files) are WF-6 owned.
- Reuse is allowed only through platform-neutral shared templates and helper scripts (for example image-variable resolution and deployment-evidence publishing).

## Scope

- Provision Azure Container Apps environments for dev, test, and prod.
- Deploy repo-managed runtime images to those environments.
- Support environment-specific ingress, target ports, scale policy, and secret references.
- Support controlled promotion flow dev -> test -> prod.
- Capture rollout and smoke-validation evidence per environment.

## Out of Scope

- Replacing local Docker Compose workstation startup.
- Kubernetes migration details (covered by WF-6).
- Rewriting service internals solely for Azure deployment.

## Environment Contract

- Dev: rapid iteration, internal ingress by default, lower scale limits.
- Test: production-like deployment checks, stricter smoke and contract validation.
- Prod: controlled rollout windows, approval gates, and hardened ingress and secret posture.

Common requirements across environments:

- Explicit environment selection (`dev`, `test`, `prod`).
- Explicit resource group and Container Apps environment identity.
- Explicit image reference and target port per deployed app.
- Environment-scoped secret and registry credentials.

## Deployment Model

- Provisioning model: OpenTofu-managed Azure Container Apps environment and workspace dependencies.
- Runtime model: per-container-app deployment pipeline using image, ingress mode, and port.
- Promotion model: deploy same immutable image tag from dev to test to prod.
- Evidence model: capture deployed image, ingress settings, rollout status, and smoke result.

## CI/CD and Promotion Flow

1. Build and publish images once.
2. Provision or validate target ACA environment for selected stage.
3. Deploy image to dev container app.
4. Run dev smoke checks.
5. Promote same image to test.
6. Run test smoke and regression checks.
7. Promote same image to prod with approval gate.
8. Run prod smoke and rollback on critical failures.

## Configuration and Secrets

- Runtime config values passed explicitly via deployment pipeline inputs.
- Registry credentials handled as secure pipeline variables or managed identities.
- Service credentials stored in Azure-managed secret stores and referenced by apps.
- No plaintext production credentials in repository-tracked files.

## Security and Policy Controls

- Restrict allowed registries and image naming policy.
- Enforce ingress mode policy per environment.
- Enforce environment-scoped Azure service connections.
- Require deployment input validation before apply.

## Rollout and Recovery

- Use revision-based ACA rollout for container updates.
- Validate effective image and target port immediately after deploy.
- Keep rollback path as redeploy of prior known-good image tag.
- Gate prod deployment on explicit approval and smoke success.

## Feature Phases

### Phase 1: Environment and Contract Baseline

- [ ] (WF7-F-P1-01) Define dev, test, and prod ACA environment contract and required variables.
- [ ] (WF7-F-P1-02) Define per-service deployment inputs (image, container name, target port, ingress).
- [ ] (WF7-F-P1-03) Define naming conventions for resource groups, environment names, and state keys.
- [ ] (WF7-F-P1-04) Define environment provisioning behavior and idempotency expectations.
- [ ] (WF7-F-P1-05) Define deployment evidence schema (image, ingress, revision, validation result).

### Phase 2: Deployment Automation

- [ ] (WF7-F-P2-01) Implement environment-aware deploy pipeline for ACA app deployment.
- [ ] (WF7-F-P2-02) Implement fail-fast input validation and required variable checks.
- [ ] (WF7-F-P2-03) Implement dev -> test promotion with immutable image tags.
- [ ] (WF7-F-P2-04) Implement test -> prod promotion with explicit approval gate.
- [ ] (WF7-F-P2-05) Persist per-environment deployment evidence for audit and release notes.

### Phase 3: Runtime Hardening

- [ ] (WF7-F-P3-01) Define environment-specific ingress policy defaults.
- [ ] (WF7-F-P3-02) Define environment-specific scale and revision behavior.
- [ ] (WF7-F-P3-03) Define secure registry-auth strategy per environment.
- [ ] (WF7-F-P3-04) Define secret-handling and rotation contract for ACA apps.
- [ ] (WF7-F-P3-05) Define monitoring and alerting contract for deployment failures.

### Phase 4: Validation and Recovery

- [ ] (WF7-F-P4-01) Add post-deploy smoke validation for each environment.
- [ ] (WF7-F-P4-02) Add rollout failure detection and pipeline fail-fast behavior.
- [ ] (WF7-F-P4-03) Add rollback workflow to previous known-good image tag.
- [ ] (WF7-F-P4-04) Add operator runbook for failed ACA deployments.
- [ ] (WF7-F-P4-05) Add release health summary for deployment status and rollbacks.

## Acceptance Criteria

- [ ] (WF7-F-AC-01) Dev, test, and prod ACA deployments can use the same immutable image tag without rebuild.
- [ ] (WF7-F-AC-02) Environment-specific config, secret scope, and ingress policy are isolated.
- [ ] (WF7-F-AC-03) Deployment fails fast when required inputs are missing or invalid.
- [ ] (WF7-F-AC-04) Post-deploy validation confirms deployed image and target port match requested values.
- [ ] (WF7-F-AC-05) Rollback to a previous known-good image is documented and executable.
- [ ] (WF7-F-AC-06) Prod deployment requires explicit approval and traceable evidence.

## Delivery Milestones

- Milestone A (Contract): WF7-F-P1-01 to WF7-F-P1-05
- Milestone B (Automation): WF7-F-P2-01 to WF7-F-P2-05
- Milestone C (Hardening): WF7-F-P3-01 to WF7-F-P3-05
- Milestone D (Validation and Recovery): WF7-F-P4-01 to WF7-F-P4-05
