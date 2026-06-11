# Purpose: Dedicated startup block for the gateway profile.

refresh_existing_kong_after_keycloak_seed_if_needed() {
  if [ "$SEED_KEYCLOAK" != "true" ] && [ "$SEED_ALL" != "true" ]; then
    return 0
  fi

  local keycloak_local_base="${KEYCLOAK_LOCAL_URL:-${KEYCLOAK_PUBLIC_URL:-https://${KEYCLOAK_PUBLIC_HOSTNAME:-keycloak.jac.dot}:9444}}"
  local keycloak_ready_url="${keycloak_local_base}"
  local kong_container_id
  local bootstrap_src="$ROOT_DIR/dq-kong/scripts/bootstrap_kong.sh"
  local bootstrap_dst="/tmp/dq-bootstrap_kong.sh"

  info "$my_name" "Checking Keycloak readiness before Kong refresh..."
  if ! wait_for_keycloak_ready "$keycloak_ready_url" "Keycloak"; then
    warning "$my_name" "Keycloak reseed detected, but Keycloak is not ready yet; skipping Kong refresh"
    return 0
  fi

  kong_container_id="$(docker ps -q -f name=^kong-gateway$ 2>/dev/null | tr -d '[:space:]' || true)"
  if [ -z "$kong_container_id" ]; then
    warning "$my_name" "Keycloak reseed detected, but Kong is not running; skipping Kong refresh"
    return 0
  fi

  if [ ! -f "$bootstrap_src" ]; then
    warning "$my_name" "Kong bootstrap source script not found at $bootstrap_src; skipping Kong refresh"
    return 0
  fi

  info "$my_name" "Keycloak reseed detected -> refreshing existing Kong routes/plugins/JWT credentials..."
  if docker cp "$bootstrap_src" "${kong_container_id}:${bootstrap_dst}" >/dev/null 2>&1 \
    && docker exec "$kong_container_id" bash -lc "bash '${bootstrap_dst}'"; then
    success "$my_name" "Existing Kong bootstrap refresh completed after Keycloak reseed"
  else
    warning "$my_name" "Existing Kong bootstrap refresh failed after Keycloak reseed"
  fi
}

