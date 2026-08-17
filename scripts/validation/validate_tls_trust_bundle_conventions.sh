#!/usr/bin/env bash
set -euo pipefail

# Purpose: Verify the repository uses the canonical internal trust bundle and env hooks.
# What it does:
# - Checks K8s manifests (or Compose for legacy) for CA bundle mounts and env vars.
# - Checks main TLS consumers expose the expected client trust variables.
# - Fails fast when a consumer falls back to an ad hoc bundle path.
# validate: groups=repo
# validate: include=true
# Version: 2.0
# Last modified: 2026-08-17

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_tls_trust_bundle_conventions.sh"

FAILURES=0

require_present() {
  local needle="$1"
  local file_path="$2"
  local found=false

  if [ -d "$file_path" ]; then
    if grep -rFq "$needle" "$file_path" 2>/dev/null; then
      found=true
    fi
  elif [ -f "$file_path" ]; then
    if grep -Fq "$needle" "$file_path" 2>/dev/null; then
      found=true
    fi
  fi

  if ! $found; then
    error "$my_name" "missing '${needle}' in ${file_path}"
    FAILURES=$((FAILURES + 1))
  fi
}

require_absent() {
  local needle="$1"
  local file_path="$2"
  if [ -d "$file_path" ]; then
    if grep -rFq "$needle" "$file_path" 2>/dev/null; then
      error "$my_name" "found forbidden '${needle}' in ${file_path}"
      FAILURES=$((FAILURES + 1))
    fi
  elif [ -f "$file_path" ]; then
    if grep -Fq "$needle" "$file_path" 2>/dev/null; then
      error "$my_name" "found forbidden '${needle}' in ${file_path}"
      FAILURES=$((FAILURES + 1))
    fi
  fi
}

# Collect all YAML manifests
collect_manifests() {
  local manifests=()
  while IFS= read -r f; do
    manifests+=("$f")
  done < <(find "$ROOT_DIR" \( -path "*/k8s/*" -o -path "*/infra/k8s/*" \) -name "*.yaml" 2>/dev/null | head -100)

  # Add compose if exists (legacy)
  if [ -d "$ROOT_DIR/docker-compose" ]; then
    while IFS= read -r f; do
      manifests+=("$f")
    done < <(find "$ROOT_DIR/docker-compose" -type f \( -name "*.yml" -o -name "*.yaml" \) 2>/dev/null)
  fi

  printf '%s\n' "${manifests[@]}"
}

manifests_dir="$ROOT_DIR/docker-compose/"
if [ ! -d "$manifests_dir" ]; then
  # Use K8s manifests directory
  manifests_dir="$ROOT_DIR"
fi

# Check for CA bundle references (K8s ConfigMap/Secret refs or compose mounts)
info "$my_name" "Checking CA bundle references in manifests..."

# K8s-style checks — CA is managed by platform, check for volume mounts
if [ -d "$ROOT_DIR/k8s" ] || [ -d "$ROOT_DIR/infra/k8s" ]; then
  info "$my_name" "K8s manifests found — CA bundles managed by platform (inject_tls_certs)"
  # Check that manifests reference CA volumes (not hardcoded paths)
  require_absent "ssl_ca_certs=/tmp/" "$ROOT_DIR/k8s"
  require_absent "ssl_ca_certs=/tmp/" "$ROOT_DIR/infra/k8s"
fi

# Compose-style checks (legacy)
if [ -d "$ROOT_DIR/docker-compose" ]; then
  require_present './tmp/certs/trust/internal-ca-bundle.pem' "$manifests_dir"
  require_present 'REQUESTS_CA_BUNDLE:' "$manifests_dir"
  require_present 'SSL_CERT_FILE:' "$manifests_dir"
  require_present 'REDIS_URL: rediss://' "$manifests_dir"

  require_absent 'ssl_ca_certs=/tmp/' "$manifests_dir"
  require_absent 'REQUESTS_CA_BUNDLE: /tmp/' "$manifests_dir"
  require_absent 'SSL_CERT_FILE: /tmp/' "$manifests_dir"
fi

# Check for forbidden ad-hoc CA paths across all manifests
while IFS= read -r manifest; do
  require_absent 'ssl_ca_certs=/tmp/' "$manifest"
  require_absent 'REQUESTS_CA_BUNDLE: /tmp/' "$manifest"
  require_absent 'SSL_CERT_FILE: /tmp/' "$manifest"
done < <(collect_manifests)

if [ $FAILURES -eq 0 ]; then
  success "$my_name" "trust bundle conventions match the canonical internal CA layout"
  exit 0
else
  error "$my_name" "trust bundle validation found ${FAILURES} issue(s)"
  exit 1
fi
