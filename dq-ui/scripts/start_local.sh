#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REPO_ROOT="$(cd "$ROOT/.." && pwd)"
source "$REPO_ROOT/scripts/supporting/root_env_file.sh"
init_root_env_file "$REPO_ROOT"

if [ ! -f "$ROOT_ENV_FILE" ]; then
	echo "Env file not found: $ROOT_ENV_FILE" >&2
	echo "Run with ROOT_ENV_FILE set explicitly or use ./scripts/common_startup.sh --env dev|test|prod." >&2
	exit 1
fi

mkdir -p logs .pids

read_root_env_var() {
	local key="$1"
	local env_file="$ROOT_ENV_FILE"
	local line value

	if [ ! -f "$env_file" ]; then
		return 1
	fi

	line=$(grep -E "^[[:space:]]*${key}=" "$env_file" | tail -n 1 || true)
	if [ -z "$line" ]; then
		return 1
	fi

	value="${line#*=}"
	# Strip surrounding single/double quotes if present.
	value="${value%\"}"
	value="${value#\"}"
	value="${value%\'}"
	value="${value#\'}"
	printf '%s' "$value"
}

resolve_root_env_var() {
	local key="$1"
	local stack="${2:-}"
	local raw_value resolved_value ref_key replacement

	case " $stack " in
		*" $key "*)
			return 1
			;;
	esac

	raw_value="$(read_root_env_var "$key" || true)"
	if [ -z "$raw_value" ]; then
		return 1
	fi

	resolved_value="$raw_value"
	while [[ "$resolved_value" =~ \$\{([A-Za-z_][A-Za-z0-9_]*)\} ]]; do
		ref_key="${BASH_REMATCH[1]}"
		replacement="${!ref_key:-}"
		if [ -z "$replacement" ]; then
			replacement="$(resolve_root_env_var "$ref_key" "$stack $key" || true)"
		fi
		resolved_value="${resolved_value//\$\{$ref_key\}/$replacement}"
	done

	printf '%s' "$resolved_value"
}

is_absolute_http_url() {
	case "$1" in
		http://*|https://*) return 0 ;;
		*) return 1 ;;
	esac
}

resolve_local_proxy_target() {
	local configured_kong_url="${KONG_LOCAL_URL:-}"
	local repo_kong_local_url

	if is_absolute_http_url "$configured_kong_url"; then
		printf '%s' "$configured_kong_url"
		return 0
	fi

	repo_kong_local_url="$(resolve_root_env_var KONG_LOCAL_URL || true)"
	if is_absolute_http_url "$repo_kong_local_url"; then
		printf '%s' "$repo_kong_local_url"
		return 0
	fi

	echo "UI API target is not configured. Set KONG_LOCAL_URL before starting the local UI." >&2
	return 1
}

resolve_local_ui_api_url() {
	if [ "${VITE_DEV_HTTPS:-true}" = "true" ]; then
		printf '%s' '/api'
		return 0
	fi

	resolve_local_proxy_target
}

VITE_DEV_HTTPS="${VITE_DEV_HTTPS:-true}"
export VITE_DEV_HTTPS

VITE_HTTPS_KEY_FILE="${VITE_HTTPS_KEY_FILE:-$REPO_ROOT/tmp/certs/dq-made-easy.jac.dot+3-key.pem}"
VITE_HTTPS_CERT_FILE="${VITE_HTTPS_CERT_FILE:-$REPO_ROOT/tmp/certs/dq-made-easy.jac.dot+3.pem}"
export VITE_HTTPS_KEY_FILE
export VITE_HTTPS_CERT_FILE

# Local UI is started as a separate process (Vite), so it won't automatically inherit
# repo-level .env variables unless they are explicitly exported here.
if [ -z "${VITE_OTEL_ENDPOINT:-}" ]; then
	VITE_OTEL_ENDPOINT="$(read_root_env_var VITE_OTEL_ENDPOINT || true)"
	if [ -n "${VITE_OTEL_ENDPOINT:-}" ]; then
		export VITE_OTEL_ENDPOINT
	fi
fi

if [ -z "${VITE_OTEL_ENABLED:-}" ]; then
	VITE_OTEL_ENABLED="$(read_root_env_var VITE_OTEL_ENABLED || true)"
	if [ -n "${VITE_OTEL_ENABLED:-}" ]; then
		export VITE_OTEL_ENABLED
	fi
fi

if [ -z "${VITE_OTEL_SAMPLE_RATIO:-}" ]; then
	VITE_OTEL_SAMPLE_RATIO="$(read_root_env_var VITE_OTEL_SAMPLE_RATIO || true)"
	if [ -n "${VITE_OTEL_SAMPLE_RATIO:-}" ]; then
		export VITE_OTEL_SAMPLE_RATIO
	fi
fi

if [ -z "${VITE_SSO_PROVIDER:-}" ]; then
	VITE_SSO_PROVIDER="$(read_root_env_var VITE_SSO_PROVIDER || true)"
	if [ -n "${VITE_SSO_PROVIDER:-}" ]; then
		export VITE_SSO_PROVIDER
	fi
fi

if [ -z "${VITE_SSO_ISSUER_URL:-}" ]; then
	VITE_SSO_ISSUER_URL="$(read_root_env_var SSO_PUBLIC_ISSUER_URL || true)"
	if [ -n "${VITE_SSO_ISSUER_URL:-}" ]; then
		export VITE_SSO_ISSUER_URL
	fi
