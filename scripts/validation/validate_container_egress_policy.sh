#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate repository-managed stack definitions against the SEC-4 egress baseline.
#
# What it does:
# - Scans repository-managed Compose stack definitions for direct public URLs.
# - Fails on unapproved public destinations outside jaccloud.nl and jacloud.nl.
# - Warns on host-local bypass candidates such as host-gateway and pinned extra_hosts aliases so they stay reviewable.
#
# validate: groups=repo
#
# Version: 1.1
# Last modified: 2026-04-23

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_container_egress_policy.sh"

FAILURES=0
WARNINGS=0

trim_url() {
  local url="$1"
  local previous=""

  while [[ "$url" != "$previous" ]]; do
    previous="$url"
    url="${url%\"}"
    url="${url%\'}"
    url="${url%,}"
    url="${url%;}"
    url="${url%]}"
    url="${url%)}"
    url="${url%\}}"
  done

  printf '%s' "$url"
}

url_host() {
  local url="$1"
  local host_port

  host_port="${url#*://}"
  host_port="${host_port%%/*}"
  host_port="${host_port#*@}"

  if [[ "$host_port" == \[*\] ]]; then
    host_port="${host_port#\[}"
    host_port="${host_port%%]*}"
    printf '%s' "$host_port"
    return 0
  fi

  printf '%s' "${host_port%%:*}"
}

classify_host() {
  local host="$1"

  case "$host" in
    localhost|127.*|0.0.0.0|::1)
      printf '%s' 'local'
      return 0
      ;;
    host.docker.internal)
      printf '%s' 'host-bypass'
      return 0
      ;;
    jaccloud.nl|*.jaccloud.nl|jacloud.nl|*.jacloud.nl)
      printf '%s' 'approved-public'
      return 0
      ;;
    jac.dot|*.jac.dot)
      printf '%s' 'host-local'
      return 0
      ;;
  esac

  if [[ "$host" != *.* ]]; then
    printf '%s' 'internal'
    return 0
  fi

  printf '%s' 'unapproved-public'
}

report_warning() {
  WARNINGS=$((WARNINGS + 1))
  warning "$my_name" "$1"
}

report_failure() {
  FAILURES=$((FAILURES + 1))
  error "$my_name" "$1"
}

scan_stack_file() {
  local file_path="$1"
  local rel_path="${file_path#"$ROOT_DIR/"}"
  local match line_no raw_url url host classification

  while IFS= read -r match; do
    [[ -n "$match" ]] || continue
    line_no="${match%%:*}"
    raw_url="${match#*:}"
    url="$(trim_url "$raw_url")"
    host="$(url_host "$url")"
    classification="$(classify_host "$host")"

    case "$classification" in
      local|internal|host-local|approved-public|host-bypass)
        ;;
      unapproved-public)
        report_failure "${rel_path}:${line_no}: unapproved public destination ${url}."
        ;;
      *)
        report_failure "${rel_path}:${line_no}: unknown host classification for ${url}."
        ;;
    esac
  done < <(grep -Eno 'https?://[^[:space:]"'"'"']+' "$file_path" || true)

  while IFS= read -r match; do
    [[ -n "$match" ]] || continue
    report_warning "${rel_path}:${match%%:*}: host-local bypass candidate '${match#*:}' should remain explicitly reviewed for SEC-4."
  done < <(grep -En 'host\.docker\.internal|host-gateway|\.jac\.dot:[0-9]{1,3}(\.[0-9]{1,3}){3}' "$file_path" || true)
}

main() {
  local stack_files
  local file_path

  stack_files="${ROOT_DIR}/docker-compose/ ${ROOT_DIR}/dq-metadata/docker-compose.yml"

  info "$my_name" "Checking repository-managed stack definitions for SEC-4 egress policy drift..."

  for file_path in $stack_files; do
    if [[ ! -f "$file_path" ]]; then
      report_failure "Missing expected stack definition: ${file_path#"$ROOT_DIR/"}"
      continue
    fi
    scan_stack_file "$file_path"
  done

  if [[ $FAILURES -gt 0 ]]; then
    error "$my_name" "container egress policy validation found ${FAILURES} blocking issue(s)."
    if [[ $WARNINGS -gt 0 ]]; then
      info "$my_name" "${WARNINGS} warning(s) require review but did not block validation."
    fi
    exit 1
  fi

  success "$my_name" "container egress policy validation found no unapproved public destinations in tracked stack definitions"
  if [[ $WARNINGS -gt 0 ]]; then
    info "$my_name" "${WARNINGS} host-local bypass candidate(s) remain review-only findings."
  fi
}

main "$@"