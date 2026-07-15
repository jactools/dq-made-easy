# dq-made-easy Kafka Consumer

Lightweight batch-style Kafka consumer image used for background processing and
event-driven tasks in the platform.

## Features

- Python-based consumer worker
- Focused on small, targeted queue processing jobs
- Designed to run as a repo-managed container image

## Quick Start

```bash
docker pull jacbeekers/dq-kafka-consumer:latest
```

## Tags

- `latest` - most recent build
- `0.11.5-<hash>` - content-addressed release tag used by the build scripts

## Usage

Run this image from the repo deployment scripts or Docker Compose profiles that
need Kafka-backed background processing.

## Documentation

Repository: [dq-made-easy](https://github.com/jacbeekers/dq-rulebuilder)