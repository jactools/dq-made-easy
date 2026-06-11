#!/usr/bin/env python3

"""Generate an importable Zammad user CSV.

The default mode combines all users from `dq-db/mock-data/users.csv` with the
dedicated Zammad admin row from `dq-db/mock-data/zammad-admin.csv`, then
writes `dq-db/mock-data/zammad-generated-users.csv` using the column order
defined by `dq-db/mock-data/zammad-user-template.csv`.

The Keycloak mode uses live realm users and role mappings as the source of
truth for workspace organizations and support visibility.

The output intentionally leaves the `id` field blank so Zammad can create or
match users by login/email during import.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from urllib import error, parse, request


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_USERS_CSV = ROOT_DIR / "dq-db" / "mock-data" / "users.csv"
DEFAULT_ADMIN_CSV = ROOT_DIR / "dq-db" / "mock-data" / "zammad-admin.csv"
DEFAULT_TEMPLATE_CSV = ROOT_DIR / "dq-db" / "mock-data" / "zammad-user-template.csv"
DEFAULT_OUTPUT_CSV = ROOT_DIR / "dq-db" / "mock-data" / "zammad-generated-users.csv"
DEFAULT_KEYCLOAK_PAGE_SIZE = 100

ZAMMAD_ADMIN_ROLES = {
    "admin",
    "cross-admin",
    "user-manager",
    "workspace-manager",
    "r11",
    "r12",
    "r13",
    "r14",
    "r15",
    "r16",
}


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def require_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"Required CSV not found: {path}")


def read_template_header(template_csv: Path) -> list[str]:
    require_file(template_csv)
    with template_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise SystemExit(f"Template CSV is empty: {template_csv}") from exc

    header = [clean(column) for column in header]
    if not header:
        raise SystemExit(f"Template CSV does not define any columns: {template_csv}")
    return header


def load_required_name_parts(row: dict[str, str]) -> tuple[str, str]:
    first_name = clean(row.get("first_name"))
    last_name = clean(row.get("last_name"))
    if first_name and last_name:
        return first_name, last_name

    identifier = clean(row.get("email")) or clean(row.get("id")) or "unknown row"
    raise SystemExit(f"users.csv row is missing required first_name/last_name for {identifier}")


def split_workspaces(workspaces: str) -> list[str]:
    values = [workspace for workspace in (part.strip() for part in clean(workspaces).split(";")) if workspace]
    return list(dict.fromkeys(values))


def split_attribute_values(raw_value: object) -> list[str]:
    if isinstance(raw_value, list):
        values = [clean(value) for value in raw_value]
    else:
        values = [part.strip() for part in clean(raw_value).replace(",", ";").split(";")]
    return [value for value in values if value]


def build_user_row(
    *,
    login: str,
    firstname: str,
    lastname: str,
    email: str,
    workspaces: list[str],
    roles: str,
    active: str,
    verified: str,
    header: list[str],
) -> dict[str, str]:
    organization = workspaces[0] if workspaces else ""
    organizations = "~~~".join(workspaces[1:])
    values = {
        "id": "",
        "login": login,
        "firstname": firstname,
        "lastname": lastname,
        "email": email,
        "web": "",
        "phone": "",
        "fax": "",
        "mobile": "",
        "department": "",
        "street": "",
        "zip": "",
        "city": "",
        "country": "",
        "address": "",
        "vip": "false",
        "verified": verified,
        "active": active,
        "note": "",
        "last_login": "",
        "out_of_office": "false",
        "out_of_office_start_at": "",
        "out_of_office_end_at": "",
        "roles": roles,
        "out_of_office_replacement": "",
        "organizations": organizations,
        "organization": organization,
    }
    return {column: values.get(column, "") for column in header}


def build_regular_user_row(row: dict[str, str], header: list[str]) -> dict[str, str]:
    user_id = clean(row.get("id"))
    email = clean(row.get("email"))
    workspaces = split_workspaces(row.get("workspaces"))

    if not user_id:
        raise SystemExit(f"users.csv row is missing id: {row}")
    if not email:
        raise SystemExit(f"users.csv row is missing email for id={user_id!r}")

    firstname, lastname = load_required_name_parts(row)
    return build_user_row(
        login=email,
        firstname=firstname,
        lastname=lastname,
        email=email,
        workspaces=workspaces,
        roles="",
        active="true",
        verified="false",
        header=header,
    )


def zammad_roles_from_realm_roles(realm_roles: list[str]) -> str:
    normalized_roles = {clean(role).lower() for role in realm_roles if clean(role)}
    if normalized_roles & ZAMMAD_ADMIN_ROLES:
        return "Admin~~~Agent"
    if normalized_roles:
        return "Agent"
    return "Customer"


def keycloak_api_json(*, url: str, token: str | None = None, data: bytes | None = None) -> object:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = request.Request(url, headers=headers, data=data)
    try:
        with request.urlopen(req) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            payload = response.read().decode(charset)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Keycloak request failed for {url}: {exc.code} {detail}") from exc
    except error.URLError as exc:
        raise SystemExit(f"Keycloak request failed for {url}: {exc}") from exc
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Keycloak returned invalid JSON for {url}") from exc


def keycloak_admin_token(args: argparse.Namespace) -> str:
    admin_username = args.keycloak_system_admin_username
    admin_password = args.keycloak_system_admin_password
    if args.keycloak_admin_realm == "master" and args.keycloak_admin_user and args.keycloak_admin_pass:
        admin_username = args.keycloak_admin_user
        admin_password = args.keycloak_admin_pass
    if not admin_username or not admin_password:
        raise SystemExit("Keycloak admin credentials are required for --source keycloak")

    token_url = (
        f"{args.keycloak_internal_url.rstrip('/')}/realms/{args.keycloak_admin_realm}/"
        "protocol/openid-connect/token"
    )
    token_payload = parse.urlencode(
        {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": admin_username,
            "password": admin_password,
        }
    ).encode("utf-8")
    response = keycloak_api_json(url=token_url, data=token_payload)
    token = clean(response.get("access_token") if isinstance(response, dict) else "")
    if not token:
        raise SystemExit("Keycloak admin token response did not include access_token")
    return token


def load_keycloak_users(args: argparse.Namespace, header: list[str]) -> list[dict[str, str]]:
    token = keycloak_admin_token(args)
    output_rows: list[dict[str, str]] = []
    seen_emails: set[str] = set()
    first = 0

    while True:
        users_url = (
            f"{args.keycloak_internal_url.rstrip('/')}/admin/realms/{args.keycloak_realm}/users"
            f"?first={first}&max={args.keycloak_page_size}&briefRepresentation=false"
        )
        users_payload = keycloak_api_json(url=users_url, token=token)
        if not isinstance(users_payload, list):
            raise SystemExit("Keycloak users response must be a list")
        if not users_payload:
            break

        for user in users_payload:
            if not isinstance(user, dict):
                continue
            email = clean(user.get("email")).lower() or clean(user.get("username")).lower()
            if not email:
                raise SystemExit(f"Keycloak user is missing email/username: {user}")
            if email in seen_emails:
                raise SystemExit(f"Duplicate Keycloak user email found: {email}")
            seen_emails.add(email)

            user_id = clean(user.get("id"))
            if not user_id:
                raise SystemExit(f"Keycloak user is missing id: {email}")

            roles_url = (
                f"{args.keycloak_internal_url.rstrip('/')}/admin/realms/{args.keycloak_realm}/users/"
                f"{parse.quote(user_id, safe='')}/role-mappings/realm"
            )
            role_payload = keycloak_api_json(url=roles_url, token=token)
            if not isinstance(role_payload, list):
                raise SystemExit(f"Keycloak role mappings response must be a list for {email}")
            realm_roles = [clean(role.get("name")) for role in role_payload if isinstance(role, dict)]

            attributes = user.get("attributes") if isinstance(user.get("attributes"), dict) else {}
            workspaces = split_attribute_values(attributes.get("workspaces") or attributes.get("workspace"))
            firstname = clean(user.get("firstName"))
            lastname = clean(user.get("lastName"))
            if not firstname and not lastname:
                firstname, lastname = split_name(clean(user.get("username")))

            output_rows.append(
                build_user_row(
                    login=clean(user.get("username")) or email,
                    firstname=firstname,
                    lastname=lastname,
                    email=email,
                    workspaces=workspaces,
                    roles=zammad_roles_from_realm_roles(realm_roles),
                    active="true" if bool(user.get("enabled", True)) else "false",
                    verified="true" if bool(user.get("emailVerified", False)) else "false",
                    header=header,
                )
            )

        if len(users_payload) < args.keycloak_page_size:
            break
        first += args.keycloak_page_size

    if not output_rows:
        raise SystemExit("Keycloak did not return any users for Zammad generation")
    return output_rows


def build_admin_row(admin_csv: Path, header: list[str]) -> dict[str, str]:
    require_file(admin_csv)
    with admin_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    if not rows:
        raise SystemExit(f"Admin CSV does not contain any rows: {admin_csv}")
    if len(rows) != 1:
        raise SystemExit(f"Admin CSV must contain exactly one row, found {len(rows)} in {admin_csv}")

    row = rows[0]
    email = clean(row.get("email"))
    if not email:
        raise SystemExit(f"Admin CSV row is missing email: {row}")

    values = {column: clean(row.get(column)) for column in header}
    values["id"] = ""
    values["login"] = clean(row.get("login")) or email
    values["email"] = email
    values["firstname"] = clean(row.get("firstname"))
    values["lastname"] = clean(row.get("lastname"))
    values["roles"] = clean(row.get("roles")) or "Admin~~~Agent"
    values["vip"] = clean(row.get("vip")) or "false"
    values["verified"] = clean(row.get("verified")) or "false"
    values["active"] = clean(row.get("active")) or "true"
    values["out_of_office"] = clean(row.get("out_of_office")) or "false"

    return values


def load_users(users_csv: Path, header: list[str]) -> list[dict[str, str]]:
    require_file(users_csv)
    with users_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing_columns = sorted({"first_name", "last_name", "email", "id"} - fieldnames)
        if missing_columns:
            raise SystemExit(f"users.csv is missing required columns: {', '.join(missing_columns)}")
        rows = list(reader)

    if not rows:
        raise SystemExit(f"Users CSV does not contain any rows: {users_csv}")

    output_rows: list[dict[str, str]] = []
    seen_emails: set[str] = set()

    for row in rows:
        email = clean(row.get("email")).lower()
        if not email:
            raise SystemExit(f"users.csv row is missing email: {row}")
        if email in seen_emails:
            raise SystemExit(f"Duplicate user email found in users.csv: {email}")
        seen_emails.add(email)
        output_rows.append(build_regular_user_row(row, header))

    return output_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("csv", "keycloak"), default="csv", help="User source for Zammad generation")
    parser.add_argument("--users-csv", type=Path, default=DEFAULT_USERS_CSV, help="Path to users.csv")
    parser.add_argument("--admin-csv", type=Path, default=DEFAULT_ADMIN_CSV, help="Path to zammad-admin.csv")
    parser.add_argument("--template-csv", type=Path, default=DEFAULT_TEMPLATE_CSV, help="Path to zammad-user-template.csv")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_CSV, help="Path to write zammad-generated-users.csv")
    parser.add_argument("--keycloak-internal-url", default=os.getenv("KEYCLOAK_INTERNAL_URL", ""), help="Keycloak admin base URL")
    parser.add_argument("--keycloak-admin-realm", default=os.getenv("KEYCLOAK_ADMIN_REALM", "master"), help="Keycloak admin realm")
    parser.add_argument("--keycloak-admin-user", default=os.getenv("KEYCLOAK_ADMIN_USER", os.getenv("KEYCLOAK_ADMIN", "")), help="Keycloak bootstrap admin username")
    parser.add_argument("--keycloak-admin-pass", default=os.getenv("KEYCLOAK_ADMIN_PASS", os.getenv("KEYCLOAK_ADMIN_PASSWORD", "")), help="Keycloak bootstrap admin password")
    parser.add_argument("--keycloak-system-admin-username", default=os.getenv("KEYCLOAK_SYSTEM_ADMIN_USERNAME", ""), help="Keycloak realm system admin username")
    parser.add_argument("--keycloak-system-admin-password", default=os.getenv("KEYCLOAK_SYSTEM_ADMIN_PASSWORD", ""), help="Keycloak realm system admin password")
    parser.add_argument("--keycloak-realm", default=os.getenv("KEYCLOAK_REALM", ""), help="Keycloak realm to mirror into Zammad")
    parser.add_argument("--keycloak-page-size", type=int, default=DEFAULT_KEYCLOAK_PAGE_SIZE, help="Keycloak admin API page size")
    args = parser.parse_args()

    header = read_template_header(args.template_csv)
    if args.source == "keycloak":
        if not args.keycloak_internal_url:
            raise SystemExit("--keycloak-internal-url is required for --source keycloak")
        if not args.keycloak_realm:
            raise SystemExit("--keycloak-realm is required for --source keycloak")
        regular_users = load_keycloak_users(args, header)
    else:
        regular_users = load_users(args.users_csv, header)
    admin_row = build_admin_row(args.admin_csv, header)

    output_emails = {clean(row.get("email")).lower() for row in regular_users}
    admin_email = clean(admin_row.get("email")).lower()
    if admin_email in output_emails:
        raise SystemExit(f"Admin email already exists in users.csv output: {admin_email}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="raise")
        writer.writeheader()
        for row in regular_users:
            writer.writerow(row)
        writer.writerow(admin_row)

    print(f"Wrote {len(regular_users) + 1} users to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())