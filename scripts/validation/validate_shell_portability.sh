#!/usr/bin/env bash
set -euo pipefail

# Purpose: Check shell scripts for macOS and Debian Linux portability hazards.
#
# What it does:
# - Scans tracked `.sh` files for known non-portable Bash 4+ syntax.
# - Flags common BSD/GNU command usage differences that often break macOS or Debian workflows.
# - Supports file-level rule suppressions so exceptional cases can be documented explicitly.
#
# validate: groups=repo
# validate: include=false
#
# Version: 1.2
# Last modified: 2026-04-22
# Changelog:
# - 1.2 (2026-04-22): Narrowed base64 detection so encode pipelines are not misreported as decode issues.
# - 1.1 (2026-04-22): Added the initial helper-only shell portability validator for future CI use.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_shell_portability.sh"
SELF_REL="scripts/validate_shell_portability.sh"

rule_pattern() {
  case "$1" in
    bash4-readarray) printf '%s' '(^|[^[:alnum:]_])(readarray|mapfile)([^[:alnum:]_]|$)' ;;
    bash4-assoc-array) printf '%s' '(^|[^[:alnum:]_])(declare|local|typeset)[[:space:]]+-A([[:space:]]|$)' ;;
    bash4-case-mod) printf '%s' '\$\{[^}]*,,[^}]*\}|\$\{[^}]*\^\^[^}]*\}' ;;
    bash4-globstar) printf '%s' '(^|[^[:alnum:]_])shopt[[:space:]]+-s[[:space:]]+globstar([[:space:]]|$)' ;;
    bad-array-length-default) printf '%s' '\$\{#[^}]*:-[^}]*\}' ;;
    nonportable-sed-inplace) printf '%s' '(^|[^[:alnum:]_])sed[[:space:]]+-i([[:space:]]|$)|(^|[^[:alnum:]_])sed[[:space:]]+-i'
      printf "''([[:space:]]|$)|(^|[^[:alnum:]_])sed[[:space:]]+-i[[:space:]]+''([[:space:]]|$)"
      ;;
    gnu-readlink-f) printf '%s' '(^|[^[:alnum:]_])readlink[[:space:]]+-f([[:space:]]|$)' ;;
    gnu-date-d) printf '%s' '(^|[^[:alnum:]_])date([[:space:]][^#]*)?[[:space:]]-d([[:space:]]|$)' ;;
    nonportable-base64-decode) printf '%s' '(^|[^[:alnum:]_])base64([^|#]*)[[:space:]](-d|--decode)([[:space:]]|$)' ;;
    gnu-grep-p) printf '%s' '(^|[^[:alnum:]_])grep([[:space:]][^#]*)?[[:space:]]-P([[:space:]]|$)' ;;
    gnu-xargs-r) printf '%s' '(^|[^[:alnum:]_])xargs([[:space:]][^#]*)?[[:space:]]-r([[:space:]]|$)' ;;
    gnu-stat-c) printf '%s' '(^|[^[:alnum:]_])stat([[:space:]][^#]*)?[[:space:]]-c([[:space:]]|$)' ;;
    gnu-sort-v) printf '%s' '(^|[^[:alnum:]_])sort([[:space:]][^#]*)?[[:space:]]-V([[:space:]]|$)' ;;
    gnu-find-printf) printf '%s' '(^|[^[:alnum:]_])find([[:space:]][^#]*)?[[:space:]]-printf([[:space:]]|$)' ;;
    gnu-sed-r) printf '%s' '(^|[^[:alnum:]_])sed([[:space:]][^#]*)?[[:space:]]-r([[:space:]]|$)' ;;
    *)
      error "$my_name" "Unknown portability rule: $1"
      exit 2
      ;;
  esac
}

rule_message() {
  case "$1" in
    bash4-readarray) printf '%s' 'Bash 4+ readarray/mapfile is unavailable in macOS default bash 3.2.' ;;
    bash4-assoc-array) printf '%s' 'Associative arrays require Bash 4+ and are unavailable in macOS default bash 3.2.' ;;
    bash4-case-mod) printf '%s' 'Case-modifying parameter expansion (${var,,}, ${var^^}) requires Bash 4+.' ;;
    bash4-globstar) printf '%s' 'globstar requires Bash 4+ behavior and should be avoided in shared scripts.' ;;
    bad-array-length-default) printf '%s' 'Array-length expansion with a default clause is not portable in macOS bash 3.2.' ;;
    nonportable-sed-inplace) printf '%s' 'Inline sed editing differs between BSD and GNU sed; use a portable helper instead.' ;;
    gnu-readlink-f) printf '%s' 'readlink -f is GNU-specific and breaks on macOS.' ;;
    gnu-date-d) printf '%s' 'date -d is GNU-specific and breaks on macOS.' ;;
    nonportable-base64-decode) printf '%s' 'base64 decode flags differ between BSD and GNU implementations; use a wrapper.' ;;
    gnu-grep-p) printf '%s' 'grep -P is not portable across default macOS and Debian environments.' ;;
    gnu-xargs-r) printf '%s' 'xargs -r is GNU-specific and breaks on macOS.' ;;
    gnu-stat-c) printf '%s' 'stat -c is GNU-specific and breaks on macOS.' ;;
    gnu-sort-v) printf '%s' 'sort -V is GNU-specific and breaks on macOS.' ;;
    gnu-find-printf) printf '%s' 'find -printf is GNU-specific and breaks on macOS.' ;;
    gnu-sed-r) printf '%s' 'sed -r is GNU-specific; prefer sed -E for BSD and GNU portability.' ;;
    *)
      error "$my_name" "Unknown portability rule: $1"
      exit 2
      ;;
  esac
}

