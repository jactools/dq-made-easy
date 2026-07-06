# Purpose: Export repo environment variables and derive shared Nexus auth values.
#
# What it does:
# - Intended to be sourced (not executed) before running compose/scripts.
# - Reads .env-derived configuration and exports image/tag/URL variables.
# - Derives shared Nexus auth values for repo-root .npmrc consumers.
#
# Version: 1.9
# Last modified: 2026-06-30
# Changelog:
# - 1.9 (2026-06-30): Stop mutating npm config in shell and derive shared Nexus auth for repo-root .npmrc.

# Source generic logging function
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/logging.sh"
my_name="setup_env.sh"

debug "$my_name" "Setting up environment variables..."

VITE_KEYCLOAK_PUBLIC_URL="${VITE_KEYCLOAK_PUBLIC_URL:-${KEYCLOAK_PUBLIC_URL:-}}"
VITE_SSO_ISSUER_URL="${VITE_SSO_ISSUER_URL:-${SSO_PUBLIC_ISSUER_URL:-}}"
DQ_API_INTERNAL_URL="${DQ_API_INTERNAL_URL:-}"
DQ_API_LOCAL_URL="${DQ_API_LOCAL_URL:-}"
DQ_ENGINE_INTERNAL_URL="${DQ_ENGINE_INTERNAL_URL:-}"
DQ_ENGINE_LOCAL_URL="${DQ_ENGINE_LOCAL_URL:-}"

if [ -z "${KEYCLOAK_PUBLIC_HOSTNAME:-}" ] && [ -n "${KEYCLOAK_PUBLIC_URL:-}" ]; then
    KEYCLOAK_PUBLIC_HOSTNAME="$(printf '%s' "$KEYCLOAK_PUBLIC_URL" | sed -E 's#^https?://([^/:]+).*$#\1#')"
fi

if [ -z "${VITE_SSO_CLIENT_ID:-}" ] && [ -n "${SSO_CLIENT_ID:-}" ]; then
    VITE_SSO_CLIENT_ID="$SSO_CLIENT_ID"
fi

if [ -z "${VITE_SSO_ENABLED:-}" ] && [ -n "${SSO_ENABLED:-}" ]; then
    VITE_SSO_ENABLED="$SSO_ENABLED"
fi

if [ -z "${VITE_KEYCLOAK_CLIENT_ID:-}" ] && [ -n "${VITE_SSO_CLIENT_ID:-}" ]; then
    VITE_KEYCLOAK_CLIENT_ID="$VITE_SSO_CLIENT_ID"
fi

if [ -z "${VITE_KEYCLOAK_REALM:-}" ] && [ -n "${KEYCLOAK_REALM:-}" ]; then
    VITE_KEYCLOAK_REALM="$KEYCLOAK_REALM"
fi

if [ -n "${KONG_PUBLIC_URL:-}" ]; then
    kong_public_authority="$(printf '%s' "$KONG_PUBLIC_URL" | sed -E 's#^[a-zA-Z][a-zA-Z0-9+.-]*://([^/]+).*$#\1#')"
    KONG_PUBLIC_HOSTNAME="${kong_public_authority%%:*}"
fi

