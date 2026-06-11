# Expanded Mock Data Summary

## Overview

Mock data has been significantly expanded to create a more realistic and comprehensive data catalog. All data is now seeded into PostgreSQL during database initialization.

## Expansion Statistics

### Products: 4 → 6
**New products added:**
- **prod-5**: Customer Service & Support
  - Help desk and support ticketing system
  - Owner: Customer Support Team
  - Icon: icon-headset
  
- **prod-6**: Marketing & Compliance
  - Marketing campaigns and regulatory compliance tracking
  - Owner: Marketing & Legal Teams
  - Icon: icon-megaphone

### Datasets: 7 → 10
**New datasets:**
- **ds-8**: Support System (linked to prod-5)
  - Help desk ticketing and support agent data
  
- **ds-9**: Campaign Management (linked to prod-6)
  - Marketing campaign and promotion data
  
- **ds-10**: Regulatory Compliance (linked to prod-6)
  - Compliance records and audit logs

### Data Objects: 12 → 16
**New objects:**
- **Ticket**: from Support System
  - Support tickets and issue tracking
  
- **SupportAgent**: from Support System
  - Support agent profiles and assignments
  
- **Campaign**: from Campaign Management
  - Marketing campaign definitions and metadata
  
- **RegulatoryRecord**: from Regulatory Compliance
  - Compliance records and audit logs

### Versions: 20 → 31
**Schema evolution tracking:**
- Added version 3 for Contact - 9 attributes
- Added version 2 for Inventory - 8 attributes
- Added version 2 for DimDate - 9 attributes
- Added version 2 for Country - 8 attributes
- Added version 2 for Currency - 7 attributes
- Initial versions for new objects (Ticket, SupportAgent, Campaign, RegulatoryRecord)

### Attributes: 94 → 226
**Attribute expansion:**
- Added support for versioning (multiple versions of same attribute with different evolution)
- Added attributes for all new objects
- Added attributes for evolved versions

**New object attributes:**
- **Ticket** (8): ticket_id, customer_id, subject, description, priority, status, created_at, resolved_at
- **SupportAgent** (6): agent_id, agent_name, email, department, is_available, assigned_tickets
- **Campaign** (7): campaign_id, campaign_name, campaign_type, target_audience, start_date, end_date, budget_amount
- **RegulatoryRecord** (8): record_id, record_type, entity_id, regulation, compliance_status, reviewed_by, review_date, last_audit

**Evolved object attributes:**
- **Contact v3**: preferred_contact, last_contacted, contact_frequency
- **Inventory v2**: warehouse_location, last_restocked, restock_status
- **DimDate v2**: fiscal_year, day_of_week, is_holiday
- **Country v2**: continent, region_code
- **Currency v2**: minor_unit_symbol, iso_numeric_code

### Deliveries: 19 → 37
**New delivery records (18 additional):**
- Multiple deliveries for version 3 objects (Contact)
- Deliveries for new objects (Ticket, SupportAgent, Campaign, RegulatoryRecord)
- Version 2 deliveries for evolved objects (Inventory, DimDate, Country, Currency)
- Extended delivery history (now covers Feb 18-21, 2026)

**Record counts range:**
- Small reference tables: 180-367 rows (Currency, Country, DimDate)
- Master data: 2.4K-91K rows (Customer, Ticket, Agent, Campaign, Inventory)
- Large transactions: 145K+ rows (Customer, Order, Transaction, Sales)
- Streaming events: 2.8M-5.4M rows (PageView, Click events)

**File sizes range:**
- 42KB-128KB for reference data (Currency, Country, DimDate)
- 650KB-1.2GB for transactional and event data

## Data Hierarchy Visualization

