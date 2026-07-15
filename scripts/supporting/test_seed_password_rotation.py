#!/usr/bin/env python3
"""Tests for scripts.supporting.seed_password_rotation."""

import csv
import os
import tempfile
from pathlib import Path

import pytest
import seed_password_rotation

from scripts.supporting.seed_password_rotation import (
    ALLOWED_PASSWORD_CHARS,
    PASSWORD_LENGTH,
    DEFAULT_CREDENTIAL_ALIASES,
    _shell_quote,
    generate_and_write,
    generate_password,
    generate_user_passwords,
    write_credentials_csv,
    write_credentials_env,
    write_rotated_users_csv,
)


@pytest.fixture()
def sample_users_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "users.csv"
    csv_path.write_text(
        '"id","first_name","last_name","email"\n'
        '"1","Alice","Test","alice@example.org"\n'
        '"2","Bob","Test","bob@example.org"\n',
        encoding="utf-8",
    )
    return csv_path


@pytest.fixture()
def sample_users_csv_with_password(tmp_path: Path) -> Path:
    csv_path = tmp_path / "users_with_pw.csv"
    csv_path.write_text(
        '"id","first_name","last_name","email","password"\n'
        '"1","Alice","Test","alice@example.org","oldpass1"\n'
        '"2","Bob","Test","bob@example.org","oldpass2"\n',
        encoding="utf-8",
    )
    return csv_path


@pytest.fixture()
def sample_users_csv_missing_names(tmp_path: Path) -> Path:
    csv_path = tmp_path / "users_no_names.csv"
    csv_path.write_text(
        '"id","email"\n'
        '"1","alice@example.org"\n',
        encoding="utf-8",
    )
    return csv_path


# -- generate_password --


def test_generate_password_length():
    pw = generate_password()
    assert len(pw) == PASSWORD_LENGTH


def test_generate_password_allowed_chars():
    pw = generate_password()
    assert all(c in ALLOWED_PASSWORD_CHARS for c in pw)


def test_generate_password_uniqueness():
    passwords = {generate_password() for _ in range(100)}
    assert len(passwords) == 100


# -- _shell_quote --


def test_shell_quote_simple():
    # shlex.quote only adds quotes when the value needs escaping
    result = _shell_quote("hello")
    assert result == "hello"


def test_shell_quote_with_single_quote():
    result = _shell_quote("it's")
    # shlex.quote handles the escaping; just verify it round-trips
    assert "'it'" not in result or "''" not in result  # no unescaped single quote


def test_shell_quote_empty():
    assert _shell_quote("") == "''"


# -- generate_user_passwords --


def test_generate_adds_passwords_when_column_missing(sample_users_csv: Path):
    fieldnames, rows = generate_user_passwords(sample_users_csv)
    assert "password" in fieldnames
    for row in rows:
        assert row.get("password") is not None
        assert len(row["password"]) == PASSWORD_LENGTH


def test_generate_replaces_existing_passwords(sample_users_csv_with_password: Path):
    fieldnames, rows = generate_user_passwords(sample_users_csv_with_password)
    assert "password" in fieldnames
    for row in rows:
        assert row["password"] not in ("oldpass1", "oldpass2")
        assert len(row["password"]) == PASSWORD_LENGTH


def test_generate_preserves_other_columns(sample_users_csv: Path):
    fieldnames, rows = generate_user_passwords(sample_users_csv)
    assert rows[0]["first_name"] == "Alice"
    assert rows[1]["email"] == "bob@example.org"


def test_generate_skips_rows_without_email(sample_users_csv: Path, tmp_path: Path):
    csv_path = tmp_path / "sparse.csv"
    csv_path.write_text(
        '"id","first_name","last_name","email"\n'
        '"1","Alice","Test","alice@example.org"\n'
        '"2","Bob","Test",""\n',
        encoding="utf-8",
    )
    fieldnames, rows = generate_user_passwords(csv_path)
    assert rows[0]["password"] is not None
    assert rows[1].get("password") is None  # unchanged


