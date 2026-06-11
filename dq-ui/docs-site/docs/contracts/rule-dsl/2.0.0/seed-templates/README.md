# DQ-7 DSL 2.0.0 Seed Templates

This directory contains the JSON Schema files and JSON template payloads used for the DQ7 seed migration plan.

Files:
- `catalog.json`: template catalog for the canonical 2.0.0 seed set
- `template-catalog.schema.json`: schema for the catalog file
- `template-entry.schema.json`: schema for individual template entries
- `*.template.json`: concrete or reserved seed templates for each semantic family

Rules:
- JSON Schema is the source of truth for the catalog and template entry shape.
- Template payloads remain canonical `2.0.0` rule documents.
- Reserved templates must stay explicit rather than being collapsed into generic placeholders.
