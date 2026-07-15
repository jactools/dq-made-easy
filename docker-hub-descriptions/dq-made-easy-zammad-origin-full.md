# dq-made-easy Zammad Origin

Repo-managed Zammad origin image that wraps the upstream Zammad container with
repository-specific TLS and entrypoint handling.

## Features

- Upstream Zammad base image with repo-owned entrypoint
- TLS certificate handoff for the origin container
- Keeps origin-specific nginx behavior in the repository

## Quick Start

```bash
docker pull jacbeekers/dq-zammad-origin:latest
```

## Tags

- `latest` - most recent build
- `0.11.5-<hash>` - content-addressed release tag used by the build scripts

## Usage

Use this image for the repo-managed Zammad origin service when deploying the
support stack.

## Documentation

Repository: [dq-made-easy](https://github.com/jacbeekers/dq-rulebuilder)