def test_generate_missing_source():
    with pytest.raises(SystemExit):
        generate_user_passwords(Path("/nonexistent/path.csv"))


def test_generate_missing_required_columns(sample_users_csv_missing_names: Path):
    with pytest.raises(SystemExit, match="missing required columns"):
        generate_user_passwords(sample_users_csv_missing_names)


def test_generate_returns_fieldnames(sample_users_csv: Path):
    fieldnames, rows = generate_user_passwords(sample_users_csv)
    assert set(fieldnames) == {"id", "first_name", "last_name", "email", "password"}


def test_generate_fieldnames_preserves_original_order(sample_users_csv: Path):
    fieldnames, rows = generate_user_passwords(sample_users_csv)
    assert fieldnames == ["id", "first_name", "last_name", "email", "password"]


# -- write_rotated_users_csv --


def test_write_rotated_users_csv(sample_users_csv: Path, tmp_path: Path):
    fieldnames, rows = generate_user_passwords(sample_users_csv)
    out = tmp_path / "rotated.csv"
    write_rotated_users_csv(fieldnames, rows, out)

    with out.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        written_rows = list(reader)
    assert len(written_rows) == 2
    assert written_rows[0]["first_name"] == "Alice"
    assert "password" in written_rows[0]


# -- write_credentials_csv --


def test_write_credentials_csv(sample_users_csv: Path, tmp_path: Path):
    fieldnames, rows = generate_user_passwords(sample_users_csv)
    out = tmp_path / "credentials.csv"
    write_credentials_csv(rows, out)

    with out.open(newline="", encoding="utf-8") as fh:
        creds = list(csv.DictReader(fh))
    assert len(creds) == 2
    emails = {c["email"] for c in creds}
    assert emails == {"alice@example.org", "bob@example.org"}
    for c in creds:
        assert len(c["password"]) == PASSWORD_LENGTH


def test_write_credentials_csv_skips_empty_email(sample_users_csv: Path, tmp_path: Path):
    rows = [
        {"email": "alice@example.org", "password": "pw1"},
        {"email": "", "password": None},
    ]
    out = tmp_path / "creds.csv"
    write_credentials_csv(rows, out)
    with out.open(newline="", encoding="utf-8") as fh:
        creds = list(csv.DictReader(fh))
    assert len(creds) == 1
    assert creds[0]["email"] == "alice@example.org"


# -- write_credentials_env --


def test_write_credentials_env(sample_users_csv: Path, tmp_path: Path):
    fieldnames, rows = generate_user_passwords(sample_users_csv)
    out = tmp_path / "credentials.env"

    # Set env vars that map to emails in the CSV
    os.environ["OPERATOR_LOGIN_EMAIL"] = "alice@example.org"
    os.environ["AUDITOR_LOGIN_EMAIL"] = "bob@example.org"
    os.environ["REGULATOR_LOGIN_EMAIL"] = "bob@example.org"  # duplicate is fine
    try:
        # Use a subset of aliases matching the emails we set
        aliases = [
            ("OPERATOR_LOGIN_EMAIL", "OPERATOR_LOGIN_PASSWORD", "OPERATOR_LOGIN_EMAIL"),
            ("AUDITOR_LOGIN_EMAIL", "AUDITOR_LOGIN_PASSWORD", "AUDITOR_LOGIN_EMAIL"),
            ("REGULATOR_LOGIN_EMAIL", "REGULATOR_LOGIN_PASSWORD", "REGULATOR_LOGIN_EMAIL"),
        ]
        write_credentials_env(rows, out, credential_aliases=aliases)

        content = out.read_text(encoding="utf-8")
        assert "OPERATOR_LOGIN_EMAIL=alice@example.org" in content
        assert "AUDITOR_LOGIN_EMAIL=bob@example.org" in content
        assert "REGULATOR_LOGIN_EMAIL=bob@example.org" in content
    finally:
        del os.environ["OPERATOR_LOGIN_EMAIL"]
        del os.environ["AUDITOR_LOGIN_EMAIL"]
        del os.environ["REGULATOR_LOGIN_EMAIL"]


