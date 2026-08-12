# Fresh Deploy Checklist — `dq-made-easy` on Kind

**Date**: 2026-08-10  
**Status**: Draft — verified on 2026-08-10

## Prerequisites

- Kind cluster `platform-dev` running
- ArgoCD installed and synced
- Root CA trusted in Kind node trust store
- `platform-foundation` and `dq-made-easy` repos at same commit

---

## Step 1: Platform Foundation

```bash
cd platform-foundation

# 1a. Generate secrets (creates random passwords if .env doesn't have them)
bash scripts/generate_secrets.sh --env dev

# 1b. Generate TLS certificates (includes K8s internal FQDNs as SANs)
bash scripts/generate_dev_certs.sh

# 1c. Load images into Kind
kind load docker-image docker-registery.host.dev.jac.dot:10443/jacbeekers/platform-kong:0.1.0 --name platform-dev
kind load docker-image docker-registery.host.dev.jac.dot:10443/jacbeekers/platform-keycloak:0.1.0 --name platform-dev

# 1d. Sync ArgoCD
bash scripts/argocd_sync.sh --group platform --watch

# 1e. Verify platform services
kubectl rollout status deployment/kong -n platform-kong --timeout=120s
kubectl rollout status deployment/keycloak -n platform-keycloak --timeout=180s
```

## Step 2: DQ Made Easy

```bash
cd dq-made-easy

# 2a. Build and push images
bash scripts/build_and_push_all.sh --env dev

# 2b. Load images into Kind
kind load docker-image docker-registery.host.dev.jac.dot:10443/jacbeekers/dq-made-easy-api:0.11 --name platform-dev
kind load docker-image docker-registery.host.dev.jac.dot:10443/jacbeekers/dq-made-easy-frontend:0.11 --name platform-dev
kind load docker-image docker-registery.host.dev.jac.dot:10443/jacbeekers/dq-made-easy-engine:0.11 --name platform-dev
kind load docker-image docker-registery.host.dev.jac.dot:10443/jacbeekers/dq-made-easy-db:0.11 --name platform-dev

# 2c. Generate tenant secrets (reads Keycloak/Kong admin passwords from platform secrets)
bash scripts/generate_secrets.sh --env dev

# 2d. Sync ArgoCD
cd ../platform-foundation && bash scripts/argocd_sync.sh --group tenants-dq --watch

# 2e. Verify deployments
kubectl rollout status deployment/dq-api -n dq-made-easy-dev --timeout=60s
kubectl rollout status deployment/dq-frontend -n dq-made-easy-dev --timeout=60s
kubectl rollout status deployment/dq-engine -n dq-made-easy-dev --timeout=60s
```

## Step 3: Bootstrap & Seed Jobs

```bash
cd platform-foundation

# 3a. Run kong-bootstrap (creates Kong routes, JWT plugins, CORS, ACL)
bash scripts/trigger_jobs.sh --jobs kong-bootstrap --watch

# 3b. Run db-seed (creates tables, seeds data, creates users)
bash scripts/trigger_jobs.sh --jobs db-seed --watch

# 3c. Run keycloak-seed (imports realm, creates users, rotates passwords)
bash scripts/trigger_jobs.sh --jobs keycloak-seed --watch
```

## Step 4: Verification

```bash
# 4a. Check login redirect
curl -sk -o /dev/null -w "%{http_code}" "https://dq-made-easy.dev.jac.dot:10443/api/auth/v1/redirect?frontend=https%3A%2F%2Fdq-made-easy.dev.jac.dot%3A10443"
# Expected: 302

# 4b. Check API endpoints (should return 401, not 404)
for url in /api/system/v1/app-config /api/data-catalog/v1/data-products /api/rulebuilder/v1/rules; do
  code=$(curl -sk -o /dev/null -w "%{http_code}" "https://dq-made-easy.dev.jac.dot:10443$url")
  echo "$url  →  $code"
done

# 4c. Check Keycloak admin login
ADMIN_PASSWORD=$(kubectl get secret keycloak-admin -n platform-keycloak -o jsonpath='{.data.KEYCLOAK_ADMIN_PASSWORD}' | base64 -d)
curl -sk -X POST https://keycloak.dev.jac.dot:10443/auth/realms/master/protocol/openid-connect/token \
  -d "grant_type=password&client_id=admin-cli&username=admin&password=$ADMIN_PASSWORD" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print('OK' if 'access_token' in d else 'FAIL: '+d.get('error',''))"
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Kong bootstrap fails: "Kong Admin API not ready after 60s" | `http_ok()` was parsing JSON body for HTTP status | Fixed in `bootstrap_kong.sh` — uses `curl -w '%{http_code}'` |
| Kong bootstrap fails: "SSO disabled or missing issuer" | `app-config` requires auth, bootstrap can't read SSO config | `SSO_ENABLED` + `SSO_PUBLIC_ISSUER_URL` env vars in job manifest |
| UI login redirects to Kong, returns "Session not found" | `TRUST_PROXY_AUTH=false` — API doesn't trust Kong JWT | Added `TRUST_PROXY_AUTH: 'true'` to `common-config.yaml` |
| UI calls Kong directly → 404 CORS | `API_BASE_URL` was Kong URL instead of same-origin | Changed to `/api` in `runtime-config.template.js` |
| Frontend nginx → Kong → 502 | Kong proxy only listens on HTTP 8000 | Added `0.0.0.0:8443 ssl` listener + cert mount in Kong deployment |
| Frontend nginx → Kong TLS cert error | Cert missing K8s internal FQDN SAN | Added `kong-proxy.platform-kong.svc.cluster.local` to cert SANs |
| Kong route paths don't match UI calls | Nginx rewrite stripped `/api`, routes had no prefix | All routes now use `/api/...` paths, nginx has no rewrite |
| Keycloak admin login fails | Secret has `replace-me`, DB has different password | Run `generate_secrets.sh --env dev` — generates random password |
