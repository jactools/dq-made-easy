#!/usr/bin/env bash
set -euo pipefail

# Purpose: Calculate content-hash version tags from VERSION_MANIFEST.json.
#
# What it does:
# - Reads major.minor from VERSION_MANIFEST.json (apps.ui) unless overridden.
# - Computes short content hashes from actual Docker build inputs per image.
# - Supports both core image tags and auxiliary repo-managed image tags.
# - Supports a display mode to print the resolved tags.
#
# Version: 1.1
# Last modified: 2026-04-26

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_ENV_FILE="${ROOT_ENV_FILE:-$ROOT_DIR/.env.dev.local}"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="calculate_versions.sh"

VERSION_MANIFEST_PATH="$ROOT_DIR/VERSION_MANIFEST.json"

if [ -f "$ROOT_ENV_FILE" ]; then
    set -a
    source "$ROOT_ENV_FILE"
    set +a
fi

read_major_minor_from_manifest() {
    if [ ! -f "$VERSION_MANIFEST_PATH" ]; then
        error "$my_name" "VERSION_MANIFEST.json not found at $VERSION_MANIFEST_PATH"
        return 1
    fi

    node -e '
const fs = require("fs")
const filePath = process.argv[1]
const payload = JSON.parse(fs.readFileSync(filePath, "utf8"))
const uiVersion = String(payload?.apps?.ui || "").trim()
if (!uiVersion) {
  process.exit(2)
}
const parts = uiVersion.split(".")
if (parts.length < 2 || !parts[0] || !parts[1]) {
  process.exit(3)
}
process.stdout.write(`${parts[0]}.${parts[1]}`)
' "$VERSION_MANIFEST_PATH"
}

hash_file() {
    local file_path="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$file_path" | awk '{print $1}'
    else
        shasum -a 256 "$file_path" | awk '{print $1}'
    fi
}

hash_stream() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum | awk '{print $1}' | cut -c1-7
    else
        shasum -a 256 | awk '{print $1}' | cut -c1-7
    fi
}

append_input_files() {
    local list_file="$1"
    local input=""
    local abs_path=""

    shift

    for input in "$@"; do
        abs_path="$ROOT_DIR/$input"
        if [ -d "$abs_path" ]; then
            find "$abs_path" \
                \( -path '*/__pycache__' -o -path '*/.pytest_cache' -o -path '*/.mypy_cache' -o -path '*/.ruff_cache' -o -path '*/venv' -o -path '*/.venv' -o -path '*/node_modules' \) -prune \
                -o -type f -print >> "$list_file"
        elif [ -f "$abs_path" ]; then
            printf '%s\n' "$abs_path" >> "$list_file"
        else
            printf 'missing:%s\n' "$input"
        fi
    done
}

print_hashed_inputs() {
    local input_list
    local entry=""
    local file_hash=""
    local file_path=""
    local rel_path=""

    input_list="$(mktemp)"
    append_input_files "$input_list" "$@"

    if [ -s "$input_list" ]; then
        LC_ALL=C sort -u "$input_list" -o "$input_list"

        if command -v sha256sum >/dev/null 2>&1; then
            while IFS=' ' read -r file_hash file_path; do
                rel_path="${file_path#$ROOT_DIR/}"
                printf 'file:%s:%s\n' "$rel_path" "$file_hash"
            done < <(tr '\n' '\0' < "$input_list" | xargs -0 sha256sum)
        else
            while IFS=' ' read -r file_hash file_path; do
                rel_path="${file_path#$ROOT_DIR/}"
                printf 'file:%s:%s\n' "$rel_path" "$file_hash"
            done < <(tr '\n' '\0' < "$input_list" | xargs -0 shasum -a 256)
        fi
    fi

    rm -f "$input_list"
}

calculate_image_hash() {
    local env_keys="$1"
    shift

    {
        if [ -n "$env_keys" ]; then
            local key=""
            for key in $env_keys; do
                printf 'env:%s=%s\n' "$key" "${!key-}"
            done
        fi
        print_hashed_inputs "$@"
    } | hash_stream
}

