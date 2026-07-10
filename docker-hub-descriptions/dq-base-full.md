# DQ Base Image

Foundation image for repo-managed Node.js workloads in Data Quality Made Easy.
It provides the shared build environment used by the base package and the images
that need a consistent Node.js toolchain.

## Features

- Node.js runtime with common build tooling
- Lightweight Debian-based foundation
- Shared parent for repo-managed Node.js services

## Quick Start

```bash
docker pull jacbeekers/dq-base:latest
```

## Tags

- `latest` - most recent build
- `0.11.5-<hash>` - content-addressed release tag used by the build scripts

## Usage

Use this image as a parent in `FROM` statements or as the base for local build
pipelines that need the same runtime and tooling as the project services.

## Documentation

Repository: [dq-made-easy](https://github.com/jacbeekers/dq-rulebuilder)