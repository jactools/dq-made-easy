#!/usr/bin/env bash
# ============================================================================
# sync_overlay_tags.sh — Update Kustomize overlay image tags from env file.
#
# Reads DQ_*_TAG values from .env.<env>.local, extracts base versions,
# and updates the overlay kustomization.yaml files with newTag.
#
# If a DQ_*_TAG is not set in the env file, falls back to the major.minor
# version from VERSION_MANIFEST.json (same source the build script uses).
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV="${ENV:-dev}"

source "${ROOT_DIR}/.env.${ENV}.local"

# Read major.minor from VERSION_MANIFEST.json (same as build script)
MAJOR_MINOR=$(node -e '
  const fs = require("fs");
  const m = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
  const v = String(m?.apps?.ui || "").trim();
  console.log(v.split(".").slice(0, 2).join("."));
' "${ROOT_DIR}/VERSION_MANIFEST.json")

# All images use the manifest major.minor version.
# The build script computes this same value from VERSION_MANIFEST.json.
export TAG_API="$MAJOR_MINOR"
export TAG_DB="$MAJOR_MINOR"
export TAG_ENGINE="$MAJOR_MINOR"
export TAG_PROFILING="$MAJOR_MINOR"
export TAG_FRONTEND="$MAJOR_MINOR"
export TAG_METADATA="$MAJOR_MINOR"
export TAG_KEYCLOAK="$MAJOR_MINOR"
export TAG_KAFKA_CONSUMER="$MAJOR_MINOR"

python3 - "$ROOT_DIR" \
  "$TAG_API" "$TAG_DB" "$TAG_ENGINE" "$TAG_PROFILING" "$TAG_FRONTEND" \
  "$TAG_METADATA" "$TAG_KEYCLOAK" "$TAG_KAFKA_CONSUMER" << 'PYEOF'
import re, os, sys

root_dir = sys.argv[1]
tags = {
    "dq-made-easy-api": sys.argv[2],
    "dq-made-easy-db": sys.argv[3],
    "dq-made-easy-engine": sys.argv[4],
    "dq-made-easy-profiling": sys.argv[5],
    "dq-made-easy-llm": sys.argv[4],           # same as engine
    "dq-made-easy-kafka-consumer": sys.argv[6],
    "dq-made-easy-openmetadata-db": sys.argv[4],
    "dq-made-easy-openmetadata": sys.argv[4],
    "dq-made-easy-openmetadata-server": sys.argv[4],
    "dq-made-easy-frontend": sys.argv[7],
    "dq-made-easy-metadata-configure": sys.argv[8],
    "dq-made-easy-keycloak-seed-artifacts": sys.argv[9],
}

overlay_dir = os.path.join(root_dir, "infra/k8s/overlays")
updated = 0

for root, dirs, files in os.walk(overlay_dir):
    for f in files:
        if f != "kustomization.yaml":
            continue
        path = os.path.join(root, f)
        with open(path) as fh:
            lines = fh.readlines()

        new_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]
            new_lines.append(line)
            # Look for name: ...dq-made-easy-xxx...
            match = re.search(r'name:.*?(dq-made-easy-\S+)', line)
            if match:
                image = match.group(1)
                if image in tags:
                    j = i + 1
                    while j < len(lines) and lines[j].strip() == '':
                        new_lines.append(lines[j])
                        j += 1
                    if j < len(lines) and 'newName' in lines[j]:
                        new_lines.append(lines[j])
                        j += 1
                    if j < len(lines) and 'newTag' in lines[j]:
                        indent = re.match(r'(\s+)', lines[j]).group(1) or '    '
                        new_lines.append(f'{indent}newTag: "{tags[image]}"\n')
                        j += 1
                    else:
                        new_lines.append('    newTag: "{}"\n'.format(tags[image]))
                    updated += 1
                    print(f"  {os.path.basename(root)}: {image} -> {tags[image]}")
                    i = j
                    continue
            i += 1

        with open(path, 'w') as fh:
            fh.writelines(new_lines)

print(f"\nUpdated {updated} image tags across overlays.")
PYEOF