MAJOR_MINOR="${MAJOR_MINOR_OVERRIDE:-}"
if [ -z "$MAJOR_MINOR" ]; then
    MAJOR_MINOR=$(read_major_minor_from_manifest) || {
        error "$my_name" "Unable to read major.minor version from VERSION_MANIFEST.json apps.ui"
        exit 1
    }
fi

if [ -z "$MAJOR_MINOR" ]; then
    error "$my_name" "Resolved major.minor version is empty"
    exit 1
fi

info "$my_name" "Calculating version tags from Docker build inputs (major.minor: $MAJOR_MINOR)..."

content_hash_base="$(calculate_image_hash \
    "NODE_REGISTRY NODE_NAMESPACE NODE_IMAGE NODE_TAG APK_REPOSITORIES" \
    dq-base/Dockerfile.base
)"
export DQ_BASE_TAG="${MAJOR_MINOR}-${content_hash_base}"

content_hash_api="$(calculate_image_hash \
    "DQ_BASE_REGISTRY DQ_BASE_NAMESPACE DQ_BASE_IMAGE DQ_BASE_TAG" \
    .dockerignore \
    dq-api/Dockerfile.fastapi \
    dq-utils \
    dq-domain-validation \
    dq-api/fastapi \
    docs/contracts/internal-api \
    data_sources/contracts \
    scripts
)"
export DQ_API_TAG="${MAJOR_MINOR}-${content_hash_api}"

content_hash_engine="$(calculate_image_hash \
    "" \
    .dockerignore \
    dq-engine/Dockerfile.engine \
    dq-engine \
    dq-utils \
    scripts \
    dq-db/mock-data
)"
export DQ_ENGINE_TAG="${MAJOR_MINOR}-${content_hash_engine}"

content_hash_profiling="$(calculate_image_hash \
    "" \
    dq-profiling/Dockerfile.profiling \
    dq-profiling/python
)"
export DQ_PROFILING_TAG="${MAJOR_MINOR}-${content_hash_profiling}"

content_hash_ui="$(calculate_image_hash \
    "NGINX_REGISTRY NGINX_NAMESPACE NGINX_IMAGE NGINX_TAG" \
    dq-ui/.dockerignore \
    dq-ui/Dockerfile.frontend \
    dq-ui/dist \
    dq-ui/nginx \
    dq-ui/scripts/docker-entrypoint-runtime-config.sh
)"
export DQ_FRONTEND_TAG="${MAJOR_MINOR}-${content_hash_ui}"

content_hash_kong="$(calculate_image_hash \
    "" \
    dq-kong/Dockerfile.kong \
    dq-kong/scripts
)"
export DQ_KONG_TAG="${MAJOR_MINOR}-${content_hash_kong}"

content_hash_db="$(calculate_image_hash \
    "" \
    dq-db/Dockerfile.db \
    dq-db/init \
    dq-db/mock-data \
    dq-db/scripts
)"
export DQ_DB_TAG="${MAJOR_MINOR}-${content_hash_db}"

content_hash_keycloak="$(calculate_image_hash \
    "" \
    dq-keycloak/Dockerfile.keycloak \
    dq-keycloak/docker-entrypoint.sh
)"
export DQ_KEYCLOAK_TAG="${MAJOR_MINOR}-${content_hash_keycloak}"

content_hash_kafka="$(calculate_image_hash \
    "" \
    dq-kafka/Dockerfile.kafka \
    dq-kafka/start-kafka.sh
)"
export DQ_KAFKA_TAG="${MAJOR_MINOR}-${content_hash_kafka}"

content_hash_kafka_consumer="$(calculate_image_hash \
    "PIP_INDEX_URL" \
    dq-kafka-consumer/Dockerfile.kafka-consumer \
    dq-kafka-consumer/kafka_consumer_worker.py \
    dq-kafka-consumer/requirements.txt
)"
export DQ_KAFKA_CONSUMER_TAG="${MAJOR_MINOR}-${content_hash_kafka_consumer}"

content_hash_trino="$(calculate_image_hash \
    "TRINO_BASE_IMAGE" \
    dq-trino/Dockerfile.trino \
    dq-trino/etc/catalog
)"
export DQ_TRINO_TAG="${MAJOR_MINOR}-${content_hash_trino}"

