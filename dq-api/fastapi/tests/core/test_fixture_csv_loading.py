from pathlib import Path

from tests.fixtures import shared_fixtures


def test_load_fixture_dict_prefers_matching_csv(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "workspace_create_payload.csv").write_text(
        "id,name,description\nworkspace-from-csv,CSV Workspace,Loaded from file\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(shared_fixtures, "_FIXTURE_DATA_DIR", data_dir)

    loaded = shared_fixtures.load_fixture_dict(
        "workspace_create_payload",
        {"id": "fallback", "name": "Fallback", "description": "Fallback"},
    )

    assert loaded == {
        "id": "workspace-from-csv",
        "name": "CSV Workspace",
        "description": "Loaded from file",
    }


def test_load_fixture_rows_coerces_scalar_types_from_csv(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "app_config_kv_rows.csv").write_text(
        "config_key,config_value,value_type,enabled,count,metadata\n"
        "api_version,v2,string,true,5,{\"source\":\"csv\"}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(shared_fixtures, "_FIXTURE_DATA_DIR", data_dir)

    loaded = shared_fixtures.load_fixture_rows(
        "app_config_kv_rows",
        [{"config_key": "fallback", "config_value": "v1", "value_type": "string"}],
    )

    assert loaded == [
        {
            "config_key": "api_version",
            "config_value": "v2",
            "value_type": "string",
            "enabled": True,
            "count": 5,
            "metadata": {"source": "csv"},
        }
    ]


def test_load_fixture_tuple_rows_uses_named_columns(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "data_catalog_attribute_counts_rows.csv").write_text(
        "attribute_id,rule_count\na1,2\n,1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(shared_fixtures, "_FIXTURE_DATA_DIR", data_dir)

    loaded = shared_fixtures.load_fixture_tuple_rows(
        "data_catalog_attribute_counts_rows",
        ("attribute_id", "rule_count"),
        [("fallback", 0)],
    )

    assert loaded == [("a1", 2), ("", 1)]