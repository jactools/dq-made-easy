# dq-made-easy OpenMetadata DB

Repo-managed PostgreSQL image used by the OpenMetadata stack. It carries the
repo-owned extension bootstrap so the metadata services can initialize cleanly.

## Features

- PostgreSQL 18 base image
- Repository extensions wired into the init flow
- Shared database for the OpenMetadata deployment profile

## Quick Start

```bash
docker pull jacbeekers/dq-openmetadata-db:latest
```

## Tags

- `latest` - most recent build
- `0.11.5-<hash>` - content-addressed release tag used by the build scripts

## Usage

Use this image together with the OpenMetadata server image and the metadata
configuration helper in the repo-managed metadata profile.

## Documentation

Repository: [dq-made-easy](https://github.com/jacbeekers/dq-rulebuilder)