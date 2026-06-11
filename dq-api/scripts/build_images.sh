#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

FRONT_TAG="${FRONT_TAG:-dq-rules-ui-frontend:local}"
API_TAG="${API_TAG:-dq-rules-ui-api:local}"
DB_TAG="${DB_TAG:-dq-rules-ui-db:local}"
KONG_PUBLIC_URL="${KONG_PUBLIC_URL:-${KONG_LOCAL_URL:-https://kong.jac.dot:9443}}"
NO_CACHE=0

usage(){
  cat <<EOF
Usage: $(basename "$0") [--no-cache] [--help]

Builds Docker images for the project:
  - frontend  (Dockerfile.frontend)
  - api       (Dockerfile.fastapi)

Environment vars:
  FRONT_TAG   image tag for frontend (default: $FRONT_TAG)
  API_TAG     image tag for api (default: $API_TAG)
  DB_TAG      image tag for db (default: $DB_TAG)
  KONG_PUBLIC_URL runtime API base for the frontend container (default: $KONG_PUBLIC_URL)

Options:
  --no-cache  build images without cache
  -h,--help   show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-cache) NO_CACHE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
done

BUILD_OPTS=""
if [[ $NO_CACHE -eq 1 ]]; then BUILD_OPTS="--no-cache"; fi

echo "Building frontend image ($FRONT_TAG)..."
if docker image inspect "$FRONT_TAG" >/dev/null 2>&1; then
  echo "Removing existing image $FRONT_TAG"
  docker rmi -f "$FRONT_TAG" || true
fi
docker build $BUILD_OPTS -f dq-ui/Dockerfile.frontend -t "$FRONT_TAG" .

echo "Building api image ($API_TAG)..."
if docker image inspect "$API_TAG" >/dev/null 2>&1; then
  echo "Removing existing image $API_TAG"
  docker rmi -f "$API_TAG" || true
fi
docker build $BUILD_OPTS -f dq-api/Dockerfile.fastapi -t "$API_TAG" .

echo "(skipping DB image — using official postgres image)"

echo "\nBuilt images:"
docker images --format "{{.Repository}}:{{.Tag}}\t{{.Size}}" | grep dq-rules-ui || true

cat <<EOF

To run locally (example with Postgres):
  docker run -d --name dq-db -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=dq -v dq_pgdata:/var/lib/postgresql postgres:18
  docker run -d --name dq-api --link dq-db -p 4010:4010 -e DQ_DB_INTERNAL_URL=postgresql://postgres:postgres@dq-db:5432/dq $API_TAG
  docker run -d --name dq-ui -p 5173:80 -e KONG_PUBLIC_URL=$KONG_PUBLIC_URL $FRONT_TAG

You may want to make the script executable:
  chmod +x scripts/build_images.sh

EOF

exit 0
