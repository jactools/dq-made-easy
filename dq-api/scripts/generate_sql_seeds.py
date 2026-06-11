#!/usr/bin/env python3
r"""
Generate SQL seed files from CSV files found under `data/mock-data`.

For each CSV file `name.csv` this script writes a file
`<output_dir>/generated_seed_<timestamp>_<name>.sql` containing a
`COPY <name> (col1, col2, ...) FROM stdin WITH (FORMAT csv, HEADER true);`
followed by the CSV content and a `\.` terminator. These SQL files can be
applied with `psql -f` or executed inside docker-compose as part of seeding.
"""

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import sys
import shutil


# Keep CSV headers aligned with ORM field names where practical, then map any
# table-specific legacy PostgreSQL column names when generating COPY headers.
TABLE_COLUMN_ALIASES = {
    "rules": {
        "created_by": "createdby",
    },
}

TABLE_EXCLUDED_COLUMNS = {
    "users": {"password"},
}


def load_default_user_preferences(input_dir: Path) -> str:
    candidate = (input_dir / "users-default-preferences.json").resolve()
    input_root = input_dir.resolve()
    try:
        candidate.relative_to(input_root)
    except ValueError as exc:
        raise RuntimeError(f"default user preferences file escapes mock-data root: {candidate}") from exc

    if not candidate.is_file():
        raise RuntimeError(f"missing default user preferences file: {candidate}")

    contents = candidate.read_text(encoding="utf-8").strip()
    if not contents:
        raise RuntimeError(f"default user preferences file is empty: {candidate}")

    json.loads(contents)
    return contents


def resolve_json_reference(input_dir: Path, csv_path: Path, value: str) -> str:
    reference = value.strip()
    if not reference.lower().endswith(".json"):
        if reference.startswith("{") or reference.startswith("["):
            raise RuntimeError(
                f"inline JSON is not allowed in mock-data CSVs: {csv_path} contains an embedded JSON value; move it to a .json file"
            )
        return value

    candidate = (input_dir / reference).resolve()
    input_root = input_dir.resolve()
    try:
        candidate.relative_to(input_root)
    except ValueError as exc:
        raise RuntimeError(f"JSON reference escapes mock-data root: {reference!r} in {csv_path}") from exc

    if not candidate.is_file():
        raise RuntimeError(f"missing JSON reference file: {reference!r} in {csv_path}")

    contents = candidate.read_text(encoding="utf-8").strip()
    if not contents:
        raise RuntimeError(f"empty JSON reference file: {candidate}")

    return contents

EXCLUDED_CSV_STEMS = {
    "zammad-admin",
    "zammad-generated-users",
    "zammad-user-template",
}


def load_data_object_catalog_ids(in_dir: Path) -> set[str]:
    for candidate_name in ("data-objects-catalog.csv", "data_objects_catalog.csv"):
        candidate = in_dir / candidate_name
        if not candidate.is_file():
            continue

        catalog_ids: set[str] = set()
        with candidate.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                object_id = (row.get("id") or "").strip()
                if object_id:
                    catalog_ids.add(object_id)

        if not catalog_ids:
            raise RuntimeError(f"No data object ids found in {candidate}")

        return catalog_ids

    return {}


