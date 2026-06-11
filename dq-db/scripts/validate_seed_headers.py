#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+([\w\"]+)\s*\((.*?)\);",
    re.IGNORECASE | re.DOTALL,
)
ALTER_TABLE_ADD_COLUMN_RE = re.compile(
    r"ALTER\s+TABLE\s+([\w\"]+)\s+ADD\s+COLUMN(?:\s+IF\s+NOT\s+EXISTS)?\s+([^;]+);",
    re.IGNORECASE | re.DOTALL,
)
COPY_RE = re.compile(
    r"^COPY\s+([\w\"]+)\s*\((.*?)\)\s+FROM\s+stdin",
    re.IGNORECASE,
)
IDENTIFIER_RE = re.compile(r'^\s*("[^"]+"|[A-Za-z_][A-Za-z0-9_]*)')
SKIP_CONSTRAINT_RE = re.compile(
    r"^(FOREIGN\s+KEY|PRIMARY\s+KEY|UNIQUE\b|CONSTRAINT\b|CHECK\s*\(|EXCLUDE\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ValidationIssue:
    seed_file: str
    table: str
    missing_columns: tuple[str, ...]


def normalize_identifier(raw: str) -> str:
    value = raw.strip()
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        return value[1:-1]
    return value.lower()


def strip_sql_comments(sql: str) -> str:
    result: list[str] = []
    in_single_quote = False
    index = 0
    while index < len(sql):
        ch = sql[index]
        nxt = sql[index + 1] if index + 1 < len(sql) else ""
        if ch == "'":
            result.append(ch)
            if in_single_quote and nxt == "'":
                result.append(nxt)
                index += 2
                continue
            in_single_quote = not in_single_quote
            index += 1
            continue
        if not in_single_quote and ch == "-" and nxt == "-":
            while index < len(sql) and sql[index] != "\n":
                index += 1
            continue
        result.append(ch)
        index += 1
    return "".join(result)


def split_top_level(body: str) -> list[str]:
    parts: list[str] = []
    token: list[str] = []
    depth = 0
    in_single_quote = False
    for ch in body:
        if ch == "'":
            token.append(ch)
            in_single_quote = not in_single_quote
            continue
        if not in_single_quote:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                part = "".join(token).strip()
                if part:
                    parts.append(part)
                token = []
                continue
        token.append(ch)
    part = "".join(token).strip()
    if part:
        parts.append(part)
    return parts


def parse_table_columns(sql_text: str) -> dict[str, list[str]]:
    tables: dict[str, list[str]] = {}
    cleaned = strip_sql_comments(sql_text)
    for raw_table_name, body in CREATE_TABLE_RE.findall(cleaned):
        table_name = normalize_identifier(raw_table_name)
        columns: list[str] = []
        for part in split_top_level(body):
            if SKIP_CONSTRAINT_RE.match(part.strip()):
                continue
            match = IDENTIFIER_RE.match(part)
            if not match:
                continue
            columns.append(normalize_identifier(match.group(1)))
        tables[table_name] = columns

    # Capture migration-style schema updates where columns are introduced after
    # table creation via ALTER TABLE ... ADD COLUMN.
    for raw_table_name, raw_column_def in ALTER_TABLE_ADD_COLUMN_RE.findall(cleaned):
        table_name = normalize_identifier(raw_table_name)
        match = IDENTIFIER_RE.match(raw_column_def)
        if not match:
            continue
        column_name = normalize_identifier(match.group(1))
        existing = tables.setdefault(table_name, [])
        if column_name not in existing:
            existing.append(column_name)

    return tables


def parse_copy_header(path: Path) -> tuple[str, list[str]] | None:
    first_line = path.read_text().splitlines()[0]
    match = COPY_RE.match(first_line)
    if not match:
        return None
    table_name = normalize_identifier(match.group(1))
    columns = [normalize_identifier(item) for item in match.group(2).split(",")]
    return table_name, columns


def load_columns_from_orm_models(fastapi_dir: Path) -> dict[str, list[str]] | None:
    """Import SQLAlchemy ORM models and return {table_name: [column_names]}.

    Returns None if the import fails (missing dependencies, wrong path, etc.).
    """
    sys.path.insert(0, str(fastapi_dir))
    try:
        import importlib
        base_mod = importlib.import_module("app.infrastructure.orm.base")
        importlib.import_module("app.infrastructure.orm.models")
        Base = base_mod.Base
        return {
            table_name: [col.name for col in table.columns]
            for table_name, table in Base.metadata.tables.items()
        }
    except Exception:
        return None
    finally:
        if str(fastapi_dir) in sys.path:
            sys.path.remove(str(fastapi_dir))


def validate_seed_headers(
    init_dir: Path,
    fastapi_dir: Path | None = None,
) -> tuple[list[ValidationIssue], int]:
    if fastapi_dir is None:
        raise RuntimeError("FastAPI directory is required for ORM-based validation.")

    table_columns = load_columns_from_orm_models(fastapi_dir)
    if not table_columns:
        raise RuntimeError(
            f"Unable to load ORM models from {fastapi_dir}; cannot validate seed headers."
        )

    issues: list[ValidationIssue] = []
    checked = 0
    for seed_file in sorted(init_dir.glob("generated_seed_*.sql")):
        parsed = parse_copy_header(seed_file)
        if parsed is None:
            continue
        checked += 1
        table_name, copy_columns = parsed
        available = set(table_columns.get(table_name, []))
        missing = tuple(column for column in copy_columns if column not in available)
        if missing:
            issues.append(
                ValidationIssue(
                    seed_file=seed_file.name,
                    table=table_name,
                    missing_columns=missing,
                )
            )
    return issues, checked


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate generated dq-db seed COPY headers against ORM model column definitions."
    )
    parser.add_argument(
        "--init-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "init",
        help="Directory containing generated_seed_*.sql files.",
    )
    parser.add_argument(
        "--fastapi-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent / "dq-api" / "fastapi",
        help="Root of the FastAPI package (contains app/infrastructure/orm/models.py).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    init_dir = args.init_dir.resolve()
    fastapi_dir = args.fastapi_dir.resolve() if args.fastapi_dir else None

    if not init_dir.is_dir():
        parser.error(f"init directory not found: {init_dir}")

    try:
        issues, checked = validate_seed_headers(init_dir, fastapi_dir)
    except RuntimeError as exc:
        print(f"FAILED: {exc}")
        return 1
    if issues:
        print(f"FAILED: {len(issues)} generated seed file(s) do not match schema definitions.")
        for issue in issues:
            print(
                f"- {issue.seed_file}: table '{issue.table}' is missing column(s) "
                f"{', '.join(issue.missing_columns)}"
            )
        return 1

    print(f"PASS: validated {checked} generated seed file(s) against ORM model definitions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())