```
Products (6)
├── prod-1: Customer & Order Management
│   ├── ds-1: CRM System
│   │   ├── Customer (3 versions, 10 attrs)
│   │   └── Contact (3 versions, 9 attrs)
│   └── ds-2: Order Processing
│       └── Order (2 versions, 9 attrs)
├── prod-2: Financial Transactions
│   └── ds-3: Payments
│       └── Transaction (2 versions, 10 attrs)
├── prod-3: Product Catalog
│   └── ds-4: Product Master
│       ├── Product (2 versions, 9 attrs)
│       └── Inventory (2 versions, 8 attrs)
├── prod-4: Analytics & Reporting
│   └── ds-5: Data Warehouse
│       ├── DimDate (2 versions, 9 attrs)
│       └── FactSales (2 versions, 10 attrs)
├── prod-5: Customer Service & Support
│   └── ds-8: Support System
│       ├── Ticket (1 version, 8 attrs)
│       └── SupportAgent (1 version, 6 attrs)
└── prod-6: Marketing & Compliance
  ├── ds-9: Campaign Management
  │   └── Campaign (1 version, 7 attrs)
  └── ds-10: Regulatory Compliance
    └── RegulatoryRecord (1 version, 8 attrs)

Standalone Datasets (2)
├── ds-6: Real-Time Events
│   ├── PageViewEvent (2 versions, 9 attrs)
│   └── ClickEvent (1 version, 6 attrs)
└── ds-7: Master Reference Data
  ├── Country (2 versions, 8 attrs)
  └── Currency (2 versions, 7 attrs)
```

## SQL Seed Files Generated

Files are located in `dq-api/db/init/`:
- `generated_seed_20260225T223841Z_data_products.sql` - 6 products
- `generated_seed_20260225T223841Z_data_sets.sql` - 10 datasets
- `generated_seed_20260225T223841Z_data_objects_catalog.sql` - 16 objects
- `generated_seed_20260225T223841Z_data_object_versions.sql` - 31 versions
- `generated_seed_20260225T223841Z_attributes_catalog.sql` - 226 attributes
- `generated_seed_20260225T223841Z_data_deliveries.sql` - 37 deliveries

All files use PostgreSQL COPY format with inline CSV data.

## Updated CSV Sources

Files in `dq-api/mock-data/`:
- `data-products.csv` - 6 products (expanded)
- `data-sets.csv` - 10 datasets (expanded)
- `data-objects-catalog.csv` - 16 objects (expanded)
- `data-object-versions.csv` - 31 versions (expanded)
- `attributes-catalog.csv` - 226 attributes (expanded)
- `data-deliveries.csv` - 37 deliveries (expanded)

## Testing the Expanded Data

After starting containers with `docker-compose up`:

```sql
-- Connect to PostgreSQL
psql postgresql://postgres:postgres@localhost:5432/dq_prototype

-- Verify products
SELECT count(*) FROM data_products;  -- Should be 6

-- Verify hierarchy depth
SELECT do.id, do.name, count(DISTINCT dov.id) as versions
FROM data_objects_catalog do
LEFT JOIN data_object_versions dov ON do.id = dov.data_object_id
GROUP BY do.id, do.name
ORDER BY do.id;

-- Check attribute coverage
SELECT COUNT(*) FROM attributes_catalog;  -- Should be 226+

-- Verify deliveries
SELECT COUNT(*) FROM data_deliveries;  -- Should be 37+
```

## Attribute Type Distribution

**Types represented:**
- string: Email, UUID, phone formats
- number: Integers for counts, IDs
- date/timestamp: Temporal data with ISO format
- decimal: Currency and financial amounts
- boolean: Status flags, activity indicators
- object/array: Complex nested data

**Nullable/Not Nullable:**
- ~60% required (NOT NULL): IDs, timestamps, core attributes
- ~40% optional (NULLABLE): Extended metadata, optional fields

## Realistic Business Scenarios

The expanded data now supports testing:
- **Multi-product portfolio**: Browse across 6 distinct data domains
- **Schema versioning**: Track attribute changes across 3 versions (Customer)
- **Large-scale data**: Support transactions with 2M+ records
- **Streaming data**: Real-time events with 5M+ row counts
- **Small reference data**: Master data tables with &lt;400 rows
- **Team-based ownership**: Different departments own different products
- **Cross-functional dependencies**: Support tickets linked to customers (prod-5 → prod-1)
- **Regulatory requirements**: Compliance tracking (prod-6)
- **Campaign management**: Marketing execution (prod-6)

## Next Steps

1. **Deploy**: Run `docker-compose up` to initialize database with expanded data
2. **UI Testing**: Browse Data Catalog to verify all 16 objects with versions
3. **Search Functionality**: Test searches across expanded attributes
4. **Rule Execution**: Set up rules that operate on new object types
5. **Delivery Tracking**: Display delivery metrics for expanded objects
