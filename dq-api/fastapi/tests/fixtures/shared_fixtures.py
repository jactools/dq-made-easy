import csv
import json
from copy import deepcopy
from pathlib import Path

_FIXTURE_DATA_DIR = Path(__file__).with_name("data")


def _coerce_csv_value(value: str) -> object:
    normalized = value.strip()
    if normalized == "":
        return ""

    if normalized.lower() in {"none", "null"}:
        return None

    if normalized.lower() == "true":
        return True

    if normalized.lower() == "false":
        return False

    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        return value


def _fixture_csv_path(fixture_name: str) -> Path:
    return _FIXTURE_DATA_DIR / f"{fixture_name}.csv"


def _load_csv_rows(fixture_name: str) -> list[dict[str, object]] | None:
    csv_path = _fixture_csv_path(fixture_name)
    if not csv_path.exists():
        return None

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [{key: _coerce_csv_value(value) for key, value in row.items()} for row in reader]


def load_fixture_dict(fixture_name: str, fallback: dict[str, object]) -> dict[str, object]:
    rows = _load_csv_rows(fixture_name)
    if rows is None:
        return deepcopy(fallback)

    if len(rows) != 1:
        raise ValueError(f"Expected exactly one row in {_fixture_csv_path(fixture_name)} for fixture {fixture_name}")

    return rows[0]


def load_fixture_rows(fixture_name: str, fallback: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = _load_csv_rows(fixture_name)
    if rows is None:
        return deepcopy(fallback)
    return rows


def load_fixture_scalar_list(fixture_name: str, fallback: list[str]) -> list[object]:
    rows = _load_csv_rows(fixture_name)
    if rows is None:
        return deepcopy(fallback)

    if not rows:
        return []

    first_column = next(iter(rows[0]))
    return [row[first_column] for row in rows]


def load_fixture_tuple_rows(
    fixture_name: str,
    columns: tuple[str, ...],
    fallback: list[tuple[object, ...]],
) -> list[tuple[object, ...]]:
    rows = _load_csv_rows(fixture_name)
    if rows is None:
        return deepcopy(fallback)

    return [tuple(row.get(column) for column in columns) for row in rows]

import pytest


@pytest.fixture
def clone_payload():
    def _clone(payload: dict[str, object]) -> dict[str, object]:
        return deepcopy(payload)

    return _clone
