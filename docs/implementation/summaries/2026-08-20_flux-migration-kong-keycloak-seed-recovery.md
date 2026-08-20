# Flux Migration Recovery — Kong Gateway + Keycloak Tenant Seeding for DQ Login

**Date**: 2026-08-20
**Status**: Code complete — pending live verification after push + Flux sync
**Scope**: `dq-made-easy` (primary), `platform-foundation` (supporting fixes)

## Objective

After the Flux GitOps migration, the DQ dev UI at `https://dq-made-easy.dev.jac.dot:10443`
could not log in. The migration dropped the legacy host-side bootstrap steps, leaving:

1. **Kong's database empty** — 0 services, 0 routes, 0 consumers, 0 plugins. The legacy
   `scripts/bootstrap_kong.sh` (host-side, run manually after deploy) was never re-created as a
   GitOps-managed resource.
2. **The Keycloak `jaccloud` realm missing DQ tenant configuration** — no `dq-rules-ui`
   public OIDC client, no DQ realm roles, no role assignments for the 30 mock users.
3. **SSO config missing/wrong in the dev overlays** — `dq-common-config` had no SSO values,
   `dq-keycloak-config` and `dq-kong-config` were never applied, and
   `SSO_INTERNAL_ISSUER_URL` pointed at a dead realm (`dq-made-easy`) over `http://`.
4. **The platform `seed-users.sh` had an idempotency bug** — it wrote a *stale*
   `CLIENT_SECRET` into the K8s secret (it read a `clientSecret` field that no longer exists in
   Keycloak 26, and called a removed rotation endpoint) and silently skipped role assignments,
   leaving the `tenant-admin` service account without any realm-management roles.

This effort restores working login end-to-end using GitOps-only primitives (Flux Kustomizations,
Jobs, ExternalSecrets). No `kubectl apply/create/patch` is used for deployment.

## Results

| Area | Before | After |
|---|---|---|
| Kong gateway | 0 services/routes/consumers/plugins (DB empty) | `dq-api` service, 29 routes, CORS + rate-limiting, JWT + ACL on 15 protected routes, consumers for all enabled realm users — all idempotent, Flux-managed |
| Keycloak tenant (realm `jaccloud`) | No DQ client/roles/assignments | `dq-rules-ui` public client (redirect URI, web origins, realm-roles + audience mappers), 28 realm roles, 40 user→role assignments — idempotent |
| DQ SSO config (dev) | Missing/wrong (dead realm, `http://` internal URL, no SSO env) | `dq-common-config` (dev-db) + `dq-keycloak-config` + `dq-kong-config` (dev) all applied with correct values |
| `tenant-admin` credentials | Stale `CLIENT_SECRET` in K8s secret (grant returned 401) | Seed job reads the live `secret` field (KC26), verifies role assignments with read-back, always re-syncs the K8s secret (self-healing) |
| Kong OOMKilled crash loop | 11 restarts (~100 min interval), 1Gi limit | `KONG_WORKER_PROCESSES: "2"` in platform Kong base ConfigMap |
| Ingress fake cert on unknown hosts | ingress-nginx served DQ cert for any SNI | `--default-ssl-certificate` (dev Kind only) + self-contained ingress patches with `http.paths` |
| `kind.sh tls` action | Targeted ambient KUBECONFIG (wrong cluster) | Calls `set_kubeconfig` explicitly |

## New files

| File | Purpose |
|---|---|
| `k8s/overlays/dev/jobs/oidc-gateway-init.py` | Idempotent Python seeder: Phase 1 Keycloak tenant (roles, assignments, `dq-rules-ui` client), Phase 2 Kong (service, routes, plugins, consumers) |
| `k8s/overlays/dev/jobs/oidc-gateway-init.yaml` | `dq-job-oidc-gateway-init` Job manifest (`python:3.13`, `backoffLimit: 3`) |
| `k8s/overlays/dev/external-secrets/keycloak-tenant-admin.yaml` | ExternalSecret → `keycloak-tenant-admin` secret in `dq-dev` (via `platform-keycloak-secrets-store`) |
| `k8s/overlays/dev-db/patches/common-config.yaml` | SSO env values on `dq-common-config` (dev-db-owned) |
| `platform-foundation/apps/platform/shared/base/cluster-secret-store-keycloak.yml` | `platform-keycloak-secrets-store` ClusterSecretStore (remote namespace `platform-keycloak`) |

## Modified files

| File | Change |
|---|---|
| `dq-made-easy k8s/overlays/dev/kustomization.yaml` | Added keycloak/kong base configs + dev patches + init Job + ExternalSecret + `configMapGenerator` for the init script |
| `dq-made-easy k8s/overlays/dev/config/dq-api-config.yaml` | `SSO_INTERNAL_ISSUER_URL` → `https://keycloak.platform-keycloak.svc.cluster.local:8443/auth/realms/jaccloud` |
| `dq-made-easy k8s/overlays/dev/patches/{keycloak,kong}-config.yaml` | Rewritten for platform Keycloak (`jaccloud` realm) and platform Kong (HTTP admin on 8444) |
| `dq-made-easy k8s/overlays/dev-db/kustomization.yaml` | Wired in the common-config patch |
| `dq-made-easy k8s/overlays/dev/patches/common-config.yaml` | **Deleted** (orphaned — `dq-common-config` is owned by dev-db) |
| `platform-foundation apps/platform/keycloak/jobs/seed-users.sh` | `kc_retry` helper (6 attempts, backoff); reads live `secret` field (KC26, rotation endpoint removed); role-assignment read-back verification; always re-syncs K8s secret |
| `platform-foundation apps/platform/kong/base/configmap.yml` | `KONG_WORKER_PROCESSES: "2"` (OOM fix) |
| `platform-foundation apps/platform/shared/base/kustomization.yml` | Wired in the new ClusterSecretStore |
| `platform-foundation scripts/kind.sh` | `do_tls_reinject` now calls `set_kubeconfig` |

