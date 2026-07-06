# Kubernetes Cloud Provider Overlays

These overlays extend environment overlays with provider-specific ingress behavior.

Layout:

- `infra/k8s/providers/aks/{dev,test,prod}`
- `infra/k8s/providers/eks/{dev,test,prod}`
- `infra/k8s/providers/gke/{dev,test,prod}`

Each target overlay references an existing environment overlay and applies provider ingress patches.

Examples:

- `kubectl kustomize infra/k8s/providers/aks/dev`
- `kubectl kustomize infra/k8s/providers/eks/test`
- `kubectl kustomize infra/k8s/providers/gke/prod`
