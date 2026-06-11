#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate GX worker execution in the existing dq-engine-gx-worker container.
#
# What it does:
# - Loads the selected validation env file so the helper uses the canonical dev/test/prod contract.
# - Delegates to a small Python helper that runs the real GX smoke through the live API and worker containers.
# - Keeps the shell entrypoint thin so the validation logic is not embedded in shell heredocs.
#
# validate: groups=engine
# Version: 1.1
# Last modified: 2026-05-11

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/venv/bin/python"
HELPER="${SCRIPT_DIR}/validate_gx_worker_smoke.py"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  exit 1
fi

set -- "${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"
validate_selected_root_env_file "$ROOT_DIR" full

if ! source_selected_root_env_file; then
  exit 1
fi

if ! dq_source_seeded_user_credentials --quiet; then
  exit 1
fi

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"

if [[ -f "$KONG_CA_CERT" && -z "${CURL_CA_BUNDLE:-}" ]]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi

if [[ -f "$KONG_CA_CERT" && -z "${REQUESTS_CA_BUNDLE:-}" ]]; then
  export REQUESTS_CA_BUNDLE="$KONG_CA_CERT"
fi

if [[ $# -gt 0 ]]; then
  echo "Unknown arg: $1" >&2
  exit 2
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing required Python interpreter: $PYTHON_BIN" >&2
  exit 2
fi

exec "$PYTHON_BIN" "$HELPER" "$@"