def generate_sql_for_csv(
    csv_path: Path,
    out_dir: Path,
    order_prefix: str = "",
    *,
    input_dir: Path,
    data_object_ids: set[str] | None = None,
) -> Path:
    # sanitize table name: replace non-alphanumeric with underscore
    raw_table = csv_path.stem
    table = re.sub(r"[^0-9a-zA-Z_]", "_", raw_table)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_file = out_dir / f"generated_seed_{order_prefix}_{timestamp}_{table}.sql"

    # Read CSV using csv module to handle quoting and newlines robustly
    # Skip any leading empty lines so we find the real header row.
    # Read file lines and robustly re-assemble records that were wrapped
    # (e.g. editors inserting newlines). We accumulate lines until parsing
    # the buffered text yields a CSV row with the expected number of columns.
    text_lines = csv_path.read_text(encoding="utf-8").splitlines()
    # find first non-empty line to use as header
    header = None
    header_line_idx = None
    for i, raw in enumerate(text_lines):
        if raw is not None and str(raw).strip() != "" and not raw.lstrip().startswith("#"):
            header_line_idx = i
            # parse header using csv.reader on a single-line input
            header = next(csv.reader([raw]))
            break
    if header is None:
        raise RuntimeError(f"Empty CSV: {csv_path}")

    # build rows by accumulating subsequent lines until a parse yields
    # the same number of columns as the header
    remaining_rows = []
    buf = None
    expected_cols = len(header)
    for raw in text_lines[header_line_idx + 1 :]:
        # skip pure comment lines
        if raw.lstrip().startswith("#"):
            continue
        if buf is None:
            buf = raw
        else:
            buf = buf + "\n" + raw
        # try to parse current buffer
        try:
            parsed = list(csv.reader([buf]))
        except Exception:
            parsed = []
        if parsed and len(parsed[0]) == expected_cols:
            remaining_rows.append(parsed[0])
            buf = None
        else:
            # keep accumulating lines until we match expected cols
            continue
    # if anything left in buffer, try a final parse and include if non-empty
    if buf is not None:
        try:
            parsed = list(csv.reader([buf]))
            if parsed:
                remaining_rows.append(parsed[0])
        except Exception:
            pass

    def sanitize_col(s: str) -> str:
        s = s.strip()
        # replace spaces and hyphens with underscore
        s = re.sub(r"[\s\-]+", "_", s)
        # replace any remaining invalid characters with underscore
        s = re.sub(r"[^0-9a-zA-Z_]+", "_", s)
        table_mapping = TABLE_COLUMN_ALIASES.get(table, {})
        # map some known header names to DB column names and normalize variants
        key = s.lower()
        if key in table_mapping:
            return table_mapping[key]
        mapping = {
            "table": "data_object",
            "generated": "generated",
            "is_template": "is_template",
            "requestedby": "requesterId",
            "requested_at": "requested_at",
            "requestedat": "requested_at",
        }
        # Prefer mapped name; fall back to sanitized key (lowercase)
        return mapping.get(key, key)

    # Include all non-empty header cells as columns (use sanitized/mapped names)
    sanitized_header = []
    included_column_indexes = []
    excluded_columns = TABLE_EXCLUDED_COLUMNS.get(table, set())
    for index, column in enumerate(header):
        if column is None or str(column).strip() == "":
            continue
        sanitized_column = sanitize_col(column)
        if sanitized_column in excluded_columns:
            continue
        sanitized_header.append(sanitized_column)
        included_column_indexes.append(index)
    cols = ", ".join(sanitized_header)

    if len(included_column_indexes) != len(header):
        remaining_rows = [
            [row[index] if index < len(row) else "" for index in included_column_indexes]
            for row in remaining_rows
        ]

    remaining_rows = [
        [resolve_json_reference(input_dir, csv_path, cell) if isinstance(cell, str) else cell for cell in row]
        for row in remaining_rows
    ]

    if table == "data_deliveries":
        if not data_object_ids:
            raise RuntimeError(
                "data_deliveries SQL generation requires data-objects-catalog.csv so data_object_id values can be validated against catalog ids"
            )
        try:
            data_object_id_idx = sanitized_header.index("data_object_id")
        except ValueError as exc:
            raise RuntimeError("data_deliveries CSV is missing required data_object_id column") from exc

        normalized_rows = []
        for row in remaining_rows:
            if len(row) <= data_object_id_idx:
                raise RuntimeError(f"data_deliveries row is missing data_object_id value: {row}")
            original_value = row[data_object_id_idx].strip()
            if not original_value:
                raise RuntimeError(f"data_deliveries row has empty data_object_id value: {row}")

            if original_value not in data_object_ids:
                raise RuntimeError(
                    f"data_deliveries.data_object_id value is not present in data-objects-catalog.csv: {original_value!r} in {csv_path}"
                )

            normalized_rows.append(list(row))

        remaining_rows = normalized_rows

    # Write COPY statement and CSV content without additional comments or blank lines
    with out_file.open("w", newline="", encoding="utf-8") as out:
        out.write(f"COPY {table} ({cols}) FROM stdin WITH (FORMAT csv, HEADER true);\n")
        # write sanitized header + rows using csv.writer to ensure proper quoting/escaping
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(sanitized_header)
        # write the rows we collected from the CSV
        for row in remaining_rows:
            if row and any((c is not None and str(c) != "") for c in row):
                writer.writerow(row)
        out.write("\\.\n")

        # Keep seeded users consistent when CSV omits preferences.
        if table == "users":
            default_preferences = load_default_user_preferences(input_dir)
            escaped_preferences = default_preferences.replace("'", "''")
            out.write("UPDATE users\n")
            out.write(f"SET preferences = '{escaped_preferences}'\n")
            out.write("WHERE preferences IS NULL OR trim(preferences) = '';\n")

    return out_file


