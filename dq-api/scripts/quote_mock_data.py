#!/usr/bin/env python3
"""Sanitize mock-data CSVs by quoting fields that contain commas or extra columns.

This script reads each CSV in mock-data, ensures each row has the same
number of columns as the header by merging any extra trailing columns into
the last header column, and writes the file back using the csv module so
that fields containing commas are properly quoted.

Usage: python3 scripts/quote_mock_data.py [mock-data-dir]
"""
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Accept mock-data directory as command-line argument, default to ROOT/mock-data
MOCK_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "mock-data"

FILES = [
    "approvals.csv",
    "data-objects.csv",
    "rule_versions.csv",
    "roles.csv",
    "rule-attributes.csv",
    "rules.csv",
    "users.csv",
    "workspaces.csv",
    "app-config.csv",
    "data-products.csv",
    "data-sets.csv",
    "data-deliveries.csv",
    "data-object-versions.csv",
    "attributes-catalog.csv",
    "data-objects-catalog.csv",
    "audit.csv",
    "test_proofs.csv",
]


def sanitize_file(path: Path) -> None:
    # Read using csv module with newline='' so quoted multiline fields are preserved
    with path.open('r', encoding='utf-8', newline='') as fh:
        # All repo-managed mock-data CSVs use comma as the canonical delimiter.
        # Sniffer misclassifies JSON-heavy samples, so keep the parser fail-fast and explicit.
        reader = csv.reader(fh, delimiter=',')
        rows = list(reader)
        if not rows:
            return
        header_row = rows[0]
        ncols = len(header_row)

        out_rows = [header_row]
        for r in rows[1:]:
            # skip entirely empty rows
            if not any((c is not None and str(c).strip() != '') for c in r):
                continue
            if len(r) > ncols:
                # merge extras into last column preserving delimiter
                merged = r[: ncols - 1] + [','.join(r[ncols - 1 :])]
                out_rows.append(merged)
            else:
                if len(r) < ncols:
                    r = r + [""] * (ncols - len(r))
                out_rows.append(r)

    # write back using comma delimiter and csv quoting (so commas in descriptions get quoted)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        # Quote all fields so string values containing commas/newlines are safe
        writer = csv.writer(fh, delimiter=",", quoting=csv.QUOTE_ALL)
        for row in out_rows:
            writer.writerow(row)

    tmp.replace(path)


def main():
    for fname in FILES:
        p = MOCK_DIR / fname
        if not p.exists():
            print(f"Skipping missing: {p}")
            continue
        if os.environ.get("LOG_LEVEL", "INFO").upper() == "DEBUG":
            print(f"Sanitizing: {p}")
        sanitize_file(p)


if __name__ == "__main__":
    main()
