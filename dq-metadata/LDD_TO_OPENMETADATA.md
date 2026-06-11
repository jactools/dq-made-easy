# LDD to OpenMetadata Transformation

This guide explains how to convert a Logical Data Definitions Excel workbook
into normalized CSV files that can be used in OpenMetadata onboarding flows.

## Script

- Path: `dq-metadata/scripts/transform_ldd_to_openmetadata.py`
- Runtime: Python 3 + `openpyxl`

## End-to-End Runner

- Path: `dq-metadata/scripts/run_ldd_openmetadata_pipeline.py`
- Purpose: orchestrate transform, glossary import, column mapping, and reporting.

Supported stages:

- `transform`
- `import-glossary`
- `apply-mappings`
- `report`

Default stage set: `all`

The runner writes these additional files into the output directory:

- `openmetadata_runner_state.json`
- `openmetadata_runner_report.json`
- `openmetadata_runner_report.md`

## Repeatable dq-db Sync

If `dq-db` is reseeded regularly, use the repeatable sync script to:

- ingest the seeded Postgres metadata into OpenMetadata (`databaseService`, `database`, schemas, tables, columns)
- optionally run the full LDD transform/import/mapping/report flow against that discovered catalog
- connect to the current OpenMetadata 1.12.4 stack over HTTPS using the bundled mkcert CA trust path

Script:

- `dq-metadata/scripts/sync_dq_db_with_openmetadata.sh`

Basic usage:

```bash
dq-metadata/scripts/sync_dq_db_with_openmetadata.sh
```

Run ingestion plus full LDD pipeline in one command:

```bash
RUN_LDD_MAPPING=true dq-metadata/scripts/sync_dq_db_with_openmetadata.sh
```

Useful overrides:

- `DB_SERVICE_NAME` (default: `dq-db`)
- `DB_HOST_PORT` (default: `db:5432` from within the ingestion container network)
- `DB_NAME` (default: `dq`)
- `DB_USERNAME` / `DB_PASSWORD` (defaults: `postgres` / `postgres`)
- `OM_BASE_URL` (default: `https://openmetadata.jac.dot:8585`)
- `OM_EMAIL` / `OM_PASSWORD_B64` (no vendor defaults; use the seeded dq-made-easy admin identity or provide `OM_TOKEN`)

## What It Produces

Output directory (default): `dq-db/mock-data/openmetadata-ready`

Generated files:

- `openmetadata_glossary_terms.csv`
- `openmetadata_column_mappings.csv`
- `openmetadata_bde_assignments.csv`
- `README.md` (run summary and counts)

## Input Workbook Detection

The script supports changing workbook filenames.

Behavior:

- If `--input` is provided, that file is used.
- If `--input` is omitted, the script scans `--input-dir` for `.xlsx` files.
- It selects files that match the expected structure by required headers.
- Temporary lock files like `~$*.xlsx` are ignored.
- If multiple files match, the most recently modified file is selected.

## Required Headers (Structure Check)

The auto-detection validates that at least these columns exist:

- `Asset Id`
- `Full Name`
- `Name`
- `Domain`
- `Status`
- `Definition`
- `Logical Data Type`
- `Domain values`
- `REF Technical Name`
- `[Data Attribute] mapping to Physical Data Dictionary [Column] > Full Name`

## Usage

From repository root:

```bash
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python \
  dq-metadata/scripts/transform_ldd_to_openmetadata.py
```

Use an explicit input file:

```bash
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python \
  dq-metadata/scripts/transform_ldd_to_openmetadata.py \
  --input "/path/to/any-workbook-name.xlsx"
```

Override auto-detect folder and output folder:

```bash
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python \
  dq-metadata/scripts/transform_ldd_to_openmetadata.py \
  --input-dir dq-db/mock-data \
  --output-dir dq-db/mock-data/openmetadata-ready
```

Set OpenMetadata FQN placeholders:

```bash
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python \
  dq-metadata/scripts/transform_ldd_to_openmetadata.py \
  --service-name my_service \
  --database-name my_database
```

Run the full pipeline:

```bash
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python \
  dq-metadata/scripts/run_ldd_openmetadata_pipeline.py \
  --service-name my_service \
  --database-name my_database
```

Run only part of the flow:

```bash
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python \
  dq-metadata/scripts/run_ldd_openmetadata_pipeline.py \
  --stages import-glossary,report
```

Preview OpenMetadata writes without applying them:

```bash
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python \
  dq-metadata/scripts/run_ldd_openmetadata_pipeline.py \
  --stages import-glossary,apply-mappings,report \
  --dry-run
```

Use an explicit token instead of login credentials:

```bash
OM_TOKEN="<jwt-or-pat>" \
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python \
  dq-metadata/scripts/run_ldd_openmetadata_pipeline.py \
  --stages import-glossary,apply-mappings,report \
  --endpoint https://openmetadata.jac.dot:8585/api
```

Limit work during testing:

```bash
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python \
  dq-metadata/scripts/run_ldd_openmetadata_pipeline.py \
  --limit-terms 20 \
  --limit-mappings 20
```

## Runner Behavior

- If `transform` is selected, the runner calls the existing transformer instead of duplicating that logic.
- Glossaries and glossary terms are upserted through the OpenMetadata REST API.
- Column mappings are applied through the column update API using glossary-term tags.
- Existing column tags are preserved and the new glossary-term tags are added on top.
- The BDE assignment CSV remains report-only for now.

## Authentication

The runner accepts either:

- `--token`
- `OM_TOKEN` environment variable
- `CATALOG_API_KEY` environment variable

If no token is provided, it logs in through OpenMetadata basic auth using:

- `--email` (defaults to `OM_EMAIL` or `OPENMETADATA_OIDC_SEED_USERNAME` when set; otherwise provide it explicitly)
- `--password` (defaults to `OM_PASSWORD` or the seeded OIDC password envs when set; otherwise provide it explicitly)

The runner first tries `POST /api/v1/users/login` and falls back to `POST /api/v1/auth/login`
for OpenMetadata deployments that expose the older route.

Default endpoint: `https://openmetadata.jac.dot:8585/api`

## Mapping Notes

- Glossary terms are deduplicated by `Asset Id` (fallback: `Full Name`, then `Name`).
- Synonyms are assembled from available technical-name style columns.
- Physical paths are parsed from `Schema > Table > Column` format.
- Column FQN pattern: `<service>.<database>.<schema>.<table>.<column>`.
- Runner imports glossary terms with safe OpenMetadata names and preserves the original business wording as display names.
- Runner groups mappings by column so each column is updated once with the full glossary-term set.

## Troubleshooting

- `ModuleNotFoundError: openpyxl`
  - Install in the project virtualenv:

```bash
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/pip install openpyxl
```

- `No .xlsx workbook with expected LDD structure found`
  - Verify the workbook is in `--input-dir` and contains the required headers.
  - Or run with `--input` to specify the file directly.

- `OpenMetadata is not healthy`
  - Confirm the stack is up in `dq-metadata` and the version endpoint responds on `https://openmetadata.jac.dot:8585/api/v1/system/version`.

- Column updates fail for placeholder FQNs
  - Re-run the transform with real `--service-name` and `--database-name` values that match the OpenMetadata table FQNs in your environment.
