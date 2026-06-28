# Validation CI Templates

This repository publishes one canonical validation entrypoint for CI: `scripts/validate.sh`.

The GitHub Actions and Azure DevOps templates in this document call that wrapper directly so validation groups, fail-fast behavior, and test-proof output stay aligned with local operator usage.

## What the templates enforce

- Create the repo-root virtual environment instead of relying on host Python.
- Install backend development dependencies from `dq-api/fastapi` so editable local paths resolve correctly.
- Activate the pinned npm toolchain from the repo manifests.
- Optionally install `dq-ui` dependencies when a validation group needs frontend tooling.
- Fail immediately when the selected validation group, required tools, or Docker prerequisites are unavailable.
- Publish generated validation evidence from `test-results/` as a CI artifact.

## GitHub Actions reusable workflow

Template path: `.github/workflows/validation-template.yml`

Example consumer workflow:

```yaml
name: Repo Validation

on:
  pull_request:
  push:
    branches:
      - main

jobs:
  repo-validation:
    uses: ./.github/workflows/validation-template.yml
    with:
      validation_group: repo

  api-validation:
    uses: ./.github/workflows/validation-template.yml
    with:
      validation_group: api
      docker_required: true
```

Supported inputs:

| Input | Default | Purpose |
| --- | --- | --- |
| `validation_group` | `repo` | Group passed to `scripts/validate.sh`. Use `scripts/validate.sh --list` to inspect available groups. |
| `python_version` | `3.13` | Python version used to build the repo virtual environment. |
| `node_version` | `22` | Node version used when validation requires frontend tooling. |
| `install_ui_dependencies` | `false` | Run `npm install` under `dq-ui` before validation. |
| `docker_required` | `false` | Fail fast with `docker version` before the validation command. |
| `env_name` | empty | Optional `--env` value forwarded to `scripts/validate.sh`. |
| `artifact_name` | `validation-test-results` | Artifact name used for uploaded test proof and validation evidence. |

## Azure DevOps template

Template path: `azure-pipelines/templates/validation-gates.yml`

Example pipeline usage:

```yaml
trigger:
  branches:
    include:
      - main

pr:
  branches:
    include:
      - main

stages:
  - stage: Validation
    jobs:
      - job: RepoValidation
        pool:
          vmImage: ubuntu-latest
        steps:
          - template: azure-pipelines/templates/validation-gates.yml
            parameters:
              validationGroup: repo

      - job: ApiValidation
        pool:
          vmImage: ubuntu-latest
        steps:
          - template: azure-pipelines/templates/validation-gates.yml
            parameters:
              validationGroup: api
              dockerRequired: true
```

Supported parameters:

| Parameter | Default | Purpose |
| --- | --- | --- |
| `validationGroup` | `repo` | Group passed to `scripts/validate.sh`. |
| `pythonVersion` | `3.13` | Python version used to build the repo virtual environment. |
| `nodeVersion` | `22.x` | Node version used when validation requires frontend tooling. |
| `installUiDependencies` | `false` | Run `npm install` under `dq-ui` before validation. |
| `dockerRequired` | `false` | Fail fast with `docker version` before the validation command. |
| `envName` | empty | Optional `--env` value forwarded to `scripts/validate.sh`. |
| `artifactName` | `validation-test-results` | Published pipeline-artifact name for validation evidence. |

## Choosing the right validation group

- Use `repo` for repo-only contract checks that should run on most pull requests.
- Use `governance` for the governance logging, monitoring baseline, and release-policy gate set used by the governance CI workflow.
- Use `api`, `ui`, `engine`, `profiling`, `observability`, or `openmetadata` when the change specifically needs that integration surface.
- Use `regression` when you need the highest-value end-to-end validation flow.
- Use `other` only for ungrouped validation scripts while you are migrating them into tagged groups.

## Fail-fast guidance

These templates intentionally do not mask dependency or validation failures.

- Do not add `continue-on-error`, `\|\| true`, or fallback install branches around required validation steps.
- If a validation group needs Docker, set the Docker flag and let the pipeline fail when the runner cannot provide it.
- If a group needs UI dependencies, opt into `install_ui_dependencies` or `installUiDependencies` instead of letting validation scripts guess.
- Keep new validation coverage behind `scripts/validate.sh` so local runs, CI templates, and published proof stay consistent.
