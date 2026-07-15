# dq-made-easy OpenMetadata Server

Repo-managed OpenMetadata server image that adds the OpenTelemetry Java agent
and a repository-owned HTTPS startup wrapper.

## Features

- OpenMetadata server base image
- Bundled OpenTelemetry Java agent
- Repository HTTPS startup script for native TLS

## Quick Start

```bash
docker pull jacbeekers/dq-openmetadata-server:latest
```

## Tags

- `latest` - most recent build
- `0.11.5-<hash>` - content-addressed release tag used by the build scripts

## Usage

This image is intended for the repo-managed OpenMetadata deployment profile and
the metadata bootstrap flow.

## Documentation

Repository: [dq-made-easy](https://github.com/jacbeekers/dq-rulebuilder)