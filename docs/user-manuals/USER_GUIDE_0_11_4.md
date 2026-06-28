# 0.11.4 User Guide

This guide summarizes the user-facing changes in the 0.11.4 release line and points readers to the right documentation for day-to-day use.

## What changed in 0.11.4

### Documentation and release alignment

- The public documentation portal and release pointers now consistently reference the 0.11.4 release line.
- The release notes and release indexes have been refreshed so current release information is easier to find.
- The docs build has been verified so the published docs remain navigable and link-safe.

### Validation evidence and proof artifacts

- The test-proof section now includes the latest Spark Expectations execution evidence.
- Users and operators can inspect proof pages for dispatching, error handling, and real-data validation outcomes.
- The implementation and feature docs now reference the new proof artifacts and runtime plans.

### Pipeline integration guidance

- A new DQ CLI pipeline integration guide explains how to trigger validation runs from orchestration systems such as Databricks, Kubernetes jobs, and Azure Container Apps jobs.
- The guide focuses on the intended flow: the orchestrator triggers the CLI, the CLI invokes the DQ run plan, and the engine executes the validation workload.

## Where to go next

- Review the release notes in [docs/releases/RELEASE_0_11_4_VERSION_ALIGNMENT_AND_DOC_REFRESH.md](../releases/RELEASE_0_11_4_VERSION_ALIGNMENT_AND_DOC_REFRESH.md).
- Browse the latest proof pages in [docs/test-proof/index.md](../test-proof/index.md).
- Follow the DQ CLI integration workflow in [docs/user-manuals/USER_GUIDE_DQ_CLI_PIPELINE_INTEGRATION.md](./USER_GUIDE_DQ_CLI_PIPELINE_INTEGRATION.md).
- Read the broader implementation summary in [docs/implementation-details/SPARK_EXPECTATIONS_ENGINE_PLAN.md](../implementation-details/SPARK_EXPECTATIONS_ENGINE_PLAN.md).

## Recommended audience

- Platform operators who need to understand the latest validation evidence and release surface
- Developers who want to trigger DQ validations from pipelines and CI/CD workflows
- Admins and product owners who want a concise summary of the 0.11.4 documentation refresh
