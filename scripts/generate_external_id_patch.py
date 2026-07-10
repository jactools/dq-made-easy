#!/usr/bin/env python3
"""Generate a safe SQL patch to populate `users.external_id` from mock CSV data.

This script is a self-contained copy placed under `dq-api/scripts` so the
API image build (which uses `dq-api` as the build context) can include it
and run the generator inside the container at startup. Keep behavior in
sync with the repository-level generator.
"""
import argparse
import csv
import json
import os
import ssl
import time
import urllib.parse
import urllib.request
import shlex
import subprocess
import shutil
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]

# The generator now expects the Keycloak-exported CSV to be present in the
# FastAPI migrations directory so Alembic revisions can access it adjacent
# to the generated revision. Fail fast if missing.
# OUT_DIR is the migrations/versions dir; parent is migrations.
OUT_DIR = ROOT / ".." / "dq-api" / "fastapi" / "migrations" / "versions"
OUT_DIR = OUT_DIR.resolve()
INPUT_FILENAME = "users.csv"
INPUT = ROOT / "dq-db" / "mock-data" / INPUT_FILENAME
INPUT = INPUT.resolve()
# Write the generated SQL directly into the FastAPI alembic revisions directory
OUT = OUT_DIR / "ensure_external_ids.sql"


def _keycloak_token(
    base: str,
    keycloak_url: str,
    token_realm: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    internal_base: Optional[str] = None,
) -> Optional[str]:
    """Obtain a Keycloak token.

    Behavior:
    - If `client_secret` is provided, use `client_credentials` against `token_realm`.
    - Otherwise, if username/password are provided, use the password grant.
    - Returns access_token or None on failure.
    """
    token_url = urllib.parse.urljoin(base.rstrip('/') + '/', f"realms/{token_realm}/protocol/openid-connect/token")
    print(f"Attempting to obtain Keycloak token for realm '{token_realm}' at {token_url} using client_id '{client_id}'")

    if client_secret:
        print ("Using client_credentials grant to obtain Keycloak token.")
        data_pairs = ["grant_type=client_credentials", f"client_id={client_id}", f"client_secret={client_secret}"]
    elif username and password:
        print("Using password grant to obtain Keycloak token.") 
        data_pairs = ["grant_type=password", f"username={username}", f"password={password}", f"client_id={client_id}"]
    else:
        print("Keycloak token request failed: insufficient credentials (provide client secret or username/password)")
        return None

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    max_attempts = 10
    sleep_seconds = 2
    data = "&".join(data_pairs).encode()

    for attempt_number in range(1, max_attempts + 1):
        if attempt_number == 1:
            print("Attempting direct HTTP request to Keycloak for token.")
        req = urllib.request.Request(token_url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=15, context=ssl_context) as resp:
                body = resp.read().decode()
                try:
                    payload = json.loads(body)
                    token = payload.get("access_token")
                    if token:
                        print(f"Successfully obtained Keycloak token from {token_url}")
                        return token
                    print(f"Keycloak token response from {token_url} contained no access_token; response: {body}")
                except json.JSONDecodeError:
                    print(f"Keycloak token response from {token_url} was not JSON: {body}")
        except urllib.error.HTTPError as he:
            try:
                body = he.read().decode()
            except Exception:
                body = str(he)
            print(f"Keycloak token request to {token_url} failed: HTTP {he.code} {body}")
        except Exception as exc:
            print(f"Keycloak token request to {token_url} failed: {exc}")

        if attempt_number < max_attempts:
            time.sleep(sleep_seconds)

    if shutil.which("docker") is None:
        return None

    # Otherwise, attempt to use docker-run curl to reach the compose network.
    # Prefer an internal HTTP base if available since local dev Keycloak may use
    # a self-signed TLS certificate on the public hostname.
    docker_attempts = []
    if internal_base:
        internal_token_url = urllib.parse.urljoin(internal_base.rstrip('/') + '/', f"realms/{token_realm}/protocol/openid-connect/token")
        docker_attempts.append(internal_token_url)
    if token_url not in docker_attempts:
        docker_attempts.append(token_url)

    project_dir = Path.cwd().name
    candidate_network = f"{project_dir}_default"
    network = candidate_network
    try:
        rc = subprocess.run(["docker", "network", "inspect", network], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc.returncode != 0:
            out = subprocess.run(["docker", "network", "ls", "--format", "{{.Name}}"], capture_output=True, text=True)
            for line in out.stdout.splitlines():
                if project_dir in line:
                    network = line.strip()
                    break
    except Exception:
        network = candidate_network

    for attempt in docker_attempts:
        curl_cmd = [
            "docker", "run", "--rm", "--network", network, "curlimages/curl:8.7.1",
            "-s", "-X", "POST", attempt,
            "-H", "Content-Type: application/x-www-form-urlencoded",
        ]
        if attempt.startswith("https://"):
            # Allow curl to succeed against local dev self-signed Keycloak certificates.
            curl_cmd.insert(6, "-k")
        for p in data_pairs:
            curl_cmd += ["-d", p]
        try:
            proc = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=15)
            if proc.returncode != 0:
                print(f"Keycloak token request to {attempt} failed (curl rc={proc.returncode}). stderr: {proc.stderr.strip()} stdout: {proc.stdout.strip()}")
                continue
            try:
                payload = json.loads(proc.stdout)
                token = payload.get("access_token")
                if token:
                    print(f"Successfully obtained Keycloak token from {attempt}")
                    return token
                else:
                    print(f"Keycloak token response from {attempt} contained no access_token; response: {proc.stdout.strip()}")
            except json.JSONDecodeError:
                print(f"Keycloak token response from {attempt} was not JSON: {proc.stdout.strip()}")
        except Exception as exc:
            print(f"Keycloak token request to {attempt} failed: {exc}")
    return None


