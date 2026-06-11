#!/usr/bin/env python3
"""Seed OpenMetadata users from a CSV file.

The input CSV is expected to include at least: id,first_name,last_name,email.
The script is idempotent by email and will create only missing users.
If role assignments are provided, users with admin-like roles are promoted to
OpenMetadata admins.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import ssl
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib import error, parse, request

from openmetadata_tls import build_ssl_context


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SSL_CONTEXT: Optional[ssl.SSLContext] = None


def resolve_default_login_email() -> str:
    return clean(__import__("os").environ.get("OM_EMAIL") or __import__("os").environ.get("OPENMETADATA_OIDC_SEED_USERNAME"))


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def normalize_endpoint(endpoint: str) -> str:
    base = endpoint.rstrip("/")
    if base.endswith("/api"):
        return base
    return f"{base}/api"


def request_json(
    api_base: str,
    path: str,
    *,
    method: str = "GET",
    token: str = "",
    body: Optional[Any] = None,
    params: Optional[Dict[str, Any]] = None,
    content_type: str = "application/json",
) -> Dict[str, Any]:
    query = f"?{parse.urlencode(params, doseq=True)}" if params else ""
    url = f"{api_base}{path}{query}"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        headers["Content-Type"] = content_type
        data = json.dumps(body).encode("utf-8")

    req = request.Request(url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=30, context=SSL_CONTEXT) as resp:
        raw = resp.read().decode("utf-8")
        if not raw:
            return {}
        return json.loads(raw)


def login(api_base: str, email: str, password: str, password_b64: str) -> str:
    encoded = password_b64 or base64.b64encode(password.encode("utf-8")).decode("ascii")
    payload = {"email": email, "password": encoded}
    errors: List[str] = []

    for path in ("/v1/users/login", "/v1/auth/login"):
        try:
            obj = request_json(api_base, path, method="POST", body=payload)
            token = clean(obj.get("accessToken"))
            if token:
                return token
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path}: {exc}")

    raise RuntimeError("Failed OpenMetadata login. " + " | ".join(errors))


def iter_existing_users(api_base: str, token: str) -> Iterable[Dict[str, Any]]:
    after: Optional[str] = None
    while True:
        params: Dict[str, Any] = {"limit": 100}
        if after:
            params["after"] = after
        obj = request_json(api_base, "/v1/users", token=token, params=params)
        for row in obj.get("data") or []:
            yield row
        after = clean(((obj.get("paging") or {}).get("after")))
        if not after:
            return


def slug_name(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()
    if not normalized:
        normalized = fallback
    if normalized and normalized[0].isdigit():
        normalized = f"u_{normalized}"
    return normalized[:64]


def choose_unique_name(base_name: str, user_id: str, existing_names: Set[str]) -> str:
    if base_name not in existing_names:
        return base_name

    suffix = slug_name(user_id, "user")[:16]
    candidate = slug_name(f"{base_name}_{suffix}", base_name)
    if candidate not in existing_names:
        return candidate

    i = 2
    while True:
        candidate = slug_name(f"{base_name}_{i}", base_name)
        if candidate not in existing_names:
            return candidate
        i += 1


def parse_admin_user_ids(roles_csv: Path, admin_roles: Set[str]) -> Set[str]:
    if not roles_csv.exists():
        return set()

    admin_ids: Set[str] = set()
    with roles_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            user_id = clean(row.get("user_id"))
            role_id = clean(row.get("role_id")).lower()
            if user_id and role_id in admin_roles:
                admin_ids.add(user_id)
    return admin_ids


def load_required_name_parts(row: Dict[str, Any], *, csv_path: Path) -> Tuple[str, str]:
    first_name = clean(row.get("first_name"))
    last_name = clean(row.get("last_name"))
    if first_name and last_name:
        return first_name, last_name

    identifier = clean(row.get("email")) or clean(row.get("id")) or "unknown row"
    raise RuntimeError(f"{csv_path} is missing required first_name/last_name for {identifier}")


def promote_user_to_admin(api_base: str, token: str, user_obj: Dict[str, Any], email: str) -> bool:
    user_id = clean(user_obj.get("id"))
    if not user_id:
        print(f"[warn] cannot promote {email}: missing OpenMetadata user id")
        return False

    patch_body = [{"op": "replace", "path": "/isAdmin", "value": True}]
    try:
        request_json(
            api_base,
            f"/v1/users/{user_id}",
            method="PATCH",
            token=token,
            body=patch_body,
            content_type="application/json-patch+json",
        )
        print(f"[promote] {email} -> isAdmin=true")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] failed to promote {email} to admin: {exc}")
        return False


def seed_users(
    csv_path: Path,
    roles_csv_path: Path,
    admin_roles: Set[str],
    api_base: str,
    token: str,
    continue_on_error: bool,
) -> Tuple[int, int, int, int, int]:
    admin_user_ids = parse_admin_user_ids(roles_csv_path, admin_roles)

    existing_users = list(iter_existing_users(api_base, token))
    existing_by_email = {
        clean(u.get("email")).lower(): u for u in existing_users if clean(u.get("email"))
    }
    existing_emails = {clean(u.get("email")).lower() for u in existing_users if clean(u.get("email"))}
    existing_names = {clean(u.get("name")) for u in existing_users if clean(u.get("name"))}

    created = 0
    skipped = 0
    failed = 0
    promoted = 0
    promote_failed = 0

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing_columns = sorted({"id", "first_name", "last_name", "email"} - fieldnames)
        if missing_columns:
            raise RuntimeError(f"{csv_path} is missing required columns: {', '.join(missing_columns)}")
        for row in reader:
            user_id = clean(row.get("id"))
            first_name, last_name = load_required_name_parts(row, csv_path=csv_path)
            display_name = f"{first_name} {last_name}"
            email = clean(row.get("email"))
            email_l = email.lower()
            wants_admin = user_id in admin_user_ids

            if not email or not EMAIL_RE.match(email):
                print(f"[skip] invalid email format for id={user_id!r}: {email!r}")
                skipped += 1
                continue

            if email_l in existing_emails:
                print(f"[skip] already exists by email: {email}")
                skipped += 1
                existing_obj = existing_by_email.get(email_l) or {}
                is_admin = bool(existing_obj.get("isAdmin"))
                if wants_admin and not is_admin:
                    if promote_user_to_admin(api_base, token, existing_obj, email):
                        promoted += 1
                        existing_obj["isAdmin"] = True
                    else:
                        promote_failed += 1
                continue

            local_part = email.split("@", 1)[0]
            base_name = slug_name(local_part, slug_name(display_name, "user"))
            name = choose_unique_name(base_name, user_id or email, existing_names)

            create_ok = False
            for attempt in range(0, 6):
                candidate_name = name if attempt == 0 else choose_unique_name(
                    slug_name(f"{base_name}_{attempt}", base_name),
                    user_id or email,
                    existing_names,
                )
                candidate_display = (
                    display_name or local_part
                    if attempt == 0
                    else f"{display_name or local_part} {attempt}"
                )
                payload = {
                    "name": candidate_name,
                    "displayName": candidate_display,
                    "email": email,
                    "isAdmin": wants_admin,
                }

                try:
                    obj = request_json(api_base, "/v1/users", method="POST", token=token, body=payload)
                    created_email = clean(obj.get("email")) or email
                    created_name = clean(obj.get("name")) or candidate_name
                    print(f"[create] {created_email} (name={created_name})")
                    created += 1
                    existing_emails.add(email_l)
                    existing_names.add(created_name)
                    if wants_admin:
                        promoted += 1
                    create_ok = True
                    break
                except error.HTTPError as exc:
                    body = exc.read().decode("utf-8", errors="replace")
                    body_l = body.lower()

                    # OpenMetadata can return a generic "Entity already exists" when
                    # identity fields conflict; treat this as idempotent for seeding.
                    if exc.code in (409, 412) and "already exists" in body_l:
                        print(f"[skip] OpenMetadata reported existing identity: {email}")
                        skipped += 1
                        create_ok = True
                        break

                    # If another process created it in parallel, treat as skip.
                    if exc.code in (409, 412) and "already exists" in body_l and "email" in body_l:
                        print(f"[skip] already exists by email: {email}")
                        skipped += 1
                        existing_emails.add(email_l)
                        create_ok = True
                        break

                    # Retry with a different username when name collision occurs.
                    if exc.code in (409, 412) and (
                        "already exists" in body_l
                        or "entityalreadyexists" in body_l
                        or "name" in body_l
                    ):
                        if attempt < 5:
                            continue

                    failed += 1
                    print(f"[error] create failed for {email}: HTTP {exc.code} {body[:300]}")
                    if not continue_on_error:
                        raise
                    break
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    print(f"[error] create failed for {email}: {exc}")
                    if not continue_on_error:
                        raise
                    break

            if not create_ok:
                continue

    return created, skipped, failed, promoted, promote_failed


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Seed OpenMetadata users from CSV")
    parser.add_argument(
        "--input",
        default=str(root / "dq-db" / "mock-data" / "users.csv"),
        help="Path to users.csv",
    )
    parser.add_argument(
        "--roles-input",
        default=str(root / "dq-db" / "mock-data" / "user_roles.csv"),
        help="Path to user_roles.csv",
    )
    parser.add_argument(
        "--admin-roles",
        default="admin,cross-admin",
        help="Comma-separated role IDs that should map to OpenMetadata isAdmin=true",
    )
    parser.add_argument(
        "--endpoint",
        default="https://openmetadata.jac.dot:8585/api",
        help="OpenMetadata endpoint (with or without /api)",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Bearer token used for OpenMetadata API access",
    )
    parser.add_argument(
        "--email",
        default=resolve_default_login_email(),
        help="OpenMetadata login email",
    )
    parser.add_argument(
        "--password",
        default=clean(__import__("os").environ.get("OM_PASSWORD") or __import__("os").environ.get("OPENMETADATA_OIDC_SEED_PASSWORD") or __import__("os").environ.get("KEYCLOAK_SEEDED_USER_PASSWORD") or __import__("os").environ.get("KEYCLOAK_USER_PASSWORD")),
        help="OpenMetadata admin login password (ignored when --password-b64 provided)",
    )
    parser.add_argument(
        "--password-b64",
        default="",
        help="Base64-encoded OpenMetadata admin password",
    )
    parser.add_argument(
        "--continue-on-error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Continue seeding on user-level create errors",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_path = Path(args.input).expanduser().resolve()
    roles_csv_path = Path(args.roles_input).expanduser().resolve()
    global SSL_CONTEXT
    SSL_CONTEXT = build_ssl_context(args.endpoint, Path(__file__).resolve().parents[2])
    if not csv_path.exists():
        print(f"Input CSV not found: {csv_path}")
        return 1

    admin_roles = {clean(v).lower() for v in args.admin_roles.split(",") if clean(v)}

    api_base = normalize_endpoint(args.endpoint)
    token = clean(args.token)
    if not token:
        token = clean(__import__("os").environ.get("OM_TOKEN", ""))

    if not token:
        if not args.email or not (args.password or args.password_b64):
            print(
                "OpenMetadata login credentials are not configured: provide --token or repo-owned --email with --password/--password-b64."
            )
            return 1
        try:
            token = login(api_base, args.email, args.password, args.password_b64)
        except Exception as exc:  # noqa: BLE001
            print(f"OpenMetadata login failed: {exc}")
            return 1

    try:
        created, skipped, failed, promoted, promote_failed = seed_users(
            csv_path,
            roles_csv_path,
            admin_roles,
            api_base,
            token,
            continue_on_error=args.continue_on_error,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"User seeding aborted: {exc}")
        return 1

    print(
        "OpenMetadata user seed summary: "
        f"created={created} skipped={skipped} failed={failed} "
        f"promoted={promoted} promote_failed={promote_failed}"
    )
    return 0 if failed == 0 and promote_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
