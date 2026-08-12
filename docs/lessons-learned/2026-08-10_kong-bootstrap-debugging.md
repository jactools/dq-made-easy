# Lessons Learned — Kong Bootstrap Debugging (2026-08-10)

## Context

The `dq-job-kong-bootstrap` job failed repeatedly for 3+ hours. The root causes spanned shell scripting, Kubernetes config, Keycloak credential management, and Kong route drift. This document captures what we learned so we don't repeat the same mistakes.

---

## 1. Never parse HTTP response bodies for status codes in shell

**What happened:** The `http_ok()` function checked `head -1` of the curl response for `HTTP/x 2xx`. With `-s` flag, curl returns only the body (JSON), not HTTP headers. The function always returned false, so readiness checks timed out.

**Lesson:** Always use `curl -w '%{http_code}'` to extract the real HTTP status code. The body and status are completely independent.

**Anti-pattern:**
```bash
response=$(curl -s "$url" 2>&1)
status=$(echo "$response" | head -1 | grep -oE 'HTTP/[0-9.]\s+[0-9]{3}')  # WRONG
```

**Correct:**
```bash
response=$(curl -s -w '\n%{http_code}' "$url" 2>&1)
status=$(printf '%s' "$response" | tail -1)  # Last line is always the status code
body=$(printf '%s' "$response" | sed '$d')   # Everything except last line
```

---

## 2. Idempotent bootstrap scripts must handle drift

**What happened:** Kong routes created in previous runs had paths like `/admin/v1/*` but the script was updated to use `/api/admin/v1/*`. The `create_route()` function only created routes that didn't exist — it never updated stale paths.

**Lesson:** Bootstrap scripts must be idempotent and handle drift. If the desired state changes, the script must converge to it, not skip existing resources.

**Anti-pattern:**
```bash
create_route() {
  if ! route_exists; then
    create_new_route  # Only creates, never updates
  fi
}
```

**Correct:**
```bash
create_route() {
  existing=$(get_route "$name")
  if existing exists; then
    if existing_path != desired_path; then
      patch_route  # Converge to desired state
    fi
  else
    create_new_route
  fi
}
```

---

## 3. Keycloak admin password is not a K8s secret → DB credential

**What happened:** The `keycloak-admin` K8s Secret held `replace-me` but the Keycloak database had a different password (or no credential at all). Changing the K8s secret had zero effect — Keycloak validates passwords against its database, not against environment variables.

**Lesson:** The K8s secret only sets the initial password at first boot. After Keycloak is running, the database is the source of truth. To change the admin password:

1. Create a temporary admin user via `kc.sh bootstrap-admin`
2. Use the admin REST API to reset the real admin's password
3. Update the K8s secret to match

**Never:**
- Change the K8s secret and expect it to take effect (it only matters at boot)
- Manually insert password hashes into the database (Keycloak uses argon2 with complex JSON structures)
- Delete and recreate the Keycloak PVC (data loss)

---

## 4. Protected endpoints break bootstrap scripts

**What happened:** The bootstrap script reads `ssoEnabled` and `ssoIssuer` from `app-config` API. That API requires authentication, so the bootstrap script (which runs before Kong is configured) can never read it. The script then aborts with "SSO disabled or missing issuer".

**Lesson:** Bootstrap scripts cannot depend on protected APIs. Either:
- Make the bootstrap config endpoint public (no auth)
- Pass critical bootstrap values as explicit environment variables
- Use a hybrid: try protected API first, fall back to env vars

We chose option 3: explicit env vars in the job manifest with fallback to app-config.

---

## 5. `TRUST_PROXY_AUTH` is the switch between session and JWT auth

**What happened:** Kong validates the JWT and forwards the request with `x-consumer-custom-id` header. But the API had `TRUST_PROXY_AUTH=false`, so it ignored the Kong header and tried to validate the token itself + look up a session in the database. No session existed → "Session not found" → login loop.

**Lesson:** When Kong sits in front as a JWT gateway, the backend must trust Kong's validation. Set `TRUST_PROXY_AUTH=true` in the shared config map so the API trusts Kong's `x-consumer-custom-id` header and skips session lookup.

---

## 6. Shell scripts in containers use the container's env, not the host's

**What happened:** We kept testing `curl` from the host and from API pods, but the bootstrap job runs in its own pod with its own env vars and mounted volumes. A URL that works from the API pod might not work from the job pod if env vars differ.

**Lesson:** Always test from the actual pod that will run the script. Use `kubectl exec` into the job pod (with a `sleep` command) to verify env vars, CA bundles, and network connectivity.

---

## 7. Debugging Keycloak authentication is a rabbit hole

**What happened:** We spent hours trying to fix the Keycloak admin password by:
- Changing the K8s secret (no effect)
- Manually inserting password hashes (JSON parse errors)
- Deleting and recreating users (foreign key constraints)
- Using `kc.sh bootstrap-admin` (different password storage format)

The only thing that worked was using a temporary admin user to reset the real admin's password via the REST API.

**Lesson:** When Keycloak authentication is broken:
1. Create a temporary admin: `kc.sh bootstrap-admin user --username temp-reset --password:env TEMP_PASS`
2. Get a token: `curl -X POST /token -d 'grant_type=password&client_id=admin-cli&username=temp-reset&password=...'`
3. Reset the real admin: `curl -X PUT /users/{id}/reset-password -d '{"type":"password","value":"newpass","temporary":false}'`
4. Never touch the database directly — Keycloak's credential format is complex and version-dependent.

---

## Checklist for next deploy

- [ ] Run `generate_secrets.sh --env dev` (generates random Keycloak admin password)
- [ ] Run `generate_secrets.sh --env dev` in dq-made-easy (syncs tenant secrets with platform)
- [ ] Run `build_and_push_all.sh --env dev`
- [ ] Load images into Kind
- [ ] Run `trigger_jobs.sh --jobs kong-bootstrap --watch`
- [ ] Verify login redirect works end-to-end
