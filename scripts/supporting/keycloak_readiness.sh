#!/usr/bin/env bash

# Purpose: Provide a shared Keycloak readiness polling helper.
#
# What it does:
# - Exposes wait_for_keycloak_ready(url, [label]).
# - Polls an OpenID configuration/readiness URL with retries.
# - Logs classified curl failures to help diagnose startup issues.
# - Uses the repo CA bundle for local mkcert TLS traffic when available.
#
# Version: 1.1
# Last modified: 2026-07-14

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/supporting/logging.sh"
my_name="keycloak_readiness.sh"

wait_for_keycloak_ready() {
  local ready_url="$1"
  local service_label="${2:-Keycloak}"
  local max_attempts="${KEYCLOAK_READINESS_MAX_ATTEMPTS:-10}"
  local sleep_seconds="${KEYCLOAK_READINESS_SLEEP_SECONDS:-3}"
  local connect_timeout=10
  local max_time=20
  local is_ready=false
  local curl_status=0
  local curl_error_output=""
  local last_failure_kind="unknown"
  local curl_args=(--connect-timeout "$connect_timeout" --max-time "$max_time" -fsS -o /dev/null)
  local ca_bundle="${CURL_CA_BUNDLE:-${SSL_CERT_FILE:-}}"

  if [ -n "$ca_bundle" ] && [ -f "$ca_bundle" ]; then
    curl_args+=(--cacert "$ca_bundle")
  fi

  classify_curl_failure() {
    local status="$1"
    local error_text="$2"

    case "$status" in
      6)
        echo "url/dns"
        return
        ;;
      7)
        echo "connect"
        return
        ;;
      28)
        if printf '%s' "$error_text" | grep -Eqi 'resolve|resolving'; then
          echo "url/dns-timeout"
          return
        fi
        if printf '%s' "$error_text" | grep -Eqi 'connect|connection|refused'; then
          echo "connect-timeout"
          return
        fi
        echo "max-time-timeout"
        return
        ;;
      22)
        echo "http-status"
        return
        ;;
      *)
        echo "other"
        return
        ;;
    esac
  }

  for attempt in $(seq 1 "$max_attempts"); do
    curl_status=0
    if curl_error_output="$(curl "${curl_args[@]}" "$ready_url" 2>&1)"; then
      is_ready=true
      break
    else
      curl_status=$?
    fi

    last_failure_kind="$(classify_curl_failure "$curl_status" "$curl_error_output")"

    printf '.'

    if (( attempt % 10 == 0 )); then
      info "$my_name" "  waiting for ${service_label}... (${attempt}/${max_attempts})"
      info "$my_name" "  last curl failure: kind=${last_failure_kind} exit=${curl_status} url=${ready_url}"
    fi
    if [ "$sleep_seconds" != "0" ]; then
      sleep "$sleep_seconds"
    fi
  done

  if [ "$is_ready" = true ]; then
    return 0
  fi

  error "$my_name" "  ${service_label} readiness failed after ${max_attempts} attempts"
  error "$my_name" "  curl diagnostics: kind=${last_failure_kind} exit=${curl_status} url=${ready_url} connect-timeout=${connect_timeout}s max-time=${max_time}s"
  if [ -n "$curl_error_output" ]; then
    error "$my_name" "  curl error: ${curl_error_output}"
  fi

  return 1
}
