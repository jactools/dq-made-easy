# Azure Container Apps to Azure Kubernetes Deployment Plan

Status: Draft
Last updated: 2026-06-10

## Purpose

This plan outlines how to deploy the repository-owned Docker images and Python wheels to Azure Container Apps first, then promote the same artifact set to Azure Kubernetes Service later when the platform needs more control over ingress, scheduling, and operational policy.

The plan is intentionally focused on the container image estate in this repository, not on rewriting product behavior or changing service contracts.

## Scope Guardrails

- Keep image publishing and runtime deployment separate from application behavior changes.
- Prefer managed Azure services for durable state where that reduces operational risk.
- Do not add compatibility shims or fallback behavior to make the deployment easier.
- Keep the deployment path explicit: NexusCloud as the Docker image and Python wheel source, then ACA or AKS as the runtime target.

## Image Estate

### Artifact distribution targets

- NexusCloud Docker registry for repo-owned container images
- NexusCloud PyPI repository for repo-owned Python wheels

### Repo-owned runtime images

- `dq-api`
- `dq-engine`
- `dq-profiling`
- `dq-frontend`
- `dq-kong`
- `dq-keycloak`
- `dq-db`
- `dq-llm`
- `dq-edge`
- `dq-openmetadata-db`
- `dq-openmetadata-server`
- `dq-metadata-configure`

### Upstream runtime images used by compose

- `postgres`
- `nginx`
- `redis`
- `openmetadata/server`
- `openmetadata/ingestion`
- `ghcr.io/zammad/zammad`

## Phase 1: Azure Container Apps

### Goal

Use Azure Container Apps for the first production-like Azure deployment so the platform can run behind a managed ingress and consume Azure-managed backing services without introducing a Kubernetes control plane too early.

### Recommended shape

- Build and push all repo-owned Docker images to NexusCloud from the Azure DevOps pipeline.
- Build and publish repo-owned Python wheels to NexusCloud PyPI from the Azure DevOps pipeline.
- Deploy the stateless application containers first:
  - `dq-api`
  - `dq-frontend`
  - `dq-engine`
  - `dq-profiling`
  - `dq-llm` is acceptable in ACA
- Keep stateful dependencies out of ACA where a managed Azure service is a better fit:
  - Azure Database for PostgreSQL for application databases
  - Azure Cache for Redis for queueing, caching, or rate limiting
  - Azure Key Vault for secrets and certificates
  - Azure Storage for durable file/object needs
- Treat `dq-edge` as a dedicated ACA app in the same Container Apps environment.
- Keep `dq-kong` in ACA for dev; for test/prod, use the central Kong infrastructure instead of a per-environment ACA Kong deployment.
- Run OpenMetadata initially in ACA.
- Treat `dq-keycloak` as a later ACA or AKS decision if the auth topology needs to move.

### ACA deployment order

1. Publish Docker images and Python wheels to NexusCloud from the Azure DevOps pipeline.
2. Create the Container Apps environment and Log Analytics workspace.
3. Provision the managed backing services required by the images.
4. Deploy the stateless services behind ACA ingress.
5. Wire environment variables, secrets, and service endpoints explicitly.
6. Validate browser-facing URLs, auth callbacks, and service-to-service connectivity.
7. Cut over traffic only after the ACA deployment passes smoke and rollback checks.

### ACA decision points

- Edge ingress runs in ACA as a separate app in the same ACA environment.
- `dq-kong` stays in ACA for dev. For test/prod, use the central Kong infrastructure.
- OpenMetadata runs initially in ACA.
- `dq-llm` is acceptable in ACA.

## Phase 2: Azure Kubernetes Service

### Goal

Use AKS as the later-stage platform when the deployment needs richer ingress control, finer scheduling, stronger workload isolation, or Kubernetes-native lifecycle management.

### What AKS should own

- Shared ingress and routing control for the full stack.
- Services that need tighter coupling to cluster policy or internal networking.
- Workloads that benefit from Kubernetes primitives such as DaemonSets, Jobs, init containers, node affinity, or GPU pools.
- Any service whose ACA ingress model becomes too constrained for long-term support.

### AKS migration order

1. Stand up the AKS cluster and configure it to pull the same artifacts from NexusCloud.
2. Define namespaces and workload boundaries by capability rather than by repository folder.
3. Migrate ingress, TLS, and path routing to the cluster ingress layer.
4. Move the deployed ACA services into Kubernetes Deployments with matching env and secret wiring.
5. Reconfirm identity, callback, and issuer URLs for each browser-facing surface.
6. Keep managed Azure backing services in place unless a workload explicitly needs a cluster-local store.
7. Add HPA, PodDisruptionBudgets, and policy controls only after the functional cutover is stable.

### AKS decision points

- Decide whether `dq-edge` becomes the cluster ingress entrypoint or remains an external front door.
- Decide whether `dq-kong` remains the API gateway in front of `dq-api` or is partially replaced by AKS ingress behavior.
- Decide whether Keycloak and OpenMetadata move as-is or are simplified to managed services plus stateless runtime containers.
- Decide whether any containerized databases should stay containerized at all, or be replaced entirely by managed Azure data services.

## Common Deployment Rules

- Push images to NexusCloud with immutable tags for release builds, and publish Python wheels there with immutable versioned filenames from the Azure DevOps pipeline.
- Keep environment values explicit and topology-specific.
- Do not store secrets in container images.
- Prefer managed services for data durability, backups, and patching.
- Keep browser-facing URLs, internal service URLs, and callback URLs separate.
- Validate one service slice at a time before broadening the deployment surface.

## Acceptance Criteria

- Every repo-owned image and wheel has a known NexusCloud target and release version strategy.
- The ACA deployment can be recreated from documented commands and environment files.
- The AKS migration path reuses the same image artifacts rather than rebuilding ad hoc variants.
- Public and internal URLs remain correct after deployment and during future migration.
- Rollback is possible by reverting image tags and environment values without changing application code.

## Related Docs

- [Azure Container Apps deployment guide](/docs/technical/AZURE_DEPLOYMENT/)
- [Kong deployment strategy](/docs/technical/KONG_DEPLOYMENT/)
- [Stack script contract](/docs/implementation-details/STACK_SCRIPT_CONTRACT/)
