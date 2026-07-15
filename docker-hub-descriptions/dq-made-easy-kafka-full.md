# dq-made-easy Kafka Broker

Repo-managed Kafka broker image used for event streaming, async workflows, and
violation/event pipelines in the Data Quality Made Easy stack.

## Features

- Apache Kafka 3.9.1 base image
- Repo-owned startup script and configuration hooks
- Used by the platform event profiles and integration flows

## Quick Start

```bash
docker pull jacbeekers/dq-kafka:latest
```

## Tags

- `latest` - most recent build
- `0.11.5-<hash>` - content-addressed release tag used by the build scripts

## Usage

This image is typically started through Docker Compose or the repo-managed
deployment scripts rather than run directly.

## Documentation

Repository: [dq-made-easy](https://github.com/jacbeekers/dq-rulebuilder)