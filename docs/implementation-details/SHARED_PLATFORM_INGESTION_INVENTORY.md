# Shared Platform Ingestion Inventory

**Status**: Complete  
**Date**: 2026-08-03  
**Work item**: SHARED-I-W1-01

## Purpose

Inventory every production ingestion or ingestion-adjacent path in `dq-made-easy`, distinguish metadata/synthetic flows from real row-data ingestion, and classify ownership.

## Classification Rules

- **Shared candidate**: reusable mechanics with no DQ business policy.
- **Split**: reusable transport/runtime mechanics can move, while DQ orchestration remains.
- **DQ-owned**: behavior exists specifically to execute, profile, seed, or report DQ workflows.
- **Not real-data ingestion**: metadata-only or synthetic flow; it cannot by itself satisfy MaaS real-data verification.

## Inventory

| Capability | Primary paths | Data handled | Classification | Boundary decision |
|---|---|---|---|---|
| Connector framework and provider discovery | `dq-api/fastapi/app/domain/interfaces/v1/connector.py`; `dq-api/fastapi/app/application/services/{postgresql_connector,sql_server_connector,azure_adls_connector,s3_blob_connector,external_api_connector}.py` | Schemas, tables, object metadata, API resource metadata | Split; metadata ingestion | Connector protocol and provider clients are shared candidates after MaaS contract comparison; DQ entities and API models stay DQ-owned. |
| Connector sync orchestration | `connector_sync_orchestrator.py`; connector job/schedule entities and repositories; connector endpoints | Sync jobs, schedules, asset snapshots | DQ-owned orchestration | Keep DQ job persistence, routes, retry policy, workspace semantics, and status views in DQ. |
| Connector background worker | `dq-engine/connector_sync_worker.py` | Connector metadata sync results | Split | Generic worker lifecycle/retry mechanics may be shared; DQ database tables, provider map, logging, and job result contract stay DQ-owned. |
| Local CSV to Parquet/S3 staging | `scripts/stage_local_csv_to_s3_parquet.py` | Caller-supplied CSV row data converted to Parquet and uploaded | **Shared candidate; real-data ingestion** | First recommended ingestion extraction: file parsing, transform selection, S3 client, bucket/prefix writes, checksums, and result contract. Keep DQ join-pair naming and catalog/delivery resolution in a thin DQ adapter. |
| Delivery object generation and upload | `scripts/seed_delivery_objects.py`; `dq-db/mock-data/data-{deliveries,delivery-notes,objects,object-versions}.csv`; `attributes-catalog.csv` | Deterministic generated rows in Parquet, CSV, JSON, Avro, Delta, and Iceberg | Split; synthetic verification data | Share format generation, schema-driven record generation, Spark setup, and object upload. Keep DQ seed catalogs, delivery semantics, and DQ defaults in DQ. |
| Playground source bundle ingestion | `playground_source_bundles.py`; `scripts/ingest_playground_source_bundles.py` | JSON records containing source URLs, licenses, and descriptions | Not real-data ingestion; metadata fixture | Generic idempotent S3 JSON storage is reusable, but the source catalog is DQ demo content. Do not use this as the first MaaS real-data proof. |
| OpenMetadata database ingestion | `dq-metadata/scripts/sync_dq_db_with_openmetadata.sh`; `docker-compose/metadata.yml`; OpenMetadata ingestion profile | PostgreSQL schema/table/column metadata | Metadata ingestion | Keep DQ database source and OpenMetadata entity mapping in DQ. Vendor runtime/image mechanics are an image inventory candidate. |
| LDD/OpenMetadata import pipelines | `run_ldd_openmetadata_pipeline.py`; `transform_ldd_to_openmetadata.py`; `seed_openmetadata_*.py` | Glossary, definitions, mappings, contracts, product specs, users | Metadata ingestion | Domain payloads and DQ/OpenMetadata mappings remain DQ-owned. Generic authenticated API and CSV transformation helpers may later move only if MaaS needs the same contract. |
| GX source-data resolution | `source_data_resolver.py`; `dq-engine/gx_dispatch_runtime.py` | Catalog targets and delivery files read for DQ execution | DQ-owned execution; ingestion-adjacent | Keep assignment scope, execution target resolution, and Spark/GX dispatch in DQ. A generic delivery-file fetcher may be reused by the ingestion runtime later. |
| Local source file execution proof | `dq-engine/scripts/spark_expectations_teller_machine_poc.py` | Parquet row data | DQ-owned proof | Retain as DQ engine proof; it is not a production ingestion entrypoint. |
| Profiling ETL | `dq-profiling/python/etl.py` | S3 objects read for profiling; profile output written back | DQ-owned processing | Keep profiling transformations and result contract in DQ. Reuse the future shared object-storage client rather than moving the whole worker. |
| Generated test-data materialization | `dq-engine/test_data_materialization_worker.py` and associated API service | Synthetic generated datasets | DQ-owned orchestration with shared storage potential | Keep rule/test-data semantics in DQ; use shared storage/format primitives after extraction. |
| Database and application seeding | `dq-db/mock-data`; `dq-api/scripts/generate_sql_seeds.py`; root seeding scripts | Application seed state and synthetic catalog data | DQ-owned; not real-data ingestion | Do not move. |
| Kafka violation consumer and exception persistence | `dq-kafka-consumer`; validation pipeline scripts; exception storage | DQ violation and exception facts | DQ-owned result ingestion | Do not move into the general ingestion package. |

## Complete Real-Data Finding

The connector framework currently performs **metadata discovery/sync**, not bulk row-data movement. The only clear reusable row-data ingestion entrypoint is `scripts/stage_local_csv_to_s3_parquet.py`. `seed_delivery_objects.py` is useful for verification but generates synthetic data. The playground bundle flow stores metadata records rather than the referenced public datasets.

## Shared Extraction Boundary

The first shared ingestion package should provide:

- explicit source-file input; no repository-relative source defaults
- CSV-to-Parquet transformation
- reusable S3-compatible client configuration
- bucket/prefix validation and idempotent upload
- checksums, row/file counts, and typed ingestion results
- generic TLS/CA and endpoint settings

Consumer adapters should provide:

- DQ or MaaS destination naming
- catalog and delivery identity resolution
- domain-specific metadata registration
- product-specific orchestration and authorization

## Recommended First Extraction

Extract a `platform_foundation` file-to-object-storage ingestion kernel from `scripts/stage_local_csv_to_s3_parquet.py`. Use one explicit real CSV fixture as the cross-repo verification proof. Add synthetic multi-format generation from `seed_delivery_objects.py` only after that vertical slice works.
