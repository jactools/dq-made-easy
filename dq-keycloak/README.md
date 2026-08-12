# Keycloak Seed Artifacts (dq-made-easy)

**Keycloak image and container lifecycle are managed by `platform-foundation` (`platform-keycloak`).**

## Platform vs Consumer Responsibilities

| Responsibility | Owner |
|---|---|
| Keycloak runtime image | `platform-foundation` (platform-keycloak) |
| Realm import from JSON | `platform-foundation` bootstrap |
| User seeding from CSV | `platform-foundation` bootstrap |
| Password rotation | `platform-foundation` bootstrap |
| DQ client redirect syncs | `dq-made-easy` (consumer bootstrap) |
| DQ service-account role assignments | `dq-made-easy` (consumer bootstrap) |

## Directory Structure

```
dq-keycloak/
├── Dockerfile.keycloak.seed      # Builds seed artifacts (realm JSON, user CSV)
├── scripts/
│   ├── generate_seed_artifacts.sh  # Realm/user generation script
│   └── consumer-bootstrap.sh       # DQ-specific client syncs and role assignments
└── README.md                      # This file
```

## Seed Artifacts

The seed artifacts are generated at container startup and mounted into the
platform-keycloak container at `/opt/keycloak/realm-import`:

- `<realm>-realm.json` — Keycloak realm configuration (clients, roles, users)
- `keycloak_seed_user_credentials.csv` — Seed user credentials for password rotation

## Consumer Bootstrap

The `consumer-bootstrap.sh` script is mounted at
`/opt/platform-keycloak/scripts/consumer-bootstrap.sh` and handles:

- DQ-rules-ui client redirect sync (OIDC, Vite, Nginx, Kong)
- Grafana client redirect sync and service-account role assignment
- Zammad client redirect sync
- DQ engine worker service-account role assignment
- OpenMetadata admin service-account role assignment

## Platform-Keycloak (platform-foundation)

The `platform-keycloak` image in `platform-foundation` provides:

- Keycloak runtime baseline (`quay.io/keycloak/keycloak:26.6.2`)
- Trust-bundle initialization (Java keystore, CA trust)
- Realm import from JSON
- User seeding from CSV
- Password rotation
- Optional consumer bootstrap mount point

See `platform-foundation/docker/keycloak/` for the Dockerfile and scripts.
