#!/usr/bin/env python3
import json
import os
import sys

import requests

def _require_env(name: str) -> str:
    value = str(os.environ.get(name, "")).strip()
    if not value:
        print(f"{name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


KEYCLOAK_LOCAL_URL = _require_env("KEYCLOAK_LOCAL_URL")
REALM = _require_env("KEYCLOAK_REALM")
KONG_PUBLIC_URL = _require_env("KONG_PUBLIC_URL")
UI_NGINX_LOCAL_URL = _require_env("UI_NGINX_LOCAL_URL")
UI_VITE_LOCAL_URL = _require_env("UI_VITE_LOCAL_URL")

try:
    # Get admin token
    print("Getting admin token...")
    token_response = requests.post(
        f"{KEYCLOAK_LOCAL_URL}/realms/master/protocol/openid-connect/token",
        data={
            "client_id": "admin-cli",
            "username": "admin",
            "password": "admin",
            "grant_type": "password"
        },
        timeout=5
    )
    token_response.raise_for_status()
    token = token_response.json()["access_token"]
    print("✓ Token obtained")

    # Check if Kong client exists
    headers = {"Authorization": f"Bearer {token}"}
    existing_response = requests.get(
        f"{KEYCLOAK_LOCAL_URL}/admin/realms/{REALM}/clients?clientId=dq-made-easy-kong",
        headers=headers,
        timeout=5
    )
    existing = existing_response.json()

    if existing:
        kong_client_id = existing[0]["id"]
        print(f"✓ Kong client already exists: {kong_client_id}")
    else:
        print("Creating Kong OIDC client...")
        client_data = {
            "clientId": "dq-made-easy-kong",
            "name": "Kong Gateway",
            "enabled": True,
            "clientAuthenticatorType": "client-secret",
            "publicClient": False,
            "protocol": "openid-connect",
            "redirectUris": [f"{KONG_PUBLIC_URL}/v1/*"],
            "webOrigins": [KONG_PUBLIC_URL, UI_NGINX_LOCAL_URL, UI_VITE_LOCAL_URL],
            "directAccessGrantsEnabled": False,
            "standardFlowEnabled": True,
            "serviceAccountsEnabled": True
        }
        response = requests.post(
            f"{KEYCLOAK_LOCAL_URL}/admin/realms/{REALM}/clients",
            json=client_data,
            headers=headers,
            timeout=5
        )
        response.raise_for_status()
        kong_client_id = response.json()["id"]
        print(f"✓ Kong client created: {kong_client_id}")

    # Get client secret
    secret_response = requests.get(
        f"{KEYCLOAK_LOCAL_URL}/admin/realms/{REALM}/clients/{kong_client_id}/client-secret",
        headers=headers,
        timeout=5
    )
    secret_response.raise_for_status()
    client_secret = secret_response.json()["value"]

    print("\n" + "="*50)
    print("Keycloak OIDC Configuration for Kong")
    print("="*50)
    print(f"Discovery URL: {KEYCLOAK_LOCAL_URL}/realms/{REALM}/.well-known/openid-configuration")
    print(f"Client ID: dq-made-easy-kong")
    print(f"Client Secret: {client_secret}")
    print(f"Token Endpoint: {KEYCLOAK_LOCAL_URL}/realms/{REALM}/protocol/openid-connect/token")
    print(f"Issuer: {KEYCLOAK_LOCAL_URL}/realms/{REALM}")

    # Save to file
    config_data = {
        "client_id": "dq-made-easy-kong",
        "client_secret": client_secret,
        "discovery_url": f"{KEYCLOAK_LOCAL_URL}/realms/{REALM}/.well-known/openid-configuration",
        "token_endpoint": f"{KEYCLOAK_LOCAL_URL}/realms/{REALM}/protocol/openid-connect/token",
        "issuer": f"{KEYCLOAK_LOCAL_URL}/realms/{REALM}"
    }
    
    with open("/tmp/kong-oidc-config.json", "w") as f:
        json.dump(config_data, f, indent=2)

    print("\n✓ Configuration saved to /tmp/kong-oidc-config.json")

except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
