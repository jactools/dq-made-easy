# DQ Trino Catalog Configs

Trino image/container lifecycle managed by platform-foundation (`platform-trino`).

This directory contains DQ-specific catalog configurations deployed to the platform Trino instance via the Trino CLI.

## Deploying

```bash
# Deploy aistor connector catalog
trino catalog create \
  --server https://trino.jac.dot:8080 \
  --file etc/catalog/aistor.properties \
  aistor
```

## Files

- `etc/catalog/aistor.properties` — Aistor (MinIO) connector with Hive metastore
