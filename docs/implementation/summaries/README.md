# Implementation Summaries

This directory contains implementation summaries for significant architectural or delivery changes.

## Index

| Date | Summary | Status | Scope |
|---|---|---|---|
| 2026-08-20 | [Flux migration recovery — Kong gateway + Keycloak tenant seeding](./2026-08-20_flux-migration-kong-keycloak-seed-recovery.md) | Code complete | Restored DQ login after Flux migration: GitOps-managed Kong/Keycloak init Job, ExternalSecret, SSO config, seed-users.sh idempotency fix, Kong OOM fix |
| 2026-08-10 | [Fresh deploy checklist](./2026-08-10_fresh-deploy-checklist.md) | Draft | Step-by-step deploy guide + troubleshooting table |
| 2026-08-10 | [Kong bootstrap — SSL verification, route paths, SSO session resolution](./2026-08-10_kong-bootstrap-ssl-sso-fix.md) | Complete | Fixed kong-bootstrap job readiness checks, route path drift, Keycloak admin password, and TRUST_PROXY_AUTH |
| 2026-08-05 | [MaaS target rollout matrix](./2026-08-05_maas-target-rollout-matrix.md) | Complete | Repo-local target/service/instance rollout contract for MaaS workloads |
| 2026-08-04 | [dq-made-easy shared image verification](./2026-08-04_dq-made-easy-shared-image-verification.md) | Complete | Verified the shared runner image through the repo pull path and container runtime |
| 2026-08-04 | [dq-made-easy shared image compatibility cleanup](./2026-08-04_dq-made-easy-shared-image-compatibility-cleanup.md) | Complete | Removed the bare shared-image scope shim and tightened operator dry-run planning |
| 2026-08-04 | [dq-api shared scope adapter extraction](./2026-08-04_dq-api-shared-scope-adapter-extraction.md) | Complete | Split dq-api scope delegation into a dedicated adapter module |
| 2026-08-04 | [dq-api shared scope resolver adoption](./2026-08-04_dq-api-shared-scope-resolver-adoption.md) | Complete | Moved dq-api scope extraction and matching onto `platform_auth` |
| 2026-08-04 | [Pre-commit hook alignment](./2026-08-04_pre-commit-hook-alignment.md) | Complete | Matched the shared validator hooks to the metadata-as-a-service style |
| 2026-08-04 | [Validation hooks for module rules and snake_case](./2026-08-04_validation-hooks-module-rules-snake-case.md) | Complete | Wired the copied validators into pre-commit and repo validation discovery |
| 2026-08-04 | [Shared platform adoption scope split](./2026-08-04_shared-platform-adoption-scope-split.md) | Complete | Split dq-made-easy and MaaS adoption into separate plans |
| 2026-08-04 | [Shared ingestion runner image version pinning](./2026-08-04_shared-ingestion-runner-image-version-pinning.md) | Complete | Documented how consumers should pin, upgrade, and roll back the shared ingestion runner image |
| 2026-08-04 | [Shared ingestion runner image local overrides](./2026-08-04_shared-ingestion-runner-image-local-overrides.md) | Complete | Documented the approved local debugging path for the shared ingestion runner image |
| 2026-08-04 | [Shared ingestion runner image consumption](./2026-08-04_shared-ingestion-runner-image-consumption.md) | Complete | Exposed the shared ingestion runner image through `dq-made-easy` pull tooling and environment defaults |
| 2026-08-04 | [Shared ingestion runner image publish contract](./2026-08-04_shared-ingestion-runner-image-publish-contract.md) | Complete | Defined the stable registry namespace and versioning contract for the shared ingestion runner |
| 2026-08-04 | [Shared ingestion runner image pipeline](./2026-08-04_shared-ingestion-runner-image-pipeline.md) | Complete | Centralized the first shared image build pipeline in `platform-foundation` |
| 2026-08-04 | [Shared ingestion W2-04 boundary clarification](./2026-08-04_shared-ingestion-w2-04-boundary-clarification.md) | Complete | Marked SHARED-I-W2-04 complete and narrowed the task to `dq-made-easy` only |
| 2026-08-04 | [Delivery metadata package adoption and cleanup](./2026-08-04_metadata-package-adoption-and-cleanup.md) | Complete | Replaced repo-local shared delivery support packages with shared metadata packages and refreshed proof/evidence artifacts |
