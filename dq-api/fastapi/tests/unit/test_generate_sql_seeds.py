import importlib.util
from pathlib import Path

import pytest


def _load_sql_seed_module():
    module_path = Path(__file__).resolve().parents[3] / "scripts" / "generate_sql_seeds.py"
    spec = importlib.util.spec_from_file_location("generate_sql_seeds", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_users_password_column_is_excluded_from_sql_seed(tmp_path: Path):
    generator = _load_sql_seed_module()
    csv_path = tmp_path / "users.csv"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (tmp_path / "users-default-preferences.json").write_text('{"display":{"theme":"auto"}}\n', encoding="utf-8")
    csv_path.write_text(
        '"id","first_name","last_name","email","external_id","workspaces","password"\n'
        '"u1","Alice","Lovelace","alice@jaccloud.nl","","retail-banking","DqME-Mock-Alice-2026!4Tq8mP1xZ6vN"\n',
        encoding="utf-8",
    )

    sql_path = generator.generate_sql_for_csv(csv_path, output_dir, input_dir=tmp_path)
    sql = sql_path.read_text(encoding="utf-8")

    assert "COPY users (id, first_name, last_name, email, external_id, workspaces)" in sql
    assert "u1,Alice,Lovelace,alice@jaccloud.nl,,retail-banking" in sql
    assert "password" not in sql


def test_json_file_references_are_inlined_into_sql_seed(tmp_path: Path):
    generator = _load_sql_seed_module()
    csv_path = tmp_path / "rules.csv"
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    json_dir = tmp_path / "rules" / "rule-1"
    json_dir.mkdir(parents=True)
    (json_dir / "dsl.json").write_text("{\"schema_version\":\"2.0.0\",\"rule\":{\"kind\":\"row_assertion\"}}\n", encoding="utf-8")

    csv_path.write_text(
        '"id","name","dsl"\n'
        '"rule-1","Example rule","rules/rule-1/dsl.json"\n',
        encoding="utf-8",
    )

    sql_path = generator.generate_sql_for_csv(csv_path, output_dir, input_dir=tmp_path)
    sql = sql_path.read_text(encoding="utf-8")

    assert 'schema_version' in sql
    assert 'row_assertion' in sql
    assert "rules/rule-1/dsl.json" not in sql


def test_inline_json_values_are_rejected(tmp_path: Path):
    generator = _load_sql_seed_module()
    csv_path = tmp_path / "rules.csv"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    csv_path.write_text(
        '"id","name","dsl"\n'
        '"rule-1","Example rule","{\"schema_version\":\"2.0.0\"}"\n',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="inline JSON is not allowed"):
        generator.generate_sql_for_csv(csv_path, output_dir, input_dir=tmp_path)


def test_generate_sql_seeds_stops_on_first_malformed_csv(tmp_path: Path):
    generator = _load_sql_seed_module()
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    (input_dir / "a_valid.csv").write_text(
        '"id","name"\n'
        '"1","Alpha"\n',
        encoding="utf-8",
    )
    (input_dir / "b_bad.csv").write_text(
        '"id","dsl"\n'
        '"rule-1","rules/rule-1/dsl.json"\n',
        encoding="utf-8",
    )
    (input_dir / "c_valid.csv").write_text(
        '"id","name"\n'
        '"2","Gamma"\n',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="missing JSON reference file"):
        generator.generate_sql_seeds(input_dir, output_dir)

    assert list(output_dir.glob("generated_seed_*_a_valid.sql"))
    assert not list(output_dir.glob("generated_seed_*_c_valid.sql"))