def generate_sql_seeds(in_dir: Path, out_dir: Path, pattern: str = "*.csv") -> int:
    out_dir.mkdir(parents=True, exist_ok=True)

    # move any existing generated files to a backup directory to avoid re-applying malformed or stale files
    backup_dir = out_dir / "generated_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    existing = list(out_dir.glob("generated_seed_*.sql"))
    nr_moved_files = 0
    for ex in existing:
        try:
            # skip files already in the backup dir
            if ex.parent == backup_dir:
                continue
            dest = backup_dir / ex.name
            shutil.move(str(ex), str(dest))
            nr_moved_files = nr_moved_files + 1
#            print(f"Moved existing generated file to backup: {dest}")
        except Exception as e:
            print(f"Failed to move existing generated file {ex}: {e}", file=sys.stderr)

    print(f"Moved {nr_moved_files} existing generated files to backup dir: {backup_dir}")

    csvs = sorted(in_dir.glob(pattern))
    filtered_csvs = []
    nr_csv_files = 0
    for csv_file in csvs:
        stem = csv_file.stem.lower()
        if stem in EXCLUDED_CSV_STEMS or stem.startswith("zammad-") or stem.startswith("zammad_"):
            print(f"Skipping support-only CSV: {csv_file}")
            continue
        if stem.endswith("-temp") or stem.endswith("_temp"):
            print(f"Skipping temporary CSV: {csv_file}")
            continue
        filtered_csvs.append(csv_file)
        nr_csv_files = nr_csv_files + 1
    csvs = filtered_csvs
    if not csvs:
        print(f"No CSV files found in {in_dir}")
        return 0

    data_object_ids = load_data_object_catalog_ids(in_dir)
    if any(c.stem.replace("-", "_") == "data_deliveries" for c in csvs) and not data_object_ids:
        raise RuntimeError(
            "data-deliveries.csv is present but data-objects-catalog.csv could not be loaded; the delivery seed would violate the data_object_id foreign key"
        )

    print(f"Found {nr_csv_files} CSV files in {in_dir} (after filtering), generating SQL seeds into {out_dir}...")

    # Define table execution order to satisfy foreign key constraints
    # This must match the ORDERED_TABLES list in seed_local_postgres.sh
    ordered_tables = [
        "workspaces",
        "users",
        "roles",
        "user_roles",
        "data_products",
        "data_sets",
        "data_objects_catalog",
        "data_object_versions",
        "attributes_catalog",
        "attribute_definition_mappings",
        "data_deliveries",
        "data_delivery_notes",
        "data_objects",
        "gx_suite_registry",
        "gx_suite_execution_target_map",
        "gx_suite_rule_map",
        "gx_run_plans",
        "gx_run_plan_versions",
        "gx_execution_runs",
        "gx_execution_run_status_history",
        "reusable_filters",
        "reusable_joins",
        "rules",
        "rule_versions",
        "rule_reusable_filters",
        "rule_attributes",
        "approvals",
        "audit",
        "app_config",
        "test_proofs",
        "validation_runs",
        "validation_run_items",
        "data_source_metadata",
        "data_source_profiling_requests",
        "suggestions",
        "suggestion_interactions",
        "system_info",
        "validation_artifact_registry",
        "validation_artifact_status_history",
        "validation_run_plans",
        "validation_run_plan_versions",
        "validation_run_plan_transitions",
    ]

    # Create a mapping of table name to order prefix
    table_order = {}
    for i, table in enumerate(ordered_tables, start=1):
        table_order[table] = f"{i:02d}"

    nr_generated_files = 0
    for c in csvs:
        table_name = re.sub(r"[^0-9a-zA-Z_]", "_", c.stem)
        # Get order prefix; if table not in ORDERED_TABLES, assign a high number
        if table_name in table_order:
            order_prefix = table_order[table_name]
        else:
            order_prefix = "99"

        generate_sql_for_csv(
            c,
            out_dir,
            order_prefix,
            input_dir=in_dir,
            data_object_ids=data_object_ids,
        )
        nr_generated_files = nr_generated_files + 1
#            print(f"Wrote: {out}")

    print(f"Generated {nr_generated_files} SQL files into {out_dir}")
    return nr_generated_files


def main():
    p = argparse.ArgumentParser(description="Generate SQL seed files from CSVs")
    p.add_argument("--input-dir", default="data/mock-data")
    p.add_argument("--output-dir", default="db/init")
    p.add_argument("--pattern", default="*.csv", help="glob pattern for CSVs")
    args = p.parse_args()

    in_dir = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    if not in_dir.exists():
        print(f"Input dir does not exist: {in_dir}", file=sys.stderr)
        sys.exit(2)
    generate_sql_seeds(in_dir, out_dir, args.pattern)


if __name__ == "__main__":
    main()
