# DQ UI

Minimal React + Vite starter app demonstrating use of webcomponents.

Prerequisites: Node.js 22+ and npm 11.14.1.

Quick start

1. Change to the folder:

```bash
cd dq-ui
```

2. Install dependencies:

```bash
npm install
```

3. Start dev server:

```bash
npm run dev
```

Documentation
- Rule Suggestions profiling flow (UI + API sequence + verification commands): see `../README.md` under **Rule Suggestions flow**.

Notes
- The app loads its UI package from `index.html`. If you have a local build of the package in the monorepo, update the import accordingly (for example to a relative path into your local package `dist`), or install the package from npm.
- This scaffold uses TypeScript and provides a `global.d.ts` that allows basic web components in JSX.
- API base URL resolution is centralized in `src/config/api.ts`.
- Runtime override is supported through `window.__DQ_CONFIG__.API_BASE_URL` (served via `/runtime-config.js` in container deployments).
- Base URL resolution in app code is: runtime `__DQ_CONFIG__` -> build-time Vite API env.
- If neither source is configured, `src/config/api.ts` fails fast.
- Local dev and container helper scripts must seed those values explicitly for their own startup flows; they no longer invent a default API target.

OpenTelemetry (UI traces)
- Browser trace export is disabled by default unless `VITE_OTEL_ENDPOINT` is explicitly set at build/dev-server time.
- Optional override: set `VITE_OTEL_ENABLED=true` to force-enable, or `VITE_OTEL_ENABLED=false` to force-disable.
- If enabled, point `VITE_OTEL_ENDPOINT` at the HTTPS OTLP/HTTP endpoint exposed by observability, for example `https://observability.jac.dot:4318`.
- The OTLP/HTTP collector must allow browser CORS for the UI origin and serve TLS with the certs in `tmp/certs/` (see `observability/otel-collector/config.yml`).
