from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from app.domain.entities.base import EntityModel


class OidcStateEntity(EntityModel):
    nonce: str = ""
    issuedAt: int | None = None
    frontendOrigin: str | None = None


class OidcTokenResponseEntity(EntityModel):
    access_token: str | None = None
    id_token: str | None = None
    refresh_token: str | None = None


def normalize_auth_frontend_origin(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlparse(value)
    except Exception:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def build_oidc_state_entity(payload: Any) -> OidcStateEntity | None:
    if not isinstance(payload, Mapping):
        return None

    nonce = str(payload.get("nonce") or "").strip()
    issued_at_raw = payload.get("issuedAt")
    issued_at: int | None = None
    if isinstance(issued_at_raw, int):
        issued_at = issued_at_raw
    elif issued_at_raw not in (None, ""):
        try:
            issued_at = int(issued_at_raw)
        except (TypeError, ValueError):
            issued_at = None

    frontend_origin = normalize_auth_frontend_origin(str(payload.get("frontendOrigin") or "").strip() or None)
    return OidcStateEntity(
        nonce=nonce,
        issuedAt=issued_at,
        frontendOrigin=frontend_origin,
    )


def build_oidc_token_response_entity(payload: Any) -> OidcTokenResponseEntity | None:
    if not isinstance(payload, Mapping):
        return None

    access_token = str(payload.get("access_token") or "").strip() or None
    id_token = str(payload.get("id_token") or "").strip() or None
    refresh_token = str(payload.get("refresh_token") or "").strip() or None
    return OidcTokenResponseEntity(
        access_token=access_token,
        id_token=id_token,
        refresh_token=refresh_token,
    )