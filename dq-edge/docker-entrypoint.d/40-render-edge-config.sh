#!/bin/sh
set -eu

mode="${EDGE_MODE:-local}"
cert_file="${EDGE_SSL_CERT_FILE:-}"
key_file="${EDGE_SSL_KEY_FILE:-}"

require_edge_setting() {
  name="$1"
  value="$2"

  case "$value" in
    ""|__MISSING_*)
      echo "Missing required edge setting: $name" >&2
      exit 1
      ;;
  esac
}

require_edge_setting "EDGE_SSL_CERT_FILE" "$cert_file"
require_edge_setting "EDGE_SSL_KEY_FILE" "$key_file"

if [ ! -f "$cert_file" ]; then
  echo "Missing edge TLS certificate: $cert_file" >&2
  exit 1
fi

if [ ! -f "$key_file" ]; then
  echo "Missing edge TLS private key: $key_file" >&2
  exit 1
fi

cat > /etc/nginx/conf.d/default.conf <<EOF
resolver 127.0.0.11 ipv6=off valid=10s;

map \$http_upgrade \$connection_upgrade {
  default upgrade;
  '' close;
}
EOF

default_server_written=0

append_common_proxy() {
  cat <<'EOF'
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
EOF
}

append_http_proxy() {
  upstream="$1"
  {
    append_common_proxy
    printf '    set $upstream %s;\n' "$upstream"
    printf '    proxy_pass $upstream;\n'
  } >> /etc/nginx/conf.d/default.conf
}

append_http_proxy_with_uri() {
  upstream="$1"
  {
    append_common_proxy
    printf '    proxy_pass %s;\n' "$upstream"
  } >> /etc/nginx/conf.d/default.conf
}

append_https_proxy_with_uri() {
  upstream="$1"
  server_name="$2"
  {
    append_common_proxy
    printf '    proxy_ssl_server_name on;\n'
    printf '    proxy_ssl_name %s;\n' "$server_name"
    printf '    proxy_ssl_verify on;\n'
    printf '    proxy_ssl_trusted_certificate /etc/nginx/certs/trust/internal-ca-bundle.pem;\n'
    printf '    proxy_ssl_verify_depth 2;\n'
    printf '    proxy_pass %s;\n' "$upstream"
  } >> /etc/nginx/conf.d/default.conf
}

append_https_proxy() {
  upstream="$1"
  server_name="$2"
  {
    append_common_proxy
    printf '    proxy_ssl_server_name on;\n'
    printf '    proxy_ssl_name %s;\n' "$server_name"
    printf '    proxy_ssl_verify off;\n'
    printf '    set $upstream %s;\n' "$upstream"
    printf '    proxy_pass $upstream;\n'
  } >> /etc/nginx/conf.d/default.conf
}

append_server_header() {
  server_names="$1"
  listen_directive="listen 443 ssl;"

  if [ "$default_server_written" -eq 0 ]; then
    listen_directive="listen 443 ssl default_server;"
    default_server_written=1
  fi

  cat >> /etc/nginx/conf.d/default.conf <<EOF

server {
  ${listen_directive}
  server_name ${server_names};
  ssl_certificate ${cert_file};
  ssl_certificate_key ${key_file};
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_prefer_server_ciphers off;
EOF
}

render_local() {
  app_host="${EDGE_LOCAL_APP_HOST:-__MISSING_EDGE_LOCAL_APP_HOST__}"
  kong_host="${EDGE_LOCAL_KONG_HOST:-__MISSING_EDGE_LOCAL_KONG_HOST__}"
  keycloak_host="${EDGE_LOCAL_KEYCLOAK_HOST:-__MISSING_EDGE_LOCAL_KEYCLOAK_HOST__}"
  metadata_host="${EDGE_LOCAL_OPENMETADATA_HOST:-__MISSING_EDGE_LOCAL_OPENMETADATA_HOST__}"
  observability_host="${EDGE_LOCAL_OBSERVABILITY_HOST:-__MISSING_EDGE_LOCAL_OBSERVABILITY_HOST__}"
  support_host="${EDGE_LOCAL_SUPPORT_HOST:-__MISSING_EDGE_LOCAL_SUPPORT_HOST__}"
  airflow_host="${EDGE_LOCAL_AIRFLOW_HOST:-}"

  require_edge_setting "EDGE_LOCAL_APP_HOST" "$app_host"
  require_edge_setting "EDGE_LOCAL_KONG_HOST" "$kong_host"
  require_edge_setting "EDGE_LOCAL_KEYCLOAK_HOST" "$keycloak_host"
  require_edge_setting "EDGE_LOCAL_OPENMETADATA_HOST" "$metadata_host"
  require_edge_setting "EDGE_LOCAL_OBSERVABILITY_HOST" "$observability_host"
  require_edge_setting "EDGE_LOCAL_SUPPORT_HOST" "$support_host"

  append_server_header "_ ${app_host}"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  location / {
EOF
  append_https_proxy "https://frontend:443" "frontend"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }
}
EOF

  append_server_header "${kong_host}"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  location /ops/kong/ {
    proxy_set_header X-Forwarded-Prefix /ops/kong;
EOF
  append_http_proxy "http://kong:8002"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location / {
EOF
  append_http_proxy "http://kong:8000"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }
}
EOF

  append_server_header "${keycloak_host}"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  location / {
EOF
  append_http_proxy "http://keycloak:8080"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }
}
EOF

  append_server_header "${metadata_host}"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  location / {
EOF
  append_https_proxy "https://openmetadata-server:8585" "openmetadata-server"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }
}
EOF

  append_server_header "${observability_host}"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  location /otlp/ {
EOF
  append_https_proxy_with_uri "https://dq-made-easy-otel-collector:4318/" "dq-made-easy-otel-collector"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location / {
EOF
  append_https_proxy "https://grafana:3000" "grafana"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }
}
EOF

  append_server_header "${support_host}"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  location / {
EOF
  append_http_proxy "http://zammad-nginx:8080"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }
}
EOF

  if [ -n "$airflow_host" ]; then
    append_server_header "${airflow_host}"
    cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  location / {
EOF
    append_http_proxy "http://airflow:8080"
    cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }
}
EOF
  fi
}

