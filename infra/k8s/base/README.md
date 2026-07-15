# Kubernetes Base Service Templates (WF6-F-P1-01)

This folder contains baseline Kubernetes templates for repo-managed runtime services.

Scope for this checkpoint:

- Base `Deployment` + `Service` templates for long-running runtime components.
- Shared namespace and common config scaffolding.
- Service-specific config/secret references are placeholders for overlay binding.

How to render:

```bash
kustomize build infra/k8s/base
```

Notes:

- Images default to Docker Hub style references and should be overridden by CI/CD promotion output.
- `envFrom` references expect service-specific ConfigMap/Secret objects from overlays.
- Non-HTTP workers include Services only where useful for metrics or service discovery.
