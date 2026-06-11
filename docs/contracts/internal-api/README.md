# Internal API Contracts

This directory contains the current generated, versioned internal API contracts for the live FastAPI route map.

The contract bundles are generated from `app.openapi()` rather than from a stale checked-in snapshot, so the paths in these artifacts match the FastAPI routes that the validator routine will see at runtime.

This directory contains two generated views:

- `aggregate/<version>/...`: aggregate contract bundle for the full FastAPI HTTP surface.
- `by-tag/<tag>/<version>/...`: focused contract bundles split by OpenAPI tag for clearer domain-level review and reuse.

Each contract bundle is organized as:

- `<group>/<version>/schema.json`: JSON Schema bundle with request, response, parameter, and shared payload definitions in `$defs`.
- `<group>/<version>/operations.json`: operation manifest mapping HTTP method and path to the relevant schema references.
- `<group>/<version>/openapi.json`: filtered OpenAPI 3.1 fragment for the same API group and version.
- `index.json`: machine-readable index of all generated API-group bundles.

Current contract rules:

- These bundles should be treated as the current published internal API contracts.
- Paths match the live FastAPI routes, for example `/api/admin/v1/...` and `/api/rulebuilder/v1/...`.
- `schema.json` is the primary payload contract artifact; `openapi.json` is the HTTP companion view of the same contract set.
- `operations.json` tells a validator exactly which request-body schema applies to each endpoint.

Runtime validation note:

- Today, FastAPI/Pydantic still performs the built-in request validation.
- These generated schemas now align with the live route map, which makes them suitable for shared validator middleware, contract tests, or external client validation.

Regenerate the bundles with:

```bash
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python dq-api/fastapi/scripts/contracts/export_docs_contracts.py --source app
```