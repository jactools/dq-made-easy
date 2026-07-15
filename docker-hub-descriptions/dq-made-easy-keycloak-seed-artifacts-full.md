# dq-made-easy Keycloak Seed Artifacts

Repo-managed helper image that generates Keycloak realm seed artifacts from the
repository's source data and mock records.

## Features

- Generates importable Keycloak realm artifacts
- Uses repo-owned data generation helpers
- Supports the auth/bootstrap workflow for local and CI environments

## Quick Start

```bash
docker pull jacbeekers/dq-keycloak-seed-artifacts:latest
```

## Tags

- `latest` - most recent build
- `0.11.5-<hash>` - content-addressed release tag used by the build scripts

## Usage

Run this image as part of the authentication bootstrap flow before launching
the Keycloak service.

## Documentation

Repository: [dq-made-easy](https://github.com/jacbeekers/dq-rulebuilder)