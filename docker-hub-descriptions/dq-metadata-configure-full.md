# dq-made-easy Metadata Configure

Repo-managed helper image that configures the OpenMetadata stack at startup and
drives repo-owned metadata synchronization routines.

## Features

- Repository bootstrap and configuration entrypoint
- OpenMetadata sync helpers and local tooling
- Designed to run alongside the metadata deployment profile

## Quick Start

```bash
docker pull jacbeekers/dq-metadata-configure:latest
```

## Tags

- `latest` - most recent build
- `0.11.5-<hash>` - content-addressed release tag used by the build scripts

## Usage

Use this helper image to initialize or resynchronize the local OpenMetadata
stack after the core services are up.

## Documentation

Repository: [dq-made-easy](https://github.com/jacbeekers/dq-rulebuilder)