# MaaS Target Rollout Matrix — dq-made-easy

**Status**: Draft  
**Date**: 2026-08-06

Authoritative per-target rollout matrix for the `dq-made-easy` tenant.

This matrix is maintained by the `dq-made-easy` team and defines which services are deployed, their instance names, and their MaaS registration status for each of the 16 MaaS targets.

## 16 MaaS targets

| target_id | Region | Provider |
|---|---|---|
| `AZ-EU` | Europe | Azure |
| `AWS-EU` | Europe | AWS |
| `EC-EU` | Europe | European Cloud |
| `OP-EU` | Europe | Oracle |
| `AZ-RANZ` | Australia & New Zealand | Azure |
| `AWS-RANZ` | Australia & New Zealand | AWS |
| `EC-RANZ` | Australia & New Zealand | European Cloud |
| `OP-RANZ` | Australia & New Zealand | Oracle |
| `AZ-NA` | North America | Azure |
| `AWS-NA` | North America | AWS |
| `EC-NA` | North America | European Cloud |
| `OP-NA` | North America | Oracle |
| `AZ-SA` | South America | Azure |
| `AWS-SA` | South America | AWS |
| `EC-SA` | South America | European Cloud |
| `OP-SA` | South America | Oracle |

## Rollout matrix

### Zone services (per-target)

| target_id | Service | workload-kind | MaaS register | Instance name | K8s resource | Namespace |
|---|---|---|---|---|---|---|
| `AZ-EU` | `dq-api` | service | true | `dq-api-AZ-EU-0` | Deployment | `<env>` |
| `AZ-EU` | `dq-engine` | service | true | `dq-engine-AZ-EU-0` | Deployment | `<env>` |
| `AWS-EU` | `dq-api` | service | true | `dq-api-AWS-EU-0` | Deployment | `<env>` |
| `AWS-EU` | `dq-engine` | service | true | `dq-engine-AWS-EU-0` | Deployment | `<env>` |
| `EC-EU` | `dq-api` | service | true | `dq-api-EC-EU-0` | Deployment | `<env>` |
| `EC-EU` | `dq-engine` | service | true | `dq-engine-EC-EU-0` | Deployment | `<env>` |
| `OP-EU` | `dq-api` | service | true | `dq-api-OP-EU-0` | Deployment | `<env>` |
| `OP-EU` | `dq-engine` | service | true | `dq-engine-OP-EU-0` | Deployment | `<env>` |
| `AZ-RANZ` | `dq-api` | service | true | `dq-api-AZ-RANZ-0` | Deployment | `<env>` |
| `AZ-RANZ` | `dq-engine` | service | true | `dq-engine-AZ-RANZ-0` | Deployment | `<env>` |
| `AWS-RANZ` | `dq-api` | service | true | `dq-api-AWS-RANZ-0` | Deployment | `<env>` |
| `AWS-RANZ` | `dq-engine` | service | true | `dq-engine-AWS-RANZ-0` | Deployment | `<env>` |
| `EC-RANZ` | `dq-api` | service | true | `dq-api-EC-RANZ-0` | Deployment | `<env>` |
| `EC-RANZ` | `dq-engine` | service | true | `dq-engine-EC-RANZ-0` | Deployment | `<env>` |
| `OP-RANZ` | `dq-api` | service | true | `dq-api-OP-RANZ-0` | Deployment | `<env>` |
| `OP-RANZ` | `dq-engine` | service | true | `dq-engine-OP-RANZ-0` | Deployment | `<env>` |
| `AZ-NA` | `dq-api` | service | true | `dq-api-AZ-NA-0` | Deployment | `<env>` |
| `AZ-NA` | `dq-engine` | service | true | `dq-engine-AZ-NA-0` | Deployment | `<env>` |
| `AWS-NA` | `dq-api` | service | true | `dq-api-AWS-NA-0` | Deployment | `<env>` |
| `AWS-NA` | `dq-engine` | service | true | `dq-engine-AWS-NA-0` | Deployment | `<env>` |
| `EC-NA` | `dq-api` | service | true | `dq-api-EC-NA-0` | Deployment | `<env>` |
| `EC-NA` | `dq-engine` | service | true | `dq-engine-EC-NA-0` | Deployment | `<env>` |
| `OP-NA` | `dq-api` | service | true | `dq-api-OP-NA-0` | Deployment | `<env>` |
| `OP-NA` | `dq-engine` | service | true | `dq-engine-OP-NA-0` | Deployment | `<env>` |
| `AZ-SA` | `dq-api` | service | true | `dq-api-AZ-SA-0` | Deployment | `<env>` |
| `AZ-SA` | `dq-engine` | service | true | `dq-engine-AZ-SA-0` | Deployment | `<env>` |
| `AWS-SA` | `dq-api` | service | true | `dq-api-AWS-SA-0` | Deployment | `<env>` |
| `AWS-SA` | `dq-engine` | service | true | `dq-engine-AWS-SA-0` | Deployment | `<env>` |
| `EC-SA` | `dq-api` | service | true | `dq-api-EC-SA-0` | Deployment | `<env>` |
| `EC-SA` | `dq-engine` | service | true | `dq-engine-EC-SA-0` | Deployment | `<env>` |
| `OP-SA` | `dq-api` | service | true | `dq-api-OP-SA-0` | Deployment | `<env>` |
| `OP-SA` | `dq-engine` | service | true | `dq-engine-OP-SA-0` | Deployment | `<env>` |

