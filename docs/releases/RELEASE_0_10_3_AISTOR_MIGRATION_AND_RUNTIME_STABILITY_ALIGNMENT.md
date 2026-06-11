# Release v0.10.3 — AIStor Migration and Runtime Stability Alignment

**Release date**: 2026-05-13
**UI version**: `0.10.3`
**API version**: `0.10.3`

## Summary

This patch release moves the local object-storage stack to AIStor free edition, keeps the application-side storage contract generic S3, fixes the Keycloak login/bootstrap edge case around generated passwords, and restores the UI mount path for async request tracking.

## Included in this release

- UI package metadata is aligned to `0.10.3`
- API package metadata is aligned to `0.10.3`
- Version markers in `VERSION_MANIFEST.json` are aligned for the changed tracked components: `Authentication`, `Infrastructure`, `DataCatalog`, `Documentation`, and `Testautomation`
- Local object storage now runs through AIStor free edition with an explicit license-file requirement
- Delivery storage, exception storage, seeding, and observability flows now use AIStor-compatible endpoints and terminology while the app-side contract stays generic S3
- Keycloak reseeding now passes generated passwords as data so hyphen-prefixed values no longer get parsed as flags
- The async request tracker provider now resolves its settings, auth, and performance dependencies correctly, preventing the blank-page UI regression

## User-visible impact

- Operators now need the repo-managed AIStor license file to be present before local stack startup
- Data delivery and exception storage continue to work through the S3-compatible object-storage contract without MinIO-specific app code
- Login and reseed flows no longer fail when a generated password begins with `-`
- The UI mounts cleanly again when the async request tracker provider initializes
- Release, deployment, and versioning docs now point at the `v0.10.3` release line

## Key implementation files

- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [dq-ui/package.json](../../dq-ui/package.json)
- [dq-api/package.json](../../dq-api/package.json)
- [docker-compose.yml](../../docker-compose.yml)
- [scripts/start-containers.sh](../../scripts/start-containers.sh)
- [scripts/seed_stack.sh](../../scripts/seed_stack.sh)
- [scripts/seeding/deliveries.sh](../../scripts/seeding/deliveries.sh)
- [scripts/seeding/keycloak.sh](../../scripts/seeding/keycloak.sh)
- [scripts/seed_delivery_objects.py](../../scripts/seed_delivery_objects.py)
- [scripts/stage_local_csv_to_s3_parquet.py](../../scripts/stage_local_csv_to_s3_parquet.py)
- [dq-api/fastapi/app/application/services/delivery_storage.py](../../dq-api/fastapi/app/application/services/delivery_storage.py)
- [dq-api/fastapi/app/application/services/exception_storage.py](../../dq-api/fastapi/app/application/services/exception_storage.py)
- [dq-api/fastapi/app/core/config.py](../../dq-api/fastapi/app/core/config.py)
- [dq-ui/src/contexts/AsyncRequestTrackerContext.tsx](../../dq-ui/src/contexts/AsyncRequestTrackerContext.tsx)
- [dq-ui/src/contexts/AsyncRequestTrackerContext.test.tsx](../../dq-ui/src/contexts/AsyncRequestTrackerContext.test.tsx)
- [dq-ui/src/components/DeliveryInventory.tsx](../../dq-ui/src/components/DeliveryInventory.tsx)
- [observability/prometheus/prometheus.yml](../../observability/prometheus/prometheus.yml)
- [observability/grafana/provisioning/dashboards/dq-storage.json](../../observability/grafana/provisioning/dashboards/dq-storage.json)
- [observability/grafana/provisioning/dashboards/dq-infrastructure-health.json](../../observability/grafana/provisioning/dashboards/dq-infrastructure-health.json)

## Documentation updated

- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [README.md](../../README.md)
- [docs/releases/README.md](./README.md)
- [TECHNICAL.md](../../TECHNICAL.md)
- [docs/technical/DEPLOYMENT.md](../technical/DEPLOYMENT.md)
- [docs/technical/QUICKSTART_DEPLOY.md](../technical/QUICKSTART_DEPLOY.md)
- [docs/technical/AUTOMATIC_VERSIONING.md](../technical/AUTOMATIC_VERSIONING.md)

## Notes

- Repo-managed Docker image tags stay on the `0.10-<hash>` release line because image tags derive from the `major.minor` base in `VERSION_MANIFEST.json`.
- The release note copy under `dq-ui/public/release-notes/` should stay in sync with the root `RELEASE_NOTES_USER.md`.