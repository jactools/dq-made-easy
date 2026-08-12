# ArgoCD and kubectl Write Policy

## Purpose

This repository should treat Git as the source of truth for every ArgoCD-managed workload. Direct `kubectl` writes to those resources should be blocked by default so that live cluster state does not drift away from Git.

## Recommendation

Block human write access to ArgoCD-managed resources in the namespaces and workloads controlled by this repository. Keep `kubectl` available for read-only debugging and diagnostics, and use a documented break-glass flow for emergencies.

## Scope

If this repository contains ArgoCD-managed namespaces, list them here and keep them in sync with the deployment policy in `AGENTS.md` and `.github/copilot-instructions.md`.

## Policy matrix

| Namespace group | `kubectl get/list/watch` | `kubectl logs/exec` | `kubectl apply/edit/patch/delete` | Notes |
|---|---|---|---|---|
| ArgoCD-managed namespaces | Allow | Allow, where needed | Deny by default | Changes go through Git |
| Break-glass operators | Allow | Allow | Allow temporarily | Must follow emergency workflow |

## Enforcement model

### 1. RBAC first

Default human roles should be read-only in ArgoCD-managed namespaces. If someone needs to troubleshoot, they should be able to inspect workloads, logs, and pod shells without being able to mutate the desired state.

### 2. Admission control second

Use Kyverno or OPA to block direct writes to resources that ArgoCD is managing. A practical match is the ArgoCD tracking annotation or instance label on the live object. That keeps the policy aligned with actual ownership instead of only namespace membership.

### 3. Self-healing stays on

Keep ArgoCD self-heal enabled on production-like applications so that any accidental mutation that slips through is quickly reverted.

### 4. Shared ownership must be explicit

If a field is legitimately owned by another controller, do not rely on ad hoc `kubectl` edits. Declare the exception in Git with `ignoreDifferences` or a controller-specific ownership rule.

## Break-glass workflow

If a live change is truly required:

1. Temporarily disable auto-sync for the affected application.
2. Apply the emergency change.
3. Open and merge the matching Git change immediately.
4. Re-enable auto-sync.
5. Verify the application is back in sync.

This keeps `kubectl` as an exception path, not a parallel deployment mechanism.

## Bottom line

Yes, blocking `kubectl` writes to ArgoCD-managed resources is the right default for this repository. Use Git for all lasting changes, reserve `kubectl` for inspection and emergency intervention, and make any exceptions explicit in policy rather than informal practice.
