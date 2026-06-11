#!/usr/bin/env python3

"""Generate the initial Zammad auto-wizard seed payload."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def require_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"Required users seed CSV not found: {path}")


def collect_organizations(users_csv: Path) -> list[str]:
    require_file(users_csv)

    organizations: list[str] = []
    seen: set[str] = set()

    with users_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            workspaces = clean(row.get("workspaces"))
            if not workspaces:
                continue

            for workspace in (part.strip() for part in workspaces.split(";")):
                if not workspace or workspace in seen:
                    continue

                seen.add(workspace)
                organizations.append(workspace)

    return organizations


def read_admin_seed(admin_csv: Path) -> dict[str, str]:
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

    login = clean(row.get("login")) or email
    firstname = clean(row.get("firstname"))
    lastname = clean(row.get("lastname"))

    return {
        "login": login,
        "firstname": firstname,
        "lastname": lastname,
        "email": email,
    }


def build_payload() -> dict:
    root_dir = Path(__file__).resolve().parents[1]
    users_csv = root_dir / "dq-db" / "mock-data" / "users.csv"
    admin_csv = root_dir / "dq-db" / "mock-data" / "zammad-admin.csv"
    admin_user = read_admin_seed(admin_csv)
    workspace_organizations = collect_organizations(users_csv)

    product_name = os.environ.get("APP_DISPLAY_NAME")
    if not product_name:
        raise SystemExit("APP_DISPLAY_NAME is required to generate the Zammad auto wizard payload")

    organization_name = os.environ.get("ZAMMAD_AUTOWIZARD_ORGANIZATION", product_name)

    organizations = [{"name": organization_name}]
    seen = {clean(organization_name)}
    for workspace_name in workspace_organizations:
        if workspace_name in seen:
            continue

        seen.add(workspace_name)
        organizations.append({"name": workspace_name})

    return {
        "TextModuleLocale": {
            "Locale": os.environ.get("ZAMMAD_AUTOWIZARD_LOCALE", "en-us"),
        },
        "Users": [admin_user],
        "Settings": [
            {
                "name": "product_name",
                "value": os.environ.get("ZAMMAD_AUTOWIZARD_PRODUCT_NAME", f"{product_name} Support"),
            },
            {
                "name": "system_online_service",
                "value": True,
            },
        ],
        "Organizations": organizations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Path to write the auto wizard JSON payload")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = build_payload()
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())