# dq-made-easy DB Seed

Repo-managed seed image for initializing and reseeding the dq PostgreSQL
database with repo-owned extensions, mock data, and helper scripts.

## Features

- PostgreSQL seed and reseed assets
- Repository-managed database initialization scripts
- Keeps schema bootstrap and demo data close to the source tree

## Quick Start

```bash
docker pull jacbeekers/dq-db-seed:latest
```

## Tags

- `latest` - most recent build
- `0.11.5-<hash>` - content-addressed release tag used by the build scripts

## Usage

Use this image when reseeding the local database or when a clean platform test
environment needs the repo-managed seed data.

## Documentation

Repository: [dq-made-easy](https://github.com/jacbeekers/dq-rulebuilder)