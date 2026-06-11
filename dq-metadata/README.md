# dq-metadata (OpenMetadata)

This folder provides a standalone Docker Compose stack for OpenMetadata.

## LDD Transformation

To convert the Logical Data Definitions workbook (`.xlsx`) into OpenMetadata-ready CSVs,
use the transformer documented in `dq-metadata/LDD_TO_OPENMETADATA.md`.

For the full staged runner that can transform, import glossary terms, apply column mappings,
or only execute selected stages, use `dq-metadata/scripts/run_ldd_openmetadata_pipeline.py`.

To seed the ISO 11179 retail-banking registry-definition demo slice used by the governed lookup
endpoint, run `scripts/seed_openmetadata_registry_definitions.sh` from the repository root.

To seed the ODPS retail-banking product-spec demo slice, first seed the linked ODCS demo contract
from `data_sources/contracts/demo-retail-banking-customer-360.odcs.yaml` with
`dq-metadata/scripts/seed_openmetadata_contracts_from_odcs.py`, then run
`scripts/seed_openmetadata_product_specs.sh` from the repository root.

For repeatable sync against seeded `dq-db` (register/ingest source metadata, optionally run
the full LDD pipeline), use `dq-metadata/scripts/sync_dq_db_with_openmetadata.sh`.

## Services

- `openmetadata-db` (PostgreSQL 18)
- `openmetadata-search` (Elasticsearch 8)
- `openmetadata-migrate` (one-shot DB/index migration bootstrap)
- `openmetadata-server` (OpenMetadata API/UI)
- `openmetadata-ingestion` (Airflow-based ingestion service, optional profile)

## Start

```bash
cd dq-metadata
docker compose --env-file ../.env.dev.local up -d
```

Start with ingestion too (heavier image pull):

```bash
docker compose --env-file ../.env.dev.local --profile metadata-ingestion up -d
```

## Endpoints

- OpenMetadata UI/API: `https://openmetadata.jac.dot:8585`
- OpenMetadata version API: `https://openmetadata.jac.dot:8585/api/v1/system/version`
- Airflow UI (ingestion, optional): `http://localhost:18080`
- PostgreSQL (host mapped): `localhost:13306`
- Elasticsearch (host mapped): `localhost:19200`

## Stop

```bash
docker compose --env-file ../.env.dev.local down
```

## Notes

- Default demo credentials for the Airflow user are created in the container command (`admin` / `admin`).
- The local OpenMetadata stack currently runs version 1.12.4 over native HTTPS.
- The PostgreSQL 18 upgrade uses a fresh `openmetadata_pgdata_v18` volume, so the previous `openmetadata_pgdata` contents are not reused.
- If you previously ran the MySQL-backed metadata stack, remove the old database volume once so Docker can initialize the new PostgreSQL data directory cleanly.
- If you need to reset all metadata and indexes, run:

```bash
docker compose --env-file ../.env.dev.local down -v
```
