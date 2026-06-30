#!/usr/bin/env bash
set -euo pipefail


# Purpose: Run validation and smoke-test scripts by group.
#
# What it does:
# - Auto-discovers internal validation implementations under scripts/validation/
# - Reads group membership from header tags (e.g. '# validate: groups=repo,api')
# - Runs the corresponding user-facing top-level scripts for a selected group
# - Emits versioned test proof JSON and republishes docs for api/regression/ui/engine/profiling validations
#
# Version: 1.5
# Last modified: 2026-05-01

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/test_proof.sh"

my_name="validate.sh"

print_usage() {
  cat <<'EOF'
Usage: scripts/validate.sh [group]

Runs repository validation and smoke-test scripts.

Groups:
  all            Run everything (default)
  smoke          Run all repo smoke-test scripts (scripts/smoke_*.sh, scripts/smoke_test*.sh)
  repo           Repo-only checks (no docker)
  governance     Governance logging/policy gates used by CI
  api            API-facing validations (may use docker)
  regression     End-to-end regression validations
  ui             UI->gateway->api propagation validations (docker)
  engine         Engine validations
  profiling      Profiling worker lifecycle validations (docker)
  observability  Monitoring/observability validations (docker)
  openmetadata   OpenMetadata OTel smoke validation (docker)
  other          Untagged validate_*.sh scripts

Options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use an explicit env file
  --list         List groups and included scripts
  --smoke        Alias for: scripts/validate.sh smoke
  -h, --help     Show this help

Examples:
  scripts/validate.sh
  scripts/validate.sh repo
  scripts/validate.sh regression
  scripts/validate.sh observability
  scripts/validate.sh other
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "$my_name" "Missing required command: $cmd"
    exit 1
  fi
}

