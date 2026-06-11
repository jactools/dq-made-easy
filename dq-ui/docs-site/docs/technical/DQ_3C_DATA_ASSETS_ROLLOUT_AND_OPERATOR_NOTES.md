# DQ-3c Data Assets Rollout and Operator Notes

This note records the rollout expectations for the DQ-3c Data Assets implementation.

## Audience

- Operators running the dq-rulebuilder stack
- Maintainers validating Data Assets in local, seeded, or staged environments

## What Is Enabled

- Data Assets can be created from source bindings, manual authoring, or schema-only uploads
- Generated ODCS contracts are stored as versioned records and can be downloaded from the Data Assets API
- Data Assets are available immediately as rule inputs
- The test-data generator can target a Data Asset and resolve its schema and derived fields
- Playground source bundles are stored once in AIStor and reused across workspaces
- Workspace bundle defaults allow every bundled playground source unless a workspace admin disables specific bundle ids

## Supported Playground Bundles

The canonical bundle list is:

- `ons-national-statistics`
- `abs-national-statistics`
- `stats-nz-national-statistics`
- `ecb-finance-terminology`
- `boe-finance-terminology`

If a workspace disables one of these ids, the UI should hide it for that workspace rather than silently substituting another source.

## Rollout Guidance

1. Rebuild the API and UI images with the release line that contains the DQ-3c changes.
2. Verify the AIStor bucket is reachable before enabling playground bundle ingestion.
3. Keep the workspace default in the allow-all state until an admin explicitly disables a bundle id.
4. Confirm at least one schema-only Data Asset can be created, contracted, and used for test-data generation.
5. Treat missing S3, missing `boto3`, missing catalog metadata, or unsupported schema inputs as fail-fast errors.

## Validation Expectations

Run the focused regression checks that cover the end-to-end Data Assets path:

```bash
cd dq-api/fastapi
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python -m pytest tests/api/test_data_assets_endpoint.py tests/api/test_data_catalog_endpoints.py tests/application/services/test_playground_source_bundles.py -q --no-cov -o addopts=''
```

```bash
cd dq-ui
npx vitest run src/components/ApplicationSettings.ui.test.tsx src/components/rules/useRuleAttributeCatalog.test.tsx src/components/JoinConditionsModal.test.tsx
```

Expected outcomes:

- schema-only upload preview columns appear in the generated contract
- Data Asset fields remain selectable as rule inputs
- test-data generation resolves a Data Asset version and its attributes
- playground bundles remain one-time AIStor objects and workspace disablement stays explicit

## Troubleshooting

- If contract download fails, confirm the Data Asset has at least one version and the repository still resolves the current version id.
- If test-data generation fails, confirm the target asset exists and the generator use case still resolves the Data Asset version metadata.
- If bundle ingestion fails, check AIStor reachability, credentials, and whether the bundle id is in the supported list.

## References

- [DQ-3c implementation details](/docs/implementation-details/DQ_3C_DATA_ASSETS_IMPLEMENTATION_DETAILS/)
- [Data Assets feature plan](/docs/features/DATA_ASSETS_FEATURES/)
- [Data Assets endpoint tests](https://github.com/jactools/dq-rulebuilder/blob/main/dq-api/fastapi/tests/api/test_data_assets_endpoint.py)
- [Data catalog endpoint tests](https://github.com/jactools/dq-rulebuilder/blob/main/dq-api/fastapi/tests/api/test_data_catalog_endpoints.py)
- [Playground bundle ingestion tests](https://github.com/jactools/dq-rulebuilder/blob/main/dq-api/fastapi/tests/application/services/test_playground_source_bundles.py)