def _keycloak_user_id_by_email(base: str, realm: str, token: str, email: str, internal_base: Optional[str] = None) -> Optional[str]:
    base_url = base.rstrip('/') + '/'
    internal_url = internal_base.rstrip('/') + '/' if internal_base else None
    direct_attempts = [urllib.parse.urljoin(base_url, f"admin/realms/{realm}/users")]
    internal_attempt = None
    if internal_url:
        internal_attempt = urllib.parse.urljoin(internal_url, f"admin/realms/{realm}/users")

    project_dir = Path.cwd().name
    candidate_network = f"{project_dir}_default"
    network = candidate_network
    try:
        rc = subprocess.run(["docker", "network", "inspect", network], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc.returncode != 0:
            out = subprocess.run(["docker", "network", "ls", "--format", "{{.Name}}"], capture_output=True, text=True)
            for line in out.stdout.splitlines():
                if project_dir in line:
                    network = line.strip()
                    break
    except Exception:
        network = candidate_network

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    for full in [f"{attempt}?" + urllib.parse.urlencode({"email": email}) for attempt in direct_attempts]:
        try:
            req = urllib.request.Request(full, method="GET")
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=15, context=ssl_context) as resp:
                body = resp.read().decode()
                data = json.loads(body)
                if isinstance(data, list) and data:
                    return data[0].get("id")
        except urllib.error.HTTPError as he:
            try:
                body = he.read().decode()
            except Exception:
                body = str(he)
            print(f"Keycloak user lookup HTTP error for {email}: {he.code} {body}")
        except Exception as exc:
            print(f"Keycloak user lookup failed for {email}: {exc}")

    if shutil.which("docker") is None:
        return None

    docker_attempts = []
    if internal_attempt:
        docker_attempts.append(internal_attempt)
    for attempt in direct_attempts:
        if attempt not in docker_attempts:
            docker_attempts.append(attempt)

    curl_cmd_base = [
        "docker", "run", "--rm", "--network", network, "curlimages/curl:8.7.1",
        "-s", "-X", "GET",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Accept: application/json",
    ]
    for attempt_base in docker_attempts:
        full = attempt_base + "?" + urllib.parse.urlencode({"email": email})
        curl_cmd = curl_cmd_base + [full]
        if attempt_base.startswith("https://"):
            curl_cmd.insert(6, "-k")
        try:
            proc = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=15)
            if proc.returncode != 0:
                print(f"Keycloak user lookup failed for {email}: curl rc={proc.returncode} stderr={proc.stderr.strip()}")
                continue
            data = json.loads(proc.stdout)
            if isinstance(data, list) and data:
                return data[0].get("id")
        except Exception as exc:
            print(f"Keycloak user lookup failed for {email}: {exc}")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SQL patch mapping users.external_id from Keycloak")
    parser.add_argument("--dry-run", action="store_true", help="Don't write SQL file; only report matches")
    parser.add_argument("--verbose", action="store_true", help="Print per-email diagnostics")
    parser.add_argument("--output-file", required=True, help="Path to write SQL patch")
    parser.add_argument("--unmatched-file", required=True, help="Path to write unmatched emails")
    args = parser.parse_args()

    if not INPUT.exists():
        print(f"{INPUT_FILENAME} not found at {INPUT}")
        raise SystemExit(2)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    kc_base = os.environ.get("KEYCLOAK_INTERNAL_URL") or os.environ.get("KEYCLOAK_PUBLIC_URL")
    kc_realm = os.environ.get("KEYCLOAK_REALM")
    kc_token_realm = os.environ.get("KEYCLOAK_TOKEN_REALM")
    kc_user = os.environ.get("KEYCLOAK_SYSTEM_ADMIN_USERNAME")
    kc_pass = os.environ.get("KEYCLOAK_SYSTEM_ADMIN_PASSWORD")
    kc_bootstrap_admin_user = (
        os.environ.get("KEYCLOAK_ADMIN_USER")
        or os.environ.get("KEYCLOAK_ADMIN_USERNAME")
        or os.environ.get("KEYCLOAK_ADMIN")
    )
    kc_bootstrap_admin_pass = (
        os.environ.get("KEYCLOAK_ADMIN_PASS")
        or os.environ.get("KEYCLOAK_ADMIN_PASSWORD")
    )
    kc_client = (
        os.environ.get("KEYCLOAK_MASTER_CLIENT_ID")
        or os.environ.get("KEYCLOAK_ADMIN_ID")
        or "admin-cli"
    )
    kc_client_secret = None

    kc_internal_base = os.environ.get("SSO_INTERNAL_ISSUER_URL")

    # The master realm is administered by the bootstrap admin account, which may
    # intentionally differ from application-level system users in deployment envs.
    if (kc_token_realm or "").strip() == "master":
        kc_user = kc_bootstrap_admin_user or kc_user
        kc_pass = kc_bootstrap_admin_pass or kc_pass

    if not kc_base:
        print("KEYCLOAK_PUBLIC_URL not set; cannot connect to Keycloak to verify users.")
        raise SystemExit(2)
    
    if not kc_realm:
        print(
            "ERROR: Keycloak configuration missing. Set KEYCLOAK_REALM."
        )
        raise SystemExit(2)

    token = _keycloak_token(
        kc_base,
        kc_base,
        token_realm=kc_token_realm,
        username=kc_user,
        password=kc_pass,
        client_id=kc_client,
        client_secret=kc_client_secret,
        internal_base=kc_internal_base,
    )
    if not token:
        print("ERROR: failed to obtain Keycloak admin token.")
        raise SystemExit(3)

    mappings: List[Tuple[str, str]] = []
    unmatched: List[str] = []
    no_email = 0
    yes_email = 0
    with INPUT.open(newline="") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            email = (r.get("email") or "").strip()
            if not email:
                no_email = no_email + 1
                continue
            yes_email = yes_email + 1
            kc_id = _keycloak_user_id_by_email(kc_base, kc_realm, token, email, internal_base=kc_internal_base)
            if kc_id:
                mappings.append((email, kc_id))
                if args.verbose:
                    print(f"MATCH: {email} -> {kc_id}")
            else:
                unmatched.append(email)
                if args.verbose:
                    print(f"NO MATCH: {email}")

    output_path = Path(args.output_file).resolve()
    unmatched_path = Path(args.unmatched_file).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    unmatched_path.parent.mkdir(parents=True, exist_ok=True)

    if unmatched:
        with unmatched_path.open("w") as uout:
            for e in unmatched:
                uout.write(e + "\n")
        print(f"Wrote unmatched emails to {unmatched_path}")

    print(f"Emails with no email field: {no_email}")
    print(f"Emails with valid email field: {yes_email}")

    if not mappings:
        print(f"ERROR: no Keycloak users found for emails in {INPUT_FILENAME}; aborting.")
        raise SystemExit(4)

    if args.dry_run:
        print(f"Found {len(mappings)} matches; dry-run mode, not writing SQL.")
        return

    from datetime import datetime

    ts = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    with output_path.open("w") as out:
        out.write(f"-- Generated patch: populate users.external_id from {INPUT_FILENAME}\n")
        out.write(f"-- Generated at UTC: {ts}\n")
        out.write("BEGIN;\n")
        for email, ext in mappings:
            out.write(
                "UPDATE users SET external_id = '%s' WHERE lower(email) = lower('%s') AND (external_id IS NULL OR external_id = '');\n" % (ext.replace("'", "''"), email.replace("'", "''"))
            )
        out.write("COMMIT;\n")

    print(f"Wrote SQL patch to {output_path}")


if __name__ == "__main__":
    main()
