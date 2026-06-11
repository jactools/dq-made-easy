from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


def normalize_database_url(database_url: str) -> str:
    """Ensure SQLAlchemy uses psycopg v3 for PostgreSQL URLs."""
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


@lru_cache(maxsize=8)
def get_engine(database_url: str) -> Engine:
    return create_engine(normalize_database_url(database_url), future=True)


@contextmanager
def session_scope(database_url: str) -> Iterator[Session]:
    session = Session(get_engine(database_url), expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()


def compile_positional_query(query: str, params: list[Any] | None) -> tuple[str, dict[str, Any]]:
    """Convert psycopg-style `%s` placeholders into SQLAlchemy named binds."""
    if not params:
        return query, {}

    placeholder_count = query.count("%s")
    if placeholder_count != len(params):
        raise ValueError("Mismatch between placeholders and parameters")

    parts = query.split("%s")
    bind_params: dict[str, Any] = {}
    compiled: list[str] = [parts[0]]

    for index, value in enumerate(params):
        key = f"p{index}"
        bind_params[key] = value
        compiled.append(f":{key}")
        compiled.append(parts[index + 1])

    return "".join(compiled), bind_params
