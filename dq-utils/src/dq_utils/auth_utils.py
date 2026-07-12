from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Protocol

import requests


class AuthConfigError(RuntimeError):
    pass


class TokenProvider(Protocol):
    def get_token(self, *, correlation_id: str) -> str: ...


@dataclass
class TokenBundle:
    access_token: str
    expires_at_epoch_seconds: float


class StaticTokenProvider:
    def __init__(self, token: str) -> None:
        token = str(token or "").strip()
        if not token:
            raise AuthConfigError("Static token is empty")
        self._token = token

    def get_token(self, *, correlation_id: str) -> str:
        _ = correlation_id
        return self._token


class OidcClientCredentialsTokenProvider:
    def __init__(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str | None = None,
        refresh_skew_seconds: int = 60,
        timeout_seconds: int = 10,
        max_startup_retries: int,
        retry_backoff_seconds: float,
    ) -> None:
        token_url = str(token_url or "").strip()
        client_id = str(client_id or "").strip()
        client_secret = str(client_secret or "").strip()
        scope = str(scope or "").strip() or None

        if not token_url:
            raise AuthConfigError("OIDC token_url is required")
        if not client_id:
            raise AuthConfigError("OIDC client_id is required")
        if not client_secret:
            raise AuthConfigError("OIDC client_secret is required")

        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._refresh_skew_seconds = int(refresh_skew_seconds)
        self._timeout_seconds = int(timeout_seconds)
        self._max_startup_retries = int(max_startup_retries)
        self._retry_backoff_seconds = float(retry_backoff_seconds)
        self._cached: TokenBundle | None = None

    def _request_token(self, data: dict[str, str], correlation_id: str) -> requests.Response:
        """Issue a single token request with optional retry on connection errors."""
        max_attempts = 1 + self._max_startup_retries
        last_exc: Exception | None = None

        for attempt in range(max_attempts):
            try:
                response = requests.post(
                    self._token_url,
                    data=data,
                    headers={"X-Correlation-ID": correlation_id},
                    timeout=self._timeout_seconds,
                )
                # Auth errors (4xx/5xx) are never retried — they signal misconfiguration
                return response
            except requests.exceptions.ConnectionError as exc:
                last_exc = exc
                if attempt < self._max_startup_retries:
                    backoff = self._retry_backoff_seconds * (attempt + 1)
                    print(
                        f"Warning: OIDC token endpoint unreachable at '{self._token_url}' "
                        f"(attempt {attempt + 1}/{max_attempts}); retrying in {backoff:.0f}s...",
                        flush=True,
                    )
                    time.sleep(backoff)
                continue

        raise AuthConfigError(
            f"Unable to obtain OIDC access token (token endpoint unreachable at "
            f"'{self._token_url}' after {max_attempts} attempt(s))"
        ) from last_exc  # type: ignore[arg-type]

    def get_token(self, *, correlation_id: str) -> str:
        now = time.time()
        if self._cached is not None and (self._cached.expires_at_epoch_seconds - self._refresh_skew_seconds) > now:
            return self._cached.access_token

        data: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        if self._scope:
            data["scope"] = self._scope

        response = self._request_token(data, correlation_id)

        if response.status_code >= 400:
            raise AuthConfigError(
                f"Unable to obtain OIDC access token (token endpoint returned {response.status_code})"
            )

        try:
            payload = response.json()
        except Exception as exc:
            raise AuthConfigError("OIDC token endpoint returned non-JSON response") from exc

        token = str(payload.get("access_token") or "").strip()
        expires_in = payload.get("expires_in")
        try:
            expires_in_seconds = int(expires_in)
        except Exception:
            expires_in_seconds = 0

        if not token:
            raise AuthConfigError("OIDC token endpoint response missing access_token")
        if expires_in_seconds <= 0:
            raise AuthConfigError("OIDC token endpoint response missing/invalid expires_in")

        self._cached = TokenBundle(
            access_token=token,
            expires_at_epoch_seconds=now + float(expires_in_seconds),
        )
        return token


