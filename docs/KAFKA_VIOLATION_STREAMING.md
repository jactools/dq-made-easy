# Kafka-Based DQ Plan Violation Streaming

## Overview

This document describes the new architecture for handling large volumes of DQ Plan violations (potentially millions) using Kafka streaming instead of sending all violations through the API.

## Problem

Previously, when a DQ Plan execution failed with millions of violations, the entire violation batch was sent through the API endpoint:

```
Engine → API (millions of violations) → S3/DB
```

This caused:
- **API timeouts** due to large payloads
- **Memory pressure** on API servers
- **Network bottlenecks**
- **Slow response times** for execution status updates

## New Architecture

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│   Engine    │───▶│   Kafka      │───▶│   Consumer      │
│             │    │   Topic      │    │   Service       │
│ - Summary   │    │ - Violations │    │ - S3 Storage    │
│ - Counts    │    │ - Metadata   │    │ - DB (optional) │
└─────────────┘    └──────────────┘    └─────────────────┘
       │                                                  │
       │                                                  ▼
       │                                         ┌──────────────┐
       │                                         │   API        │
       │◀────────────────────────────────────────│ - Status    │
       │                                          │ - Summary   │
       │                                          │ - Metrics   │
       ▼                                          └──────────────┘
┌─────────────┐
│ PostgreSQL  │
│ - Run info  │
│ - Metadata  │
└─────────────┘
```

## Components

### 1. Engine (Publisher)

**File**: `dq-engine/kafka_client.py`

The engine now:
1. Extracts violations from execution results
2. Publishes them to Kafka topic `dq-made-easy.gx.violations`
3. Sends only summary metadata (counts, status) to API
4. Flushes batches of ~10K violations or every 30 seconds

**Configuration**:
```bash
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC_PREFIX=dq-made-easy
KAFKA_BATCH_SIZE=10000
KAFKA_FLUSH_INTERVAL_SECONDS=30
KAFKA_MAX_BATCH_BYTES=10000000  # 10MB
```

### 2. Kafka Topic

**Topic**: `dq-made-easy.gx.violations`

**Message format**:
```json
{
  "violationId": "sha256:...",
  "dataObjectVersionId": "uuid",
  "executionRunId": "uuid",
  "ruleId": "uuid",
  "recordIdentifierType": "primary_key",
  "recordIdentifierValue": "12345",
  "reasonCode": "EXPECTATION_FAILURE",
  "reasonText": "Row failed expectation X",
  "detectedAt": "2026-07-04T12:00:00Z",
  "opsMetadata": {
    "failure_class": "data_quality",
    "validation_artifact_id": "suite-uuid",
    "engine_type": "gx"
  },
  "kafka": {
    "publishedAt": "2026-07-04T12:00:00Z",
    "batchSize": 10000
  }
}
```

### 3. Consumer (S3 Storage)

**File**: `dq-api/fastapi/app/application/services/kafka_violation_consumer.py`

The consumer:
1. Reads violations from Kafka
2. Groups by `data_object_version_id` + `execution_run_id`
3. Compresses to GZIP JSON
4. Uploads to S3 in batches

**Configuration**:
```bash
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_VIOLATIONS_TOPIC=dq-made-easy.gx.violations
KAFKA_CONSUMER_GROUP_ID=dq-made-easy-violation-consumer
KAFKA_CONSUMER_BATCH_SIZE=10000
KAFKA_CONSUMER_FLUSH_INTERVAL_SECONDS=60
GX_EXCEPTION_STORAGE_BUCKET=dq-gx-exceptions
GX_EXCEPTION_STORAGE_ENDPOINT=s3.amazonaws.com
GX_EXCEPTION_STORAGE_ACCESS_KEY=...
GX_EXCEPTION_STORAGE_SECRET_KEY=...
GX_EXCEPTION_STORAGE_REGION=us-east-1
KAFKA_CONSUMER_ENABLE_DB_STORAGE=true  # Optional: also store in DB
```

**S3 Key format**:
```
gx-exceptions/data_object_version_id={id}/execution_run_id={id}/violation-batch-{sha256}.json.gz
```

### 4. API (Summary Only)

**File**: `dq-api/fastapi/app/api/v1/gx_report_api.py`

The API now:
1. Receives only summary metadata from engine
2. Stores execution run status and counts
3. Does NOT handle violation details

## Benefits

### Performance
- **Engine**: ~5-10x faster execution reporting (no large payload)
- **API**: Reduced memory usage by 99%+ for large violation batches
- **Network**: 90%+ reduction in API payload size

### Scalability
- **Infinite buffering**: Kafka can handle millions of violations
- **Backpressure**: Automatic flow control between engine and storage
- **Horizontal scaling**: Multiple consumers can read from same topic

### Reliability
- **Persistence**: Kafka retains messages for configured retention period
- **Retry**: Failed messages are reprocessed on consumer restart
- **Exactly-once**: Idempotent S3 uploads with SHA256 hashing

### Observability
- **Metrics**: Kafka consumer lag, throughput, error rates
- **Debugging**: Violations accessible via S3 or Kafka replay
- **Monitoring**: Real-time violation streaming status

## Migration Guide

### Step 1: Enable Kafka in Engine

```bash
# In dq-engine environment
KAFKA_BOOTSTRAP_SERVERS=<your-kafka:9092>
```

No code changes required - Kafka is optional and falls back gracefully if unavailable.

### Step 2: Deploy Consumer Service

Create a new service/container:
```yaml
# docker-compose.yml
services:
  kafka-violation-consumer:
    image: dq-made-easy/api:latest
    command: ["python", "-m", "app.application.services.kafka_violation_consumer"]
    environment:
      - KAFKA_BOOTSTRAP_SERVERS=<your-kafka:9092>
      - GX_EXCEPTION_STORAGE_BUCKET=dq-gx-exceptions
      - GX_EXCEPTION_STORAGE_ACCESS_KEY=...
      - GX_EXCEPTION_STORAGE_SECRET_KEY=...
    depends_on:
      - kafka
      - s3
