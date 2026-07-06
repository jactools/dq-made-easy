# Kubernetes Environment Conventions (WF6-F-P1-03)

This document defines namespace and ingress hostname conventions for WF6 Kubernetes deployments.

## Namespace Convention

Environment namespaces are fixed and must match pipeline environment selection.

- dev: `dq-made-easy-dev`
- test: `dq-made-easy-test`
- prod: `dq-made-easy-prod`

Namespace names are applied in overlays and represented as a concrete `Namespace` object in rendered output.

## Ingress Convention

Base ingress resources are hosted in `infra/k8s/base/ingress` and are patched per environment.

Ingress resources:

- `dq-ingress-frontend` -> path `/`
- `dq-ingress-keycloak` -> path `/iam`
- `dq-ingress-openmetadata` -> path `/openmetadata`

All ingress routes terminate at service `dq-kong` port `8443`.

### Hostname Matrix

- dev:
  - frontend: `dq-made-easy.jac.dot`
  - keycloak: `keycloak.jac.dot`
  - openmetadata: `openmetadata.jac.dot`
- test:
  - frontend: `dq-made-easy.nl`
  - keycloak: `keycloak.dq-made-easy.nl`
  - openmetadata: `openmetadata.dq-made-easy.nl`
- prod:
  - frontend: `dq-made-easy.eu`
  - keycloak: `dq-made-easy.eu` with `/iam`
  - openmetadata: `dq-made-easy.eu` with `/openmetadata`

TLS secret names are environment-specific overlay values and should map to externally provisioned certificates.

## Render Commands

```bash
kubectl kustomize infra/k8s/base
kubectl kustomize infra/k8s/overlays/dev
kubectl kustomize infra/k8s/overlays/test
kubectl kustomize infra/k8s/overlays/prod
```

Provider-aware render helper:

```bash
./scripts/k8s/render.sh --env dev --cloud-provider aks
./scripts/k8s/render.sh --env test --cloud-provider eks --output tmp/k8s-test-eks.yaml
./scripts/k8s/render.sh --env prod --cloud-provider gke --output tmp/k8s-prod-gke.yaml
```

Provider-specific render examples:

```bash
kubectl kustomize infra/k8s/providers/aks/dev
kubectl kustomize infra/k8s/providers/eks/test
kubectl kustomize infra/k8s/providers/gke/prod
```

## Migration And Seed Job Lifecycle

Base job templates are defined in `infra/k8s/base/jobs` and are orchestrated by `scripts/k8s/deploy.sh`.

- Migration jobs run by default in all environments.
  - `dq-job-api-migrate`
  - `dq-job-kong-migrate`
- Seed jobs are environment-aware.
  - `auto` mode (default): runs in dev/test, skipped in prod
  - `always` mode: runs in all environments, requires `--allow-prod-seed` for prod
  - `never` mode: skips all seed jobs

Example deploy commands:

```bash
./scripts/k8s/deploy.sh --env dev
./scripts/k8s/deploy.sh --env test --seed-mode auto
./scripts/k8s/deploy.sh --env prod --seed-mode never
```

Multi-cloud deploy examples:

```bash
./scripts/k8s/deploy.sh --env dev --cloud-provider aks
./scripts/k8s/deploy.sh --env test --cloud-provider eks
./scripts/k8s/deploy.sh --env prod --cloud-provider gke --seed-mode never
```

Dry-run deploy example (server-side validation only):

```bash
./scripts/k8s/deploy.sh --env dev --cloud-provider aks --dry-run
```

Preflight validator:

```bash
./scripts/validation/validate_k8s_cluster_capabilities.sh --provider aks --namespace dq-made-easy-dev
./scripts/validation/validate_k8s_cluster_capabilities.sh --provider eks --namespace dq-made-easy-test
./scripts/validation/validate_k8s_cluster_capabilities.sh --provider gke --namespace dq-made-easy-prod
```

## Local Build And Deploy Workflow (macOS: minikube or kind)

To mirror pipeline stages locally (Build -> Test -> Publish -> Deploy -> Smoke), use:

- `scripts/k8s/local_pipeline.sh`

What it does:

- Build: calls `scripts/build_and_push_one.sh` with `--no-push`
- Test: runs a local test command (default `./scripts/validate.sh`)
- Publish (local): loads image into kind or minikube cluster runtime
- Deploy: runs `scripts/k8s/deploy.sh` with local-safe defaults
- Smoke: verifies rollout, deployed image, and running pods

Typical kind example:

```bash
./scripts/k8s/local_pipeline.sh --env dev \
  --service-name dq-api \
  --image-name jacbeekers/dq-made-easy-api \
  --image-tag local-dev \
  --cluster-runtime kind
```

Typical minikube example:

```bash
./scripts/k8s/local_pipeline.sh --env dev \
  --service-name dq-api \
  --image-name jacbeekers/dq-made-easy-api \
  --image-tag local-dev \
  --cluster-runtime minikube
```

Dry-run local pipeline example:

```bash
./scripts/k8s/local_pipeline.sh --env dev \
  --service-name dq-api \
  --image-name jacbeekers/dq-made-easy-api \
  --image-tag local-dev \
  --cluster-runtime kind \
  --dry-run
```

Recommended local flags for fast feedback:

- `--skip-tests` to bypass the local Test stage.
- `--skip-migrations` (default true) to avoid rerunning migration jobs.
- `--run-seeds` only when seed behavior is part of the test.
- `--run-preflight` when validating ingress/controller readiness on local clusters.

### Multi-service local loop

To rebuild and redeploy a service set in sequence (for example API + engine + frontend), use:

- `scripts/k8s/local_pipeline_batch.sh`

kind example:

```bash
./scripts/k8s/local_pipeline_batch.sh --env dev \
  --cluster-runtime kind \
  --services dq-api,dq-engine,dq-frontend \
  --image-tag-prefix local-dev
```

minikube example:

```bash
./scripts/k8s/local_pipeline_batch.sh --env dev \
  --cluster-runtime minikube \
  --services dq-api,dq-engine,dq-frontend \
  --image-tag-prefix local-dev
```

Dry-run batch example:

```bash
./scripts/k8s/local_pipeline_batch.sh --env dev \
  --cluster-runtime kind \
  --services all \
  --image-tag-prefix local-dev \
  --dry-run
```

Useful options:

- `--run-tests` to execute the Test stage per service.
- `--run-migrations` when migration jobs must be replayed.
- `--run-seeds` when seed data changes are under test.
- `--run-preflight-first` to validate cluster capabilities before the first service deploy.

## Traceability Labels And Annotations

WF6 base manifests apply a required traceability contract through kustomize transformers:

- labels transformer: `infra/k8s/base/metadata/labels.yaml`
- annotations transformer: `infra/k8s/base/metadata/annotations.yaml`

Required labels:

- `app.kubernetes.io/managed-by=dq-made-easy-wf6`
- `app.kubernetes.io/version=from-version-manifest`
- `dq.jaccloud.nl/traceability=enabled`

Required annotations:

- `dq.jaccloud.nl/traceability-contract=wf6-v1`
- `dq.jaccloud.nl/version-manifest-path=VERSION_MANIFEST.json`
- `dq.jaccloud.nl/release-channel=promoted`