if [ -n "${KONG_LOCAL_URL:-${KONG_PUBLIC_URL:-}}" ]; then
    kong_local_url="${KONG_LOCAL_URL:-${KONG_PUBLIC_URL:-}}"
    kong_local_scheme="$(printf '%s' "$kong_local_url" | sed -E 's#^([a-zA-Z][a-zA-Z0-9+.-]*)://.*$#\1#')"
    if [ "$kong_local_scheme" = "$kong_local_url" ]; then
        kong_local_scheme="https"
    fi

    kong_local_authority="$(printf '%s' "$kong_local_url" | sed -E 's#^[a-zA-Z][a-zA-Z0-9+.-]*://([^/]+).*$#\1#')"
    KONG_LOCAL_HOSTNAME="${kong_local_authority%%:*}"
    if [ "$kong_local_authority" != "$KONG_LOCAL_HOSTNAME" ]; then
        kong_local_port="${kong_local_authority##*:}"
    else
        kong_local_port=""
    fi

    KONG_LOCAL_PROBE_SCHEME="$kong_local_scheme"
    if [ -n "${KONG_PROXY_HOST_PORT:-}" ]; then
        KONG_LOCAL_PROBE_PORT="$KONG_PROXY_HOST_PORT"
    elif [ -n "$kong_local_port" ]; then
        KONG_LOCAL_PROBE_PORT="$kong_local_port"
    elif [ "$KONG_LOCAL_PROBE_SCHEME" = "http" ]; then
        KONG_LOCAL_PROBE_PORT="80"
    else
        KONG_LOCAL_PROBE_PORT="443"
    fi

    KONG_LOCAL_PROBE_TARGET_HOST="${KONG_PROXY_HOST_BIND:-127.0.0.1}"
    case "$KONG_LOCAL_PROBE_TARGET_HOST" in
        ""|0.0.0.0|::)
            KONG_LOCAL_PROBE_TARGET_HOST="127.0.0.1"
            ;;
    esac

    KONG_LOCAL_PROBE_BASE_URL="${KONG_LOCAL_PROBE_SCHEME}://${KONG_LOCAL_HOSTNAME}"
    if ! { [ "$KONG_LOCAL_PROBE_SCHEME" = "https" ] && [ "$KONG_LOCAL_PROBE_PORT" = "443" ]; } \
        && ! { [ "$KONG_LOCAL_PROBE_SCHEME" = "http" ] && [ "$KONG_LOCAL_PROBE_PORT" = "80" ]; }; then
        KONG_LOCAL_PROBE_BASE_URL="${KONG_LOCAL_PROBE_BASE_URL}:${KONG_LOCAL_PROBE_PORT}"
    fi

    KONG_LOCAL_PROBE_RESOLVE="${KONG_LOCAL_HOSTNAME}:${KONG_LOCAL_PROBE_PORT}:${KONG_LOCAL_PROBE_TARGET_HOST}"
fi

curl_kong_host_probe() {
    if [ -n "${KONG_LOCAL_PROBE_RESOLVE:-}" ]; then
        curl --resolve "$KONG_LOCAL_PROBE_RESOLVE" "$@"
    else
        curl "$@"
    fi
}

nexuscloud_hostname="${NEXUSCLOUD_HOSTNAME:-}"
nexuscloud_dns="${NEXUSCLOUD_DNS:-}"
nexuscloud_registry="${NEXUSCLOUD_REGISTRY:-}"
nexuscloud_username="${NEXUSCLOUD_USERNAME:-}"
nexuscloud_password="${NEXUSCLOUD_PASSWORD:-}"
nexuscloud_password_base64="${NEXUSCLOUD_PASSWORD_BASE64:-}"
nexuscloud_group_repo="${NEXUSCLOUD_PYPI_GROUP_REPO:-}"
nexuscloud_maven_group_repo="${NEXUSCLOUD_MAVEN_GROUP_REPO:-${NEXUSCLOUD_MPM_GROUP_REPO:-}}"

if [ -z "$nexuscloud_hostname" ] && [ -n "$nexuscloud_dns" ]; then
    nexuscloud_hostname="${nexuscloud_dns#//}"
fi

if [ -n "$nexuscloud_hostname" ]; then
    nexuscloud_dns="//${nexuscloud_hostname}"
    NEXUSCLOUD_HOSTNAME="$nexuscloud_hostname"
    NEXUSCLOUD_DNS="$nexuscloud_dns"
    export NEXUSCLOUD_HOSTNAME NEXUSCLOUD_DNS
fi

if [ -z "$nexuscloud_password_base64" ] && [ -n "$nexuscloud_username" ] && [ -n "$nexuscloud_password" ]; then
    nexuscloud_password_base64=$(printf '%s' "${nexuscloud_username}:${nexuscloud_password}" | base64)
fi

NEXUSCLOUD_PASSWORD_BASE64="$nexuscloud_password_base64"
export NEXUSCLOUD_PASSWORD_BASE64

if [ -n "$nexuscloud_hostname" ] || [ -n "$nexuscloud_registry" ]; then
    debug "$my_name" "NEXUSCLOUD_HOSTNAME: ${nexuscloud_hostname}"
    debug "$my_name" "NEXUSCLOUD_REGISTRY: ${nexuscloud_registry}"
    if [ -z "$nexuscloud_password_base64" ]; then
        warning "$my_name" "Nexus Cloud is configured but no shared npm auth value is available"
    fi
fi

if [ -n "${NEXUSCLOUD_NPM_REGISTRY:-}" ]; then
    NPM_CONFIG_REGISTRY="$NEXUSCLOUD_NPM_REGISTRY"