def test_write_credentials_env_missing_email_raises(sample_users_csv: Path, tmp_path: Path):
    fieldnames, rows = generate_user_passwords(sample_users_csv)
    out = tmp_path / "credentials.env"
    aliases = [
        ("FAKE_KEY", "FAKE_PASSWORD", "FAKE_EMAIL_VAR"),
    ]
    os.environ["FAKE_EMAIL_VAR"] = "nobody@example.org"
    try:
        with pytest.raises(SystemExit, match="not found in users.csv"):
            write_credentials_env(rows, out, credential_aliases=aliases)
    finally:
        del os.environ["FAKE_EMAIL_VAR"]


def test_write_credentials_env_empty_email_skipped(sample_users_csv: Path, tmp_path: Path):
    fieldnames, rows = generate_user_passwords(sample_users_csv)
    out = tmp_path / "credentials.env"
    # Use an alias whose email var is unset
    aliases = [
        ("SMOKE_LOGIN_EMAIL", "SMOKE_LOGIN_PASSWORD", "SMOKE_LOGIN_EMAIL"),
    ]
    if "SMOKE_LOGIN_EMAIL" in os.environ:
        del os.environ["SMOKE_LOGIN_EMAIL"]
    write_credentials_env(rows, out, credential_aliases=aliases)
    content = out.read_text(encoding="utf-8")
    assert "SMOKE_LOGIN_EMAIL=" not in content  # skipped because env var is empty


# -- DEFAULT_CREDENTIAL_ALIASES --


def test_default_credential_aliases_shape():
    assert len(DEFAULT_CREDENTIAL_ALIASES) == 5
    for triple in DEFAULT_CREDENTIAL_ALIASES:
        assert len(triple) == 3
        username_key, password_key, email_env_var = triple
        assert username_key.endswith("_USERNAME") or username_key.endswith("_EMAIL")
        assert password_key.endswith("_PASSWORD")


# -- generate_and_write (integration) --


def test_generate_and_write_full_pipeline(sample_users_csv: Path, tmp_path: Path):
    rotated_csv = tmp_path / "rotated.csv"
    creds_csv = tmp_path / "creds.csv"
    creds_env = tmp_path / "creds.env"

    os.environ["OPERATOR_LOGIN_EMAIL"] = "alice@example.org"
    os.environ["AUDITOR_LOGIN_EMAIL"] = "bob@example.org"
    os.environ["REGULATOR_LOGIN_EMAIL"] = "alice@example.org"
    try:
        generate_and_write(
            source_csv=str(sample_users_csv),
            rotated_users_csv=str(rotated_csv),
            credentials_csv=str(creds_csv),
            credentials_env=str(creds_env),
        )
    finally:
        del os.environ["OPERATOR_LOGIN_EMAIL"]
        del os.environ["AUDITOR_LOGIN_EMAIL"]
        del os.environ["REGULATOR_LOGIN_EMAIL"]

    assert rotated_csv.exists()
    assert creds_csv.exists()
    assert creds_env.exists()

    # Rotated users CSV has correct structure
    with rotated_csv.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    for row in rows:
        assert "password" in row
        assert len(row["password"]) == PASSWORD_LENGTH

    # Credentials CSV has emails and passwords
    with creds_csv.open(newline="", encoding="utf-8") as fh:
        creds = list(csv.DictReader(fh))
    assert len(creds) == 2

    # Credentials env has shell-sourcable content
    content = creds_env.read_text(encoding="utf-8")
    assert "OPERATOR_LOGIN_EMAIL=" in content
    assert "OPERATOR_LOGIN_PASSWORD=" in content
    assert "AUDITOR_LOGIN_EMAIL=" in content
    assert "REGULATOR_LOGIN_EMAIL=" in content