### Cluster-wide services

| Service | workload-kind | MaaS register | Instance name | K8s resource | Namespace |
|---|---|---|---|---|---|
| `dq-ui` | service | true | `dq-ui-CLUSTER-0` | Deployment | `<env>` |

### Ephemeral jobs (no MaaS registration)

| Workload | workload-kind | MaaS register | Spawns from | Telemetry |
|---|---|---|---|---|
| Spark jobs | job | false | `dq-engine` | `job.runner.*` |
| Profiling workers | job | false | `dq-api` | `job.runner.*` |
| Airflow DAGs | job | false | Platform Airflow | `job.runner.*` |

## Dev/test rollout

| target_id | Environment | dq-api | dq-engine | dq-ui |
|---|---|---|---|---|
| `DEV-LOCAL` | dev (Kind local) | `dq-api-DEV-LOCAL-0` | `dq-engine-DEV-LOCAL-0` | `dq-ui-CLUSTER-0` |
| `TEST-REMOTE` | test (Kind Debian) | `dq-api-TEST-REMOTE-0` | `dq-engine-TEST-REMOTE-0` | `dq-ui-CLUSTER-0` |

## Rollout status

| target_id | Region | Provider | Status | Last deploy | Image tag |
|---|---|---|---|---|---|
| `AZ-EU` | Europe | Azure | Not deployed | — | — |
| `AWS-EU` | Europe | AWS | Not deployed | — | — |
| `EC-EU` | Europe | European Cloud | Not deployed | — | — |
| `OP-EU` | Europe | Oracle | Not deployed | — | — |
| `AZ-RANZ` | Australia & New Zealand | Azure | Not deployed | — | — |
| `AWS-RANZ` | Australia & New Zealand | AWS | Not deployed | — | — |
| `EC-RANZ` | Australia & New Zealand | European Cloud | Not deployed | — | — |
| `OP-RANZ` | Australia & New Zealand | Oracle | Not deployed | — | — |
| `AZ-NA` | North America | Azure | Not deployed | — | — |
| `AWS-NA` | North America | AWS | Not deployed | — | — |
| `EC-NA` | North America | European Cloud | Not deployed | — | — |
| `OP-NA` | North America | Oracle | Not deployed | — | — |
| `AZ-SA` | South America | Azure | Not deployed | — | — |
| `AWS-SA` | South America | AWS | Not deployed | — | — |
| `EC-SA` | South America | European Cloud | Not deployed | — | — |
| `OP-SA` | South America | Oracle | Not deployed | — | — |
| `DEV-LOCAL` | N/A | Kind (local) | Planned | — | 0.1.0 |
| `TEST-REMOTE` | N/A | Kind (Debian) | Planned | — | 0.1.0 |

## Rollout process

1. **Build**: CI builds `dq-api`, `dq-engine`, `dq-ui` images with pinned tag
2. **Publish**: Images pushed to shared registry
3. **Update config**: `platform-argocd-apps/environments/<env>/image-registry-config.yml` updated with new tag
4. **Update overlay**: Consumer overlay `kustomization.yml` `images:` patch updated
5. **Sync**: ArgoCD syncs the overlay to the target Kind cluster
6. **Validate**: Health checks pass, smoke tests run, MaaS registration confirmed

## Ownership

- **Rollout matrix**: Owned by `dq-made-easy` team (this document)
- **ArgoCD Applications**: Defined in `platform-argocd-apps/apps/tenants/dq/`
- **Image publishing**: Owned by `dq-made-easy` CI pipeline, consumed by platform registry
- **Platform services**: Owned by `platform-foundation` (Kong, Keycloak, observability)

## Related documents

- [Platform Kubernetes Service Design](../../platform-foundation/docs/infra/PLATFORM_KUBERNETES_SERVICE_DESIGN.md)
- [Environment and Deployment Contract](../../platform-foundation/docs/infra/LOCAL_TO_PRODUCTION_HANDBOFF_CONTRACT.md)
- [Tenant overlay (platform-argocd-apps)](../../platform-argocd-apps/apps/tenants/dq/README.md)
- [Service split](../../platform-argocd-apps/apps/tenants/dq/service-split.md)
