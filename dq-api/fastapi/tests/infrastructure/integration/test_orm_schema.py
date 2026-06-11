"""Integration test: every ORM column name declared in models.py must exist in the
live database schema.

Uses SQLAlchemy's Inspector to reflect the containerised Postgres and compares
column names for each table against what the ORM has declared via mapped_column().

This test would have caught the camelCase/lowercase mismatch bug:
  ORM declared  mapped_column("ruleId", ...)
  DB stored as  ruleid            ← PostgreSQL folds unquoted identifiers to lowercase

Run:
    pytest -m integration tests/infrastructure/integration/test_orm_schema.py
"""
from __future__ import annotations

import pytest
from sqlalchemy import inspect as sa_inspect

from app.infrastructure.orm.base import Base
from app.infrastructure.orm import models  # noqa: F401 — register all model classes


def _orm_table_columns() -> list[tuple[str, frozenset[str]]]:
    """Return (table_name, {sql_column_name, ...}) for every ORM-declared table."""
    return [
        (table.name, frozenset(col.name for col in table.columns))
        for table in Base.metadata.tables.values()
    ]


@pytest.mark.integration
@pytest.mark.parametrize("table_name,orm_cols", _orm_table_columns(), ids=[t for t, _ in _orm_table_columns()])
def test_orm_columns_exist_in_live_schema(
    table_name: str,
    orm_cols: frozenset[str],
    live_engine,
) -> None:
    """Every column declared in the ORM model must exist as a real column in the DB.

    Failures here mean the ORM's mapped_column() SQL name doesn't match what
    PostgreSQL actually stored (typically a camelCase vs lowercase mismatch).
    """
    inspector = sa_inspect(live_engine)
    existing_tables = inspector.get_table_names()

    if table_name not in existing_tables:
        pytest.skip(f"Table '{table_name}' not present in live DB (optional/profiling schema)")

    live_cols = frozenset(c["name"] for c in inspector.get_columns(table_name))
    missing = orm_cols - live_cols

    assert not missing, (
        f"ORM declares column(s) not found in live '{table_name}' table: {sorted(missing)}\n"
        f"Live columns : {sorted(live_cols)}\n"
        f"ORM columns  : {sorted(orm_cols)}\n"
        "Likely cause: DDL used unquoted camelCase (e.g. ruleId) which PostgreSQL "
        "stores lowercase (ruleid), but mapped_column() was given the camelCase name."
    )
