# DQ Kafka

Kafka image/container lifecycle managed by platform-foundation (`platform-kafka`).

This directory is retained only for reference. All Kafka broker configuration has been migrated to:
- `platform-foundation/docker/kafka/Dockerfile.kafka`
- `platform-foundation/docker/kafka/start-kafka.sh`
- `platform-foundation/docker-compose/messaging.yml`

Consumer repos provision topics/config via kafka-topics.sh (no mounts).
