# OpenMetadata LDD Transformation Summary

- Source workbook: `/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-db/mock-data/Logical Data Definitions.xlsx`
- Glossary terms exported: `1917`
- Physical column mappings exported: `6554`
- BDE assignments exported: `1139`

## Notes

- `openmetadata_glossary_terms.csv`: normalized logical/business terms.
- `openmetadata_column_mappings.csv`: parsed `Schema > Table > Column` path with generated OpenMetadata FQN.
- `openmetadata_bde_assignments.csv`: leading/supporting business data element relationships.

## OpenMetadata FQN Placeholder

Generated FQN pattern uses service/database placeholders: `dq-db.dq.<schema>.<table>.<column>`
Update `--service-name` and `--database-name` values if needed.