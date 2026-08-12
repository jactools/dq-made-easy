#!/usr/bin/env bash

runtime_profile_values() {
  printf '%s\n' \
    base \
    redis \
     spark \
    core \
    gateway \
    auth \
    engine \
    workers \
    trino \
    profiling \
    metadata \
    llm \
    support \
    observability \
    edge
}

default_runtime_profile_values() {
  printf '%s\n' \
    base \
    redis \
    core \
    gateway \
    auth \
    engine \
    workers \
    trino \
    profiling \
    metadata \
    support \
    observability \
    edge
}

is_runtime_profile() {
  case "$1" in
    base|redis|spark|core|gateway|auth|engine|workers|trino|profiling|metadata|llm|support|observability|edge)
      return 0
      ;;
    *)
      return 1
      ;;
    spark)
      return 2
      ;;
  esac
}

repo_image_values() {
  printf '%s\n' \
    dq-base \
    dq-api \
    dq-engine \
    dq-profiling \
    dq-frontend \
    dq-db \
    # Keycloak image/container lifecycle managed by platform-foundation
    dq-kong \
    dq-kafka-consumer \
    dq-edge \
    dq-db-seed \
    dq-keycloak-seed-artifacts \
    dq-openmetadata-db \
    dq-openmetadata-server \
    dq-metadata-configure \
    dq-container-metrics \
    dq-zammad-seed
}

shared_image_values() {
  printf '%s\n' \
    platform-ingestion-runner
}

core_repo_image_values() {
  printf '%s\n' \
    dq-base \
    dq-api \
    dq-engine \
    dq-profiling \
    dq-frontend \
    dq-db
    # Keycloak image/container lifecycle managed by platform-foundation
}

is_core_repo_image() {
  case "$1" in
    dq-base|dq-api|dq-engine|dq-profiling|dq-frontend|dq-db)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_repo_managed_image() {
  case "$1" in
    dq-base|dq-api|dq-engine|dq-profiling|dq-frontend|dq-db|dq-kafka|dq-kafka-consumer|dq-edge|dq-db-seed|dq-keycloak-seed-artifacts|dq-openmetadata-db|dq-openmetadata-server|dq-metadata-configure|dq-container-metrics|dq-zammad-seed)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_platform_image() {
  case "$1" in
    platform-ingestion-runner)
      return 0
      ;;
    platform-kong|platform-keycloak|platform-kafka|platform-llm|platform-trino|platform-airflow)
      return 0
      ;;
    platform-observability-loki|platform-observability-prometheus|platform-observability-grafana|platform-observability-tempo)
      return 0
      ;;
    platform-observability-container-metrics|platform-observability-otel-collector)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

image_targets_for_profile() {
  case "$1" in
    base)
      printf '%s\n' dq-base
      ;;
    core)
      printf '%s\n' dq-db dq-api dq-frontend
      ;;
    gateway)
      return 2
      ;;
    auth)
      printf '%s\n' dq-keycloak-seed-artifacts
      ;;
    engine)
      printf '%s\n' dq-engine dq-db-seed
      ;;
    workers)
      printf '%s\n' dq-engine dq-profiling
      ;;
    trino)
      return 2
      ;;
    profiling)
      printf '%s\n' dq-profiling
      ;;
    metadata)
      printf '%s\n' dq-openmetadata-db dq-openmetadata-server dq-metadata-configure
      ;;
    observability)
      printf '%s\n' dq-container-metrics
      ;;
    support)
      printf '%s\n' dq-zammad-seed
      ;;
    llm)
      return 2
      ;;
    redis|edge)
      return 2
      ;;
    *)
      return 1
      ;;
  esac
}

