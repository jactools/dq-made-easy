#!/usr/bin/env bash
set -euo pipefail


# Purpose: Convert the first embedded Mermaid diagram in a Markdown file into an SVG.
#
# What it does:
# - Extracts the first ```mermaid fenced block from a Markdown source file.
# - Writes the extracted diagram to a repo-local temporary .mmd file under tmp/.
# - Renders the extracted Mermaid with mmdc or npx to the requested SVG output path.
# - Uses the repo's internal Nexus npm config when it has to invoke npx.
# - Reuses an installed Chromium or Chrome executable so Puppeteer does not try to download one.
# - Fails fast if the source file, Mermaid block, or renderer is missing.
#
# Version: 1.4
# Last modified: 2026-06-10
# Changelog:
# - 1.4 (2026-06-10): Skip the Puppeteer browser download and point Mermaid CLI at an installed browser.
# - 1.3 (2026-06-10): Stop overriding the registry so npx uses dq-api/.npmrc directly.
# - 1.2 (2026-06-10): Source the canonical root env file before invoking Mermaid so NPM_TOKEN is available.
# - 1.1 (2026-06-10): Added npx fallback with the repo's internal Nexus npm config for fresh checkouts.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
my_name="render_embedded_mermaid.sh"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

init_root_env_file "$ROOT_DIR"
source_selected_root_env_file

if [[ -z "${NPM_TOKEN:-}" ]]; then
  error "$my_name" "NPM_TOKEN is missing after sourcing $ROOT_ENV_FILE"
  error "$my_name" "Source .env.dev.local before running the Mermaid renderer"
  exit 1
fi

usage() {
  cat <<'EOF'
Usage: scripts/render_embedded_mermaid.sh <input.md> <output.svg>

Extracts the first Mermaid fenced block from the Markdown input and renders it
to an SVG file using mmdc.
EOF
}

detect_puppeteer_executable_path() {
  if [[ -n "${PUPPETEER_EXECUTABLE_PATH:-}" && -x "${PUPPETEER_EXECUTABLE_PATH}" ]]; then
    printf '%s\n' "$PUPPETEER_EXECUTABLE_PATH"
    return 0
  fi

  local browser_candidates=(
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    "/Applications/Chromium.app/Contents/MacOS/Chromium"
  )

  local browser_path
  for browser_path in "${browser_candidates[@]}"; do
    if [[ -x "$browser_path" ]]; then
      printf '%s\n' "$browser_path"
      return 0
    fi
  done

  for browser_path in google-chrome chromium chromium-browser; do
    if command -v "$browser_path" >/dev/null 2>&1; then
      command -v "$browser_path"
      return 0
    fi
  done

  return 1
}

if [[ $# -ne 2 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

input_md="$1"
output_svg="$2"

if [[ ! -f "$input_md" ]]; then
  error "$my_name" "Input Markdown file not found: $input_md"
  exit 1
fi

run_mermaid_cli() {
  local puppeteer_executable_path

  if ! puppeteer_executable_path="$(detect_puppeteer_executable_path)"; then
    error "$my_name" "No installed Chrome or Chromium executable was found"
    return 1
  fi

  if command -v mmdc >/dev/null 2>&1; then
    PUPPETEER_SKIP_DOWNLOAD=1 PUPPETEER_EXECUTABLE_PATH="$puppeteer_executable_path" \
      mmdc -i "$diagram_mmd" -o "$output_svg"
    return $?
  fi

  if ! command -v npx >/dev/null 2>&1; then
    error "$my_name" "Neither mmdc nor npx is available in PATH"
    return 1
  fi

  npmrc_path="${MERMAID_NPMRC:-$ROOT_DIR/dq-api/.npmrc}"
  if [[ ! -f "$npmrc_path" ]]; then
    error "$my_name" "NPM config not found for npx fallback: $npmrc_path"
    return 1
  fi

  PUPPETEER_SKIP_DOWNLOAD=1 PUPPETEER_EXECUTABLE_PATH="$puppeteer_executable_path" \
    npm_config_userconfig="$npmrc_path" npx -y @mermaid-js/mermaid-cli -i "$diagram_mmd" -o "$output_svg"
}

mkdir -p "$ROOT_DIR/tmp"
work_dir="$(mktemp -d "$ROOT_DIR/tmp/render-embedded-mermaid.XXXXXX")"
trap 'rm -rf "$work_dir"' EXIT

diagram_mmd="$work_dir/diagram.mmd"

awk '
  BEGIN { in_block = 0; found = 0; closed = 0 }
  /^```mermaid[[:space:]]*$/ {
    if (!found) {
      in_block = 1
      found = 1
      next
    }
  }
  in_block && /^```[[:space:]]*$/ {
    in_block = 0
    closed = 1
    exit 0
  }
  in_block { print }
  END {
    if (!found) {
      exit 2
    }
    if (!closed) {
      exit 3
    }
  }
' "$input_md" > "$diagram_mmd" || {
  exit_code="$?"
  case "$exit_code" in
    2)
      error "$my_name" "No Mermaid fenced block found in $input_md"
      ;;
    3)
      error "$my_name" "Unterminated Mermaid fenced block in $input_md"
      ;;
    *)
      error "$my_name" "Failed to extract Mermaid from $input_md"
      ;;
  esac
  exit 1
}

if [[ ! -s "$diagram_mmd" ]]; then
  error "$my_name" "Extracted Mermaid block is empty: $input_md"
  exit 1
fi

mkdir -p "$(dirname "$output_svg")"

if ! run_mermaid_cli; then
  error "$my_name" "Mermaid rendering failed for $input_md"
  exit 1
fi

echo "Rendered $input_md -> $output_svg"