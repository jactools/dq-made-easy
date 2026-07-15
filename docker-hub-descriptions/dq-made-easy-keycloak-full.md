# Data Quality Made Easy Keycloak

Keycloak 26 image with the Data Quality Made Easy realm configuration baked into the container. It is intended for local development and packaged deployments that need a ready-to-import identity provider for SSO and JWT flows.

## Features

- Based on `quay.io/keycloak/keycloak:26.6.2`
- Bundled realm import at `/opt/keycloak/data/import/jaccloud-realm.json`
- Designed for platform login, OIDC, and Kong JWT validation flows
- No host volume required for realm import

## Quick Start

```bash
docker pull jacbeekers/dq-keycloak:latest

docker run -d \
  --name dq-keycloak \
  -p 8080:8080 \
  -e KEYCLOAK_ADMIN=admin \
  -e KEYCLOAK_ADMIN_PASSWORD=admin \
  jacbeekers/dq-keycloak:latest \
  start-dev --import-realm
```

## Exposed Ports

- `8080` - Keycloak HTTP

## Bundled Assets

- `/opt/keycloak/data/import/jaccloud-realm.json` - preconfigured realm import

## Typical Usage

Use this image alongside:

- `jacbeekers/dq-api` for authentication callbacks and user bootstrap
- `jacbeekers/dq-kong` for JWT validation at the gateway layer
- `jacbeekers/dq-frontend` for browser-based SSO

## Tags

- `latest` - Most recent build
- `0.3.3` and newer - explicit release tags

## Part of Data Quality Made Easy

This image is part of the Data Quality Made Easy platform and is optimized for its local and packaged deployment workflows.