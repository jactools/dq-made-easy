# MaaS Target Rollout Matrix for `dq-made-easy`

**Date**: 2026-08-05  
**Status**: Complete

## Objective and scope

Create a repo-local rollout matrix for the `dq-made-easy` workloads so the internal-only UI contract, API placement, and DQ-job behavior live in the repository that owns them.

## Results

| Area | Before | After |
| --- | --- | --- |
| Rollout authority | The platform repo described the shared contract and consumer draft together | `dq-made-easy` now owns its own target rollout matrix |
| UI exposure | Internal-only UI guidance existed only as a platform note | The repo-local matrix states the UI remains internal-only |
| Job behavior | DQ jobs were noted as unregistered in the platform plan | The repo-local matrix documents job/non-registration behavior |
| Namespace naming | Not owned by the repo-local doc | Lowercase target-suffixed namespace convention documented here |

## Files created or updated

| Path | Change |
| --- | --- |
| `docs/implementation-details/MAAS_TARGET_ROLLOUT_MATRIX.md` | Added the repo-local 16-target rollout matrix for the `dq-made-easy` UI, API, and DQ jobs |
| `docs/implementation-details/README.md` | Added the new matrix doc to the implementation-details index |

## Known issues or remaining work

- The matrix currently covers the `dq-made-easy` UI, API, and DQ job paths; if additional long-lived services become target-managed workloads, the matrix needs to be extended.
- Any future public exposure must be justified explicitly because the UI is documented as internal-only.

## Next steps

1. Keep the matrix aligned with deployment manifests and environment files.
2. Extend the matrix if the repository adds more long-lived service instances.
3. Use this matrix as the authoritative reference for deployment and smoke checks.
