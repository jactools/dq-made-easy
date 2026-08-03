#!/usr/bin/env bash
###
# Name: populate_spark_jar_cache.sh
# Description: Pre-populate tmp/spark-jars-cache/ so dq-engine builds
#              do not depend on external Maven/Debian network access.
# Usage: ./scripts/populate_spark_jar_cache.sh
###

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CACHE_DIR="$REPO_ROOT/tmp/spark-jars-cache"

echo "========================================"
echo "Populating Spark jar cache"
echo "========================================"
echo "Cache directory: $CACHE_DIR"
echo "========================================"
echo ""

mkdir -p "$CACHE_DIR"

# Run the warmup script with --cache-dir to populate the cache.
# This requires network access (Maven Central or Nexus) and a working
# Java runtime, but only needs to be done once per package version change.
python scripts/warmup_spark_jars.py \
    --ivy-dir /tmp/dq-ivy2-cache \
    --jar-dir "$CACHE_DIR" \
    --cache-dir "$CACHE_DIR" \
    --packages "org.apache.spark:spark-avro_2.13:4.1.1,org.apache.hadoop:hadoop-aws:3.4.2,io.delta:delta-spark_2.13:4.1.0,org.apache.iceberg:iceberg-spark-runtime-4.0_2.13:1.10.1"

echo ""
echo "========================================"
echo "Spark jar cache populated successfully"
echo "========================================"
echo ""
echo "Cached jars:"
ls -lh "$CACHE_DIR"/*.jar 2>/dev/null || echo "(no jars found)"
echo ""
echo "Version marker:"
cat "$CACHE_DIR"/.spark-jars-version 2>/dev/null || echo "(no version marker)"
echo ""
