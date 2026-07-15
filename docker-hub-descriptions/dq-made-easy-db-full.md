# Data Quality Made Easy Database

PostgreSQL 18 image for the Data Quality Made Easy platform. It bundles the application schema, generated seed data, mock-data assets, and in-container reseed scripts so local and deployed environments can bootstrap consistently without relying on host bind mounts.

## Features

- PostgreSQL 18 base image
- Bundled schema and initialization SQL in `/docker-entrypoint-initdb.d`
- Seed data and mock-data assets baked into the image
- In-container reseed scripts for repeatable refreshes
- Designed to work with `dq-api`, `dq-profiling`, `dq-kong`, and `dq-keycloak`

## Quick Start

```bash
docker pull jacbeekers/dq-db:latest

docker run -d \
  --name dq-db \
  -p 5432:5432 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=dq \
  jacbeekers/dq-db:latest
```

## Exposed Ports

- `5432` - PostgreSQL

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `POSTGRES_USER` | Database user | No |
| `POSTGRES_PASSWORD` | Database password | No |
| `POSTGRES_DB` | Initial database name | No |

## Image Contents

- `/docker-entrypoint-initdb.d` - first-boot schema and seed SQL
- `/opt/dq-db/init` - bundled initialization assets
- `/opt/dq-db/mock-data` - CSV/mock-data sources used by the platform
- `/opt/dq-db/scripts/reseed_running_db.sh` - reseed entrypoint for running containers

## Reseeding a Running Container

```bash
docker exec -it dq-db bash /opt/dq-db/scripts/reseed_running_db.sh
```

## Tags

- `latest` - Most recent build
- `0.3.3` and newer - explicit release tags

## Part of Data Quality Made Easy

This image is part of the Data Quality Made Easy platform.

Related images:
- `jacbeekers/dq-api` - REST API backend
- `jacbeekers/dq-profiling` - background profiling worker
- `jacbeekers/dq-frontend` - React web UI
- `jacbeekers/dq-kong` - Kong API gateway
- `jacbeekers/dq-keycloak` - bundled Keycloak realm image