else
    NPM_CONFIG_REGISTRY="https://registry.npmjs.org/"
fi

# ---------------------------------------------------------------------------
# PyPI (pip) registry configuration
#
# We intentionally derive these (instead of hardcoding them in .env) because
# docker-compose does not reliably expand nested ${VAR} references inside .env.
#
# Fail-fast policy: if Nexus Cloud is configured, the PyPI group repo must be
# provided so Docker builds can be deterministic.
# ---------------------------------------------------------------------------

if [ -n "$nexuscloud_hostname" ]; then
    nexus_host="$nexuscloud_hostname"
    if [ -z "$nexus_host" ]; then
        error "$my_name" "NEXUSCLOUD_HOSTNAME is set but empty"
        return 1
    fi

    if [ -z "$nexuscloud_group_repo" ]; then
        error "$my_name" "NEXUSCLOUD_HOSTNAME is set but NEXUSCLOUD_GROUP_REPO is not set (expected e.g. gr-pypi-36)"
        return 1
    fi

    NEXUSCLOUD_PYPI_URL_NO_AUTH="https://${nexus_host}/repository/${nexuscloud_group_repo}/simple"

    if [ -z "$nexuscloud_username" ] || [ -z "$nexuscloud_password" ]; then
        error "$my_name" "NEXUSCLOUD_HOSTNAME is set but NEXUSCLOUD_USERNAME/NEXUSCLOUD_PASSWORD are not set (required for authenticated PyPI URL)"
        return 1
    fi

    # Do not log this value; it contains credentials.
    NEXUSCLOUD_PYPI_URL="https://${nexuscloud_username}:${nexuscloud_password}@${nexus_host}/repository/${nexuscloud_group_repo}/simple"
    export NEXUSCLOUD_PYPI_URL NEXUSCLOUD_PYPI_URL_NO_AUTH
fi

if [ -z "${PIP_INDEX_URL:-}" ]; then
    if [ -n "${NEXUSCLOUD_PYPI_URL:-}" ]; then
        PIP_INDEX_URL="$NEXUSCLOUD_PYPI_URL"
    elif [ -n "${NEXUSCLOUD_PYPI_URL_NO_AUTH:-}" ] && [ -n "$nexuscloud_username" ] && [ -n "$nexuscloud_password" ]; then
        pip_index_host="${NEXUSCLOUD_PYPI_URL_NO_AUTH#https://}"
        pip_index_host="${pip_index_host%%/repository/*}"
        PIP_INDEX_URL="https://${nexuscloud_username}:${nexuscloud_password}@${pip_index_host}/repository/${nexuscloud_group_repo}/simple"
    fi
fi

if [ -n "${PIP_INDEX_URL:-}" ]; then
    export PIP_INDEX_URL
fi

# ---------------------------------------------------------------------------
# Maven repositories configuration
#
# Spark package warm-up uses Maven/Ivy under the hood. Derive a Nexus-backed
# Maven repository URL when a Nexus host and Maven group repo are configured.
# Keep explicit MAVEN_REPOSITORIES overrides intact.
# ---------------------------------------------------------------------------

if [ -n "$nexuscloud_hostname" ] && [ -n "$nexuscloud_maven_group_repo" ]; then
    NEXUSCLOUD_MAVEN_REPOSITORY_URL_NO_AUTH="https://${nexuscloud_hostname}/repository/${nexuscloud_maven_group_repo}/"
    if [ -n "$nexuscloud_username" ] && [ -n "$nexuscloud_password" ]; then
        NEXUSCLOUD_MAVEN_REPOSITORY_URL="https://${nexuscloud_username}:${nexuscloud_password}@${nexuscloud_hostname}/repository/${nexuscloud_maven_group_repo}/"
    fi
fi

if [ -z "${MAVEN_REPOSITORIES:-}" ]; then
    if [ -n "${NEXUSCLOUD_MAVEN_REPOSITORY_URL:-}" ]; then
        MAVEN_REPOSITORIES="$NEXUSCLOUD_MAVEN_REPOSITORY_URL"
    elif [ -n "${NEXUSCLOUD_MAVEN_REPOSITORY_URL_NO_AUTH:-}" ]; then
        MAVEN_REPOSITORIES="$NEXUSCLOUD_MAVEN_REPOSITORY_URL_NO_AUTH"
    fi
fi

