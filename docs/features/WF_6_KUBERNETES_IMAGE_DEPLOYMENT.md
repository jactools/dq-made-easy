# WF-6 Kubernetes Image Deployment for Dev, Test, and Prod

Goal: define a single, environment-aware deployment feature that promotes repository-managed Docker images to Kubernetes clusters in dev, test, and prod with repeatable rollout, rollback, and validation behavior.

Implementation plan: [WF_6_KUBERNETES_IMAGE_DEPLOYMENT_IMPLEMENTATION_PLAN.md](../implementation-details/WF_6_KUBERNETES_IMAGE_DEPLOYMENT_IMPLEMENTATION_PLAN.md)

Implementation status: base manifests, environment overlays, provider-aware render/deploy scripts, local pipeline wrappers, and local cluster bootstrap helpers are implemented. The remaining work is tracked in the implementation plan.

## Principles

- Keep one deployment contract across all environments, with environment-specific values and guardrails.
- Promote immutable image tags across environments; do not rebuild the same version separately per environment.
- Use GitOps-compatible manifests and overlays so rendered runtime state is auditable.
- Separate image build concerns from cluster deploy concerns.
- Enforce fail-fast validation before applying changes to any cluster.
- Keep secret material out of repository-tracked files.
- Keep Kubernetes deployment files and pipelines separate from Azure Container Apps deployment files and pipelines.

## Platform Separation

- Kubernetes deployment assets (manifests, deploy scripts, AKS pipelines, AKS parameter files) are WF-6 owned.
- Azure Container Apps deployment assets (OpenTofu modules, ACA deploy/provision pipelines, ACA parameter files) are WF-7 owned.
- Reuse is allowed only through platform-neutral shared templates and helper scripts (for example image-variable resolution and evidence publishing).

## Scope

- Deploy repository-managed images to Kubernetes namespaces for dev, test, and prod.
- Support environment overlays for config, replicas, ingress hosts, and resource policies.
- Provide rollout and rollback flows for API, engine, profiling, frontend, gateway, and supporting services.
- Provide post-deploy validation checks and evidence capture.

## Out of Scope

- Replacing local Docker Compose workflows for workstation development.
- Rewriting service internals purely for Kubernetes migration.
- Introducing multi-cloud abstractions before the single-cluster-per-environment contract is stable.

## Environment Contract

- Dev: fast iteration, lower replica counts, optional preview namespaces, reduced SLO expectations.
- Test: release-candidate validation, production-like topology, stricter policy checks.
- Prod: hardened policy baseline, controlled rollout windows, explicit approval gates.

Common requirements across dev/test/prod:

- Immutable image reference policy: prefer digest pins for production-grade rollouts.
- Environment-specific hostnames and TLS certificates.
- Environment-specific secret sources and rotation policies.
- Environment-specific replica and autoscaling thresholds.

## Kubernetes Deployment Model

- Base manifests per service: Deployment, Service, ConfigMap, Secret references, PodDisruptionBudget, HorizontalPodAutoscaler where applicable.
- Overlay model: one base plus overlays for dev, test, prod.
- Namespace model: one namespace per environment baseline, with optional short-lived preview namespaces in dev.
- Ingress model: environment-scoped hosts and TLS secrets.
- Job model: one-shot migration and seeding jobs aligned with environment gates.

## CI/CD and Promotion Flow

1. Build and publish images once.
2. Record tag and digest metadata in a deploy artifact.
3. Deploy to dev overlay.
4. Run post-deploy smoke validations in dev.
5. Promote same image digests to test overlay.
6. Run regression and contract validations in test.
7. Promote same image digests to prod overlay with approval gate.
8. Run production smoke checks and rollback automatically on hard failures.

## Configuration and Secrets

- Non-secret runtime configuration in ConfigMaps.
- Secrets sourced from managed secret stores and projected into workloads.
- No plaintext production credentials in repository-tracked env files.
- Strict separation of secret scopes by environment and namespace.

