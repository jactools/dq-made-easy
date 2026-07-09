# TLS Edge Architecture Reference

**Last Updated**: 2026-07-09  
**Source**: Analysis of `dq-edge/docker-entrypoint.d/40-render-edge-config.sh` and Zammad support stack  

---

## Current Architecture Overview

### Build & Deployment
- **Image**: `nginx:stable-bookworm` with custom entrypoint
- **Entrypoint**: `/opt/edge/render-edge-config.sh` generates config dynamically, then executes nginx
- **Location**: `dq-edge/docker-entrypoint.d/40-render-edge-config.sh`
- **Port**: 443 (TLS ingress on both LOCAL and PUBLIC modes)

### Two Operating Modes

#### LOCAL MODE (Stream + SNI Passthrough)
Uses **Nginx stream module** with **SSL preread** for transparent TLS passthrough by SNI:

**Key Features**:
- Loads `ngx_stream_module` in the main nginx.conf
- Uses `$ssl_preread_server_name` to route by SNI *before* TLS decryption
- Zero TLS termination; pure passthrough to upstream
- Upstream mapping (after W6 changes):
  ```
  ${app_host}          frontend:443
  ${kong_host}         kong:8443
  ${keycloak_host}     keycloak:8443
  ${metadata_host}     openmetadata-server:8585
  ${observability_host} grafana:3000
  ${support_host}      zammad-railsserver:3000   ← direct, no intermediate proxy
  default              127.0.0.1:1
  ```

#### PUBLIC MODE (HTTP Proxy with HTTPS Upstream)
Uses traditional HTTP-based routing with TLS termination + re-encryption:

**HTTP Routes** (Kong routes by path):
- `/auth/v1/` → `http://kong:8000`
- `/admin/v1/` → `http://kong:8000`
- `/system/v1/` → `http://kong:8000`
- `/data-catalog/v1/` → `http://kong:8000`
- `/rulebuilder/v1/` → `http://kong:8000`
- `/v1/`, `/health`, `/api-docs`, `/api-docs-json` → `http://kong:8000`
- `/rulebuilder/` → `http://kong:8000`
- `/iam/` → `http://keycloak:8080`
- `/ops/kong/` → `http://kong:8002`

**HTTPS Routes** (with SNI verification):
- `/metadata/` → `https://openmetadata-server:8585`
- `/observability/otlp/` → `https://dq-made-easy-otel-collector:4318/`
- `/observability/` → `https://grafana:3000`
- `/support/` → `https://zammad-https:443`
- `/` (default) → `https://frontend:443`

---

## Zammad Support Stack

### Before W6 (Double-Termination Model)
```
Browser → EDGE:443 (TLS terminate #1 with canonical hostname cert)
       → EDGE detects /support/ path (HTTP path inspection, requires decryption)
       → https://zammad-https:443
       → zammad-https:443 (TLS terminate #2 with same cert)
       → https://zammad-railsserver:3000 (HTTPS)
```

### After W6 (LOCAL Mode — Direct SNI Passthrough)
```
Browser → EDGE:443 (SNI preread, no TLS termination)
       → SNI = "itsm.jac.dot" → routes to zammad-railsserver:3000
       → zammad-railsserver:3000 (native TLS, cert includes itsm.jac.dot SAN)
```

### Backend Services (Post W6)

**zammad-railsserver** (port 3000):
- Native TLS via Puma: `-b ssl://[::]:3000?key=...&cert=...`
- Certificate SAN: `zammad-railsserver`, `itsm.jac.dot`, `localhost`
- Healthcheck: `curl --cacert /etc/zammad/certs/mkcert-rootCA.pem https://127.0.0.1:3000/health`

**zammad-websocket** (port 6042):
- Native TLS via websocket-server.rb: `-s -k tls.key -c tls.crt`
- Certificate SAN: `zammad-websocket`, `itsm.jac.dot`, `localhost`
- Healthcheck: `openssl s_client -connect 127.0.0.1:6042 -CAfile mkcert-rootCA.pem`

**zammad-https** (port 443):
- Optional/deprecated for LOCAL mode as of W6
- Retained for PUBLIC mode backwards compatibility
- See `ARCH-EXC-0011` in exception registry

---

## Key Proxy Functions in render-edge-config.sh

| Function | Purpose | TLS Behaviour |
|----------|---------|---------------|
| `append_https_proxy()` | HTTPS upstream with SNI + verify off | Terminates at edge, re-encrypts upstream |
| `append_https_proxy_with_uri()` | HTTPS with full URI + verify on | Terminates at edge, verifies upstream cert |
| `append_http_proxy()` | HTTP upstream | Terminates at edge, plaintext upstream |
| `append_http_proxy_with_uri()` | HTTP with full URI | Terminates at edge, plaintext upstream |

For SNI passthrough: uses stream module (LOCAL mode only), not HTTP location blocks.

---

## TLS-Capable Services

| Service | Port | TLS | Mode | Notes |
|---------|------|-----|------|-------|
| frontend | 443 | ✅ | LOCAL | SNI passthrough |
| kong | 8443 | ✅ | LOCAL | SNI passthrough |
| kong admin | 8000 | ❌ HTTP | PUBLIC | Path-based route |
| keycloak | 8443 | ✅ | LOCAL | SNI passthrough |
| keycloak | 8080 | ❌ HTTP | PUBLIC | Path-based route |
| openmetadata-server | 8585 | ✅ | Both | TLS native |
| grafana | 3000 | ✅ | Both | TLS native |
| zammad-railsserver | 3000 | ✅ | LOCAL | Direct via SNI (W6) |
| zammad-websocket | 6042 | ✅ | Both | TLS native (W6) |
| Ollama (retired mTLS proxy) | — | Removed | — | `dq-made-easy-llm` is TLS-native; direct access via dq-network |
| Airflow | 8080 | ❌ HTTP | — | Host-bind exception (ARCH-EXC-0010) |
| Postgres | 5432 | ✅ | Both | sslmode=verify-full |
| Redis | 6379 | ✅ | Both | rediss:// with CA bundle |
| Kafka | 9092 | ✅ | Both | SSL listener |

---

## Related Documents

- [SEC_5_END_TO_END_NO_HTTP_TLS_IMPLEMENTATION_PLAN.md](./SEC_5_END_TO_END_NO_HTTP_TLS_IMPLEMENTATION_PLAN.md)
- [SEC_5_W6_IMPLEMENTATION_STRATEGY.md](./SEC_5_W6_IMPLEMENTATION_STRATEGY.md)
- [SEC_5_W7_CUTOVER_RUNBOOK.md](./SEC_5_W7_CUTOVER_RUNBOOK.md)
- [SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md](./SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md)