fi

if [ -z "${VITE_SSO_CLIENT_ID:-}" ]; then
	VITE_SSO_CLIENT_ID="$(read_root_env_var VITE_SSO_CLIENT_ID || true)"
	if [ -n "${VITE_SSO_CLIENT_ID:-}" ]; then
		export VITE_SSO_CLIENT_ID
	fi
fi

if [ -z "${VITE_SSO_ENABLED:-}" ]; then
	VITE_SSO_ENABLED="$(read_root_env_var VITE_SSO_ENABLED || true)"
	if [ -z "${VITE_SSO_ENABLED:-}" ]; then
		VITE_SSO_ENABLED="$(read_root_env_var SSO_ENABLED || true)"
	fi
	if [ -n "${VITE_SSO_ENABLED:-}" ]; then
		export VITE_SSO_ENABLED
	fi
fi

# Ensure idempotent startup: stop any previously launched local Vite instance.
if [ -f .pids/vite.pid ]; then
	OLD_PID=$(cat .pids/vite.pid)
	if kill -0 "$OLD_PID" 2>/dev/null; then
		echo "Stopping existing Vite (pid=$OLD_PID)"
		kill "$OLD_PID" 2>/dev/null || true
		sleep 1
	fi
	rm -f .pids/vite.pid
fi

# Also clean up stale Vite listeners on common fallback ports from previous runs.
if command -v lsof >/dev/null 2>&1; then
	STALE_VITE_PIDS=$(for p in {5173..5205}; do
		lsof -nP -iTCP:"$p" -sTCP:LISTEN -t 2>/dev/null || true
	done | sort -u)
	for pid in $STALE_VITE_PIDS; do
		cmd=$(ps -p "$pid" -o command= 2>/dev/null || true)
		if echo "$cmd" | grep -qi "vite"; then
			echo "Stopping stale Vite listener (pid=$pid)"
			kill "$pid" 2>/dev/null || true
		fi
	done
fi

LOCAL_UI_PROXY_TARGET="$(resolve_local_proxy_target)"
export KONG_LOCAL_URL="${KONG_LOCAL_URL:-$LOCAL_UI_PROXY_TARGET}"

# Derive the internal Vite env from the canonical KONG_LOCAL_URL input.
VITE_API_URL="$(resolve_local_ui_api_url)"
export VITE_API_URL

VITE_HOST="${VITE_HOST:-0.0.0.0}"
export VITE_HOST

if [ "$VITE_DEV_HTTPS" = "true" ]; then
	if [ ! -r "$VITE_HTTPS_KEY_FILE" ]; then
		echo "Missing HTTPS key file: $VITE_HTTPS_KEY_FILE" >&2
		exit 1
	fi
	if [ ! -r "$VITE_HTTPS_CERT_FILE" ]; then
		echo "Missing HTTPS cert file: $VITE_HTTPS_CERT_FILE" >&2
		exit 1
	fi
fi

VITE_PORT="${VITE_PORT:-5174}"
export VITE_PORT

# By default do not tail logs — set NO_TAIL=0 to keep tailing in the foreground
NO_TAIL="${NO_TAIL:-1}"
export NO_TAIL

echo "Starting Vite dev server (background) -> logs/vite.log"

echo "Using Vite host ${VITE_HOST} on port ${VITE_PORT}"
VITE_DEV_ARGS=(-- --host "$VITE_HOST" --port "$VITE_PORT" --strictPort)

# Build the Vite app before starting the dev server to ensure any build errors are caught early.
# Set SKIP_DIST_BUILD=true to skip this when the caller has already done a fresh build.
if [ "${SKIP_DIST_BUILD:-false}" != "true" ]; then
        npm run build
fi

# Start Vite detached so it doesn't rely on the calling shell staying open.
# Use `nohup` + redirect + `< /dev/null` and `disown` to fully detach.
if command -v nohup >/dev/null 2>&1; then
	nohup npm run dev "${VITE_DEV_ARGS[@]}" > logs/vite.log 2>&1 < /dev/null &
	VITE_PID=$!
	# disown so it doesn't get SIGHUP when this script exits
	disown $VITE_PID 2>/dev/null || true
elif command -v setsid >/dev/null 2>&1; then
	setsid npm run dev "${VITE_DEV_ARGS[@]}" > logs/vite.log 2>&1 < /dev/null &
	VITE_PID=$!
else
	# fallback to backgrounding with explicit input redirect
	npm run dev "${VITE_DEV_ARGS[@]}" > logs/vite.log 2>&1 < /dev/null &
	VITE_PID=$!
fi
echo $VITE_PID > .pids/vite.pid

# wait briefly and confirm Vite is listening on the expected port
sleep 1
if command -v lsof >/dev/null 2>&1; then
	if ! lsof -i tcp:"$VITE_PORT" -sTCP:LISTEN -n -P >/dev/null 2>&1; then
		echo "Warning: Vite didn't bind to port $VITE_PORT yet — check logs/vite.log"
		tail -n 50 logs/vite.log
	fi
fi

sleep 1

echo "Services started. Tail logs with Ctrl-C (services keep running)."
echo "To stop services: ./scripts/stop_local.sh"
if [ "${NO_TAIL:-0}" = "1" ] || [ "${CI:-}" = "true" ]; then
	echo "NO_TAIL set; not tailing logs. Services are running in background."
	exit 0
fi

tail -n +1 -f logs/api.log logs/vite.log
