# dq-made-easy Edge

Repo-owned edge ingress image that renders Nginx configuration from environment
variables and keeps the edge-specific TLS handling inside the repository.

## Features

- Nginx-based edge service image
- Runtime config renderer for the edge ingress
- Placeholder certificate support for fail-fast mount validation

## Quick Start

```bash
docker pull jacbeekers/dq-edge:latest
```

## Tags

- `latest` - most recent build
- `0.11.5-<hash>` - content-addressed release tag used by the build scripts

## Usage

This image is the repo-managed ingress front door and is normally launched
through the edge Compose or deployment profiles.

## Documentation

Repository: [dq-made-easy](https://github.com/jacbeekers/dq-rulebuilder)