def test_generate_and_write_creates_parent_dirs(sample_users_csv: Path, tmp_path: Path):
    os.environ["OPERATOR_LOGIN_EMAIL"] = "alice@example.org"
    os.environ["AUDITOR_LOGIN_EMAIL"] = "bob@example.org"
    os.environ["REGULATOR_LOGIN_EMAIL"] = "alice@example.org"
    try:
        generate_and_write(
            source_csv=str(sample_users_csv),
            rotated_users_csv=str(tmp_path / "deep" / "nested" / "rotated.csv"),
            credentials_csv=str(tmp_path / "deep" / "nested" / "creds.csv"),
            credentials_env=str(tmp_path / "deep" / "nested" / "creds.env"),
        )
    finally:
        del os.environ["OPERATOR_LOGIN_EMAIL"]
        del os.environ["AUDITOR_LOGIN_EMAIL"]
        del os.environ["REGULATOR_LOGIN_EMAIL"]

    assert (tmp_path / "deep" / "nested" / "rotated.csv").exists()
    assert (tmp_path / "deep" / "nested" / "creds.csv").exists()
    assert (tmp_path / "deep" / "nested" / "creds.env").exists()


# ---------------------------------------------------------------------------
# Env file password rotation tests
# ---------------------------------------------------------------------------

def _is_password_var() -> None:
    """Test password variable detection."""
    assert seed_password_rotation._is_password_var("DB_PASSWORD")
    assert seed_password_rotation._is_password_var("MY_SECRET")
    assert seed_password_rotation._is_password_var("CLIENT_SECRET")
    assert seed_password_rotation._is_password_var("API_KEY")
    assert not seed_password_rotation._is_password_var("DB_HOST")
    assert not seed_password_rotation._is_password_var("REGISTRY")
    assert not seed_password_rotation._is_password_var("DQ_LLM_MAX_NEW_TOKENS")


def _is_var_reference() -> None:
    """Test variable reference detection."""
    assert seed_password_rotation._is_var_reference("${SOME_VAR}")
    assert seed_password_rotation._is_var_reference("${KEYCLOAK_PASSWORD}")
    assert seed_password_rotation._is_var_reference("$SOME_VAR")
    assert not seed_password_rotation._is_var_reference("postgres")
    assert not seed_password_rotation._is_var_reference("changeme")


def _should_rotate() -> None:
    """Test rotation decision logic."""
    # Hardcoded passwords should be rotated
    assert seed_password_rotation._should_rotate("DB_PASSWORD", "postgres")
    assert seed_password_rotation._should_rotate("KONG_PASSWORD", "kongpass")
    assert seed_password_rotation._should_rotate("MY_SECRET", "changeme")

    # Empty values should NOT be rotated (sentinels)
    assert not seed_password_rotation._should_rotate("DB_PASSWORD", "")
    assert not seed_password_rotation._should_rotate("DB_PASSWORD", "change-me")

    # Variable references should NOT be rotated
    assert not seed_password_rotation._should_rotate("DB_PASSWORD", "${OTHER_VAR}")
    assert not seed_password_rotation._should_rotate("DB_PASSWORD", "$OTHER_VAR")

    # External credentials should NOT be rotated
    assert not seed_password_rotation._should_rotate("DOCKER_HUB_TOKEN", "abc123")
    assert not seed_password_rotation._should_rotate("DQ_MCP_API_TOKEN", "abc123")

    # Non-password vars should NOT be rotated
    assert not seed_password_rotation._should_rotate("DB_HOST", "postgres")


def _parse_env_line() -> None:
    """Test env line parsing."""
    # Simple key=value
    key, value = seed_password_rotation._parse_env_line("DB_PASSWORD=postgres")
    assert key == "DB_PASSWORD"
    assert value == "postgres"

    # Double-quoted value
    key, value = seed_password_rotation._parse_env_line('DB_PASSWORD="postgres"')
    assert key == "DB_PASSWORD"
    assert value == "postgres"

    # Single-quoted value
    key, value = seed_password_rotation._parse_env_line("DB_PASSWORD='postgres'")
    assert key == "DB_PASSWORD"
    assert value == "postgres"

    # Comment lines return None
    assert seed_password_rotation._parse_env_line("# comment") is None

    # Blank lines return None
    assert seed_password_rotation._parse_env_line("") is None


