# Purpose: Dedicated seed block for the keycloak profile.

generate_keycloak_seed_artifacts() {
  docker_compose --profile auth build keycloak-seed-artifacts || {
    error "$my_name" "Keycloak seed artifact image build failed"
    return 1
  }

  docker_compose --profile auth run --rm --no-deps keycloak-seed-artifacts || {
    error "$my_name" "Keycloak seed artifact generation failed"
    return 1
  }
}

sync_keycloak_seed_credentials_to_workspace() {
  local keycloak_container_id="$1"
  local workspace_environment_label workspace_stage_suffix
  local workspace_credentials_csv workspace_credentials_env

  workspace_environment_label="$(printf '%s' "${ENVIRONMENT:-}" | tr '[:upper:]' '[:lower:]')"
  case "$workspace_environment_label" in
    dev|development)
      workspace_stage_suffix=".dev"
      ;;
    test|testing)
      workspace_stage_suffix=".test"
      ;;
    prod|production)
      workspace_stage_suffix=".prod"
      ;;
    *)
      error "$my_name" "ENVIRONMENT must resolve to dev, test, or prod for Keycloak credential sync"
      return 1
      ;;
  esac

  workspace_credentials_csv="$ROOT_DIR/tmp/keycloak_seed_user_credentials${workspace_stage_suffix}.csv"
  workspace_credentials_env="$ROOT_DIR/tmp/keycloak_seed_user_credentials${workspace_stage_suffix}.env"

  info "$my_name" "Syncing generated Keycloak credential artifacts from container to workspace tmp (overwriting $workspace_credentials_csv and $workspace_credentials_env)..."
  docker cp "$keycloak_container_id:/opt/keycloak/realm-import/keycloak_seed_user_credentials.csv" "$workspace_credentials_csv" >/dev/null || return 1
  docker cp "$keycloak_container_id:/opt/keycloak/realm-import/keycloak_seed_user_credentials.env" "$workspace_credentials_env" >/dev/null || return 1

  info "$my_name" "✓ Keycloak credential artifacts synced to workspace tmp"
}

run_keycloak_kcadm() {
  local keycloak_container_id="$1"
  shift

  local attempt max_attempts output
  max_attempts=10

  attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if output="$(docker exec "$keycloak_container_id" /opt/keycloak/kcadm-trust.sh "$@" 2>&1)"; then
      printf '%s' "$output"
      return 0
    fi

    if printf '%s' "$output" | grep -Eq 'Connect to 127\.0\.0\.1:8080|Connection refused|HTTP request error'; then
      sleep 5
      attempt=$((attempt + 1))
      continue
    fi

    printf '%s\n' "$output" >&2
    return 1
  done

  printf '%s\n' "$output" >&2
  return 1
}

keycloak_realm_role_exists() {
  local keycloak_container_id="$1"
  local role_name="$2"
  local role_json role_attempt role_max_attempts

  role_max_attempts=5
  role_attempt=1

  while [ "$role_attempt" -le "$role_max_attempts" ]; do
    if [[ "$role_name" == *:* ]]; then
      if role_json="$(run_keycloak_kcadm "$keycloak_container_id" get roles -r "${KEYCLOAK_REALM}" -q "search=${role_name}" --fields name)"; then
        printf '%s' "$role_json" | jq -e --arg role "$role_name" 'any(.[]?; (.name // empty) == $role)' >/dev/null
        return $?
      fi
    else
      if run_keycloak_kcadm "$keycloak_container_id" get "roles/${role_name}" -r "${KEYCLOAK_REALM}" >/dev/null 2>&1; then
        return 0
      fi
    fi

    sleep 2
    role_attempt=$((role_attempt + 1))
  done

  return 1
}