if [ -n "${MAVEN_REPOSITORIES:-}" ]; then
    export MAVEN_REPOSITORIES
fi

export NEXUSCLOUD_REGISTRY
export NEXUSCLOUD_GROUP_REPO
export NEXUSCLOUD_PYPI_URL
export NEXUSCLOUD_PYPI_URL_NO_AUTH
export NEXUSCLOUD_MAVEN_REPOSITORY_URL
export NEXUSCLOUD_MAVEN_REPOSITORY_URL_NO_AUTH
export PIP_INDEX_URL
export NPM_CONFIG_REGISTRY

export REGISTRY

export PG_REGISTRY
export PG_NAMESPACE
export PG_IMAGE

export KEYCLOAK_REGISTRY
export KEYCLOAK_NAMESPACE
export KEYCLOAK_IMAGE

export NODE_REGISTRY
export NODE_NAMESPACE
export NODE_IMAGE

export NGINX_REGISTRY
export NGINX_NAMESPACE
export NGINX_IMAGE
export NGINX_TAG

export PYTHON_REGISTRY
export PYTHON_NAMESPACE
export PYTHON_IMAGE
export PYTHON_TAG

export APK_REPOSITORIES

export REGISTRY

export PG_REGISTRY
export PG_NAMESPACE
export PG_IMAGE
export PG_TAG

export KEYCLOAK_REGISTRY
export KEYCLOAK_NAMESPACE
export KEYCLOAK_IMAGE
export KEYCLOAK_TAG

export NODE_REGISTRY
export NODE_NAMESPACE
export NODE_IMAGE
export NODE_TAG

export NGINX_REGISTRY
export NGINX_NAMESPACE
export NGINX_IMAGE
export NGINX_TAG

export DOCKER_BASE_REGISTRY

export DQ_BASE_REGISTRY
export DQ_BASE_NAMESPACE
export DQ_BASE_IMAGE
export DQ_BASE_TAG

export DQ_API_REGISTRY
export DQ_API_NAMESPACE
export DQ_API_IMAGE
export DQ_API_TAG

export DQ_ENGINE_REGISTRY
export DQ_ENGINE_NAMESPACE
export DQ_ENGINE_IMAGE
export DQ_ENGINE_TAG

export DQ_PROFILING_REGISTRY
export DQ_PROFILING_NAMESPACE
export DQ_PROFILING_IMAGE
export DQ_PROFILING_TAG

export DQ_KONG_REGISTRY
export DQ_KONG_NAMESPACE
export DQ_KONG_IMAGE
export DQ_KONG_TAG

export DQ_KEYCLOAK_REGISTRY
export DQ_KEYCLOAK_NAMESPACE
export DQ_KEYCLOAK_IMAGE
export DQ_KEYCLOAK_TAG

export DQ_DB_REGISTRY
export DQ_DB_NAMESPACE
export DQ_DB_IMAGE
export DQ_DB_TAG

export DQ_FRONTEND_REGISTRY
export DQ_FRONTEND_NAMESPACE
export DQ_FRONTEND_IMAGE
export DQ_FRONTEND_TAG

export REDIS_REGISTRY
export REDIS_NAMESPACE
export REDIS_IMAGE
export REDIS_TAG

export DQ_DB_INTERNAL_URL
export DQ_DB_LOCAL_URL
export DATABASE_SCHEMA
export DQ_DB_HOST
export ALEMBIC_DB_HOST

export OPENMETADATA_VERSION
export OM_DB_ROOT_PASSWORD
export OM_DB_NAME
export OM_DB_USER
export OM_DB_PASSWORD
export OM_AIRFLOW_SECRET_KEY

export START_METADATA
export START_METADATA_INGESTION

export NODE_ENV
export OIDC_REDIRECT_BASE_URL
export DQ_API_INTERNAL_URL
export DQ_API_LOCAL_URL
export UI_VITE_LOCAL_URL
export UI_NGINX_LOCAL_URL