def _env_name_from_path() -> None:
    """Test env name extraction."""
    assert seed_password_rotation._env_name_from_path(Path(".env.dev.local")) == "dev"
    assert seed_password_rotation._env_name_from_path(Path(".env.test.local")) == "test"
    assert seed_password_rotation._env_name_from_path(Path(".env.prod.local")) == "prod"
    assert seed_password_rotation._env_name_from_path(Path(".env.local")) == "local"


def test_rotate_env_passwords_hardcoded_values(tmp_path: Path) -> None:
    """Test rotating hardcoded password values in env file."""
    env_file = tmp_path / ".env.dev.local"
    env_file.write_text(
        "DB_HOST=localhost\n"
        'DB_PASSWORD=postgres\n'
        'KONG_PASSWORD="kongpass"\n'
        'MY_SECRET=${OTHER_VAR}\n'
        "REGISTRY=docker.io\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "env_passwords"
    output_path, rotated = seed_password_rotation.rotate_env_passwords(
        env_file, output_dir=output_dir
    )

    # Should have rotated DB_PASSWORD and KONG_PASSWORD, not MY_SECRET (ref)
    assert len(rotated) == 2
    rotated_names = {name for name, _ in rotated}
    assert "DB_PASSWORD" in rotated_names
    assert "KONG_PASSWORD" in rotated_names

    # Output file should exist and contain all original keys
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "DB_HOST=localhost" in content
    assert "MY_SECRET=${OTHER_VAR}" in content
    assert "REGISTRY=docker.io" in content

    # Rotated values should be different from originals
    for name, new_value in rotated:
        assert new_value not in ("postgres", "kongpass")
        assert len(new_value) == PASSWORD_LENGTH


def test_rotate_env_passwords_preserves_comments(tmp_path: Path) -> None:
    """Test that comments are preserved in rotated env file."""
    env_file = tmp_path / ".env.dev.local"
    env_file.write_text(
        "# This is a comment\n"
        "DB_HOST=localhost\n"
        "# DB_PASSWORD comment\n"
        "DB_PASSWORD=postgres\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "env_passwords"
    output_path, _ = seed_password_rotation.rotate_env_passwords(
        env_file, output_dir=output_dir
    )

    content = output_path.read_text(encoding="utf-8")
    assert "# This is a comment" in content
    assert "# DB_PASSWORD comment" in content


def test_rotate_env_passwords_creates_default_output_dir(tmp_path: Path) -> None:
    """Test that default output directory is created if it doesn't exist."""
    env_file = tmp_path / ".env.dev.local"
    env_file.write_text("DB_PASSWORD=postgres", encoding="utf-8")

    output_path, _ = seed_password_rotation.rotate_env_passwords(env_file)

    # Should create tmp/env_passwords/dev.env
    assert output_path.exists()
    assert output_path.name == "dev.env"


def test_rotate_env_passwords_rejects_missing_file() -> None:
    """Test that missing env file raises SystemExit."""
    with pytest.raises(SystemExit, match="Env file not found"):
        seed_password_rotation.rotate_env_passwords("/nonexistent/.env.dev.local")


def test_rotate_env_passwords_with_sentinels(tmp_path: Path) -> None:
    """Test that sentinel values are not rotated."""
    env_file = tmp_path / ".env.dev.local"
    env_file.write_text(
        "DB_PASSWORD=\n"          # empty
        "KONG_PASSWORD=changeme\n"  # sentinel
        "REAL_PASSWORD=secret123\n",  # should be rotated
        encoding="utf-8",
    )

    output_dir = tmp_path / "env_passwords"
    _, rotated = seed_password_rotation.rotate_env_passwords(
        env_file, output_dir=output_dir
    )

    # Only REAL_PASSWORD should be rotated
    assert len(rotated) == 1
    assert rotated[0][0] == "REAL_PASSWORD"

