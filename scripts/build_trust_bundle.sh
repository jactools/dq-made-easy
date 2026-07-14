#!/usr/bin/env bash
# Purpose: Build and run the trust-bundle container to generate JKS/P12 truststores.
#
# The trust-bundle image collects all PEM certificates from tmp/certs/ and
# produces trust-bundle.jks, trust-bundle.p12, trust-bundle.pem and
# java-truststore-env.sh inside tmp/certs/trust/.
#
# This is a standalone step — it replaces the compose service 'trust-bundle'
# and must run BEFORE any docker-compose up.
#
# Usage:
#   ./scripts/build_trust_bundle.sh [--env dev] [--env-file PATH]
#
# Version: 1.0
# Last modified: 2026-07-14

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/env/selection.sh"

init_root_env_file "$ROOT_DIR"

# Consume --env / --env-file args (but don't error on unknowns)
consume_root_env_selection_args "$ROOT_DIR" "$@" 2>/dev/null || true

CERTS_DIR="$ROOT_DIR/tmp/certs"
TRUST_DIR="$CERTS_DIR/trust"
IMAGE_NAME="dq-made-easy-trust-bundle"

# Pre-flight: certs must exist (mkcert + create_certs.sh must run first)
if [ ! -d "$CERTS_DIR" ]; then
  error "build_trust_bundle.sh" "Certs directory missing: $CERTS_DIR"
  error "build_trust_bundle.sh" "Run create_certs.sh first"
  exit 1
fi

PEM_COUNT=$(find "$CERTS_DIR" -maxdepth 1 -type f \( -name '*.pem' -o -name '*.crt' \) \
  ! -name '*-key.pem' ! -name '*-key.crt' | wc -l)
if [ "$PEM_COUNT" -eq 0 ]; then
  error "build_trust_bundle.sh" "No PEM certificates found in $CERTS_DIR"
  exit 1
fi

info "build_trust_bundle.sh" "Building trust-bundle image..."
docker build -t "$IMAGE_NAME" \
  -f "$ROOT_DIR/docker/trust-bundle/Dockerfile" \
  "$ROOT_DIR" || {
  error "build_trust_bundle.sh" "Failed to build trust-bundle image"
  exit 1
}

info "build_trust_bundle.sh" "Running trust-bundle container (${PEM_COUNT} source certs)..."
docker run --rm \
  -v "$CERTS_DIR:/certs" \
  "$IMAGE_NAME" || {
  error "build_trust_bundle.sh" "Trust-bundle container failed"
  exit 1
}

# Verify output
if [ ! -f "$TRUST_DIR/trust-bundle.jks" ]; then
  error "build_trust_bundle.sh" "JKS not generated: $TRUST_DIR/trust-bundle.jks"
  exit 1
fi

success "build_trust_bundle.sh" "Trust bundle generated in $TRUST_DIR"
