#!/usr/bin/env bash
# ============================================================================
# sync_overlay_tags.sh — Update Kustomize overlay image tags from env file.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV="${ENV:-dev}"

source "${ROOT_DIR}/.env.${ENV}.local"

# Extract base versions (strip commit hash: 0.10-7a9c018 -> 0.10)
get_base_tag() {
  local var_name="$1"
  local full_tag="${!var_name:-}"
  if [ -z "$full_tag" ]; then
    echo "${DEFAULT_TAG}"
  else
    echo "${full_tag%%-*}"
  fi
}

export TAG_DEFAULT="${DQ_BASE_TAG%%-*}"
export TAG_API="${DQ_API_TAG%%-*}"
export TAG_ENGINE="${DQ_ENGINE_TAG%%-*}"
export TAG_FRONTEND="${DQ_FRONTEND_TAG%%-*}"
export TAG_PROFILING="${DQ_PROFILING_TAG%%-*}"
export TAG_DB="${DQ_DB_TAG%%-*}"
export TAG_METADATA="${DQ_METADATA_CONFIGURE_TAG%%-*}"
export TAG_KEYCLOAK="${DQ_KEYCLOAK_SEED_ARTIFACTS_TAG:-$TAG_DEFAULT}"
export TAG_KAFKA_CONSUMER="${DQ_KAFKA_CONSUMER_TAG%%-*}"

python3 << 'PYEOF'
import re, os, sys

tags = {
    "dq-made-easy-api": os.environ["TAG_API"],
    "dq-made-easy-db": os.environ["TAG_DB"],
    "dq-made-easy-engine": os.environ["TAG_ENGINE"],
    "dq-made-easy-profiling": os.environ["TAG_PROFILING"],
    "dq-made-easy-llm": os.environ["TAG_DEFAULT"],
    "dq-made-easy-kafka-consumer": os.environ["TAG_KAFKA_CONSUMER"],
    "dq-made-easy-openmetadata-db": os.environ["TAG_DEFAULT"],
    "dq-made-easy-openmetadata-server": os.environ["TAG_DEFAULT"],
    "dq-made-easy-frontend": os.environ["TAG_FRONTEND"],
    "dq-made-easy-metadata-configure": os.environ["TAG_METADATA"],
    "dq-made-easy-keycloak-seed-artifacts": os.environ["TAG_KEYCLOAK"],
}

root_dir = os.environ["ROOT_DIR"]
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
                    # Next non-empty line should be newName, then newTag
                    j = i + 1
                    while j < len(lines) and lines[j].strip() == '':
                        new_lines.append(lines[j])
                        j += 1
                    # newName line
                    if j < len(lines) and 'newName' in lines[j]:
                        new_lines.append(lines[j])
                        j += 1
                    # newTag line - replace it
                    if j < len(lines) and 'newTag' in lines[j]:
                        indent = re.match(r'(\s+)', lines[j]).group(1) or '    '
                        new_lines.append(f'{indent}newTag: "{tags[image]}"\n')
                        j += 1
                    else:
                        # Add newTag if missing
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
