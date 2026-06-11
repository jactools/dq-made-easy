# OpenMetadata LDD Runner Report

- Generated at: `2026-04-20T22:59:45+00:00`
- Stages: `transform, import-glossary, apply-mappings, report`
- Glossary CSV rows: `1917`
- Column mapping CSV rows: `6554`
- BDE assignment CSV rows: `1139`

## Glossary Import

- Dry run: `False`
- Glossaries processed: `1`
- Terms processed: `1917`
- Failures: `0`

## Mapping Preflight

- Distinct mapping schema.table pairs: `0`
- Distinct catalog schema.table pairs: `52`
- Present pairs: `0`
- Missing pairs: `0`
- Coverage: `100.0%`
- Minimum required coverage: `0.05`

## Mapping Alignment

- Input mapping rows: `6554`
- Aligned mapping rows: `0`
- Dropped mapping rows: `6554`
- Input distinct schema.table pairs: `539`
- Aligned distinct schema.table pairs: `0`
- Dropped distinct schema.table pairs: `539`

## Column Mapping

- Dry run: `False`
- Columns requested: `0`
- Applied or planned updates: `0`
- Unchanged columns: `0`
- Unresolved mappings: `0`
- Missing target entities: `0`
- Failures: `0`

## Notes

- BDE assignments remain report-only in this runner.
- Column mapping updates preserve existing column tags and add glossary-term tags on top.
