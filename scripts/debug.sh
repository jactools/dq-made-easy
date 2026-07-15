#!/usr/bin/env bash
set -euo pipefail

# Purpose: Ad-hoc Keycloak admin/debug command scratchpad.
#
# What it does:
# - Runs manual `kcadm.sh` commands used during local debugging.
# - Uses the selected repo env file for compose access.
# - Not intended to be run as part of automation.
#
# Version: 1.1
# Last modified: 2026-05-08

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
init_root_env_file "$ROOT_DIR"

my_name="debug.sh"

if [ ! -f "$ROOT_ENV_FILE" ]; then
  error "$my_name" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

validate_selected_root_env_file "$ROOT_DIR" full

info "$my_name" "find client internal id"
docker_compose exec keycloak /opt/keycloak/kcadm-trust.sh config credentials --server http://127.0.0.1:8080 --realm master --user admin --password admin
docker_compose exec keycloak /opt/keycloak/kcadm-trust.sh get clients -r jaccloud -q clientId=dq-rules-ui

info "$my_name" "convert to confidential + enable direct grants"
docker_compose exec keycloak /opt/keycloak/kcadm-trust.sh update clients/dq-rules-ui -r jaccloud -s 'publicClient=false' -s 'clientAuthenticatorType=client-secret' -s 'directAccessGrantsEnabled=true'

info "$my_name" "fetch the secret"
docker_compose exec keycloak /opt/keycloak/kcadm-trust.sh get clients/dq-rules-ui/client-secret -r jaccloud
