from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "generate_keycloak_realm.py"


def _load_generator_module():
    spec = importlib.util.spec_from_file_location("generate_keycloak_realm", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_generate_realm_sets_token_lifespans():
    generator = _load_generator_module()

    realm = generator.generate_realm(
        users=[
            {
                "username": "alice@jaccloud.nl",
                "email": "alice@jaccloud.nl",
                "emailVerified": True,
                "enabled": True,
                "credentials": [{"type": "password", "value": "password", "temporary": False}],
                "realmRoles": [],
            }
        ],
        realm_roles=[{"name": "viewer"}],
        client_redirect="http://localhost:5173",
        realm_name="jaccloud",
        realm_display_name="Jaccloud Realm",
        frontend_origins=["http://localhost:5173"],
        engine_service_client_id="dq-engine-gx-worker",
        engine_service_client_secret="secret-value",
    )

    assert realm["accessTokenLifespan"] == 24 * 60 * 60

    engine_client = next(client for client in realm["clients"] if client["clientId"] == "dq-engine-gx-worker")
    assert engine_client["serviceAccountsEnabled"] is True
    assert engine_client["attributes"]["access.token.lifespan"] == "3600"


def test_build_realm_roles_includes_admin_read_scopes():
    generator = _load_generator_module()

    role_names = {
        role["name"]
        for role in generator.build_realm_roles(
            [
                {"id": "admin", "permissions": ["dq:admin:read", "dq:workspace:read"]},
                {"id": "viewer", "permissions": []},
            ]
        )
    }

    assert "dq:admin:read" in role_names
    assert "dq:workspace:read" in role_names


def test_load_users_uses_password_column(tmp_path: Path):
    generator = _load_generator_module()
    users_csv = tmp_path / "users.csv"
    users_csv.write_text(
        '"id","first_name","last_name","email","external_id","workspaces","password"\n'
        '"u1","Alice","Lovelace","alice@jaccloud.nl","","retail-banking","DqME-Mock-Alice-2026!4Tq8mP1xZ6vN"\n',
        encoding="utf-8",
    )

    users = generator.load_users(users_csv)

    assert users[0]["firstName"] == "Alice"
    assert users[0]["lastName"] == "Lovelace"
    assert users[0]["credentials"] == [
        {"type": "password", "value": "DqME-Mock-Alice-2026!4Tq8mP1xZ6vN", "temporary": False}
    ]


def test_load_users_requires_strong_password_column(tmp_path: Path):
    generator = _load_generator_module()
    users_csv = tmp_path / "users.csv"
    users_csv.write_text(
        '"id","first_name","last_name","email","external_id","workspaces","password"\n'
        '"u1","Alice","Lovelace","alice@jaccloud.nl","","retail-banking","password"\n',
        encoding="utf-8",
    )

    try:
        generator.load_users(users_csv)
    except ValueError as exc:
        assert "must not be a default or placeholder password" in str(exc)
    else:
        raise AssertionError("weak mock user password was accepted")


def test_load_users_requires_split_name_columns(tmp_path: Path):
    generator = _load_generator_module()
    users_csv = tmp_path / "users.csv"
    users_csv.write_text(
        '"id","first_name","last_name","email","external_id","workspaces","password"\n'
        '"u1","Alice","","alice@jaccloud.nl","","retail-banking","DqME-Mock-Alice-2026!4Tq8mP1xZ6vN"\n',
        encoding="utf-8",
    )

    try:
        generator.load_users(users_csv)
    except ValueError as exc:
        assert "missing required first_name/last_name" in str(exc)
    else:
        raise AssertionError("missing split name values were accepted")