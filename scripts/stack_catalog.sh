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
    profiling \
    metadata \
    support \
    observability \
    edge
}

is_runtime_profile() {
  case "$1" in
     base|redis|spark|core|gateway|auth|engine|workers|profiling|metadata|llm|support|observability|edge)
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
    dq-kong \
    dq-db \
    dq-keycloak \
    dq-llm \
    dq-db-seed \
    dq-keycloak-seed-artifacts \
    dq-openmetadata-db \
    dq-openmetadata-server \
    dq-metadata-configure \
    dq-container-metrics \
    dq-zammad-seed
}

core_repo_image_values() {
  printf '%s\n' \
    dq-base \
    dq-api \
    dq-engine \
    dq-profiling \
    dq-frontend \
    dq-kong \
    dq-db \
    dq-keycloak
}

is_core_repo_image() {
  case "$1" in
    dq-base|dq-api|dq-engine|dq-profiling|dq-frontend|dq-kong|dq-db|dq-keycloak)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_repo_managed_image() {
  case "$1" in
    dq-base|dq-api|dq-engine|dq-profiling|dq-frontend|dq-kong|dq-db|dq-keycloak|dq-llm|dq-db-seed|dq-keycloak-seed-artifacts|dq-openmetadata-db|dq-openmetadata-server|dq-metadata-configure|dq-container-metrics|dq-zammad-seed)
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
      printf '%s\n' dq-kong
      ;;
    auth)
      printf '%s\n' dq-keycloak dq-keycloak-seed-artifacts
      ;;
    engine)
      printf '%s\n' dq-engine dq-db-seed
      ;;
    workers)
      printf '%s\n' dq-engine dq-profiling
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
    dq-kong)
      printf '%s\n' DQ_KONG_REGISTRY DQ_KONG_NAMESPACE DQ_KONG_IMAGE DQ_KONG_TAG
      ;;
    dq-db)
      printf '%s\n' DQ_DB_REGISTRY DQ_DB_NAMESPACE DQ_DB_IMAGE DQ_DB_TAG
      ;;
    dq-keycloak)
      printf '%s\n' DQ_KEYCLOAK_REGISTRY DQ_KEYCLOAK_NAMESPACE DQ_KEYCLOAK_IMAGE DQ_KEYCLOAK_TAG
      ;;
    dq-llm)
      printf '%s\n' DQ_LLM_REGISTRY DQ_LLM_NAMESPACE DQ_LLM_IMAGE DQ_LLM_TAG
      ;;
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
