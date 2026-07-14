#!/usr/bin/env python3
"""Generate random passwords for mock seed users and env-file secrets.

Reads the mock-data users CSV (password column not required), generates
random passwords for every user with an email, and writes out a users CSV
(with password column), a credentials CSV, and a credentials env file.

Also supports rotating hardcoded passwords/secrets in .env.*.local files.

Designed to replace the inline heredoc in
dq-keycloak/scripts/generate_seed_artifacts.sh.
"""

import csv
import os
import re
import secrets
import shlex
import string
import sys
from pathlib import Path


ALLOWED_PASSWORD_CHARS = string.ascii_letters + string.digits + "-_"
PASSWORD_LENGTH = 32

# Regex patterns that identify password / secret / token env var names.
_PASSWORD_INDICATORS = re.compile(
    r"PASSWORD|_PASS\b|_PWD\b|_SECRET\b|_CLIENT_SECRET\b|_API_KEY\b",
    re.IGNORECASE,
)

# Values that look like env var references — leave them alone.
_VAR_REF_RE = re.compile(r"^\$\{[^}]+\}|\$[A-Z_]+$")

# Well-known sentinel placeholders that are intentionally not rotated
_SENTINEL_VALUES = frozenset({
    "",
    "change-me",
    "changeme",
    "replace-with-current-generated-password-from-keycloak-seed-user-credentials-env",
})

# Docker Hub tokens and other external credentials are NOT rotated here
_NO_ROTATE_PREFIXES = ("DOCKER_HUB_", "DQ_MCP_API_")


def generate_password() -> str:
    """Return a cryptographically random password."""
    return "".join(secrets.choice(ALLOWED_PASSWORD_CHARS) for _ in range(PASSWORD_LENGTH))


def _shell_quote(value: str) -> str:
    """Shell-quote a value for safe embedding in env files."""
    return shlex.quote(value)