## Key design decisions

- **SSO config via env vars only.** `apply_env_sso_overrides` is applied on every
  `get_app_config` read — env vars override the DB, so no DB migration is needed to enable SSO.
- **`OIDC_REDIRECT_BASE_URL = https://dq-made-easy.dev.jac.dot:10443`** (no `/api`): the API
  appends `/api/auth/v1/callback` itself (v0.11 behavior, differs from legacy which had no
  `/api` prefix).
- **Kong trust flow (unchanged from legacy):** JWT plugin identifies the consumer by
  `preferred_username` claim matching the credential key → Kong sets `X-Consumer-Custom-ID`
  (consumer `custom_id` = username) → ACL plugin sets `X-Consumer-Groups`
  (`hide_groups_header: false`) → API middleware trusts the proxy
  (`TRUST_PROXY_AUTH=true` + header present). Verified in Kong 3.9.1 source that
  `X-Consumer-Custom-ID` is set when the consumer has a `custom_id`.
- **`retry_404` is opt-in per target.** Keycloak's Admin API exhibits transient 404s in this
  cluster (observed live) so Keycloak calls retry 404s; Kong 404s are deterministic
  (create-if-missing lookups) and must *not* be retried — retrying them would stall a first run
  by minutes (29 routes × 5 retries × backoff).
- **Engine service-account consumer is best-effort** (skip + log if the
  `dq-made-easy-engine-gx-worker` client is absent from the realm) — the legacy bootstrap
  hard-failed, but blocking the login path on engine setup is the wrong trade-off in dev.
- **ClusterSecretStore needs no new RBAC** — the existing `eso-platform-secret-reader`
  ClusterRole is cluster-wide secret read, already bound to the `external-secrets` SA.

## Testing performed

- **JWK→PEM builder**: byte-for-byte verified against `openssl` (SPKI DER sha256 match). This
  caught a real bug: `base64.encodebytes` wraps at 76 chars and corrupted the 64-char PEM line
  slicing (embedded blank line → unparseable PEM). Fixed with `base64.b64encode`.
- **Full mock-server dry run** (Keycloak + Kong mocks on localhost): first run (create paths)
  and second run (update/idempotency paths) both exit 0. Verified final state: 28 roles, client
  with correct redirect URIs/web origins/mappers, 29 routes (`/me` route `regex_priority: 100`),
  15 JWT + 15 ACL plugins (no duplicates across runs), service-level CORS + rate-limiting,
  consumers with `custom_id` = username and role-derived ACL groups, exactly one JWT credential
  per consumer after re-runs.
- **Bugs caught by the dry run and fixed**:
  1. `base64.encodebytes` PEM corruption (above)
  2. Role creation used `POST /roles/{name}` — Keycloak 26 uses the collection endpoint
     `POST /roles`
  3. Role-mapping POST returns **204**, not 200/201 — now accepted
  4. Kong 404 retry storm (see design decisions)
  5. Engine consumer JWT credential duplicated on re-run — now replaced
- **kustomize build**: `k8s/overlays/dev` and `k8s/overlays/dev-db` both render cleanly;
  the Job correctly references the hashed `configMapGenerator` script; rendered
  `dq-keycloak-config` / `dq-kong-config` / `dq-common-config` values verified.

## Known issues / remaining work

- **Live verification pending** — requires the user to commit + push both repos (git is not
  available in this sandbox), then:
  1. Re-run the platform seed job to fix `tenant-admin` credentials + roles:
     `kubectl delete job keycloak-seed -n platform-keycloak`
  2. Let Flux sync `dq-made-easy` (dev-db) → `dq-made-easy-app` (dev); the init Job runs after.
- The init Job's Pod needs the `keycloak-tenant-admin` secret, which the ExternalSecret creates
  asynchronously. `wait: true` on the Flux Kustomization waits for ExternalSecret readiness, and
  the Job's `backoffLimit: 3` covers any residual race at Pod start.
- Kong DB state is not GitOps-managed (it's seeded at runtime by the Job, mirroring how the
  legacy bootstrap worked). A full Kong DB snapshot/export is a future hardening item.
- The broken `dq-secret-init` Flux Kustomization (points at `./k8s/overlays/dev-secret-init`,
  which is superseded) should be deleted in a follow-up.

## Next steps

1. Commit + push `platform-foundation` and `dq-made-easy` (branch `release/dev`).
2. `kubectl delete job keycloak-seed -n platform-keycloak` (self-heals tenant-admin secret + roles).
3. Watch Flux: `kubectl -n flux-system get ks -w` until `dq-made-easy-app` is Ready.
4. Verify Job: `kubectl -n dq-dev logs job/dq-job-oidc-gateway-init`.
5. Verify Kong: `kubectl -n platform-kong exec deploy/kong -- kong-cli kong routes list`.
6. Log in at `https://dq-made-easy.dev.jac.dot:10443` (e.g. `alice@jaccloud.nl`).
