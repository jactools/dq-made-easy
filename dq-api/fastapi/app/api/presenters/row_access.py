from __future__ import annotations


def read_row_field(row: object, key: str) -> object:
    if isinstance(row, dict):
        return row.get(key)

    snake_key = "".join([f"_{char.lower()}" if char.isupper() else char for char in key]).lstrip("_")

    if hasattr(row, key):
        return getattr(row, key)
    if hasattr(row, snake_key):
        return getattr(row, snake_key)

    return None
