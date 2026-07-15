import importlib.util
import stat
from pathlib import Path


def _load_seed_password_rotation_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "supporting" / "seed_password_rotation.py"
    spec = importlib.util.spec_from_file_location("seed_password_rotation", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_generate_and_write_makes_credentials_artifacts_readable(tmp_path, monkeypatch):
    module = _load_seed_password_rotation_module()

    source_csv = tmp_path / "users.csv"
    source_csv.write_text("first_name,last_name,email\nAlice,Smith,alice@example.com\n", encoding="utf-8")

    rotated_users_csv = tmp_path / "users.csv"
    credentials_csv = tmp_path / "keycloak_seed_user_credentials.csv"
    credentials_env = tmp_path / "keycloak_seed_user_credentials.env"

    monkeypatch.setenv("SMOKE_LOGIN_EMAIL", "alice@example.com")

    module.generate_and_write(
        source_csv,
        rotated_users_csv,
        credentials_csv,
        credentials_env,
        credential_aliases=[("SMOKE_LOGIN_EMAIL", "SMOKE_LOGIN_PASSWORD", "SMOKE_LOGIN_EMAIL")],
    )

    assert stat.S_IMODE(credentials_csv.stat().st_mode) == 0o644
    assert stat.S_IMODE(credentials_env.stat().st_mode) == 0o644