content_hash_edge="$(calculate_image_hash \
    "" \
    dq-edge/Dockerfile.edge \
    dq-edge/docker-entrypoint.d/40-render-edge-config.sh \
    dq-edge/placeholders
)"
export DQ_EDGE_TAG="${MAJOR_MINOR}-${content_hash_edge}"

content_hash_airflow="$(calculate_image_hash \
    "" \
    .dockerignore \
    docker/airflow/Dockerfile.airflow \
    docker/airflow/webserver_config.py \
    docker/airflow/dags \
    dq-airflow-sdk \
    dq-airflow-operator \
    dq-api/fastapi/app/airflow_sdk.py \
    dq-api/fastapi/app/airflow_operator.py \
    scripts/package-releases/build_dq_airflow_dag_artifact.sh \
    scripts/package-releases/build_dq_airflow_wheels.sh \
    scripts/package-releases/build_dq_airflow_sdk_wheel.sh \
    scripts/package-releases/build_dq_airflow_operator_wheel.sh
)"
export DQ_AIRFLOW_TAG="${MAJOR_MINOR}-${content_hash_airflow}"

content_hash_db_seed="$(calculate_image_hash \
    "PIP_INDEX_URL" \
    .dockerignore \
    dq-db/Dockerfile.seed \
    dq-utils \
    dq-domain-validation \
    dq-api/fastapi/requirements.txt \
    dq-api/fastapi \
    dq-api/scripts/generate_sql_seeds.py \
    dq-api/scripts/quote_mock_data.py \
    dq-db/mock-data \
    dq-db/scripts \
    scripts/generate_external_id_patch.py \
    VERSION_MANIFEST.json \
    docs/contracts/internal-api \
    data_sources/contracts
)"
export DQ_DB_SEED_TAG="${MAJOR_MINOR}-${content_hash_db_seed}"

content_hash_keycloak_seed_artifacts="$(calculate_image_hash \
    "" \
    .dockerignore \
    dq-keycloak/Dockerfile.seed \
    dq-api/scripts/generate_keycloak_realm.py \
    dq-db/mock-data \
    dq-keycloak/scripts/generate_seed_artifacts.sh
)"
export DQ_KEYCLOAK_SEED_TAG="${MAJOR_MINOR}-${content_hash_keycloak_seed_artifacts}"

content_hash_dq_llm="$(calculate_image_hash \
    "PIP_INDEX_URL" \
    .dockerignore \
    dq-llm/Dockerfile.llm \
    dq-llm/entrypoint.py \
    dq-llm/extract_rules_prompt.jinja2 \
    dq-llm/requirements.txt \
    dq-llm/warm_cache.py
)"
export DQ_LLM_TAG="${MAJOR_MINOR}-${content_hash_dq_llm}"

content_hash_openmetadata_db="$(calculate_image_hash \
    "DOCKER_DOMAIN OPENMETADATA_DB_BASE_IMAGE" \
    .dockerignore \
    dq-metadata/Dockerfile.openmetadata-db \
    dq-db/init/00_extensions.sql
)"
export DQ_OPENMETADATA_DB_TAG="${MAJOR_MINOR}-${content_hash_openmetadata_db}"

content_hash_openmetadata_server="$(calculate_image_hash \
    "OPENMETADATA_REGISTRY OPENMETADATA_NAMESPACE OPENMETADATA_IMAGE OPENMETADATA_TAG DOCKER_DOMAIN OTEL_JAVAAGENT_VERSION OTEL_JAVAAGENT_HELPER_IMAGE" \
    .dockerignore \
    dq-metadata/Dockerfile.openmetadata-server \
    dq-metadata/scripts/openmetadata_https_start.sh
)"
export DQ_OPENMETADATA_SERVER_TAG="${MAJOR_MINOR}-${content_hash_openmetadata_server}"

content_hash_metadata_configure="$(calculate_image_hash \
    "" \
    .dockerignore \
    dq-metadata/Dockerfile.configure \
    dq-metadata/scripts \
    scripts/python_arm64.sh \
    dq-db/mock-data
)"
export DQ_METADATA_CONFIGURE_TAG="${MAJOR_MINOR}-${content_hash_metadata_configure}"

