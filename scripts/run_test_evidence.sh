#!/usr/bin/env bash
set -euo pipefail

# Purpose: Run UI/API tests while storing command evidence in one central location.
# What it does:
# - Writes each run under test-results/evidence/<app_version>/<mode>/<timestamp>-<label>/
# - Captures command, output log, status, and metadata
# - Uses the repo-root Python virtual environment for API pytest runs
# Version: 1.0
# Last modified: 2026-05-26

usage() {
  cat <<'USAGE' >&2
Usage:
  scripts/run_test_evidence.sh ui [--label LABEL] -- [vitest args...]
  scripts/run_test_evidence.sh api [--label LABEL] -- [pytest args...]
  scripts/run_test_evidence.sh command [--label LABEL] -- <command> [args...]

Examples:
  scripts/run_test_evidence.sh ui -- src/components/Dashboard.test.tsx --run
  scripts/run_test_evidence.sh api -- tests/api/test_approvals_endpoints.py -q
  scripts/run_test_evidence.sh command --label ux-1-proof -- npm --prefix dq-ui test -- src/components/Dashboard.test.tsx --run
USAGE
}

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

slugify() {
  printf '%s' "$1" | LC_ALL=C tr -cs 'A-Za-z0-9._-' '-' | sed 's/^-//; s/-$//'
}

write_command_file() {
  command_file="$1"
  shift
  : > "$command_file"
  for part in "$@"; do
    printf '%s\n' "$part" >> "$command_file"
  done
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

mode="$1"
shift

case "$mode" in
  ui|api|command) ;;
  *)
    echo "Unsupported evidence mode: $mode" >&2
    usage
    exit 2
    ;;
esac

label="manual"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --label)
      shift
      if [[ $# -eq 0 ]]; then
        echo "--label requires a value" >&2
        exit 2
      fi
      label="$1"
      shift
      ;;
    --)
      shift
      break
      ;;
    *)
      break
      ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest_path="$repo_root/VERSION_MANIFEST.json"
timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
label_slug="$(slugify "$label")"
if [[ -z "$label_slug" ]]; then
  label_slug="manual"
fi

case "$mode" in
  ui|command)
    version_key="ui"
    ;;
  api)
    version_key="api"
    ;;
esac

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required to read ${manifest_path}" >&2
  exit 1
fi

app_version="$(jq -r --arg key "$version_key" '.apps[$key] // empty' "$manifest_path")"
if [[ -z "$app_version" ]]; then
  echo "Unable to read app version for ${version_key} from ${manifest_path}" >&2
  exit 1
fi

run_dir="$repo_root/test-results/evidence/$app_version/$mode/$timestamp-$label_slug"
mkdir -p "$run_dir"

case "$mode" in
  ui)
    cwd="$repo_root"
    cmd=(npm --prefix "$repo_root/dq-ui" test -- "$@")
    ;;
  api)
    cwd="$repo_root/dq-api/fastapi"
    python_runner="$repo_root/scripts/python_arm64.sh"
    venv_python="$repo_root/venv/bin/python"
    if [[ ! -x "$venv_python" ]]; then
      echo "Required repo-root venv Python is missing: venv/bin/python" >&2
      exit 1
    fi
    cmd=("$python_runner" --python-bin "$venv_python" -m pytest "$@" --junitxml "$run_dir/junit.xml")
    ;;
  command)
    if [[ $# -eq 0 ]]; then
      echo "command mode requires a command after --" >&2
      usage
      exit 2
    fi
    cwd="$repo_root"
    cmd=("$@")
    ;;
esac

write_command_file "$run_dir/command.txt" "cwd=$cwd" "mode=$mode" "label=$label" "command_parts:" "${cmd[@]}"

set +e
(
  cd "$cwd" && "${cmd[@]}"
) 2>&1 | tee "$run_dir/output.log"
cmd_status=${PIPESTATUS[0]}
set -e

printf '%s\n' "$cmd_status" > "$run_dir/status.txt"

metadata_file="$run_dir/metadata.json"
{
  printf '{\n'
  printf '  "app_version": "%s",\n' "$(json_escape "$app_version")"
  printf '  "mode": "%s",\n' "$(json_escape "$mode")"
  printf '  "label": "%s",\n' "$(json_escape "$label")"
  printf '  "timestamp_utc": "%s",\n' "$(json_escape "$timestamp")"
  printf '  "cwd": "%s",\n' "$(json_escape "$cwd")"
  printf '  "evidence_directory": "%s",\n' "$(json_escape "${run_dir#$repo_root/}")"
  printf '  "status": %s\n' "$cmd_status"
  printf '}\n'
} > "$metadata_file"

echo "Evidence written to ${run_dir#$repo_root/}"
exit "$cmd_status"
