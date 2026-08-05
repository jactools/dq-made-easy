# MaaS Target Rollout Matrix for `dq-made-easy`

**Date**: 2026-08-05  
**Status**: Complete

## Purpose

This document is the repo-local source of truth for where `dq-made-easy` services run, how they are named, and whether they register with MaaS.

It reflects the shared target matrix from `platform-foundation`, but the authoritative rollout details live here in the `dq-made-easy` repository.

## Scope

- all 16 MaaS target combinations from `docs/targets.md`
- the `dq-made-easy` UI
- the `dq-made-easy` API
- DQ/ETL jobs executed as Kubernetes jobs or pods
- internal-only exposure for the UI
- MaaS registration for long-lived services only

## Service contract

| Service | Workload kind | Exposure | MaaS registration | Instance naming |
|---|---|---|---|---|
| `dq-made-easy-ui` | service | internal-only ingress / internal load balancer | yes | `dq-made-easy-ui-<target_id>-<replica_index>` |
| `dq-made-easy-api` | service | internal service-to-service only | yes | `dq-made-easy-api-<target_id>-<replica_index>` |
| `dq-made-easy-dq-job` | job | no ingress | no | `dq-made-easy-dq-job-<target_id>-<run_id>` |

## Target rollout matrix

Namespace naming uses the lowercase target id suffix, for example `dq-made-easy-az-eu` and `dq-made-easy-op-na`.

| Target | Namespace | `dq-made-easy-ui` | `dq-made-easy-api` | `dq-made-easy-dq-job` |
|---|---|---|---|---|
| Europe / AZ-EU | `dq-made-easy-az-eu` | internal-only / registered / `dq-made-easy-ui-AZ-EU-<replica_index>` | internal-only / registered / `dq-made-easy-api-AZ-EU-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-AZ-EU-<run_id>` |
| Europe / AWS-EU | `dq-made-easy-aws-eu` | internal-only / registered / `dq-made-easy-ui-AWS-EU-<replica_index>` | internal-only / registered / `dq-made-easy-api-AWS-EU-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-AWS-EU-<run_id>` |
| Europe / EC-EU | `dq-made-easy-ec-eu` | internal-only / registered / `dq-made-easy-ui-EC-EU-<replica_index>` | internal-only / registered / `dq-made-easy-api-EC-EU-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-EC-EU-<run_id>` |
| Europe / OP-EU | `dq-made-easy-op-eu` | internal-only / registered / `dq-made-easy-ui-OP-EU-<replica_index>` | internal-only / registered / `dq-made-easy-api-OP-EU-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-OP-EU-<run_id>` |
| Australia & New Zealand / AZ-RANZ | `dq-made-easy-az-ranz` | internal-only / registered / `dq-made-easy-ui-AZ-RANZ-<replica_index>` | internal-only / registered / `dq-made-easy-api-AZ-RANZ-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-AZ-RANZ-<run_id>` |
| Australia & New Zealand / AWS-RANZ | `dq-made-easy-aws-ranz` | internal-only / registered / `dq-made-easy-ui-AWS-RANZ-<replica_index>` | internal-only / registered / `dq-made-easy-api-AWS-RANZ-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-AWS-RANZ-<run_id>` |
| Australia & New Zealand / EC-RANZ | `dq-made-easy-ec-ranz` | internal-only / registered / `dq-made-easy-ui-EC-RANZ-<replica_index>` | internal-only / registered / `dq-made-easy-api-EC-RANZ-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-EC-RANZ-<run_id>` |
| Australia & New Zealand / OP-RANZ | `dq-made-easy-op-ranz` | internal-only / registered / `dq-made-easy-ui-OP-RANZ-<replica_index>` | internal-only / registered / `dq-made-easy-api-OP-RANZ-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-OP-RANZ-<run_id>` |
| North America / AZ-NA | `dq-made-easy-az-na` | internal-only / registered / `dq-made-easy-ui-AZ-NA-<replica_index>` | internal-only / registered / `dq-made-easy-api-AZ-NA-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-AZ-NA-<run_id>` |
| North America / AWS-NA | `dq-made-easy-aws-na` | internal-only / registered / `dq-made-easy-ui-AWS-NA-<replica_index>` | internal-only / registered / `dq-made-easy-api-AWS-NA-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-AWS-NA-<run_id>` |
| North America / EC-NA | `dq-made-easy-ec-na` | internal-only / registered / `dq-made-easy-ui-EC-NA-<replica_index>` | internal-only / registered / `dq-made-easy-api-EC-NA-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-EC-NA-<run_id>` |
| North America / OP-NA | `dq-made-easy-op-na` | internal-only / registered / `dq-made-easy-ui-OP-NA-<replica_index>` | internal-only / registered / `dq-made-easy-api-OP-NA-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-OP-NA-<run_id>` |
| South America / AZ-SA | `dq-made-easy-az-sa` | internal-only / registered / `dq-made-easy-ui-AZ-SA-<replica_index>` | internal-only / registered / `dq-made-easy-api-AZ-SA-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-AZ-SA-<run_id>` |
| South America / AWS-SA | `dq-made-easy-aws-sa` | internal-only / registered / `dq-made-easy-ui-AWS-SA-<replica_index>` | internal-only / registered / `dq-made-easy-api-AWS-SA-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-AWS-SA-<run_id>` |
| South America / EC-SA | `dq-made-easy-ec-sa` | internal-only / registered / `dq-made-easy-ui-EC-SA-<replica_index>` | internal-only / registered / `dq-made-easy-api-EC-SA-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-EC-SA-<run_id>` |
| South America / OP-SA | `dq-made-easy-op-sa` | internal-only / registered / `dq-made-easy-ui-OP-SA-<replica_index>` | internal-only / registered / `dq-made-easy-api-OP-SA-<replica_index>` | job only / unregistered / `dq-made-easy-dq-job-OP-SA-<run_id>` |

## Notes

- The UI must remain internal-only; no public edge exposure is permitted for the target rollout contract.
- Long-lived service instances register with MaaS on start and de-register on stop or completion.
- ETL and DQ jobs are deliberately excluded from MaaS registration.
- If a future deployment adds more long-lived services, extend this document in the repo that owns the workload.