sync_keycloak_seed_user_profiles() {
  local keycloak_container_id="$1"
  local _kc_admin_user="${2:-}"
  local _kc_admin_pass="${3:-}"
  local keycloak_admin_base_url="${4:-}"
  local realm_import_file="/opt/keycloak/realm-import/${KEYCLOAK_REALM}-realm.json"
  local user_payloads operator_email operator_payload operator_user_id operator_user_json operator_current_roles missing_role_args
  local updated_user_count=0
  local user_payload username email first_name last_name user_json user_id desired_role

  if ! docker exec "$keycloak_container_id" test -s "$realm_import_file"; then
    error "$my_name" "Generated Keycloak realm import file is missing in the running stack"
    exit 33
  fi

  # Validate the realm file is parseable JSON before proceeding.
  # Docker exec can return error messages (e.g. stale container ID) that jq
  # will happily try to parse and fail on with "Invalid numeric literal".
  local realm_file_content
  realm_file_content="$(docker exec "$keycloak_container_id" cat "$realm_import_file" 2>&1)"
  if ! printf '%s' "$realm_file_content" | jq empty >/dev/null 2>&1; then
    error "$my_name" "Realm import file is not valid JSON (container may have been recreated)"
    error "$my_name" "File content preview: $(printf '%s' "$realm_file_content" | head -c 120)"
    exit 33
  fi

  operator_email="${OPERATOR_LOGIN_EMAIL:-${SMOKE_LOGIN_EMAIL:-}}"
  if [ -z "$operator_email" ]; then
    error "$my_name" "OPERATOR_LOGIN_EMAIL or SMOKE_LOGIN_EMAIL is required for Keycloak profile reconciliation"
    exit 33
  fi
  operator_payload="$(printf '%s' "$realm_file_content" | jq -c --arg operator_email "$operator_email" '.users[] | select((.username // .email // empty) == $operator_email) | {
    username: (.username // .email // empty),
    email: (.email // empty),
    first_name: (.firstName // empty),
    last_name: (.lastName // empty),
    enabled: (.enabled // true),
    email_verified: (.emailVerified // false),
    realm_roles: [.realmRoles[]?]
  }')" || {
    error "$my_name" "Failed to parse generated Keycloak operator user for reconciliation"
    exit 33
  }

  if [ -z "$operator_payload" ]; then
    error "$my_name" "Generated Keycloak realm user is missing operator persona ${operator_email}"
    exit 33
  fi

  if ! run_keycloak_kcadm "$keycloak_container_id" get "roles/operator" -r "${KEYCLOAK_REALM}" >/dev/null 2>&1; then
    run_keycloak_kcadm "$keycloak_container_id" create roles -r "${KEYCLOAK_REALM}" -s 'name=operator' >/dev/null || {
      error "$my_name" "Failed to create Keycloak realm role operator"
      exit 33
    }

    run_keycloak_kcadm "$keycloak_container_id" add-roles -r "${KEYCLOAK_REALM}" --rname operator --rolename dq:rules:write >/dev/null || {
      error "$my_name" "Failed to assign dq:rules:write to Keycloak realm role operator"
      exit 33
    }
  fi

  user_payloads="$(printf '%s' "$realm_file_content" | jq -c '.users[] | {
    username: (.username // .email // empty),
    email: (.email // empty),
    first_name: (.firstName // empty),
    last_name: (.lastName // empty),
    enabled: (.enabled // true),
    email_verified: (.emailVerified // false),
    realm_roles: [.realmRoles[]?]
  }')" || {
    error "$my_name" "Failed to parse generated Keycloak realm users for profile reconciliation"
    exit 33
  }

  while IFS= read -r user_payload || [ -n "$user_payload" ]; do
    [ -n "$user_payload" ] || continue

    username="$(printf '%s' "$user_payload" | jq -r '.username // empty')"
    email="$(printf '%s' "$user_payload" | jq -r '.email // empty')"
    first_name="$(printf '%s' "$user_payload" | jq -r '.first_name // empty')"
    last_name="$(printf '%s' "$user_payload" | jq -r '.last_name // empty')"

    if [ -z "$username" ] || [ -z "$email" ] || [ -z "$first_name" ] || [ -z "$last_name" ]; then
      error "$my_name" "Generated Keycloak realm user is missing username, email, firstName, or lastName"
      exit 33
    fi

    user_json="$(run_keycloak_kcadm "$keycloak_container_id" get users -r "${KEYCLOAK_REALM}" -q "username=${username}" --fields id)"
    user_id="$(printf '%s\n' "$user_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
    if [ -z "$user_id" ]; then
      local create_output
      create_output="$(run_keycloak_kcadm "$keycloak_container_id" create users -r "${KEYCLOAK_REALM}" \
        -s "username=${username}" \
        -s "email=${email}" \
        -s "firstName=${first_name}" \
        -s "lastName=${last_name}" \
        -s 'enabled=true' \
        -s 'emailVerified=true' 2>&1)"
      local create_rc=$?

      if [ "$create_rc" -ne 0 ]; then
        # User may have been created by realm import during seed-artifacts run.
        # Re-query for the user by username.
        user_json="$(docker exec "$keycloak_container_id" /opt/keycloak/kcadm-trust.sh get users -r "${KEYCLOAK_REALM}" -q "username=${username}" --fields id)"
        user_id="$(printf '%s\n' "$user_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
        if [ -z "$user_id" ]; then
          error "$my_name" "Seeded Keycloak user not found and could not be created for profile reconciliation: ${username}"
          info "$my_name" "Create output: $create_output"
          exit 33
        fi
      else
        # User was created successfully, query for ID
        user_json="$(docker exec "$keycloak_container_id" /opt/keycloak/kcadm-trust.sh get users -r "${KEYCLOAK_REALM}" -q "username=${username}" --fields id)"
        user_id="$(printf '%s\n' "$user_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
        if [ -z "$user_id" ]; then
          error "$my_name" "Seeded Keycloak user still missing after create: ${username}"
          exit 33
        fi
      fi
    fi

    if [ "$username" = "$operator_email" ]; then
      # Refresh kcadm token before operator role reconciliation
      # (token may have expired during the user reconciliation loop)
      if [ -n "$_kc_admin_user" ] && [ -n "$_kc_admin_pass" ] && [ -n "$keycloak_admin_base_url" ]; then
        run_keycloak_kcadm "$keycloak_container_id" config credentials \
          --server "$keycloak_admin_base_url" \
          --realm master \
          --user "$_kc_admin_user" \
          --password "$_kc_admin_pass" >/dev/null 2>&1 || true
      fi

      operator_current_roles="$(run_keycloak_kcadm "$keycloak_container_id" get "users/${user_id}/role-mappings/realm" -r "${KEYCLOAK_REALM}" | jq -r '.[].name' 2>/dev/null || true)"
      missing_role_args=()
      if ! printf '%s\n' "$operator_current_roles" | grep -Fxq 'operator'; then
        missing_role_args+=(--rolename operator)
      fi

      if [ "${#missing_role_args[@]}" -gt 0 ]; then
        run_keycloak_kcadm "$keycloak_container_id" add-roles -r "${KEYCLOAK_REALM}" --uid "$user_id" "${missing_role_args[@]}" >/dev/null || {
          error "$my_name" "Failed to reconcile Keycloak operator role for ${username}"
          exit 33
        }
      fi
    fi

    local profile_update_attempt profile_update_max_attempts profile_update_output
    profile_update_max_attempts=5
    profile_update_attempt=1
    while [ "$profile_update_attempt" -le "$profile_update_max_attempts" ]; do
      if profile_update_output="$(run_keycloak_kcadm "$keycloak_container_id" update "users/${user_id}" -r "${KEYCLOAK_REALM}" \
        -s "email=${email}" \
        -s "firstName=${first_name}" \
        -s "lastName=${last_name}" \
        -s 'enabled=true' \
        -s 'emailVerified=true' 2>&1)"; then
        break
      fi

      sleep 2
      profile_update_attempt=$((profile_update_attempt + 1))
    done

    if [ "$profile_update_attempt" -gt "$profile_update_max_attempts" ]; then
      printf '%s\n' "$profile_update_output" >&2
      error "$my_name" "Failed to reconcile Keycloak profile fields for ${username}"
      exit 33
    fi

    updated_user_count=$((updated_user_count + 1))
  done <<EOF
${user_payloads}
EOF

  info "$my_name" "✓ Keycloak seeded user profiles reconciled against generated realm JSON (${updated_user_count} users updated)"
}

seed_keycloak_in_docker() {
  local keycloak_container_id
  local keycloak_local_base keycloak_ready_url keycloak_https_relative_path keycloak_admin_base_url
  local seed_credentials_file rotated_password_count credential_line email password user_json user_id

  info "$my_name" "Reseeding Keycloak in the existing Docker stack (no container restart, no volume deletion)..."

  keycloak_container_id="$(docker_compose ps -q keycloak 2>/dev/null | tr -d '[:space:]' || true)"
  if [ -z "$keycloak_container_id" ]; then
    error "$my_name" "Keycloak is not running; start the stack before running --seed-keycloak"
    exit 33
  fi

  if [ "$(docker inspect -f '{{.State.Running}}' "$keycloak_container_id" 2>/dev/null || true)" != "true" ]; then
    error "$my_name" "Keycloak container exists but is not running; start the stack before running --seed-keycloak"
    exit 33
  fi

  # For readiness checks, prefer a direct localhost connection over the external
  # hostname to avoid DNS resolution issues and Kong proxy overhead during seeding.
  local keycloak_host_port="${KEYCLOAK_HTTPS_HOST_PORT:-9444}"
  keycloak_local_base="https://127.0.0.1:${keycloak_host_port}"

  info "$my_name" "Using direct URL for readiness check: $keycloak_local_base"
  keycloak_ready_url="${keycloak_local_base}/realms/${KEYCLOAK_REALM}/.well-known/openid-configuration"

  info "$my_name" "Checking Keycloak realm readiness before applying seed artifacts..."
  if ! wait_for_keycloak_ready "$keycloak_ready_url" "Keycloak"; then
    error "$my_name" "Keycloak is not ready; refusing to seed against an unavailable stack"
    exit 33
  fi

  generate_keycloak_seed_artifacts || exit 33

  # Re-resolve the container ID after seed-artifacts build/run in case
  # docker compose recreated the keycloak container.
  local fresh_keycloak_container_id
  fresh_keycloak_container_id="$(docker_compose ps -q keycloak 2>/dev/null | tr -d '[:space:]' || true)"
  if [ -n "$fresh_keycloak_container_id" ] && [ "$fresh_keycloak_container_id" != "$keycloak_container_id" ]; then
    info "$my_name" "Keycloak container was recreated during seed-artifacts build (old: ${keycloak_container_id:0:12}... new: ${fresh_keycloak_container_id:0:12}...), re-resolving"
    keycloak_container_id="$fresh_keycloak_container_id"
  fi
  if [ -z "$keycloak_container_id" ] || [ "$(docker inspect -f '{{.State.Running}}' "$keycloak_container_id" 2>/dev/null || true)" != "true" ]; then
    error "$my_name" "Keycloak container is not running after seed-artifacts build; cannot proceed with seeding"
    exit 33
  fi

  keycloak_https_relative_path="${KEYCLOAK_HTTPS_RELATIVE_PATH:-}"
  if [ -n "$keycloak_https_relative_path" ]; then
    keycloak_https_relative_path="/${keycloak_https_relative_path#/}"
    keycloak_https_relative_path="${keycloak_https_relative_path%/}"
  fi
  keycloak_admin_base_url="https://127.0.0.1:8443${keycloak_https_relative_path}"

  # Use KEYCLOAK_SYSTEM_ADMIN vars if set, else fall back to KEYCLOAK_ADMIN vars
  local kc_admin_user="${KEYCLOAK_SYSTEM_ADMIN_USERNAME:-${KEYCLOAK_ADMIN_USER:-}}"
  local kc_admin_pass="${KEYCLOAK_SYSTEM_ADMIN_PASSWORD:-${KEYCLOAK_ADMIN_PASS:-}}"

  local login_attempt login_max_attempts login_output
  login_max_attempts=5
  login_attempt=1
  while [ "$login_attempt" -le "$login_max_attempts" ]; do
    if login_output="$(run_keycloak_kcadm "$keycloak_container_id" config credentials \
      --server "$keycloak_admin_base_url" \
      --realm master \
      --user "${kc_admin_user:?kc admin username required}" \
      --password "${kc_admin_pass:?kc admin password required}" 2>&1)"; then
      break
    fi

    sleep 2
    login_attempt=$((login_attempt + 1))
  done

  if [ "$login_attempt" -gt "$login_max_attempts" ]; then
    printf '%s\n' "$login_output" >&2
    error "$my_name" "Unable to authenticate to the running Keycloak admin API"
    exit 33
  fi

  seed_credentials_file="/opt/keycloak/realm-import/keycloak_seed_user_credentials.csv"
  if ! docker exec "$keycloak_container_id" test -s "$seed_credentials_file"; then
    error "$my_name" "Generated Keycloak credential artifact is missing in the running stack"
    exit 33
  fi

  for role_name in dq:exceptions:read dq:exceptions:detail exception-fact-reader exception-fact-investigator; do
    if ! keycloak_realm_role_exists "$keycloak_container_id" "$role_name"; then
      if ! run_keycloak_kcadm "$keycloak_container_id" create roles -r "${KEYCLOAK_REALM}" -s "name=${role_name}" >/dev/null; then
        if keycloak_realm_role_exists "$keycloak_container_id" "$role_name"; then
          info "$my_name" "✓ Keycloak realm role ${role_name} already exists"
          continue
        fi

        error "$my_name" "Failed to create Keycloak realm role ${role_name}"
        exit 33
      fi
    fi
  done

  sync_keycloak_seed_user_profiles "$keycloak_container_id" "$kc_admin_user" "$kc_admin_pass" "$keycloak_admin_base_url"

  # Refresh kcadm token before the password loop — the config-credentials
  # call above happened before generate_keycloak_seed_artifacts() and
  # sync_keycloak_seed_user_profiles(), so the token may have expired by now.
  # Wait for the container to be healthy first (it may have been restarted by
  # the seed-artifacts volume change).
  info "$my_name" "Waiting for Keycloak to be healthy before password rotation..."
  if ! wait_for_compose_service_healthy keycloak "Keycloak" 180 5; then
    error "$my_name" "Keycloak did not become healthy before password rotation"
    exit 33
  fi

  info "$my_name" "Refreshing kcadm admin token for password rotation..."
  if ! run_keycloak_kcadm "$keycloak_container_id" config credentials \
    --server "$keycloak_admin_base_url" \
    --realm master \
    --user "${kc_admin_user:?kc admin username required}" \
    --password "${kc_admin_pass:?kc admin password required}" >/dev/null 2>&1; then
    error "$my_name" "Unable to re-authenticate kcadm for password rotation"
    exit 33
  fi

  rotated_password_count=0
  while IFS= read -r credential_line || [ -n "$credential_line" ]; do
    credential_line="${credential_line%$'\r'}"
    if [ -z "$credential_line" ] || [ "$credential_line" = '"email","password"' ]; then
      continue
    fi

    email="${credential_line%%\",\"*}"
    email="${email#\"}"
    password="${credential_line#*\",\"}"
    password="${password%$'\r'}"
    password="${password%\"}"

    if [ "$email" = "email" ] && [ "$password" = "password" ]; then
      continue
    fi

    if [ -z "$email" ] || [ -z "$password" ]; then
      error "$my_name" "Invalid seeded credential row"
      exit 33
    fi

    user_json="$(run_keycloak_kcadm "$keycloak_container_id" get users -r "${KEYCLOAK_REALM}" -q "username=${email}" --fields id)"
    user_id="$(printf '%s\n' "$user_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
    if [ -z "$user_id" ]; then
      error "$my_name" "Seeded Keycloak user not found: ${email}"
      exit 33
    fi

    # Generated passwords never start with '-' or '_' (see seed_password_rotation.py)
    # so kcadm argument parsing is safe with "--new-password=${password}".
    if ! run_keycloak_kcadm "$keycloak_container_id" set-password -r "${KEYCLOAK_REALM}" \
      --userid "$user_id" "--new-password=${password}" >/dev/null 2>&1; then
      error "$my_name" "Failed to set password for ${email}"
      exit 33
    fi
    rotated_password_count=$((rotated_password_count + 1))
  done <<EOF
$(docker exec "$keycloak_container_id" cat "$seed_credentials_file")
EOF

  sync_keycloak_seed_credentials_to_workspace "$keycloak_container_id" || {
    error "$my_name" "Failed to sync rotated Keycloak credentials back to the workspace"
    exit 33
  }

  # Restart Keycloak so the entrypoint applies the new passwords from the
  # updated seed-artifacts volume.  kcadm set-password is unreliable for
  # bulk password rotation (token expiry, argument parsing quirks).
  # The entrypoint's kcadm loop is deterministic and uses the correct CSV.
  info "$my_name" "Restarting Keycloak to apply rotated passwords via entrypoint..."
  docker_compose restart keycloak || {
    error "$my_name" "Failed to restart Keycloak container"
    exit 33
  }
  wait_for_compose_service_healthy keycloak "Keycloak" 180 3 || {
    error "$my_name" "Keycloak did not become healthy after restart"
    exit 33
  }

  info "$my_name" "✓ Keycloak reseed completed against existing stack (${rotated_password_count} passwords applied)"
}

seed_stack_block_keycloak() {
  if [ "$SEED_KEYCLOAK" != "true" ]; then
    return 0
  fi

  seed_keycloak_in_docker
}