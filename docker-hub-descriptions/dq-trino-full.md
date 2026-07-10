# dq-made-easy Trino

Repo-managed Trino image for federated SQL access across platform data sources
and catalog-backed analytics workflows.

## Features

- Trino 482 base image
- Used for SQL access to object stores and external connectors
- Supports the repo-managed query-engine deployment profile

## Quick Start

```bash
docker pull jacbeekers/dq-trino:latest
```

## Tags

- `latest` - most recent build
- `0.11.5-<hash>` - content-addressed release tag used by the build scripts

## Usage

This image is intended for the repo-managed Trino service and its Kubernetes or
Compose deployments.

## Documentation

Repository: [dq-made-easy](https://github.com/jacbeekers/dq-rulebuilder)