repo_image_env_vars() {
  case "$1" in
    dq-base)
      printf '%s\n' DQ_BASE_REGISTRY DQ_BASE_NAMESPACE DQ_BASE_IMAGE DQ_BASE_TAG
      ;;
    dq-api)
      printf '%s\n' DQ_API_REGISTRY DQ_API_NAMESPACE DQ_API_IMAGE DQ_API_TAG
      ;;
    dq-engine)
      printf '%s\n' DQ_ENGINE_REGISTRY DQ_ENGINE_NAMESPACE DQ_ENGINE_IMAGE DQ_ENGINE_TAG
      ;;
    dq-profiling)
      printf '%s\n' DQ_PROFILING_REGISTRY DQ_PROFILING_NAMESPACE DQ_PROFILING_IMAGE DQ_PROFILING_TAG
      ;;
    dq-frontend)
      printf '%s\n' DQ_FRONTEND_REGISTRY DQ_FRONTEND_NAMESPACE DQ_FRONTEND_IMAGE DQ_FRONTEND_TAG
      ;;
    dq-db)
      printf '%s\n' DQ_DB_REGISTRY DQ_DB_NAMESPACE DQ_DB_IMAGE DQ_DB_TAG
      ;;
    # Keycloak image/container lifecycle managed by platform-foundation
    # Kafka broker is managed by platform-foundation (platform-kafka).
    dq-kafka-consumer)
      printf '%s\n' DQ_KAFKA_CONSUMER_REGISTRY DQ_KAFKA_CONSUMER_NAMESPACE DQ_KAFKA_CONSUMER_IMAGE DQ_KAFKA_CONSUMER_TAG
      ;;
    # Trino image/container lifecycle managed by platform-foundation (platform-trino).
    dq-edge)
      printf '%s\n' DQ_EDGE_REGISTRY DQ_EDGE_NAMESPACE DQ_EDGE_IMAGE DQ_EDGE_TAG
      ;;
    # Airflow image/container lifecycle managed by platform-foundation (platform-airflow).
    # LLM image/container lifecycle managed by platform-foundation (platform-llm).
    dq-db-seed)
      printf '%s\n' DQ_DB_SEED_REGISTRY DQ_DB_SEED_NAMESPACE DQ_DB_SEED_IMAGE DQ_DB_SEED_TAG
      ;;
    dq-keycloak-seed-artifacts)
      printf '%s\n' DQ_KEYCLOAK_SEED_REGISTRY DQ_KEYCLOAK_SEED_NAMESPACE DQ_KEYCLOAK_SEED_IMAGE DQ_KEYCLOAK_SEED_TAG
      ;;
    dq-openmetadata-db)
      printf '%s\n' DQ_OPENMETADATA_DB_REGISTRY DQ_OPENMETADATA_DB_NAMESPACE DQ_OPENMETADATA_DB_IMAGE DQ_OPENMETADATA_DB_TAG
      ;;
    dq-openmetadata-server)
      printf '%s\n' DQ_OPENMETADATA_SERVER_REGISTRY DQ_OPENMETADATA_SERVER_NAMESPACE DQ_OPENMETADATA_SERVER_IMAGE DQ_OPENMETADATA_SERVER_TAG
      ;;
    dq-metadata-configure)
      printf '%s\n' DQ_METADATA_CONFIGURE_REGISTRY DQ_METADATA_CONFIGURE_NAMESPACE DQ_METADATA_CONFIGURE_IMAGE DQ_METADATA_CONFIGURE_TAG
      ;;
    dq-container-metrics)
      printf '%s\n' DQ_CONTAINER_METRICS_REGISTRY DQ_CONTAINER_METRICS_NAMESPACE DQ_CONTAINER_METRICS_IMAGE DQ_CONTAINER_METRICS_TAG
      ;;
    dq-zammad-seed)
      printf '%s\n' DQ_ZAMMAD_SEED_REGISTRY DQ_ZAMMAD_SEED_NAMESPACE DQ_ZAMMAD_SEED_IMAGE DQ_ZAMMAD_SEED_TAG
      ;;
    *)
      return 1
      ;;
  esac
}

platform_image_env_vars() {
  case "$1" in
    platform-ingestion-runner)
      printf '%s\n' PLATFORM_REGISTRY PLATFORM_NAMESPACE PLATFORM_INGESTION_RUNNER_IMAGE PLATFORM_SHARED_INGESTION_RUNNER_TAG
      ;;
    platform-kong)
      printf '%s\n' PLATFORM_REGISTRY PLATFORM_NAMESPACE PLATFORM_KONG_TAG
      ;;
    platform-keycloak)
      printf '%s\n' PLATFORM_REGISTRY PLATFORM_NAMESPACE PLATFORM_KEYCLOAK_TAG
      ;;
    platform-kafka)
      printf '%s\n' PLATFORM_REGISTRY PLATFORM_NAMESPACE PLATFORM_KAFKA_TAG
      ;;
    platform-llm)
      printf '%s\n' PLATFORM_REGISTRY PLATFORM_NAMESPACE PLATFORM_LLM_TAG
      ;;
    platform-trino)
      printf '%s\n' PLATFORM_REGISTRY PLATFORM_NAMESPACE PLATFORM_TRINO_TAG
      ;;
    platform-airflow)
      printf '%s\n' PLATFORM_REGISTRY PLATFORM_NAMESPACE PLATFORM_AIRFLOW_TAG
      ;;
    platform-observability-loki)
      printf '%s\n' PLATFORM_REGISTRY PLATFORM_NAMESPACE PLATFORM_OBS_LOKI_TAG
      ;;
    platform-observability-prometheus)
      printf '%s\n' PLATFORM_REGISTRY PLATFORM_NAMESPACE PLATFORM_OBS_PROMETHEUS_TAG
      ;;
    platform-observability-grafana)
      printf '%s\n' PLATFORM_REGISTRY PLATFORM_NAMESPACE PLATFORM_OBS_GRAFANA_TAG
      ;;
    platform-observability-tempo)
      printf '%s\n' PLATFORM_REGISTRY PLATFORM_NAMESPACE PLATFORM_OBS_TEMPO_TAG
      ;;
    platform-observability-container-metrics)
      printf '%s\n' PLATFORM_REGISTRY PLATFORM_NAMESPACE PLATFORM_OBS_CONTAINER_METRICS_TAG
      ;;
    platform-observability-otel-collector)
      printf '%s\n' PLATFORM_REGISTRY PLATFORM_NAMESPACE PLATFORM_OBS_OTEL_COLLECTOR_TAG
      ;;
    *)
      return 1
      ;;
  esac
}

seed_target_values() {
  printf '%s\n' postgres keycloak zammad deliveries openmetadata
}

is_seed_target() {
  case "$1" in
    postgres|keycloak|zammad|deliveries|openmetadata)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

seed_flag_for_target() {
  case "$1" in
    postgres)
      printf '%s' '--seed-postgres'
      ;;
    keycloak)
      printf '%s' '--seed-keycloak'
      ;;
    zammad)
      printf '%s' '--seed-zammad'
      ;;
    deliveries)
      printf '%s' '--seed-deliveries'
      ;;
    openmetadata)
      printf '%s' '--seed-openmetadata'
      ;;
    *)
      return 1
      ;;
  esac
}
