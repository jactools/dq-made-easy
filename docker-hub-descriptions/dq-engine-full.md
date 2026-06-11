# Data Quality Rules Engine

Python-based rule translation service for dq-made-easy. It exposes compile-time Great Expectations translation, while Spark execution and run reporting are handled by the `dq-engine-gx-worker` runtime.

## Features

- Rule translation from JSON to Great Expectations expectations
- `POST /compile` translation endpoint
- `GET /health` and `GET /readiness` management endpoints
- FastAPI-based management interface

## Quick Start

```bash
# Pull image
docker pull jacbeekers/dq-engine:latest

# Run engine
docker run -d \
  -p 8000:8000 \
  -e DQ_LOG_LEVEL=INFO \
  jacbeekers/dq-engine:latest
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DQ_LOG_LEVEL` | Python logging level | No (default: INFO) |

## Exposed Ports

- **8000** - HTTP management interface

## Supported Rule Types

- ✅ Completeness checks (NULL/NOT NULL)
- ✅ Uniqueness checks (duplicate detection)
- ✅ Value range validation
- ✅ Pattern matching (regex)
- ✅ Custom SQL expressions

## Tags

- `latest` - Most recent build
- `0.3.0-xxxxxxx` - Semantic version with content hash

## Part of Data Quality Made Easy Platform

Complete deployment: [GitHub Repository](https://github.com/jacbeekers/dq-rulebuilder)