render_public() {
  apex_host="${EDGE_PUBLIC_APEX_HOST:-__MISSING_PUBLIC_APEX_HOST__}"
  canonical_host="${EDGE_PUBLIC_CANONICAL_HOST:-__MISSING_PUBLIC_CANONICAL_HOST__}"

  require_edge_setting "PUBLIC_APEX_HOST" "$apex_host"
  require_edge_setting "PUBLIC_CANONICAL_HOST" "$canonical_host"

  append_server_header "${apex_host}"
  cat >> /etc/nginx/conf.d/default.conf <<EOF
  return 308 https://${canonical_host}\$request_uri;
}
EOF

  append_server_header "_ ${canonical_host}"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  location /auth/v1/ {
EOF
  append_http_proxy "http://kong:8000"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location /admin/v1/ {
EOF
  append_http_proxy "http://kong:8000"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location /system/v1/ {
EOF
  append_http_proxy "http://kong:8000"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location /data-catalog/v1/ {
EOF
  append_http_proxy "http://kong:8000"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location /rulebuilder/v1/ {
EOF
  append_http_proxy "http://kong:8000"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location /v1/ {
EOF
  append_http_proxy "http://kong:8000"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location /health {
EOF
  append_http_proxy "http://kong:8000"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location /api-docs {
EOF
  append_http_proxy "http://kong:8000"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location /api-docs-json {
EOF
  append_http_proxy "http://kong:8000"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location /rulebuilder/ {
EOF
  append_http_proxy "http://kong:8000"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location /iam/ {
    proxy_set_header X-Forwarded-Prefix /iam;
EOF
  append_http_proxy "http://keycloak:8080"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location /metadata/ {
    proxy_set_header X-Forwarded-Prefix /metadata;
EOF
  append_https_proxy "https://openmetadata-server:8585" "openmetadata-server"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location /observability/otlp/ {
EOF
  append_https_proxy_with_uri "https://dq-made-easy-otel-collector:4318/" "dq-made-easy-otel-collector"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location /observability/ {
    proxy_set_header X-Forwarded-Prefix /observability;
EOF
  append_https_proxy "https://grafana:3000" "grafana"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location /support/ {
    proxy_set_header X-Forwarded-Prefix /support;
EOF
  append_http_proxy "http://zammad-nginx:8080"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location /ops/kong/ {
    proxy_set_header X-Forwarded-Prefix /ops/kong;
EOF
  append_http_proxy "http://kong:8002"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }

  location / {
EOF
  append_https_proxy "https://frontend:443" "frontend"
  cat >> /etc/nginx/conf.d/default.conf <<'EOF'
  }
}
EOF
}

case "$mode" in
  local)
    render_local
    ;;
  public)
    render_public
    ;;
  *)
    echo "Unsupported EDGE_MODE: $mode" >&2
    exit 1
    ;;
esac