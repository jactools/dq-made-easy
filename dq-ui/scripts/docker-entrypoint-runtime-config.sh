#!/bin/sh
set -eu

escape_js() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

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