export KEYCLOAK_INTERNAL_URL
export KEYCLOAK_LOCAL_URL
export KEYCLOAK_REALM
export KEYCLOAK_CLIENT_ID
export KEYCLOAK_MASTER_CLIENT_ID
export KEYCLOAK_SYSTEM_ADMIN_USERNAME
export KEYCLOAK_SYSTEM_ADMIN_PASSWORD
export KEYCLOAK_PUBLIC_HOSTNAME
export SSO_INTERNAL_ISSUER_URL
export SSO_PUBLIC_ISSUER_URL
export KEYCLOAK_TOKEN_REALM
export KEYCLOAK_USERNAME
export KEYCLOAK_PASSWORD
export KEYCLOAK_JACCLOUD_USERNAME
export KEYCLOAK_JACCLOUD_PASSWORD
export KEYCLOAK_CLIENT_SECRET
export KEYCLOAK_HOST
export KEYCLOAK_PUBLIC_URL
export VITE_KEYCLOAK_PUBLIC_URL
export VITE_KEYCLOAK_REALM
export VITE_KEYCLOAK_CLIENT_ID
export VITE_SSO_ISSUER_URL
export KONG_INTERNAL_URL
export KONG_LOCAL_URL
export KONG_ADMIN_INTERNAL_URL
export KONG_ADMIN_LOCAL_URL
export KONG_ADMIN_PUBLIC_URL
export KONG_MANAGER_LOCAL_URL
export KONG_MANAGER_PUBLIC_URL
export KONG_PUBLIC_HOSTNAME
export KONG_LOCAL_HOSTNAME
export KONG_LOCAL_PROBE_SCHEME
export KONG_LOCAL_PROBE_PORT
export KONG_LOCAL_PROBE_TARGET_HOST
export KONG_LOCAL_PROBE_BASE_URL
export KONG_LOCAL_PROBE_RESOLVE
export VITE_SSO_CLIENT_ID
export VITE_SSO_ENABLED

export KONG_PUBLIC_URL

export DQ_ENGINE_INTERNAL_URL
export DQ_ENGINE_LOCAL_URL

export MAVEN_REPOSITORIES

if [ -f "$ROOT_DIR/tmp/certs/mkcert-rootCA.pem" ]; then
    MKCERT_ROOT_CA="$(openssl base64 -A -in "$ROOT_DIR/tmp/certs/mkcert-rootCA.pem")"
    export MKCERT_ROOT_CA
fi

if [ -f "$ROOT_DIR/tmp/certs/internal-root-ca-2024.crt" ]; then
    INTERNAL_ROOT_CA="$(openssl base64 -A -in "$ROOT_DIR/tmp/certs/internal-root-ca-2024.crt")"
    export INTERNAL_ROOT_CA
fi

if [ -z "${INTERNAL_CORPORATE_ROOT_CA:-}" ] && command -v security >/dev/null 2>&1; then
    if internal_corporate_root_ca_pem="$(security find-certificate -a -c 'RI Corporate Root CA2' -p 2>/dev/null)" && [ -n "$internal_corporate_root_ca_pem" ]; then
        INTERNAL_CORPORATE_ROOT_CA="$(printf '%s' "$internal_corporate_root_ca_pem" | openssl base64 -A)"
        export INTERNAL_CORPORATE_ROOT_CA
    fi
fi

if command -v security >/dev/null 2>&1; then
    if internal_corporate_root_ca_pem="$(security find-certificate -a -c 'RI Corporate Root CA2' -p 2>/dev/null)" && [ -n "$internal_corporate_root_ca_pem" ]; then
        INTERNAL_CORPORATE_ROOT_CA_FILE="$ROOT_DIR/tmp/certs/internal-corporate-root-ca2.pem"
        printf '%s' "$internal_corporate_root_ca_pem" > "$INTERNAL_CORPORATE_ROOT_CA_FILE"
        export INTERNAL_CORPORATE_ROOT_CA_FILE
    fi
fi

internal_ca_bundle_file="$(mktemp)"
internal_ca_bundle_found=false
if [ -n "${INTERNAL_CORPORATE_ROOT_CA_FILE:-}" ] && [ -f "$INTERNAL_CORPORATE_ROOT_CA_FILE" ]; then
    internal_ca_bundle_found=true
    cat "$INTERNAL_CORPORATE_ROOT_CA_FILE" >> "$internal_ca_bundle_file"
fi
for cert_file in "$ROOT_DIR"/tmp/certs/internal*.crt; do
    [ -e "$cert_file" ] || continue
    internal_ca_bundle_found=true
    if openssl x509 -inform PEM -in "$cert_file" -noout >/dev/null 2>&1; then
        cat "$cert_file" >> "$internal_ca_bundle_file"
    else
        openssl x509 -inform DER -in "$cert_file" -outform PEM >> "$internal_ca_bundle_file"
    fi
