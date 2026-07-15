# dq-made-easy LLM Service

Repo-managed Python LLM inference image used for local model-backed assistance
and platform integrations that need a built-in model endpoint.

## Features

- Python 3.14-slim runtime
- Installs LLM dependencies from the project requirements set
- Exposes the service on port 8000

## Quick Start

```bash
docker pull jacbeekers/dq-llm:latest
```

## Tags

- `latest` - most recent build
- `0.11.5-<hash>` - content-addressed release tag used by the build scripts

## Usage

This image is intended for the repository LLM profile and the platform services
that call the local model endpoint.

## Documentation

Repository: [dq-made-easy](https://github.com/jacbeekers/dq-rulebuilder)