class OidcPasswordTokenProvider:
    def __init__(
        self,
        *,
        token_url: str,
        client_id: str,
        username: str,
        password: str,
        client_secret: str | None = None,
        scope: str | None = None,
        refresh_skew_seconds: int = 60,
        timeout_seconds: int = 10,
        max_startup_retries: int,
        retry_backoff_seconds: float,
    ) -> None:
        token_url = str(token_url or "").strip()
        client_id = str(client_id or "").strip()
        username = str(username or "").strip()
        password = str(password or "").strip()
        client_secret = str(client_secret or "").strip() or None
        scope = str(scope or "").strip() or None

        if not token_url:
            raise AuthConfigError("OIDC token_url is required")
        if not client_id:
            raise AuthConfigError("OIDC client_id is required")
        if not username:
            raise AuthConfigError("OIDC username is required")
        if not password:
            raise AuthConfigError("OIDC password is required")

        self._token_url = token_url
        self._client_id = client_id
        self._username = username
        self._password = password
        self._client_secret = client_secret
        self._scope = scope
        self._refresh_skew_seconds = int(refresh_skew_seconds)
        self._timeout_seconds = int(timeout_seconds)
        self._max_startup_retries = int(max_startup_retries)
        self._retry_backoff_seconds = float(retry_backoff_seconds)
        self._cached: TokenBundle | None = None

    def _request_token(self, data: dict[str, str], correlation_id: str) -> requests.Response:
        """Issue a single token request with optional retry on connection errors."""
        max_attempts = 1 + self._max_startup_retries
        last_exc: Exception | None = None

        for attempt in range(max_attempts):
            try:
                response = requests.post(
                    self._token_url,
                    data=data,
                    headers={"X-Correlation-ID": correlation_id},
                    timeout=self._timeout_seconds,
                )
                # Auth errors (4xx/5xx) are never retried — they signal misconfiguration
                return response
            except requests.exceptions.ConnectionError as exc:
                last_exc = exc
                if attempt < self._max_startup_retries:
                    backoff = self._retry_backoff_seconds * (attempt + 1)
                    print(
                        f"Warning: OIDC token endpoint unreachable at '{self._token_url}' "
                        f"(attempt {attempt + 1}/{max_attempts}); retrying in {backoff:.0f}s...",
                        flush=True,
                    )
                    time.sleep(backoff)
                continue

        raise AuthConfigError(
            f"Unable to obtain OIDC access token (token endpoint unreachable at "
            f"'{self._token_url}' after {max_attempts} attempt(s))"
        ) from last_exc  # type: ignore[arg-type]

    def get_token(self, *, correlation_id: str) -> str:
        now = time.time()
        if self._cached is not None and (self._cached.expires_at_epoch_seconds - self._refresh_skew_seconds) > now:
            return self._cached.access_token

        data: dict[str, str] = {
            "grant_type": "password",
            "client_id": self._client_id,
            "username": self._username,
            "password": self._password,
        }
        if self._client_secret:
            data["client_secret"] = self._client_secret
        if self._scope:
            data["scope"] = self._scope

        response = self._request_token(data, correlation_id)

        if response.status_code >= 400:
            raise AuthConfigError(
                f"Unable to obtain OIDC access token (token endpoint returned {response.status_code})"
            )

        try:
            payload = response.json()
        except Exception as exc:
            raise AuthConfigError("OIDC token endpoint returned non-JSON response") from exc

        token = str(payload.get("access_token") or "").strip()
        expires_in = payload.get("expires_in")
        try:
            expires_in_seconds = int(expires_in)
        except Exception:
            expires_in_seconds = 0

        if not token:
            raise AuthConfigError("OIDC token endpoint response missing access_token")
        if expires_in_seconds <= 0:
            raise AuthConfigError("OIDC token endpoint response missing/invalid expires_in")

        self._cached = TokenBundle(
            access_token=token,
            expires_at_epoch_seconds=now + float(expires_in_seconds),
        )
        return token


def resolve_oidc_token_url(*, issuer: str | None, token_url: str | None) -> str | None:
    token_url_value = str(token_url or "").strip()
    if token_url_value:
        return token_url_value

    issuer_value = str(issuer or "").strip().rstrip("/")
    if issuer_value:
        return issuer_value + "/protocol/openid-connect/token"

    return None


def build_token_provider_from_env(
    *,
    static_token_env_var: str,
    issuer_env_var: str,
    token_url_env_var: str,
    client_id_env_var: str,
    client_secret_env_var: str,
    scope_env_var: str,
    refresh_skew_seconds: int = 60,
    max_startup_retries: int,
    retry_backoff_seconds: float,
) -> TokenProvider:
    static_token = str(os.getenv(static_token_env_var) or "").strip()
    if static_token:
        return StaticTokenProvider(static_token)

    token_url = resolve_oidc_token_url(
        issuer=os.getenv(issuer_env_var),
        token_url=os.getenv(token_url_env_var),
    )
    client_id = str(os.getenv(client_id_env_var) or "").strip()
    client_secret = str(os.getenv(client_secret_env_var) or "").strip()
    scope = str(os.getenv(scope_env_var) or "").strip() or None

    if token_url and client_id and client_secret:
        return OidcClientCredentialsTokenProvider(
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
            scope=scope,
            refresh_skew_seconds=refresh_skew_seconds,
            max_startup_retries=max_startup_retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )

    raise AuthConfigError(
        "Auth is not configured. Set a static bearer token in "
        f"{static_token_env_var}, or configure OIDC client credentials using "
        f"({issuer_env_var} or {token_url_env_var}) plus {client_id_env_var} and {client_secret_env_var}."
    )


def build_oidc_token_provider_from_env(
    *,
    issuer_env_var: str,
    token_url_env_var: str,
    client_id_env_var: str,
    client_secret_env_var: str,
    scope_env_var: str,
    refresh_skew_seconds: int = 60,
    max_startup_retries: int,
    retry_backoff_seconds: float,
) -> TokenProvider:
    """Build an OIDC client-credentials token provider from env.

    This intentionally does not support static bearer tokens. Callers that need
    fail-fast token rotation should use this helper.
    """

    token_url = resolve_oidc_token_url(
        issuer=os.getenv(issuer_env_var),
        token_url=os.getenv(token_url_env_var),
    )
    client_id = str(os.getenv(client_id_env_var) or "").strip()
    client_secret = str(os.getenv(client_secret_env_var) or "").strip()
    scope = str(os.getenv(scope_env_var) or "").strip() or None

    if token_url and client_id and client_secret:
        return OidcClientCredentialsTokenProvider(
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
            scope=scope,
            refresh_skew_seconds=refresh_skew_seconds,
            max_startup_retries=max_startup_retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )

    raise AuthConfigError(
        "OIDC auth is not configured. Configure OIDC client credentials using "
        f"({issuer_env_var} or {token_url_env_var}) plus {client_id_env_var} and {client_secret_env_var}."
    )
