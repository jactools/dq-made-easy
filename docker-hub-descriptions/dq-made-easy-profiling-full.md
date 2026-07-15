# Data Profiling Worker

Background worker service that consumes profiling jobs from Redis, performs profiling/ETL steps, and reports request lifecycle status back to the DQ API.

## Features

- Automated data profiling for tables and columns
- Statistical analysis (min, max, avg, distinct counts, NULL %)
- Pattern detection and data type inference
- Rule suggestion generation
- Redis-based job queue
- Concurrent job processing

## Quick Start

```bash
# Pull image
docker pull jacbeekers/dq-profiling:latest

# Run worker
docker run -d \
  -e DQ_API_INTERNAL_URL=http://api:4010 \
  -e REDIS_HOST=redis \
  -e PROFILING_WORKER_CONCURRENCY=2 \
  jacbeekers/dq-profiling:latest
```

## Required Services

- Redis 7+ (job queue)
- DQ API (request lifecycle reporting)

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DQ_API_INTERNAL_URL` | Internal API base URL used for profiling lifecycle callbacks | Yes |
| `REDIS_HOST` | Redis hostname | Yes |
| `REDIS_PORT` | Redis port | No (default: 6379) |
| `PROFILING_WORKER_CONCURRENCY` | Concurrent jobs | No (default: 2) |
| `NODE_ENV` | Environment mode | No |

## Profiling Capabilities

- Column-level statistics
- Data type detection
- NULL value analysis
- Uniqueness analysis
- Value distribution patterns

## Generated Rule Suggestions

- Completeness rules
- Uniqueness constraints
- Value range rules

## Tags

- `latest` - Most recent build
- `0.3.0-xxxxxxx` - Semantic version with content hash

## Part of Data Quality Made Easy Platform

Complete deployment: [GitHub Repository](https://github.com/jacbeekers/dq-rulebuilder)
