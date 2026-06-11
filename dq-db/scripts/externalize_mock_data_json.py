#!/usr/bin/env python3
"""Externalize inline JSON values from mock-data CSVs into entity-specific files.

This utility rewrites CSV cells containing JSON objects or arrays into relative
`.json` file references under a per-entity subfolder, for example:

    rules/<rule-id>/dsl.json
    validation-run-plan-versions/<version-id>/artifact_snapshot_json.json

It is intended for repo-maintained mock-data CSVs that are later consumed by
the SQL seed generator.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _safe_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value.strip())


def _json_file_name(column_name: str) -> str:
    safe_column = _safe_name(column_name)
    if safe_column.endswith("_json"):
        safe_column = safe_column[:-5]
    return f"{safe_column}.json"


def _load_json_value(raw_value: str):
    parsed = json.loads(raw_value)
    if not isinstance(parsed, (dict, list)):
        raise ValueError("only JSON objects and arrays are externalized")
    return parsed


def _row_score(row: list[str]) -> int:
    score = 0
    for cell in row:
        value = cell.strip()
        if not value:
            continue
        if UUID_RE.fullmatch(value) or ISO_DATE_RE.fullmatch(value):
            score -= 5
        elif value.startswith("{") or value.startswith("["):
            score -= 4
        elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            score += 2
        elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_:-]*", value):
            score += 1
    return score


def externalize_csv(csv_path: Path, mock_data_root: Path) -> int:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))

    if not rows:
        return 0

    header = rows[0]
    if not header:
        return 0

    header_index = 0
    best_score = _row_score(header)
    for index, row in enumerate(rows[1:], start=1):
        score = _row_score(row)
        if score > best_score:
            header_index = index
            best_score = score

    if header_index != 0:
        header = rows[header_index]

    data_rows = rows[:header_index] + rows[header_index + 1 :]

    row_id_index = 0
    changed_cells = 0

    for row in data_rows:
        if not row:
            continue

        row_id = _safe_name(row[row_id_index]) if row_id_index < len(row) and row[row_id_index].strip() else "row"

        for index, raw_value in enumerate(row):
            if not raw_value or not raw_value.strip():
                continue

            trimmed = raw_value.strip()
            if trimmed.lower().endswith(".json"):
                continue

            try:
                parsed = _load_json_value(trimmed)
            except Exception:
                continue

            column_name = header[index] if index < len(header) else f"column_{index}"
            file_name = _json_file_name(column_name)
            json_rel_path = Path(csv_path.stem) / row_id / file_name
            json_abs_path = mock_data_root / json_rel_path
            json_abs_path.parent.mkdir(parents=True, exist_ok=True)
            json_abs_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            row[index] = str(json_rel_path).replace("\\", "/")
            changed_cells += 1

    if changed_cells == 0:
        return 0

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(data_rows)

    return changed_cells


def main() -> None:
    parser = argparse.ArgumentParser(description="Externalize inline JSON values from mock-data CSVs")
    parser.add_argument(
        "--mock-data-dir",
        default=Path(__file__).resolve().parents[1] / "mock-data",
        type=Path,
        help="Path to dq-db/mock-data",
    )
    args = parser.parse_args()

    mock_data_root = args.mock_data_dir.resolve()
    if not mock_data_root.is_dir():
        raise SystemExit(f"mock-data directory not found: {mock_data_root}")

    total_csvs = 0
    total_cells = 0
    for csv_path in sorted(mock_data_root.glob("*.csv")):
        total_csvs += 1
        total_cells += externalize_csv(csv_path, mock_data_root)

    print(f"Externalized {total_cells} JSON cells across {total_csvs} CSV files in {mock_data_root}")


if __name__ == "__main__":
    main()