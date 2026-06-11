import logging
import os
from collections.abc import Iterable
from typing import Any

import jwt
from airflow.providers.fab.auth_manager.security_manager.override import (
    FabAirflowSecurityManagerOverride,
)
from flask_appbuilder.security.manager import AUTH_OAUTH
from jwt import PyJWKClient

log = logging.getLogger(__name__)
log.setLevel(os.getenv("AIRFLOW__LOGGING__FAB_LOGGING_LEVEL", "INFO"))

AUTH_TYPE = AUTH_OAUTH
AUTH_USER_REGISTRATION = True
AUTH_ROLES_SYNC_AT_LOGIN = True
AUTH_USER_REGISTRATION_ROLE = "Viewer"
AUTH_ROLES_MAPPING = {
    "Admin": ["Admin"],
    "User": ["User"],
    "Viewer": ["Viewer"],
    "Op": ["Op"],
    "Public": ["Public"],
}

KEYCLOAK_PUBLIC_ISSUER_URL = os.environ["SSO_PUBLIC_ISSUER_URL"].rstrip("/")
KEYCLOAK_INTERNAL_ISSUER_URL = os.environ["SSO_INTERNAL_ISSUER_URL"].rstrip("/")
AIRFLOW_FAB_CLIENT_ID = os.environ["AIRFLOW_FAB_CLIENT_ID"]
AIRFLOW_FAB_CLIENT_SECRET = os.environ["AIRFLOW_FAB_CLIENT_SECRET"]
KEYCLOAK_JWKS_CLIENT = PyJWKClient(
    f"{KEYCLOAK_INTERNAL_ISSUER_URL}/protocol/openid-connect/certs"
)

OAUTH_PROVIDERS = [
    {
        "name": "keycloak",
        "icon": "fa-key",
        "token_key": "access_token",
        "remote_app": {
            "client_id": AIRFLOW_FAB_CLIENT_ID,
            "client_secret": AIRFLOW_FAB_CLIENT_SECRET,
            "api_base_url": f"{KEYCLOAK_INTERNAL_ISSUER_URL}/protocol/openid-connect",
            "access_token_url": f"{KEYCLOAK_INTERNAL_ISSUER_URL}/protocol/openid-connect/token",
            "authorize_url": f"{KEYCLOAK_PUBLIC_ISSUER_URL}/protocol/openid-connect/auth",
            "request_token_url": None,
            "client_kwargs": {"scope": "openid email profile roles"},
        },
    }
]


def _realm_roles_from_claims(claims: dict[str, Any]) -> list[str]:
    realm_access = claims.get("realm_access", {})
    roles = realm_access.get("roles", [])
    if not isinstance(roles, list):
        return []
    return [role for role in roles if isinstance(role, str)]


def _role_to_fab_role(role: str) -> str:
    normalized = role.lower()
    if normalized in {"admin", "cross-admin"}:
        return "Admin"
    if normalized in {"viewer", "auditor", "regulator", "exception-fact-reader"}:
        return "Viewer"
    if normalized in {
        "rule-approver",
        "user",
        "user-manager",
        "workspace-manager",
        "analyst",
        "data-steward",
        "exception-fact-investigator",
    }:
        return "User"
    if normalized.startswith("r") and normalized[1:].isdigit():
        return "User"
    if normalized.startswith("dq:"):
        if normalized.endswith(":read"):
            return "Viewer"
        return "User"
    return "Viewer"


def _fab_roles_from_realm_roles(realm_roles: Iterable[str]) -> list[str]:
    if any(_role_to_fab_role(role) == "Admin" for role in realm_roles):
        return ["Admin"]
    if any(_role_to_fab_role(role) == "User" for role in realm_roles):
        return ["User"]
    return ["Viewer"]


class KeycloakSecurityManager(FabAirflowSecurityManagerOverride):
    def get_oauth_user_info(self, provider: str, response: Any) -> dict[str, Any]:
        if provider != "keycloak":
            return {}

        token = response["access_token"]
        signing_key = KEYCLOAK_JWKS_CLIENT.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=AIRFLOW_FAB_CLIENT_ID,
        )

        realm_roles = _realm_roles_from_claims(claims)
        role_keys = _fab_roles_from_realm_roles(realm_roles)

        return {
            "username": claims.get("preferred_username") or claims.get("email") or claims.get("sub"),
            "email": claims.get("email"),
            "first_name": claims.get("given_name"),
            "last_name": claims.get("family_name"),
            "role_keys": role_keys,
        }


SECURITY_MANAGER_CLASS = KeycloakSecurityManager