start_stack_block_gateway() {
  case "$START_PHASE" in
    pre)
      if [ "$START_GATEWAY" != "true" ]; then
        return 0
      fi

      PROFILE_ARGS+=(--profile gateway)
      info "$my_name" "Gateway profile enabled"
      ;;
    post)
      if [ "$START_GATEWAY" != "true" ]; then
        info "$my_name" "Gateway profile disabled: skipping Kong readiness checks"
        if [ "$SKIP_POST_STACK_KONG_REFRESH" = "true" ]; then
          info "$my_name" "Skipping stack-level Keycloak->Kong refresh"
        else
          refresh_existing_kong_after_keycloak_seed_if_needed
        fi
        return 0
      fi

      info "$my_name" "Waiting for Kong Gateway (http://localhost:8001) to become available..."
      if ! wait_for_kong_admin_ready "http://localhost:8001" "Kong Admin API" 30 1; then
        error "$my_name" "Kong Admin API did not respond after 30 seconds"
        exit 1
      fi

      info "$my_name" "Kong Admin API responded with HTTP 200"
      info "$my_name" "Running Kong bootstrap to configure routes/plugins/JWT credentials..."
      if docker cp "$ROOT_DIR/dq-kong/scripts/bootstrap_kong.sh" kong-gateway:/tmp/dq-bootstrap_kong.sh >/dev/null 2>&1 \
        && docker exec kong-gateway bash -lc "bash /tmp/dq-bootstrap_kong.sh"; then
        info "$my_name" "Kong bootstrap completed"
      else
        error "$my_name" "Kong bootstrap failed; refusing to continue with stale Kong state"
        error "$my_name" "  Check Kong logs: docker compose logs --tail=120 kong"
        exit 1
      fi

      info "$my_name" "Validating Kong -> API upstream connectivity via host-local probe (${KONG_HEALTHCHECK_URL})..."
      if ! wait_for_kong_proxy_ready "$KONG_HEALTHCHECK_URL" "Kong upstream connectivity" 15 1; then
        warning "$my_name" "Kong upstream not healthy yet. Restarting Kong and re-running bootstrap..."
        docker_compose restart kong >/dev/null || true
        sleep 3
        if docker cp "$ROOT_DIR/dq-kong/scripts/bootstrap_kong.sh" kong-gateway:/tmp/dq-bootstrap_kong.sh >/dev/null 2>&1 \
          && docker exec kong-gateway bash -lc "bash /tmp/dq-bootstrap_kong.sh"; then
          info "$my_name" "Kong bootstrap completed after restart"
        else
          error "$my_name" "Kong bootstrap failed after restart"
          error "$my_name" "  Check Kong logs: docker compose logs --tail=120 kong"
          exit 1
        fi

        info "$my_name" "Re-validating Kong -> API upstream connectivity after restart via host-local probe (${KONG_HEALTHCHECK_URL})..."
        if ! wait_for_kong_proxy_ready "$KONG_HEALTHCHECK_URL" "Kong upstream connectivity after restart" 20 2; then
          error "$my_name" "Kong upstream still unhealthy after restart"
          error "$my_name" "  Check Kong logs: docker compose logs --tail=120 kong"
          exit 1
        fi
      fi

      if ! wait_for_kong_proxy_ready "$KONG_HEALTHCHECK_URL" "Kong configuration seeding" 20 1; then
        error "$my_name" "Kong configuration seeding not ready"
        error "$my_name" "  Check Kong logs: docker compose logs --tail=120 kong"
        exit 1
      fi

      docs_code=$(curl_kong_host_probe --max-time 2 -sS -o /dev/null -w "%{http_code}" "$KONG_HEALTHCHECK_URL" || true)
      docs_code="${docs_code:-000}"
      info "$my_name" "Kong upstream connectivity validated (${KONG_HEALTHCHECK_URL})"

      app_config_local_url="${DQ_API_LOCAL_URL:?DQ_API_LOCAL_URL is required}"
      APP_CFG=$(curl -s --max-time 5 "${app_config_local_url%/}/api/system/v1/app-config" || true)
      SSO_ENABLED=$(printf '%s' "$APP_CFG" | jq -r '.ssoEnabled // false' 2>/dev/null || echo false)
      SSO_ISSUER=$(printf '%s' "$APP_CFG" | jq -r '.ssoIssuer // empty' 2>/dev/null || true)
      if [[ "$SSO_ENABLED" == "true" ]] && [[ -n "$SSO_ISSUER" ]]; then
        if curl -s http://localhost:8001/consumers/oidc-issuer/jwt | jq -r '.data[]?.key' | grep -qx "$SSO_ISSUER"; then
          info "$my_name" "Kong JWT credentials include SSO issuer: $SSO_ISSUER"
        else
          error "$my_name" "Kong JWT credentials missing SSO issuer: $SSO_ISSUER"
          error "$my_name" "  Check Kong logs: docker compose logs --tail=120 kong"
          exit 1
        fi
      fi

      info "$my_name" "Kong gateway is ready (${KONG_LOCAL_URL:-${KONG_PUBLIC_URL:-}})"
      info "$my_name" "Kong Admin API is ready (${KONG_ADMIN_LOCAL_URL:-${KONG_ADMIN_PUBLIC_URL:-}})"
      info "$my_name" "Kong Manager GUI available at ${KONG_MANAGER_LOCAL_URL:-${KONG_MANAGER_PUBLIC_URL:-}}"
      echo ""

      proxy_code="$docs_code"
      info "$my_name" "Kong configuration seeded successfully"
      if [[ "$proxy_code" == "401" ]]; then
        info "$my_name" "  Auth: JWT enforced on group routes (see dq-kong/scripts/bootstrap_kong.sh)"
      fi
      info "$my_name" "  Services: dq-api → http://api:4010 (FastAPI)"
      info "$my_name" "  Routes: /auth/v1, /admin/v1, /system/v1, /data-catalog/v1, /rulebuilder/v1"
      info "$my_name" "  Plugins: CORS, rate-limiting"
      info "$my_name" "Public API is accessible through Kong at $KONG_PUBLIC_URL"
      info "$my_name" "Local Kong manager is available at ${KONG_MANAGER_LOCAL_URL:-${KONG_MANAGER_PUBLIC_URL:-}}"
      ;;
  esac
}
