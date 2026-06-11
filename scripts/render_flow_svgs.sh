#!/usr/bin/env bash
set -euo pipefail


# Purpose: Rebuild every Mermaid-backed SVG under docs/flows.
#
# What it does:
# - Walks the docs/flows directory for Markdown files.
# - Derives the matching .svg path for each Markdown file.
# - Delegates conversion to scripts/render_embedded_mermaid.sh.
# - Fails fast if the flows directory or renderer is unavailable.
#
# Version: 1.0
# Last modified: 2026-06-10

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
my_name="render_flow_svgs.sh"

source "$ROOT_DIR/scripts/supporting/logging.sh"

flows_dir="${1:-$ROOT_DIR/docs/flows}"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: scripts/render_flow_svgs.sh [flows-dir]

Rebuilds all SVG diagrams for Markdown files in the given flows directory.
Defaults to docs/flows in the repository root.
EOF
  exit 0
fi

if [[ ! -d "$flows_dir" ]]; then
  error "$my_name" "Flows directory not found: $flows_dir"
  exit 1
fi

renderer="$ROOT_DIR/scripts/render_embedded_mermaid.sh"
if [[ ! -x "$renderer" ]]; then
  error "$my_name" "Renderer script not found or not executable: $renderer"
  exit 1
fi

rendered_count=0

while IFS= read -r -d '' markdown_file; do
  svg_file="${markdown_file%.md}.svg"
  echo "Rendering $(basename "$markdown_file") -> $(basename "$svg_file")"
  "$renderer" "$markdown_file" "$svg_file"
  rendered_count=$((rendered_count + 1))
done < <(find "$flows_dir" -maxdepth 1 -type f -name '*.md' -print0)

if [[ "$rendered_count" -eq 0 ]]; then
  error "$my_name" "No Markdown files found in $flows_dir"
  exit 1
fi

echo "Rendered $rendered_count flow diagram(s)"