read_ignore_rules() {
  local file_path="$1"
  local header_line raw

  header_line="$(sed -n '1,80p' "$file_path" | grep -E '^[[:space:]]*#[[:space:]]*portability:[[:space:]]*ignore=' | tail -n 1 || true)"
  if [[ -z "$header_line" ]]; then
    printf ''
    return 0
  fi

  raw="${header_line#*=}"
  raw="$(printf '%s' "$raw" | tr ',' ' ' | tr -s ' ')"
  raw="${raw#${raw%%[![:space:]]*}}"
  raw="${raw%${raw##*[![:space:]]}}"
  printf '%s' "$raw"
}

ignore_has_rule() {
  local ignore_rules="$1"
  local wanted="$2"
  local entry

  for entry in $ignore_rules; do
    if [[ "$entry" == "$wanted" ]]; then
      return 0
    fi
  done
  return 1
}

discover_shell_scripts() {
  local rel

  if command -v git >/dev/null 2>&1 && git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    while IFS= read -r rel; do
      [[ -n "$rel" ]] || continue
      [[ "$rel" == "$SELF_REL" ]] && continue
      case "$rel" in
        */dist/*|dist/*|venv/*|*/venv/*|node_modules/*|*/node_modules/*)
          continue
          ;;
      esac
      printf '%s\n' "$rel"
    done < <(git -C "$ROOT_DIR" ls-files -- '*.sh' | LC_ALL=C sort)
    return 0
  fi

  find "$ROOT_DIR" -type f -name '*.sh' \
    -not -path "$ROOT_DIR/venv/*" \
    -not -path '*/node_modules/*' \
    -not -path '*/dist/*' \
    | LC_ALL=C sort \
    | while IFS= read -r abs; do
        rel="${abs#"$ROOT_DIR/"}"
        [[ "$rel" == "$SELF_REL" ]] && continue
        printf '%s\n' "$rel"
      done
}

scan_rule() {
  local file_path="$1"
  local rule_id="$2"
  local regex="$3"

  awk '
    /^[[:space:]]*#/ { next }
    { printf "%d:%s\n", NR, $0 }
  ' "$file_path" | grep -E "$regex" || true
}

main() {
  local rule_ids
  local rel abs ignore_rules regex message matches issues
  local total_issues=0

  rule_ids='bash4-readarray bash4-assoc-array bash4-case-mod bash4-globstar bad-array-length-default nonportable-sed-inplace gnu-readlink-f gnu-date-d nonportable-base64-decode gnu-grep-p gnu-xargs-r gnu-stat-c gnu-sort-v gnu-find-printf gnu-sed-r'

  while IFS= read -r rel; do
    [[ -n "$rel" ]] || continue
    abs="$ROOT_DIR/$rel"
    ignore_rules="$(read_ignore_rules "$abs")"

    for rule_id in $rule_ids; do
      if ignore_has_rule "$ignore_rules" "$rule_id"; then
        continue
      fi

      regex="$(rule_pattern "$rule_id")"
      message="$(rule_message "$rule_id")"
      matches="$(scan_rule "$abs" "$rule_id" "$regex")"
      [[ -n "$matches" ]] || continue

      issues=0
      while IFS= read -r match_line; do
        [[ -n "$match_line" ]] || continue
        issues=$((issues + 1))
        total_issues=$((total_issues + 1))
        error "$my_name" "$rel:$match_line: $message [$rule_id]"
      done <<EOF
$matches
EOF

      if [[ $issues -gt 0 ]]; then
        info "$my_name" "Add \\`# portability: ignore=${rule_id}\\` near the top of ${rel} only when the exception is deliberate and documented."
      fi
    done
  done < <(discover_shell_scripts)

  if [[ $total_issues -gt 0 ]]; then
    error "$my_name" "found ${total_issues} shell portability issue(s)."
    info "$my_name" "This script is available for manual use and future CI adoption, but is not auto-run by scripts/validate.sh yet."
    exit 1
  fi

  success "$my_name" "no shell portability issues detected by static rule set"
}

main "$@"