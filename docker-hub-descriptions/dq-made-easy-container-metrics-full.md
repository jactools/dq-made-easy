# dq-made-easy Container Metrics

Repo-managed container metrics exporter used by the observability stack for
dashboards, alerts, and local platform inspection.

## Features

- Python-based metrics exporter
- Built for the repository observability profile
- Publishes container-level metrics for Prometheus scraping

## Quick Start

```bash
docker pull jacbeekers/dq-container-metrics:latest
```

## Tags

- `latest` - most recent build
- `0.11.5-<hash>` - content-addressed release tag used by the build scripts

## Usage

This image is intended for the observability stack and for repo-managed
deployments that want to monitor container health.

## Documentation

Repository: [dq-made-easy](https://github.com/jacbeekers/dq-rulebuilder)