# OpenMetadata Mapping vs Catalog Gap

Generated: 2026-03-12 (local)

## Summary
- Mapping distinct `schema.table` pairs: `539`
- Catalog distinct `schema.table` pairs: `30`
- Mapping pairs present in catalog: `0`
- Mapping pairs missing in catalog: `539`
- Catalog schemas observed: `public`

## Top Missing Schemas (by distinct tables)
- `Schema_tdf`: `81`
- `Schema_dbo`: `69`
- `Schema_OWNER_PUB`: `53`
- `Schema_dwfr`: `48`
- `Schema_dih`: `48`
- `Schema_tdm`: `34`
- `Schema_gfportal`: `34`
- `Schema_idq`: `24`
- `Schema_ebx5`: `23`
- `Schema_split`: `18`
- `Schema_gfs`: `18`
- `Schema_safe`: `16`

## Sample Missing Pairs
- `Schema_OWNER_PUB.ACG_ENTR__BES_AC_1DB3C54FB4AAC`
- `Schema_OWNER_PUB.BAL_CMPS__BES_BA_16406583D9637`
- `Schema_OWNER_PUB.BBO_CR_D__BES_BB_1FAB1B62FE520`
- `Schema_OWNER_PUB.BBO_MUT___BES_BB_16CBB3028DF57`
- `Schema_OWNER_PUB.BBP_DS__BES_BB_17467B31E51CD`
- `Schema_OWNER_PUB.BSC_PYMT__BES_BS_1ADCFD5EB25DA`
- `Schema_OWNER_PUB.BSC_PYMT__BES_BS_1ADCFD70226F1`
- `Schema_OWNER_PUB.BSC_PYMT__S_BSC__15EFFAF291F95`
- `Schema_OWNER_PUB.BSC_PYMT__S_BSC__1A5926212D27E`
- `Schema_OWNER_PUB.CIA_DS__BES_CI_176785EB3FD62`

## Interpretation
`apply-mappings` is currently robust (non-fatal) but cannot resolve targets because the active OpenMetadata catalog only contains `dq-db.dq.public.*`, while the mapping file targets many non-public schemas (`Schema_*`).

Code-level FQN reconciliation cannot recover these mappings without one of:
1. Ingesting the missing source schemas/tables into OpenMetadata.
2. Applying an explicit, deterministic schema/table remap before `apply-mappings`.