def generate_user_passwords(source_csv: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read *source_csv* and generate a random password for every user with an email.

    The source CSV may or may not have a ``password`` column — if it does, values
    are replaced; if it doesn't, the column is appended.

    Returns ``(fieldnames, rows)`` where *fieldnames* always includes ``password``
    and *rows* contain freshly generated passwords.
    Raises SystemExit if the source is missing.
    """
    if not source_csv.exists():
        raise SystemExit(f"Source users CSV not found: {source_csv}")

    with source_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        if "first_name" not in fieldnames or "last_name" not in fieldnames:
            raise SystemExit(f"{source_csv} is missing required columns: first_name, last_name")
        rows = list(reader)

    # Ensure password column exists in fieldnames
    if "password" not in fieldnames:
        fieldnames.append("password")

    seen_passwords: set[str] = set()
    for row in rows:
        email = (row.get("email") or "").strip()
        if not email:
            continue
        new_password = generate_password()
        while new_password in seen_passwords:
            new_password = generate_password()
        seen_passwords.add(new_password)
        row["password"] = new_password

    return fieldnames, rows


def write_rotated_users_csv(fieldnames: list[str], rows: list[dict[str, str]], output: Path) -> None:
    """Write the rotated user rows to a new CSV using the given *fieldnames*."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_credentials_csv(rows: list[dict[str, str]], output: Path) -> None:
    """Write an ``email,password`` CSV for seed-credential tracking."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["email", "password"], quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            email = (row.get("email") or "").strip()
            if email:
                writer.writerow({"email": email, "password": row.get("password", "")})


def _password_by_email(rows: list[dict[str, str]]) -> dict[str, str]:
    return {(row.get("email") or "").strip(): row.get("password", "") for row in rows}


# Default credential aliases sourced from environment variables.
# Each triple: (username_key, password_key, env_var_for_email)
DEFAULT_CREDENTIAL_ALIASES = [
    ("KEYCLOAK_JACCLOUD_USERNAME", "KEYCLOAK_JACCLOUD_PASSWORD", "KEYCLOAK_JACCLOUD_USERNAME"),
    ("SMOKE_LOGIN_EMAIL", "SMOKE_LOGIN_PASSWORD", "SMOKE_LOGIN_EMAIL"),
    ("OPERATOR_LOGIN_EMAIL", "OPERATOR_LOGIN_PASSWORD", "OPERATOR_LOGIN_EMAIL"),
    ("AUDITOR_LOGIN_EMAIL", "AUDITOR_LOGIN_PASSWORD", "AUDITOR_LOGIN_EMAIL"),
    ("REGULATOR_LOGIN_EMAIL", "REGULATOR_LOGIN_PASSWORD", "REGULATOR_LOGIN_EMAIL"),
]


def write_credentials_env(
    rows: list[dict[str, str]],
    output: Path,
    credential_aliases: list[tuple[str, str, str]] | None = None,
) -> None:
    """Write a shell-sourceable env file with username/password pairs.

    *credential_aliases* is a list of ``(username_key, password_key,
    email_env_var)`` triples.  The email is read from ``os.environ`` using
    ``email_env_var``, then looked up in the rows.
    """
    credential_aliases = credential_aliases or DEFAULT_CREDENTIAL_ALIASES
    password_map = _password_by_email(rows)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        fh.write("# Generated by scripts/supporting/seed_password_rotation.py\n")
        fh.write("# Do not commit. Credentials rotate on each seed-artifacts run.\n")

        for username_key, password_key, email_env_var in credential_aliases:
            selected_email = (os.environ.get(email_env_var) or "").strip()
            if not selected_email:
                continue
            if selected_email not in password_map:
                raise SystemExit(f"{username_key} not found in users.csv: {selected_email}")
            fh.write(f"{username_key}={_shell_quote(selected_email)}\n")
            fh.write(f"{password_key}={_shell_quote(password_map[selected_email])}\n")


def _restrict_permissions(path: Path) -> None:
    """Best-effort permission tightening on sensitive output files."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _make_readable(path: Path, *, mode: int = 0o644) -> None:
    """Best-effort permission adjustment so generated artifacts are readable by containers."""
    try:
        os.chmod(path, mode)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Env-file password rotation
# ---------------------------------------------------------------------------

def _is_password_var(name: str) -> bool:
    """Return True if *name* looks like a password / secret variable."""
    return bool(_PASSWORD_INDICATORS.search(name))


def _is_var_reference(value: str) -> bool:
    """Return True if *value* is a ${...} or $VAR reference."""
    return bool(_VAR_REF_RE.match(value))


def _should_rotate(name: str, value: str) -> bool:
    """Return True if the value of env var *name* should be rotated.

    Skips:
    - Empty values (sentinels)
    - ${...} references (resolved at runtime)
    - External credentials (DOCKER_HUB_*, DQ_MCP_API_*)
    """
    if not _is_password_var(name):
        return False
    if not value:
        return False
    if _is_var_reference(value):
        return False
    if value.strip('"\'') in _SENTINEL_VALUES:
        return False
    for prefix in _NO_ROTATE_PREFIXES:
        if name.startswith(prefix):
            return False
    return True


def _parse_env_line(line: str) -> tuple[str, str] | None:
    """Parse a ``KEY=VALUE`` line into ``(key, value)``.

    Handles optional surrounding quotes.  Returns None for blank or
    comment lines.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if "=" not in stripped:
        return None
    key, _, raw_value = stripped.partition("=")
    key = key.strip()
    # Strip surrounding quotes (single or double)
    value = raw_value.strip()
    if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
        value = value[1:-1]
    return key, value


def _env_name_from_path(path: Path) -> str:
    """Extract 'dev', 'test', 'prod' from '.env.dev.local' etc."""
    name = path.name
    # Strip .local suffix
    if name.endswith(".local"):
        name = name[: -len(".local")]
    # Strip .env prefix
    if name.startswith(".env."):
        name = name[len(".env."):]
    elif name.startswith(".env"):
        name = name[len(".env"):]
    if not name:
        name = "local"
    return name


def rotate_env_passwords(
    env_file: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[Path, list[tuple[str, str]]]:
    """Read *env_file*, rotate hardcoded passwords, write rotated file.

    Returns ``(output_path, rotated_vars)`` where *rotated_vars* is a list of
    ``(key, new_value)`` pairs for the variables that were changed.
    """
    env_file = Path(env_file)
    if not env_file.is_file():
        raise SystemExit(f"Env file not found: {env_file}")

    env_name = _env_name_from_path(env_file)
    output_dir = Path(output_dir) if output_dir else Path("tmp/env_passwords")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{env_name}.env"
    rotated_vars: list[tuple[str, str]] = []

    lines: list[str] = []
    with env_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            parsed = _parse_env_line(line)
            if parsed is None:
                lines.append(line.rstrip("\n"))
                continue
            key, value = parsed
            if _should_rotate(key, value):
                new_value = generate_password()
                lines.append(f'{key}="{new_value}"')
                rotated_vars.append((key, new_value))
            else:
                # Preserve original line (including comments, refs, etc.)
                lines.append(line.rstrip("\n"))

    header = [
        f"# Auto-generated by seed_password_rotation.py",
        f"# Source: {env_file.name}",
        f"# Rotated {len(rotated_vars)} password variable(s).",
        "# Do not commit — regenerated on each startup.",
        "",
    ]

    with output_path.open("w", encoding="utf-8") as fh:
        for hdr in header:
            fh.write(hdr + "\n")
        for l in lines:
            fh.write(l + "\n")

    _restrict_permissions(output_path)
    return output_path, rotated_vars


def generate_and_write(
    source_csv: str | Path,
    rotated_users_csv: str | Path,
    credentials_csv: str | Path,
    credentials_env: str | Path,
    credential_aliases: list[tuple[str, str, str]] | None = None,
) -> None:
    """Full pipeline: generate passwords, write all output artifacts.

    This is the main convenience entry point used by the seed-artifacts script.
    """
    fieldnames, rows = generate_user_passwords(Path(source_csv))

    rotated_users_csv_path = Path(rotated_users_csv)
    credentials_csv_path = Path(credentials_csv)
    credentials_env_path = Path(credentials_env)

    write_rotated_users_csv(fieldnames, rows, rotated_users_csv_path)
    write_credentials_csv(rows, credentials_csv_path)
    write_credentials_env(rows, credentials_env_path, credential_aliases)

    _make_readable(credentials_csv_path)
    _make_readable(credentials_env_path)


def main() -> None:
    """CLI entry point for use from shell scripts.

    Usage (seed user passwords)::

        python scripts/supporting/seed_password_rotation.py \\
            --source mock-data/users.csv \\
            --rotated-users /seed-data/users.csv \\
            --credentials-csv /seed-data/keycloak_seed_user_credentials.csv \\
            --credentials-env /seed-data/keycloak_seed_user_credentials.env

    Usage (env file password rotation)::

        python scripts/supporting/seed_password_rotation.py \\
            --env-file .env.dev.local \\
            --output-dir tmp/env_passwords
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate random passwords for seed users and/or env files"
    )
    # Seed user password mode
    parser.add_argument("--source", help="Path to the source users CSV")
    parser.add_argument("--rotated-users", help="Output path for users CSV with generated passwords")
    parser.add_argument("--credentials-csv", help="Output path for email,password CSV")
    parser.add_argument("--credentials-env", help="Output path for shell-sourceable env file")
    # Env file password rotation mode
    parser.add_argument("--env-file", help="Path to .env.*.local file to rotate passwords in")
    parser.add_argument("--output-dir", default=None, help="Output directory for rotated env file (default: tmp/env_passwords)")
    args = parser.parse_args()

    if args.env_file:
        # Env file password rotation mode
        rotate_env_passwords(args.env_file, output_dir=args.output_dir)
    elif args.source and args.rotated_users and args.credentials_csv and args.credentials_env:
        # Seed user password mode
        generate_and_write(
            source_csv=args.source,
            rotated_users_csv=args.rotated_users,
            credentials_csv=args.credentials_csv,
            credentials_env=args.credentials_env,
        )
    else:
        parser.error("Either --env-file or (--source, --rotated-users, --credentials-csv, --credentials-env) is required")


if __name__ == "__main__":
    main()
