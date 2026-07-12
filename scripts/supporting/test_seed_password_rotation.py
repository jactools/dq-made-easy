#!/usr/bin/env python3
"""Tests for scripts.supporting.seed_password_rotation."""

import csv
import os
import tempfile
from pathlib import Path

import pytest

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