content_hash_container_metrics="$(calculate_image_hash \
    "PIP_INDEX_URL" \
    observability/container-metrics/Dockerfile.container-metrics \
    observability/container-metrics/requirements.txt \
    observability/container-metrics/container_metrics_exporter.py
)"
export DQ_CONTAINER_METRICS_TAG="${MAJOR_MINOR}-${content_hash_container_metrics}"

content_hash_zammad_seed="$(calculate_image_hash \
    "PIP_INDEX_URL" \
    .dockerignore \
    docker/Dockerfile.zammad-seed \
    dq-api/fastapi/requirements.txt \
    dq-domain-validation/pyproject.toml \
    dq-domain-validation/src \
    dq-utils/pyproject.toml \
    dq-utils/src \
    dq-api/fastapi \
    dq-api/scripts/update_support_itsm_token.py \
    dq-db/mock-data \
    scripts/generate_zammad_autowizard.py \
    scripts/generate_zammad_generated_users.py \
    scripts/run_zammad_seed_container.sh
)"
export DQ_ZAMMAD_SEED_TAG="${MAJOR_MINOR}-${content_hash_zammad_seed}"

if [ "${1:-}" = "--display" ] || [ "${1:-}" = "--show" ]; then
    info "$my_name" "========================================"
    info "$my_name" "Calculated Version Tags"
    info "$my_name" "========================================"
    info "$my_name" "Base version: $MAJOR_MINOR"
    info "$my_name" ""
    info "$my_name" "Core images:"
    info "$my_name" "DQ_BASE_TAG:                $DQ_BASE_TAG"
    info "$my_name" "DQ_API_TAG:                 $DQ_API_TAG"
    info "$my_name" "DQ_ENGINE_TAG:              $DQ_ENGINE_TAG"
    info "$my_name" "DQ_PROFILING_TAG:           $DQ_PROFILING_TAG"
    info "$my_name" "DQ_FRONTEND_TAG:            $DQ_FRONTEND_TAG"
    info "$my_name" "DQ_KONG_TAG:                $DQ_KONG_TAG"
    info "$my_name" "DQ_DB_TAG:                  $DQ_DB_TAG"
    info "$my_name" "DQ_KEYCLOAK_TAG:            $DQ_KEYCLOAK_TAG"
    info "$my_name" "DQ_KAFKA_TAG:               $DQ_KAFKA_TAG"
    info "$my_name" "DQ_KAFKA_CONSUMER_TAG:      $DQ_KAFKA_CONSUMER_TAG"
    info "$my_name" "DQ_TRINO_TAG:               $DQ_TRINO_TAG"
    info "$my_name" "DQ_EDGE_TAG:                $DQ_EDGE_TAG"
    info "$my_name" "DQ_AIRFLOW_TAG:             $DQ_AIRFLOW_TAG"
    info "$my_name" ""
    info "$my_name" "Auxiliary repo images:"
    info "$my_name" "DQ_DB_SEED_TAG:             $DQ_DB_SEED_TAG"
    info "$my_name" "DQ_KEYCLOAK_SEED_TAG:       $DQ_KEYCLOAK_SEED_TAG"
    info "$my_name" "DQ_LLM_TAG:                 $DQ_LLM_TAG"
    info "$my_name" "DQ_OPENMETADATA_DB_TAG:     $DQ_OPENMETADATA_DB_TAG"
    info "$my_name" "DQ_OPENMETADATA_SERVER_TAG: $DQ_OPENMETADATA_SERVER_TAG"
    info "$my_name" "DQ_METADATA_CONFIGURE_TAG:  $DQ_METADATA_CONFIGURE_TAG"
    info "$my_name" "DQ_CONTAINER_METRICS_TAG:   $DQ_CONTAINER_METRICS_TAG"
    info "$my_name" "DQ_ZAMMAD_SEED_TAG:         $DQ_ZAMMAD_SEED_TAG"
    info "$my_name" "========================================"
fi
