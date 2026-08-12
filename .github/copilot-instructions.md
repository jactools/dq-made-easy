# Copilot Instructions

See `AGENTS.md` for the complete repository rules. The critical rules repeated here for reliability:

## Git — NO COMMITS EVER
Agents may only run `git status`. All other `git` commands are FORBIDDEN.

## No Fallbacks
Fail fast when a required API or script is unavailable. Do not silently substitute behavior.

## GitOps Write Policy
- Treat Git as the source of truth for ArgoCD-managed resources.
- Do not use `kubectl apply`, `kubectl patch`, or `kubectl rollout restart` on ArgoCD-managed workloads.
- Use `kubectl` for read-only inspection and debugging only.
- Make lasting changes through Git and ArgoCD reconciliation.

## Validation
Run the repository's standard tests and checks after changes, and prefer repo-local validation scripts when they exist.