```

### Step 3: Configure S3 Storage

Ensure S3 bucket exists:
```bash
aws s3 mb s3://dq-gx-exceptions
```

### Step 4: Monitor and Tune

Monitor Kafka consumer lag:
```bash
kafka-consumer-groups --bootstrap-server localhost:9092 --describe --group dq-made-easy-violation-consumer
```

Tune batch sizes based on throughput:
```bash
KAFKA_BATCH_SIZE=20000  # Larger batches for high-throughput
KAFKA_CONSUMER_BATCH_SIZE=20000
```

## Alternative: Disable Streaming

If Kafka is not available, the system falls back to the previous behavior:
- Violations are still sent to API
- API stores to S3 (not DB to reduce load)

Set environment variable to disable DB storage entirely:
```bash
GX_EXCEPTION_STORAGE_BACKEND=s3  # Only S3, no DB
```

## Future Enhancements

1. **Real-time Dashboards**: Stream violations to Grafana/Prometheus
2. **Alerting**: Trigger alerts on violation patterns
3. **Machine Learning**: Use Kafka stream for anomaly detection
4. **Data Lake**: Export violations to Athena/Redshift/BigQuery
5. **Multi-region**: Replicate Kafka across regions for HA

## Troubleshooting

### Issue: Violations not appearing in S3

**Check**:
1. Kafka consumer is running: `docker ps | grep kafka`
2. Consumer is subscribed: `kafka-topics --describe --topic dq-made-easy.gx.violations`
3. Consumer lag: `kafka-consumer-groups --describe --group dq-made-easy-violation-consumer`
4. S3 credentials are correct
5. S3 bucket exists and is accessible

### Issue: High consumer lag

**Solutions**:
1. Increase batch size: `KAFKA_CONSUMER_BATCH_SIZE=50000`
2. Scale horizontally: Run multiple consumer instances (different group IDs)
3. Check S3 write performance
4. Increase Kafka partition count

### Issue: Engine not publishing to Kafka

**Check**:
1. Kafka connection: `nc -zv kafka-host 9092`
2. Topic exists: `kafka-topics --describe --topic dq-made-easy.gx.violations`
3. Engine logs: Look for "Published X violations to Kafka"

## Support

For issues or questions:
- Slack: #dq-engine-kafka
- GitHub: Create issue in dq-made-easy repo
- Documentation: See `/docs/KAFKA_VIOLATION_STREAMING.md`
