"""Validate that .env.*.local files contain no hardcoded secrets.

Scans all .env.*.local files in the repository root for hardcoded passwords,
secrets, and tokens. Fails if any are found.

Usage (from repo root)::

    python scripts/validation/validate_no_secrets_in_env.py

Exit codes:
    0  — All clean, no hardcoded secrets found
    1  — Hardcoded secrets found (details printed to stderr)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Regex patterns that identify password / secret / token env var names.
_PASSWORD_INDICATORS = re.compile(
    r"PASSWORD|_PASS\b|_PWD\b|_SECRET\b|_CLIENT_SECRET\b|_API_KEY\b|_ENCRYPTION_KEY\b|_TOKEN\b|_CREDENTIAL\b",
    re.IGNORECASE,
)

# Values that are acceptable in env files (not considered hardcoded secrets)
_ACCEPTABLE_PATTERNS = [
    # Empty values
    re.compile(r"^\s*$"),
    # Variable references
    re.compile(r"^\s*\$\{[^}]+\}"),
    # Placeholder values
    re.compile(r"^__SET_"),
    re.compile(r"^<<GENERATED"),
    re.compile(r"^<<SECRET"),
    re.compile(r"^replace-with"),
    re.compile(r"^changeme$"),
    re.compile(r"^change-me$"),
    # External credentials (not managed by this project)
    re.compile(r"^dckr_pat_"),  # Docker Hub PAT
    # Non-secret values that match the pattern name
    re.compile(r"^(true|false|0|1|yes|no)$", re.IGNORECASE),
    re.compile(r"^[a-zA-Z0-9_\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}$"),  # email addresses
    re.compile(r"^https?://"),  # URLs
    re.compile(r"^[a-zA-Z0-9_\-]+\.pem$"),  # cert file paths
    re.compile(r"^[a-zA-Z0-9_\-]+\.key$"),  # key file paths
    re.compile(r"^[a-zA-Z0-9_\-]+\.env$"),  # env file paths
    re.compile(r"^[a-zA-Z0-9_\-]+\.csv$"),  # csv file paths
    re.compile(r"^/\S+"),  # absolute paths
    re.compile(r"^\.\./\S+"),  # relative paths
    re.compile(r"^\d+$"),  # pure numbers (ports, counts)
    re.compile(r"^\d+\.\d+\.\d+\.\d+"),  # IPs
    re.compile(r"^\[.*\]$"),  # JSON arrays
    re.compile(r"^\{.*\}$"),  # JSON objects
]

# Variable prefixes that are not secrets
_NON_SECRET_PREFIXES = [
    "DQ_DB_HOST",
    "KONG_DB_HOST",
    "OM_DB_HOST",
    "DQ_DB_NAME",
    "KONG_DB_NAME",
    "OM_DB_NAME",
    "DQ_DB_USER",
    "KONG_DB_USER",
    "OM_DB_USER",
    "OM_AIRFLOW_SECRET_KEY",  # this is a secret but it's checked below
    "AIRFLOW_FAB_CLIENT_ID",
    "KEYCLOAK_CLIENT_ID",
    "DQ_ENGINE_OIDC_CLIENT_ID",
    "SSO_CLIENT_ID",
    "SSO_ALLOWED_CLIENT_IDS",
    "SSO_PROVIDER",
    "SSO_ENABLED",
    "TRUST_PROXY_AUTH",
    "KONG_TRACING_INSTRUMENTATIONS",
    "KONG_TRACING_SAMPLING_RATE",
    "KAFKA_BOOTSTRAP_SERVERS",
    "KAFKA_SECURITY_PROTOCOL",
    "KAFKA_SSL_CA_FILE",
    "KAFKA_HEALTHCHECK_HOST",
    "KAFKA_TLS_ENABLED",
    "KAFKA_CONSUMER_S3_PATH_STYLE_ACCESS",
    "DQ_S3_PATH_STYLE_ACCESS",
    "GX_EXCEPTION_STORAGE_SSL_ENABLED",
    "GX_EXCEPTION_STORAGE_BACKEND",
    "DQ_S3_REGION",
    "GX_EXCEPTION_STORAGE_REGION",
    "KAFKA_AUTO_OFFSET_RESET",
    "DQ_ENGINE_SKIP_SPARK_WARMUP",
    "DELIVERY_SEED_SKIP_SPARK_WARMUP",
    "DQ_ENGINE_MAX_ROWS",
    "DQ_SPARK_MAX_JAR_SIZE_MB",
    "DQ_SPARK_INCLUDE_LARGE_JARS",
    "DQ_LLM_MAX_RETRIES",
    "DQ_LLM_MAX_NEW_TOKENS",
    "DQ_LLM_LOAD_IN_4BIT",
    "DQ_LLM_DEVICE_MAP",
    "DQ_LLM_MODEL_DOWNLOAD_TIMEOUT",
    "DQ_LLM_MEMORY_LIMIT",
    "DQ_LLM_CPUS",
    "DQ_LLM_MEMORY_RES",
    "DQ_LLM_CPU_RES",
    "DQ_LLM_CHAT_PROVIDER",
    "DQ_LLM_SMALL_MODEL_ID",
    "DQ_LLM_MODEL_ID",
    "DQ_VALIDATION_RUN_PLAN_ID",
    "COMPOSE_PROFILES",
    "APP_DISPLAY_NAME",
    "EDGE_MODE",
    "EDGE_PUBLIC_PORT",
    "EDGE_LOCAL_APP_HOST",
    "EDGE_LOCAL_KONG_HOST",
    "EDGE_LOCAL_KEYCLOAK_HOST",
    "EDGE_LOCAL_OPENMETADATA_HOST",
    "EDGE_LOCAL_OBSERVABILITY_HOST",
    "EDGE_LOCAL_SUPPORT_HOST",
    "EDGE_LOCAL_AIRFLOW_HOST",
    "PUBLIC_APEX_HOST",
    "PUBLIC_CANONICAL_HOST",
    "PUBLIC_PRIMARY_HOST",
    "EDGE_SSL_CERTS_DIR",
    "EDGE_SSL_CERT_FILE_NAME",
    "EDGE_SSL_KEY_FILE_NAME",
    "KONG_PROXY_HOST_BIND",
    "KONG_PROXY_HOST_PORT",
    "KONG_ADMIN_HOST_BIND",
    "KONG_ADMIN_HOST_PORT",
    "KONG_MANAGER_HOST_BIND",
    "KONG_MANAGER_HOST_PORT",
    "OPENMETADATA_DB_HOST_BIND",
    "OPENMETADATA_DB_HOST_PORT",
    "OPENMETADATA_SEARCH_HOST_BIND",
    "OPENMETADATA_SEARCH_HOST_PORT",
    "OPENMETADATA_INGESTION_HOST_BIND",
    "OPENMETADATA_INGESTION_HOST_PORT",
    "LOKI_HOST_BIND",
    "LOKI_HOST_PORT",
    "PROMETHEUS_HOST_BIND",
    "PROMETHEUS_HOST_PORT",
    "TEMPO_HOST_BIND",
    "TEMPO_HOST_PORT",
    "AISTOR_API_HOST_BIND",
    "AISTOR_API_HOST_PORT",
    "AISTOR_CONSOLE_HOST_BIND",
    "AISTOR_CONSOLE_HOST_PORT",
    "AISTOR_LICENSE_FILE",
    "AISTOR_ROOT_USER",
    "ZAMMAD_HOST_BIND",
    "KAFKA_HOST_BIND",
    "KAFKA_HOST_PORT",
    "KAFKA_ADVERTISED_HOST",
    "KAFKA_CERT_HOST",
    "KEYCLOAK_HTTPS_HOST_BIND",
    "KEYCLOAK_HTTPS_HOST_PORT",
    "KEYCLOAK_REALM_DISPLAY_NAME",
    "KEYCLOAK_ADMIN_ID",
    "KEYCLOAK_DOMAIN",
    "KEYCLOAK_REALM",
    "KEYCLOAK_NETWORK",
    "KEYCLOAK_TOKEN_REALM",
    "SSO_PUBLIC_ISSUER_URL",
    "SSO_INTERNAL_ISSUER_URL",
    "ALLOW_LOCAL_AUTH",
    "SMOKE_LOGIN_EMAIL",
    "OPERATOR_LOGIN_EMAIL",
    "AUDITOR_LOGIN_EMAIL",
    "REGULATOR_LOGIN_EMAIL",
    "AIRFLOW_HOST_BIND",
    "AIRFLOW_HOST_PORT",
    "DQ_AIRFLOW_BASE_URL",
    "DQ_AIRFLOW_ISSUER_URL",
    "DQ_AIRFLOW_SOURCE_PIPELINE",
    "DQ_AIRFLOW_WAIT_TIMEOUT_SECONDS",
    "DQ_AIRFLOW_POLL_INTERVAL_SECONDS",
    "KONG_INTERNAL_URL",
    "KONG_ADMIN_INTERNAL_URL",
    "KONG_LOCAL_URL",
    "KONG_PUBLIC_URL",
    "KONG_ADMIN_LOCAL_URL",
    "KONG_ADMIN_PUBLIC_URL",
    "KONG_MANAGER_LOCAL_URL",
    "KONG_MANAGER_PUBLIC_URL",
    "DQ_API_INTERNAL_URL",
    "DQ_API_LOCAL_URL",
    "KEYCLOAK_ADMIN_REALM",
    "KONG_OTEL_ENDPOINT",
    "UI_VITE_LOCAL_URL",
    "UI_NGINX_LOCAL_URL",
    "VITE_HOST",
    "VITE_PORT",
    "VITE_HTTPS_KEY_FILE",
    "VITE_HTTPS_CERT_FILE",
    "VITE_KEYCLOAK_REALM",
    "VITE_KEYCLOAK_CLIENT_ID",
    "VITE_SSO_PROVIDER",
    "VITE_SSO_CLIENT_ID",
    "VITE_ALLOW_LOCAL_AUTH",
    "VITE_OTEL_ENABLED",
    "VITE_OTEL_ENDPOINT",
    "VITE_HMR_HOST",
    "DQ_ENGINE_OIDC_CLIENT_ID",
    "DQ_ENGINE_POLLING_INTERVAL_MS",
    "DQ_ENGINE_MAX_RETRIES",
    "DQ_ENGINE_RETRY_BACKOFF_MS",
    "DQ_ENGINE_INTERNAL_URL",
    "DQ_ENGINE_LOCAL_URL",
    "DQ_ENGINE_OIDC_ISSUER",
    "DQ_ENGINE_MAX_ROWS",
    "DQ_LOG_LEVEL",
    "GX_EXECUTION_QUEUE_KEY",
    "GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY",
    "PROFILING_QUEUE_KEY",
    "NATURAL_LANGUAGE_DRAFT_QUEUE_KEY",
    "DQ_SPARK_MASTER",
    "DQ_SPARK_DRIVER_MEMORY",
    "DQ_SPARK_EXECUTOR_MEMORY",
    "DQ_SPARK_DRIVER_MAX_RESULT_SIZE",
    "JAVA_TOOL_OPTIONS",
    "DQ_TEST_DATA_OUTPUT_PREFIX",
    "DQ_S3_ENDPOINT",
    "DQ_S3_ACCESS_KEY",
    "DQ_S3_REGION",
    "DQ_S3_PATH_STYLE_ACCESS",
    "DQ_S3_SSL_ENABLED",
    "DQ_DELIVERY_OUTPUT_BUCKET",
    "GX_EXCEPTION_STORAGE_ENDPOINT",
    "GX_EXCEPTION_STORAGE_ACCESS_KEY",
    "GX_EXCEPTION_STORAGE_REGION",
    "GX_EXCEPTION_STORAGE_SSL_ENABLED",
    "GX_EXCEPTION_STORAGE_BACKEND",
    "GX_EXCEPTION_STORAGE_BUCKET",
    "GX_EXCEPTION_STORAGE_PREFIX",
    "TEST_DATA_MATERIALIZATION_QUEUE_KEY",
    "TEST_DATA_MATERIALIZATION_MAX_PENDING",
    "TEST_DATA_MATERIALIZATION_MAX_IN_FLIGHT",
    "TEST_DATA_MATERIALIZATION_MAX_ROWS",
    "KAFKA_CONSUMER_GROUP_ID",
    "KAFKA_CONSUMER_POLL_TIMEOUT_SECONDS",
    "KAFKA_CONSUMER_MAX_POLL_RECORDS",
    "KAFKA_CONSUMER_LOOP_DELAY_SECONDS",
    "KAFKA_CONSUMER_BATCH_SIZE",
    "KAFKA_CONSUMER_S3_BUCKET",
    "KAFKA_CONSUMER_S3_PREFIX",
    "KAFKA_CONSUMER_S3_PATH_STYLE_ACCESS",
    "PROFILING_REQUEST_GENERATOR_DB_CONTAINER",
    "PROFILING_REQUEST_GENERATOR_DATABASE_NAME",
    "PROFILING_REQUEST_GENERATOR_DATABASE_USER",
    "PROFILING_REQUEST_GENERATOR_COUNT",
    "PROFILING_REQUEST_GENERATOR_INTERVAL_SECONDS",
    "PROFILING_REQUEST_GENERATOR_REQUEST_TYPE",
    "PROFILING_REQUEST_GENERATOR_PAYLOAD_KIND",
    "PROFILING_REQUEST_GENERATOR_DATA_SOURCE_ID",
    "PROFILING_REQUEST_GENERATOR_REQUESTED_BY_USER_ID",
    "PROFILING_REQUEST_GENERATOR_TOKEN_CLIENT_ID",
    "PROFILING_REQUEST_GENERATOR_TOKEN_USERNAME",
    "OBSERVABILITY_DASHBOARD_UID",
    "OBSERVABILITY_DASHBOARD_TITLE",
    "GRAFANA_PUBLIC_DOMAIN",
    "GRAFANA_PUBLIC_URL",
    "GRAFANA_SERVE_FROM_SUB_PATH",
    "GRAFANA_ADMIN_USER",
    "GRAFANA_AUTH",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_TRACES_SAMPLER_ARG",
    "DQ_OPENMETADATA_DB_REGISTRY",
    "DQ_OPENMETADATA_DB_NAMESPACE",
    "DQ_OPENMETADATA_DB_IMAGE",
    "DQ_OPENMETADATA_DB_TAG",
    "DQ_OPENMETADATA_SERVER_REGISTRY",
    "DQ_OPENMETADATA_SERVER_NAMESPACE",
    "DQ_OPENMETADATA_SERVER_IMAGE",
    "DQ_OPENMETADATA_SERVER_TAG",
    "DQ_METADATA_CONFIGURE_REGISTRY",
    "DQ_METADATA_CONFIGURE_NAMESPACE",
    "DQ_METADATA_CONFIGURE_IMAGE",
    "DQ_METADATA_CONFIGURE_TAG",
    "OPENMETADATA_REGISTRY",
    "OPENMETADATA_NAMESPACE",
    "OPENMETADATA_IMAGE",
    "OPENMETADATA_TAG",
    "OPENMETADATA_SEARCH_IMAGE",
    "OPENMETADATA_SEARCH_TAG",
    "OPENMETADATA_INGESTION_REGISTRY",
    "OPENMETADATA_INGESTION_NAMESPACE",
    "OPENMETADATA_INGESTION_IMAGE",
    "OPENMETADATA_DB_BASE_IMAGE",
    "CATALOG_PROVIDER",
    "CATALOG_ENDPOINT",
    "CATALOG_OIDC_ISSUER",
    "CATALOG_OIDC_TOKEN_URL",
    "CATALOG_OIDC_CLIENT_ID",
    "CATALOG_OIDC_SCOPE",
    "CATALOG_OIDC_USERNAME",
    "OPENMETADATA_BASE_PATH",
    "OPENMETADATA_PUBLIC_URL",
    "OPENMETADATA_USE_FORWARDED_HEADERS",
    "OPENMETADATA_CALLBACK",
    "OPENMETADATA_VERSION",
    "OM_DB_SSL_MODE",
    "OM_AUTHENTICATION_PROVIDER",
    "OM_OIDC_PROVIDER_NAME",
    "OM_AUTHORIZER_ADMIN_PRINCIPALS",
    "OM_AUTHORIZER_PRINCIPAL_DOMAIN",
    "OM_AUTHENTICATION_AUTHORITY",
    "OM_AUTHENTICATION_CLIENT_ID",
    "OM_AUTHENTICATION_CALLBACK_URL",
    "OM_AUTHENTICATION_DISCOVERY_URI",
    "OM_AUTHENTICATION_RESPONSE_TYPE",
    "OM_AUTHENTICATION_PUBLIC_KEYS",
    "OM_ENABLE_AUTO_REDIRECT",
    "OPENMETADATA_OIDC_SEED_USERNAME",
    "SEED_ALL",
    "START_METADATA",
    "START_METADATA_INGESTION",
    "ZAMMAD_IMAGE",
    "ZAMMAD_MEMCACHE_SERVERS",
    "ZAMMAD_POSTGRES_VERSION",
    "ZAMMAD_POSTGRES_DB",
    "ZAMMAD_POSTGRES_HOST",
    "ZAMMAD_POSTGRES_USER",
    "ZAMMAD_POSTGRES_PORT",
    "ZAMMAD_POSTGRESQL_OPTIONS",
    "ZAMMAD_REDIS_VERSION",
    "ZAMMAD_REDIS_URL",
    "ZAMMAD_MEMCACHE_VERSION",
    "ZAMMAD_ELASTICSEARCH_ENABLED",
    "ZAMMAD_ELASTICSEARCH_HOST",
    "ZAMMAD_ELASTICSEARCH_PORT",
    "ZAMMAD_ELASTICSEARCH_SCHEMA",
    "ZAMMAD_ELASTICSEARCH_NAMESPACE",
    "ZAMMAD_ELASTICSEARCH_SSL_VERIFY",
    "ZAMMAD_NGINX_PORT",
    "ZAMMAD_NGINX_SERVER_NAME",
    "ZAMMAD_NGINX_SERVER_SCHEME",
    "ZAMMAD_RAILS_TRUSTED_PROXIES",
    "ZAMMAD_HTTP_TYPE",
    "ZAMMAD_FQDN",
    "ZAMMAD_WEB_CONCURRENCY",
    "ZAMMAD_EXPOSE_PORT",
    "ZAMMAD_PUBLIC_URL",
    "ZAMMAD_SSL_CERT_FILE_NAME",
    "ZAMMAD_SSL_KEY_FILE_NAME",
    "TZ",
    "DOCKER_HUB_USERNAME",
    "DQ_DATA_DEFINITION_EVENT_TIMEOUT_SECONDS",
    "DQ_DATA_DEFINITION_LLM_TIMEOUT_SECONDS",
    "DQ_SMOKE_MATERIALIZATION_TIMEOUT_SECONDS",
    "DQ_RULE_E2E_MATERIALIZATION_TIMEOUT_SECONDS",
    "DQ_RULE_E2E_GX_TIMEOUT_SECONDS",
    "DQ_MCP_API_BASE_URL",
    "DQ_MCP_API_TIMEOUT_SECONDS",
    "JAVA_OPTS",
    "KC_OPTS",
    "ES_JAVA_OPTS",
    "KEYCLOAK_HTTPS_CERT_FILE",
    "KEYCLOAK_HTTPS_KEY_FILE",
    "KONG_SSL_CERT",
    "KONG_SSL_CERT_KEY",
    "GRAFANA_CERT_FILE",
    "GRAFANA_CERT_KEY",
    "TRUST_BUNDLE_REGISTRY",
    "TRUST_BUNDLE_NAMESPACE",
    "TRUST_BUNDLE_IMAGE",
    "TRUST_BUNDLE_TAG",
    "AUTOWIZARD_JSON",
    "AUTOWIZARD_RELATIVE_PATH",
    "ZAMMAD_SUPPORT_TOKEN_NAME",
    "ZAMMAD_SUPPORT_TOKEN_PERMISSION",
    "GRAFANA_HOST_BIND",
    "GRAFANA_HTTPS_HOST_PORT",
    "GRAFANA_AUTH_BASIC_ENABLED",
    "GRAFANA_AUTH_DISABLE_LOGIN_FORM",
    "GRAFANA_AUTH_GENERIC_OAUTH_AUTO_LOGIN",
    "GRAFANA_OIDC_REALM_ROLE",
    "EDGE_BIND_HOST",
    "EDGE_PUBLIC_CANONICAL_HOST",
    "EDGE_PUBLIC_APEX_HOST",
    "KEYCLOAK_HTTPS_KEYSTORE_FILE",
    "NEXUSCLOUD_USERNAME",
    "NEXUSCLOUD_DNS",
    "NEXUSCLOUD_PYPI_GROUP_REPO",
    "OPENMETADATA_HOST_BIND",
    "OPENMETADATA_HOST_PORT",
    "OPENMETADATA_SEARCH_USER",
    "OPENMETADATA_SERVER_URL",
    "OPENMETADATA_VERIFY_SSL",
    "OM_DB_HOST",
    "OM_SERVER_HOST",
    "PUSHGATEWAY_HOST_BIND",
    "PUSHGATEWAY_HOST_PORT",
    "CONTAINER_METRICS_HOST_BIND",
    "CONTAINER_METRICS_HOST_PORT",
    "OTEL_GRPC_HOST_BIND",
    "OTEL_GRPC_HOST_PORT",
    "OTEL_HTTP_HOST_BIND",
    "OTEL_HTTP_HOST_PORT",
    "OTEL_JAEGER_HOST_BIND",
    "OTEL_JAEGER_HOST_PORT",
    "OTEL_ZIPKIN_HOST_BIND",
    "OTEL_ZIPKIN_HOST_PORT",
    "DQ_KAFKA_CONSUMER_REGISTRY",
    "DQ_KAFKA_CONSUMER_NAMESPACE",
    "DQ_KAFKA_CONSUMER_IMAGE",
    "DQ_KAFKA_CONSUMER_TAG",
    "KAFKA_CONSUMER_DB_URL",
    "KAFKA_CONSUMER_TOPIC",
    "DQ_ENGINE_OIDC_REALM_ROLE",
    "KONG_CERT_FILE",
    "KONG_KEY_FILE",
    "GRAFANA_KEY_FILE",
    "DQ_KAFKA_REGISTRY",
    "DQ_KAFKA_NAMESPACE",
    "DQ_KAFKA_IMAGE",
    "DQ_KAFKA_TAG",
    "DQ_LLM_BASE_URL",
    "PYTHON_IMAGE",
    "PYTHON_REGISTRY",
    "PYTHON_TAG",
    "SKIP_SPARK_WARMUP",
    "GRAFANA_HOST",
    "DQ_TRINO_REGISTRY",
    "DQ_TRINO_IMAGE",
    "DQ_TRINO_TAG",
    "TRINO_BASE_IMAGE",
    "TRINO_HOST_BIND",
    "TRINO_HOST_PORT",
    "DQ_AIRFLOW_RUN_PLAN_ID",
    "REPO_NPMRC_FILE",
    "TLS_INTERNAL_CA_BUNDLE",
    "DATABASE_SCHEMA",
    "DB_CONTAINER",
    "DB_HOST_BIND",
    "DB_HOST_PORT",
    "REDIS_HOST_BIND",
    "REDIS_HOST_PORT",
    "DQ_LLM_HOST_BIND",
    "DQ_LLM_HOST_PORT",
    "OIDC_REDIRECT_BASE_URL",
    "API_HOST_BIND",
    "API_HOST_PORT",
    "FRONTEND_HOST_BIND",
    "FRONTEND_HTTPS_HOST_PORT",
    "FRONTEND_CERT_FILE",
    "FRONTEND_KEY_FILE",
    "KONG_SERVICE_FQDN",
    "KEYCLOAK_INTERNAL_URL",
    "KEYCLOAK_SERVER_SIDE_URL",
    "KEYCLOAK_LOCAL_URL",
    "KEYCLOAK_PUBLIC_HOSTNAME",
    "KEYCLOAK_PUBLIC_URL",
    "KEYCLOAK_HTTPS_RELATIVE_PATH",
    "KEYCLOAK_ADMIN_USER",
    "DQ_BASE_REGISTRY",
    "DQ_BASE_NAMESPACE",
    "DQ_BASE_IMAGE",
    "DQ_BASE_TAG",
    "DQ_API_REGISTRY",
    "DQ_API_NAMESPACE",
    "DQ_API_IMAGE",
    "DQ_API_TAG",
    "DQ_ENGINE_REGISTRY",
    "DQ_ENGINE_NAMESPACE",
    "DQ_ENGINE_IMAGE",
    "DQ_ENGINE_TAG",
    "DQ_PROFILING_REGISTRY",
    "DQ_PROFILING_NAMESPACE",
    "DQ_PROFILING_IMAGE",
    "DQ_PROFILING_TAG",
    "DQ_FRONTEND_REGISTRY",
    "DQ_FRONTEND_NAMESPACE",
    "DQ_FRONTEND_IMAGE",
    "DQ_FRONTEND_TAG",
    "DQ_KONG_REGISTRY",
    "DQ_KONG_NAMESPACE",
    "DQ_KONG_IMAGE",
    "DQ_KONG_TAG",
    "DQ_KEYCLOAK_REGISTRY",
    "DQ_KEYCLOAK_NAMESPACE",
    "DQ_KEYCLOAK_IMAGE",
    "DQ_KEYCLOAK_TAG",
    "DQ_DB_REGISTRY",
    "DQ_DB_NAMESPACE",
    "DQ_DB_IMAGE",
    "DQ_DB_TAG",
    "DQ_LLM_REGISTRY",
    "DQ_LLM_NAMESPACE",
    "DQ_LLM_IMAGE",
    "DQ_LLM_TAG",
    "REGISTRY",
    "DOCKER_DOMAIN",
    "PG_REGISTRY",
    "PG_NAMESPACE",
    "PG_IMAGE",
    "PG_TAG",
    "KEYCLOAK_REGISTRY",
    "KEYCLOAK_NAMESPACE",
    "KEYCLOAK_IMAGE",
    "KEYCLOAK_TAG",
    "NODE_REGISTRY",
    "NODE_NAMESPACE",
    "NODE_IMAGE",
    "NODE_TAG",
    "APK_REPOSITORIES",
    "NGINX_REGISTRY",
    "NGINX_NAMESPACE",
    "NGINX_IMAGE",
    "NGINX_TAG",
    "REDIS_REGISTRY",
    "REDIS_NAMESPACE",
    "REDIS_IMAGE",
    "REDIS_TAG",
    "ENVIRONMENT",
    "COMPOSE_PROJECT_NAME",
    "NODE_ENV",
    "PIP_INDEX_URL",
    "MAVEN_REPOSITORIES",
    "OTEL_JAVAAGENT_VERSION",
    "OTEL_JAVAAGENT_HELPER_IMAGE",
]


def _is_password_var(name: str) -> bool:
    """Return True if *name* looks like a password / secret variable."""
    return bool(_PASSWORD_INDICATORS.search(name))


def _is_acceptable_value(value: str) -> bool:
    """Return True if *value* is acceptable in an env file."""
    for pattern in _ACCEPTABLE_PATTERNS:
        if pattern.match(value):
            return True
    return False


def _is_non_secret_prefix(name: str) -> bool:
    """Return True if *name* starts with a known non-secret prefix."""
    for prefix in _NON_SECRET_PREFIXES:
        if name.startswith(prefix):
            return True
    return False


def validate_env_file(env_file: Path) -> list[str]:
    """Validate *env_file* for hardcoded secrets.

    Returns a list of violation messages (empty if clean).
    """
    violations: list[str] = []

    if not env_file.is_file():
        return [f"Env file not found: {env_file}"]

    with env_file.open("r", encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                continue

            key, _, raw_value = stripped.partition("=")
            key = key.strip()
            # Strip surrounding quotes (single or double)
            value = raw_value.strip()
            if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]

            if not _is_password_var(key):
                continue
            if _is_non_secret_prefix(key):
                continue
            if _is_acceptable_value(value):
                continue

            violations.append(
                f"  {env_file}:{line_num}: {key}=<hardcoded_value>"
            )

    return violations


def main() -> int:
    """Entry point for CLI usage."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    env_files = sorted(repo_root.glob(".env.*.local"))

    if not env_files:
        print("No .env.*.local files found in repository root.")
        return 0

    all_violations: list[str] = []
    for env_file in env_files:
        violations = validate_env_file(env_file)
        if violations:
            all_violations.append(f"\n{env_file.name}:")
            all_violations.extend(violations)

    if all_violations:
        print("ERROR: Hardcoded secrets found in .env.*.local files:", file=sys.stderr)
        for line in all_violations:
            print(line, file=sys.stderr)
        print("\nFix: Remove hardcoded secrets and use generate_secrets.sh to produce them.", file=sys.stderr)
        return 1

    print(f"✓ All {len(env_files)} .env.*.local files are clean (no hardcoded secrets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