trim_ws() {
  local s="$1"
  s="${s#"${s%%[!$' \t\r\n']*}"}"
  s="${s%"${s##*[!$' \t\r\n']}"}"
  printf '%s' "$s"
}

to_lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

discover_validate_scripts() {
  # Emit absolute paths, sorted.
  find "${ROOT_DIR}/scripts/validation" -maxdepth 1 -type f -name 'validate_*.sh' -print | LC_ALL=C sort
}

discover_smoke_scripts() {
  # Emit absolute paths, sorted.
  find "${ROOT_DIR}/scripts/validation" -maxdepth 1 -type f \( -name 'smoke_*.sh' -o -name 'smoke_test*.sh' \) -print | LC_ALL=C sort
}

display_script_rel() {
  local internal_abs="$1"
  printf 'scripts/%s' "$(basename "$internal_abs")"
}

read_validate_header() {
  local script_path="$1"
  # Only scan a small header window for tags.
  sed -n '1,120p' "$script_path"
}

validate_get_groups() {
  local script_path="$1"
  local header
  header="$(read_validate_header "$script_path")"

  # Supports either:
  #   # validate: groups=repo,api
  #   # validate: group=repo
  local line
  line="$(printf '%s\n' "$header" | grep -E '^[[:space:]]*#[[:space:]]*validate:[[:space:]]*groups?=' | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    printf ''
    return 0
  fi

  local value
  value="${line#*=}"
  value="$(trim_ws "$value")"
  value="$(to_lower "$value")"
  # normalize separators: commas -> spaces
  value="$(printf '%s' "$value" | tr ',' ' ')"
  # collapse multiple spaces
  value="$(printf '%s' "$value" | tr -s ' ' | sed 's/^ //; s/ $//')"
  printf '%s' "$value"
}

validate_get_include() {
  local script_path="$1"
  local header
  header="$(read_validate_header "$script_path")"

  local line
  line="$(printf '%s\n' "$header" | grep -E '^[[:space:]]*#[[:space:]]*validate:[[:space:]]*include=' | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    printf 'true'
    return 0
  fi

  local value
  value="${line#*=}"
  value="$(trim_ws "$value")"
  value="$(to_lower "$value")"
  if [[ "$value" == "false" || "$value" == "0" || "$value" == "no" ]]; then
    printf 'false'
    return 0
  fi

  printf 'true'
}

validate_get_ignore() {
  local script_path="$1"
  local header
  header="$(read_validate_header "$script_path")"

  local line
  line="$(printf '%s\n' "$header" | grep -E '^[[:space:]]*#[[:space:]]*validate:[[:space:]]*ignore=' | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    printf 'false'
    return 0
  fi

  local value
  value="${line#*=}"
  value="$(trim_ws "$value")"
  value="$(to_lower "$value")"
  if [[ "$value" == "true" || "$value" == "1" || "$value" == "yes" ]]; then
    printf 'true'
    return 0
  fi

  printf 'false'
}

has_group() {
  local groups_str="$1"
  local group="$2"
  if [[ "$group" == "all" ]]; then
    return 0
  fi

  if [[ "$group" == "other" ]]; then
    return 1
  fi

  local g
  for g in $groups_str; do
    if [[ "$g" == "$group" ]]; then
      return 0
    fi
  done
  return 1
}

list_groups() {
  local groups
  groups="all smoke repo governance api regression ui engine profiling observability openmetadata other"

  info "$my_name" "Groups:"
  for g in $groups; do
    info "$my_name" "- $g"

    if [[ "$g" == "all" ]]; then
      while IFS= read -r abs; do
        local rel
        rel="$(display_script_rel "$abs")"
        info "$my_name" "  - $rel"
      done < <(discover_smoke_scripts)

      while IFS= read -r abs; do
        local ignore include rel
        ignore="$(validate_get_ignore "$abs")"
        include="$(validate_get_include "$abs")"
        if [[ "$ignore" == "true" || "$include" != "true" ]]; then
          continue
        fi
        rel="$(display_script_rel "$abs")"
        info "$my_name" "  - $rel"
      done < <(discover_validate_scripts)
      continue
    fi

    if [[ "$g" == "smoke" ]]; then
      while IFS= read -r abs; do
        local rel
        rel="$(display_script_rel "$abs")"
        info "$my_name" "  - $rel"
      done < <(discover_smoke_scripts)
      continue
    fi

    while IFS= read -r abs; do
      local ignore include groups_str
      ignore="$(validate_get_ignore "$abs")"
      if [[ "$ignore" == "true" ]]; then
        continue
      fi

      groups_str="$(validate_get_groups "$abs")"
      include="$(validate_get_include "$abs")"
      if [[ "$g" == "other" ]]; then
        if [[ -n "$groups_str" ]]; then
          continue
        fi
      else
        if [[ -z "$groups_str" ]]; then
          continue
        fi
        if ! has_group "$groups_str" "$g"; then
          continue
        fi
      fi

      local rel
      rel="$(display_script_rel "$abs")"
      if [[ "$include" == "true" ]]; then
        info "$my_name" "  - $rel"
      else
        info "$my_name" "  - $rel (helper)"
      fi
    done < <(discover_validate_scripts)
  done
}

run_one() {
  local rel="$1"
  local abs="${ROOT_DIR}/${rel}"
  local bash_bin="${BASH:-bash}"
  local command_text="${bash_bin} ${abs}"
  local proof_path=""
  local exit_code=0

  if [[ ! -f "$abs" ]]; then
    error "$my_name" "Missing script: $rel"
    exit 1
  fi

  if [[ "$bash_bin" == */* ]] && [[ ! -x "$bash_bin" ]]; then
    error "$my_name" "Current bash executable is not usable: $bash_bin"
    exit 1
  fi

  info "$my_name" "==> $rel"
  if "$bash_bin" "$abs"; then
    exit_code=0
  else
    exit_code=$?
  fi

  proof_path="$(record_validation_test_proof "$abs" "$group" "$exit_code" "$command_text")"
  if [[ -n "$proof_path" ]]; then
    "$ROOT_DIR/scripts/publish_test_proof.sh"
  fi

  return "$exit_code"
}

main() {
  local group="all"

  init_root_env_file "$ROOT_DIR"

  if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
    exit 1
  fi
  set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    print_usage
    exit 0
  fi

  if [[ "${1:-}" == "--list" ]]; then
    list_groups
    exit 0
  fi

  if [[ "${1:-}" == "--smoke" ]]; then
    group="smoke"
    shift
  fi

  if [[ -n "${1:-}" ]]; then
    group="$1"
  fi

  case "$group" in
    all|smoke|repo|governance|api|regression|ui|engine|profiling|observability|openmetadata|other)
      ;;
    *)
      error "$my_name" "Unknown group '$group'"
      info "$my_name" ""
      print_usage >&2
      exit 2
      ;;
  esac

  require_cmd bash

  if [[ ! -f "$ROOT_ENV_FILE" ]]; then
    error "$my_name" "Env file not found: $ROOT_ENV_FILE"
    exit 2
  fi

  export ROOT_ENV_FILE
  if ! source_selected_root_env_file; then
    exit 1
  fi

  info "$my_name" "=============================================="
  info "$my_name" "Validation Runner"
  info "$my_name" "=============================================="
  info "$my_name" "Group: ${group}"
  info "$my_name" "Environment: $(describe_root_env_file_selection "$ROOT_DIR" "$ROOT_ENV_FILE")"

  local had_any="false"

  if [[ "$group" == "all" ]]; then
    while IFS= read -r abs; do
      had_any="true"
      run_one "$(display_script_rel "$abs")"
    done < <(discover_smoke_scripts)

    while IFS= read -r abs; do
      local ignore include
      ignore="$(validate_get_ignore "$abs")"
      if [[ "$ignore" == "true" ]]; then
        continue
      fi

      include="$(validate_get_include "$abs")"
      if [[ "$include" != "true" ]]; then
        continue
      fi

      had_any="true"
      run_one "$(display_script_rel "$abs")"
    done < <(discover_validate_scripts)

    if [[ "$had_any" != "true" ]]; then
      error "$my_name" "No validation or smoke scripts found"
      exit 2
    fi

    info "$my_name" "=============================================="
    success "$my_name" "Group '${group}'"
    return 0
  fi

  if [[ "$group" == "smoke" ]]; then
    while IFS= read -r abs; do
      had_any="true"
      run_one "$(display_script_rel "$abs")"
    done < <(discover_smoke_scripts)

    if [[ "$had_any" != "true" ]]; then
      error "$my_name" "No smoke scripts found (expected internal implementations under scripts/validation/ with top-level wrappers under scripts/)"
      exit 2
    fi

    info "$my_name" "=============================================="
    success "$my_name" "Group '${group}'"
    return 0
  fi

  while IFS= read -r abs; do
    local ignore include groups_str
    ignore="$(validate_get_ignore "$abs")"
    if [[ "$ignore" == "true" ]]; then
      continue
    fi

    groups_str="$(validate_get_groups "$abs")"
    include="$(validate_get_include "$abs")"

    if [[ "$group" == "other" ]]; then
      if [[ -n "$groups_str" ]]; then
        continue
      fi
    else
      if [[ -z "$groups_str" ]]; then
        continue
      fi
      if ! has_group "$groups_str" "$group"; then
        continue
      fi
      if [[ "$include" != "true" ]]; then
        continue
      fi
    fi

    had_any="true"
    run_one "$(display_script_rel "$abs")"
  done < <(discover_validate_scripts)

  if [[ "$had_any" != "true" ]]; then
    if [[ "$group" == "other" ]]; then
      success "$my_name" "No untagged validate scripts found"
      exit 0
    fi
    error "$my_name" "No scripts configured for group '${group}'"
    exit 2
  fi

  info "$my_name" "=============================================="
  success "$my_name" "Group '${group}'"
}

main "$@"