done
if [ "$internal_ca_bundle_found" = true ]; then
    INTERNAL_CA_BUNDLE="$(openssl base64 -A -in "$internal_ca_bundle_file")"
    export INTERNAL_CA_BUNDLE

    INTERNAL_CA_BUNDLE_FILE="$ROOT_DIR/tmp/certs/internal-ca-bundle.pem"
    INTERNAL_CA_BUNDLE_FILE="$ROOT_DIR/tmp/certs/trust/internal-ca-bundle.pem"
    mkdir -p "$ROOT_DIR/tmp/certs/trust"
    cp "$internal_ca_bundle_file" "$INTERNAL_CA_BUNDLE_FILE"
    cp "$internal_ca_bundle_file" "$ROOT_DIR/tmp/certs/internal-ca-bundle.pem"
    export INTERNAL_CA_BUNDLE_FILE
fi
rm -f "$internal_ca_bundle_file"

if [ -n "${INTERNAL_CA_BUNDLE_FILE:-}" ]; then
    export PIP_CERT="$INTERNAL_CA_BUNDLE_FILE"
    export REQUESTS_CA_BUNDLE="$INTERNAL_CA_BUNDLE_FILE"
    export SSL_CERT_FILE="$INTERNAL_CA_BUNDLE_FILE"
    if [ -z "${CURL_CA_BUNDLE:-}" ]; then
        export CURL_CA_BUNDLE="$INTERNAL_CA_BUNDLE_FILE"
    fi
fi

export DQ_SPARK_DRIVER_MEMORY
export DQ_SPARK_EXECUTOR_MEMORY

# Prefer explicit DOCKER_DOMAIN, otherwise derive it from NEXUSCLOUD_DNS.
if [ -z "${DOCKER_DOMAIN:-}" ]; then
    DOCKER_DOMAIN="${NEXUSCLOUD_HOSTNAME}"
fi
if [ -n "${DOCKER_DOMAIN:-}" ]; then
    export DOCKER_DOMAIN
    debug "$my_name" "Using Docker registry domain: $DOCKER_DOMAIN"

    # Force base image registries through Nexus group.
    NODE_REGISTRY="${DOCKER_DOMAIN}/"
    NGINX_REGISTRY="${DOCKER_DOMAIN}/"
    if [ -n "${NEXUSCLOUD_DOCKER_IO_REGISTRY:-}" ]; then
        PYTHON_REGISTRY=""
    else
        PYTHON_REGISTRY="${DOCKER_DOMAIN}/"
    fi
    export NODE_REGISTRY NGINX_REGISTRY PYTHON_REGISTRY

    # Ensure Docker is authenticated to Docker Hub for public base-image pulls.
    if [ -n "${DOCKER_HUB_USERNAME:-}" ] && [ -n "${DOCKER_HUB_TOKEN:-}" ]; then
        if ! printf '%s' "$DOCKER_HUB_TOKEN" | docker login "$DOCKER_DOMAIN" --username "$DOCKER_HUB_USERNAME" --password-stdin >/dev/null 2>&1; then
            error "$my_name" "Docker login failed for Docker registry $DOCKER_DOMAIN"
            return 1
        fi
    else
        warning "$my_name" "Docker Hub credentials missing; cannot login to $DOCKER_DOMAIN"
    fi
fi

if [ -n "${NEXUSCLOUD_DOCKER_IO_REGISTRY:-}" ] && [ -n "${NEXUSCLOUD_USERNAME:-}" ] && [ -n "${NEXUSCLOUD_PASSWORD:-}" ]; then
    nexus_docker_io_registry="${NEXUSCLOUD_DOCKER_IO_REGISTRY#http://}"
    nexus_docker_io_registry="${nexus_docker_io_registry#https://}"
    nexus_docker_io_host="${nexus_docker_io_registry%%/*}"
    if [ -n "$nexus_docker_io_host" ]; then
        info "$my_name" "Logging in to Nexus Docker registry host: $nexus_docker_io_host"
        if ! printf '%s' "$NEXUSCLOUD_PASSWORD" | docker login "$nexus_docker_io_host" --username "$NEXUSCLOUD_USERNAME" --password-stdin >/dev/null 2>&1; then
            error "$my_name" "Docker login failed for Nexus registry host $nexus_docker_io_host"
            return 1
        fi
    fi
fi

debug "$my_name" "Environment variables exported for docker-compose: REGISTRY=${REGISTRY:-}"
