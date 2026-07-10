# dq-made-easy Airflow

Repo-managed Apache Airflow image used for orchestration jobs, DAG execution,
and validation run-plan workflows.

## Features

- Apache Airflow 3.2.2 base image
- Bundled dq-made-easy SDK and operator wheels
- Includes repo-owned DAG artifacts at build time

## Quick Start

```bash
docker pull jacbeekers/dq-airflow:latest
```

## Tags

- `latest` - most recent build
- `0.11.5-<hash>` - content-addressed release tag used by the build scripts

## Usage

Use this image for the repo-managed Airflow deployment profile or for local
validation of orchestration workflows.

## Documentation

Repository: [dq-made-easy](https://github.com/jacbeekers/dq-rulebuilder)