## Observability and Operations

- Emit deployment events and rollout status to centralized logs.
- Capture readiness, liveness, and startup probe outcomes as deployment evidence.
- Export per-release health summary including image digest, namespace, and rollout result.
- Define on-call runbook steps for rollback, restart, and scale operations.

## Security and Policy Controls

- Enforce image provenance checks in deployment pipeline.
- Enforce admission policies for required labels, resource limits, and allowed registries.
- Enforce network policies for least-privilege service communication.
- Require TLS for ingress and inter-service channels where applicable.

## Rollout Strategy

- Default rolling updates for stateless services.
- Optional canary strategy for high-risk services.
- Explicit max unavailable and surge values per environment.
- Automatic rollback trigger conditions for failed readiness or critical smoke checks.

## Feature Phases

### Phase 1: Baseline Kubernetes Contract

- [x] (WF6-F-P1-01) Define base Kubernetes resource templates for each repo-managed runtime service.
- [x] (WF6-F-P1-02) Define dev, test, and prod overlays with environment-specific config boundaries.
- [x] (WF6-F-P1-03) Define namespace and ingress hostname conventions for all environments.
- [x] (WF6-F-P1-04) Define migration and seed job lifecycle behavior per environment.
- [x] (WF6-F-P1-05) Define required labels and annotations for traceability.

### Phase 2: Pipeline and Promotion Automation

- [ ] (WF6-F-P2-01) Publish build artifact containing image tags and digests for all deployable services.
- [ ] (WF6-F-P2-02) Implement deploy pipeline step for dev overlay with validation gate.
- [ ] (WF6-F-P2-03) Implement promotion pipeline step from dev to test using identical digests.
- [ ] (WF6-F-P2-04) Implement gated promotion pipeline step from test to prod.
- [ ] (WF6-F-P2-05) Persist deployment evidence per environment for audit and release notes.

### Phase 3: Runtime Hardening

- [ ] (WF6-F-P3-01) Add readiness, liveness, and startup probes for all long-running services.
- [ ] (WF6-F-P3-02) Add resource requests and limits with environment-specific defaults.
- [ ] (WF6-F-P3-03) Add network policies for service-to-service communication boundaries.
- [ ] (WF6-F-P3-04) Add pod disruption budgets for critical services.
- [ ] (WF6-F-P3-05) Add autoscaling policy where runtime behavior supports it.

### Phase 4: Rollout Safety and Recovery

- [ ] (WF6-F-P4-01) Define per-service rollout strategy and rollback policy.
- [ ] (WF6-F-P4-02) Implement automated post-deploy smoke validation execution.
- [ ] (WF6-F-P4-03) Implement rollback on critical smoke failures in non-dev environments.
- [ ] (WF6-F-P4-04) Define and document manual recovery runbook for failed deployments.
- [ ] (WF6-F-P4-05) Add release-health dashboard inputs for deployment status and rollback events.

## Acceptance Criteria

- [ ] (WF6-F-AC-01) Dev, test, and prod can deploy the same immutable image digests without rebuilding.
- [ ] (WF6-F-AC-02) Each environment has isolated configuration, secrets, and ingress boundaries.
- [ ] (WF6-F-AC-03) Deployments fail fast when required config, secret references, or policy checks are missing.
- [ ] (WF6-F-AC-04) Rollback path is validated and executable for every production-deployed service.
- [ ] (WF6-F-AC-05) Post-deploy smoke checks produce environment-specific evidence artifacts.
- [ ] (WF6-F-AC-06) Production promotions require an explicit approval gate and traceable deployment record.

## Delivery Milestones

- Milestone A (Contract): WF6-F-P1-01 to WF6-F-P1-05
- Milestone B (Automation): WF6-F-P2-01 to WF6-F-P2-05
- Milestone C (Hardening): WF6-F-P3-01 to WF6-F-P3-05
- Milestone D (Rollout Safety): WF6-F-P4-01 to WF6-F-P4-05
