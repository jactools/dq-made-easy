# dq-edge

Purpose: own the repository-managed assets for the edge ingress service.

Current scope:

- dedicated container image definition for the edge ingress service
- runtime config renderer for the stock Nginx-based `edge` Compose service
- placeholder TLS files used for fail-fast mount validation
- future home for edge-specific templates, tests, and packaging if the service grows

Layout:

- `Dockerfile.edge`: builds the repo-owned edge image on top of upstream Nginx
- `docker-entrypoint.d/40-render-edge-config.sh`: renders the active Nginx config from env vars
- `placeholders/edge-cert.pem`: placeholder certificate bundled into the image
- `placeholders/edge-key.pem`: placeholder private key bundled into the image

Notes:

- The current image still builds on upstream `nginx:1.27-alpine`.
- Compose should build this service from `dq-edge/Dockerfile.edge` rather than bind-mounting repo assets into a stock Nginx container.
- Repo-owned ingress behavior should live here rather than under the shared `docker/` helper area.