#!/bin/sh
set -eu

escape_js() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

# ---------------------------------------------------------------------------
# Validate required environment variables
# ---------------------------------------------------------------------------

CONFIGURED_API_URL="${KONG_PUBLIC_URL:-}"

if [ -z "$CONFIGURED_API_URL" ]; then
  echo "KONG_PUBLIC_URL must be set before starting the frontend container." >&2
  exit 1
fi

case "$CONFIGURED_API_URL" in
  http://*|https://*)
    ;;
  *)
    echo "Frontend runtime API URL must be an absolute http(s) URL, got: $CONFIGURED_API_URL" >&2
    exit 1
    ;;
esac

KONG_PUBLIC_URL="$(escape_js "$CONFIGURED_API_URL")"

FRONTEND_CERT_FILE="${FRONTEND_CERT_FILE:-}"
FRONTEND_KEY_FILE="${FRONTEND_KEY_FILE:-}"
KONG_SERVICE_FQDN="${KONG_SERVICE_FQDN:-}"

if [ -z "$FRONTEND_CERT_FILE" ]; then
  echo "FRONTEND_CERT_FILE must be set (e.g. dq-made-easy.jac.dot+3.pem)." >&2
  exit 1
fi
if [ -z "$FRONTEND_KEY_FILE" ]; then
  echo "FRONTEND_KEY_FILE must be set (e.g. dq-made-easy.jac.dot+3-key.pem)." >&2
  exit 1
fi
if [ -z "$KONG_SERVICE_FQDN" ]; then
  echo "KONG_SERVICE_FQDN must be set (e.g. kong.jac.dot)." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Render the nginx config template
# ---------------------------------------------------------------------------

NGINX_CONF_TEMPLATE="/etc/nginx/conf.d/default.conf.template"
NGINX_CONF="/etc/nginx/conf.d/default.conf"

if [ -f "$NGINX_CONF_TEMPLATE" ]; then
  sed \
    -e "s|{{FRONTEND_CERT_FILE}}|${FRONTEND_CERT_FILE}|g" \
    -e "s|{{FRONTEND_KEY_FILE}}|${FRONTEND_KEY_FILE}|g" \
    -e "s|{{KONG_SERVICE_FQDN}}|${KONG_SERVICE_FQDN}|g" \
    "$NGINX_CONF_TEMPLATE" > "$NGINX_CONF"
else
  echo "Missing nginx config template: $NGINX_CONF_TEMPLATE" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Render runtime JS config
# ---------------------------------------------------------------------------

if [ -f /usr/share/nginx/html/runtime-config.template.js ]; then
  sed "s|\${KONG_PUBLIC_URL}|${KONG_PUBLIC_URL}|g" \
    /usr/share/nginx/html/runtime-config.template.js \
    > /usr/share/nginx/html/runtime-config.js
else
  # Avoid heredoc; write the JS runtime config atomically using printf.
  printf '%s\n' \
    "window.__DQ_CONFIG__ = Object.assign({}, window.__DQ_CONFIG__, {" \
    "  API_BASE_URL: \"${KONG_PUBLIC_URL}/api\"" \
    "});" \
    > /usr/share/nginx/html/runtime-config.js
fi

exec nginx -g 'daemon off;'
