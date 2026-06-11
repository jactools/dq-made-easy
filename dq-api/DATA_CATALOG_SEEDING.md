# Data Catalog Seeding Guide

## Overview

The Data Catalog feature allows browsing and managing data products, datasets, data objects, versions, attributes, and deliveries. This guide explains how the mock data is generated and seeded into the database.

## Files Structure

### Mock Data Files
CSV files are located in `dq-api/mock-data/`:
- **data-products.csv** - Product definitions (4 products)
- **data-sets.csv** - Datasets within products (7 datasets)
- **data-objects-catalog.csv** - Data objects/entities (12 objects)
- **data-object-versions.csv** - Schema versions (20 versions)
- **attributes-catalog.csv** - Attribute definitions (94 attributes)
- **data-deliveries.csv** - Data delivery records (19 deliveries)

### Database Schema
Tables are defined in `dq-api/db/init/01_schema.sql`:
- `data_products` - Product master data
- `data_sets` - Datasets (with optional product reference)
- `data_objects_catalog` - Data objects/tables
- `data_object_versions` - Schema versions with change tracking
- `attributes_catalog` - Column/field definitions
- `data_deliveries` - Data delivery metrics

## How Seeding Works

### 1. Generate SQL from CSV
The seed generation script converts CSV files to SQL COPY statements:

```bash
cd dq-api
python3 scripts/generate_sql_seeds.py \
  --input-dir mock-data \
  --output-dir db/init
```

Support-only Zammad CSVs in `dq-db/mock-data/` are intentionally excluded from this generator. The shared app database only receives the regular Data Catalog seed files; Zammad uses its own seeding flow for `zammad-admin.csv`, `zammad-generated-users.csv`, and `zammad-user-template.csv`.

This creates SQL files like:
```
generated_seed_20260225T223446Z_data_products.sql
generated_seed_20260225T223446Z_data_sets.sql
... etc
```

### 2. Docker Initialization
When running with `docker-compose up`:
1. PostgreSQL container starts
2. Mounts `db/init` directory as `/docker-entrypoint-initdb.d`
3. Executes `01_schema.sql` first (creates tables)
4. Executes all `generated_seed_*.sql` files in alphabetical order
5. Data is now available in the database

### 3. Frontend Access
The Data Catalog appears in the UI under the sidebar "Data Catalog" menu item, where users can:
- Browse products and datasets
- View data object schemas
- Explore different versions and their changes
- See attribute details and nullability
- Track delivery history

## Regenerating Seeds

When CSV files change, regenerate the SQL:

```bash
cd dq-api
python3 scripts/generate_sql_seeds.py --input-dir mock-data --output-dir db/init
```

Old files are automatically backed up to `db/init/generated_backup/`

## CSV Format

Each CSV follows this pattern:

**data-products.csv**
```csv
id,name,description,owner,created_at,icon
prod-1,Customer & Order Management,...
```

**data-object-versions.csv**
```csv
id,data_object_id,version,created_at,schema_hash,attribute_count
dov-1,do-1,1,2025-01-15T10:00:00Z,v1_abc123,4
```

**attributes-catalog.csv**
```csv
id,name,type,nullable,format,data_object_id,version_id
attr-1,customer_id,string,false,uuid,do-1,dov-1
```

## Data Relationships

```
data_products (1)
    ↓ (many)
data_sets
    ↓ (many)
data_objects_catalog
    ↓ (many)
data_object_versions
    ↓ (many)
attributes_catalog

data_deliveries → data_objects_catalog
```

Standalone datasets have `NULL` product_id.

## Example Workflow

1. **Add new data product**: Edit `data-products.csv`, add row
2. **Add related dataset**: Edit `data-sets.csv`, reference product ID
3. **Add objects/versions**: Update catalog tables
4. **Regenerate SQL**: Run seed generation script
5. **Test locally**: `docker-compose up` (fresh database)
6. **Verify**: Browse in UI under Data Catalog

## Notes

- Always run seed generation script after modifying CSV files
- Backup old seeds are kept for reference
- Schema validation happens at database level (foreign keys, types)
- CSV parser handles quoted fields with special characters
- Timestamps use ISO 8601 format
