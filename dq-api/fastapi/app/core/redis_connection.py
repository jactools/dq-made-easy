from __future__ import annotations

from typing import Any
from urllib.parse import quote
from urllib.parse import urlencode


def resolve_redis_ca_bundle() -> str | None:
    for value in (
        "REDIS_CA_BUNDLE",
        "SSL_CERT_FILE",
    ):
        candidate = str(__import__("os").environ.get(value) or "").strip()
        if candidate:
            return candidate
    for fallback in (
        "/etc/ssl/certs/platform-root-ca.pem",
        "/etc/openmetadata/certs/internal-ca-bundle.pem",
    ):
        if fallback:
            return fallback
    return None


def resolve_explicit_redis_url(*env_names: str) -> str | None:
    env = __import__("os").environ
    for name in (*env_names, "REDIS_URL"):
        value = str(env.get(name) or "").strip()
        if value:
            return value
    return None


def build_redis_url(
    settings: Any,
    *,
    explicit_env_names: tuple[str, ...] = (),
) -> str | None:
    explicit_url = resolve_explicit_redis_url(*explicit_env_names)
    if explicit_url:
        return explicit_url

    redis_host = str(getattr(settings, "redis_host", "") or "").strip()
    if not redis_host:
        return None

    redis_port = int(getattr(settings, "redis_port", 6379))
    redis_db = int(getattr(settings, "redis_db", 0))
    redis_username = str(getattr(settings, "redis_username", "") or "").strip()
    redis_password = str(getattr(settings, "redis_password", "") or "").strip()
    redis_tls_enabled = bool(getattr(settings, "redis_tls_enabled", False))
    redis_ca_bundle = str(getattr(settings, "redis_ca_bundle", "") or "").strip() or resolve_redis_ca_bundle() or ""

    auth = ""
    if redis_username and redis_password:
        auth = f"{quote(redis_username, safe='')}:{quote(redis_password, safe='')}@"
    elif redis_username:
        auth = f"{quote(redis_username, safe='')}@"
    elif redis_password:
        auth = f":{quote(redis_password, safe='')}@"

    scheme = "rediss" if redis_tls_enabled else "redis"
    base_url = f"{scheme}://{auth}{redis_host}:{redis_port}/{redis_db}"

    if not redis_tls_enabled:
        return base_url

    query: dict[str, str] = {
        "ssl_cert_reqs": "required",
        "ssl_check_hostname": "true",
    }
    if redis_ca_bundle:
        query["ssl_ca_certs"] = redis_ca_bundle
    return f"{base_url}?{urlencode(query)}"


def build_redis_client_kwargs(
    *,
    redis_host: str,
    redis_port: int,
    redis_db: int,
    redis_username: str | None = None,
    redis_password: str | None = None,
    redis_tls_enabled: bool = False,
    redis_ca_bundle: str | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "host": redis_host,
        "port": int(redis_port),
        "db": int(redis_db),
        "decode_responses": True,
    }
    if redis_username:
        kwargs["username"] = redis_username
    if redis_password:
        kwargs["password"] = redis_password
    if redis_tls_enabled:
        kwargs.update(
            {
                "ssl": True,
                "ssl_cert_reqs": "required",
                "ssl_check_hostname": True,
                "ssl_ca_certs": redis_ca_bundle or resolve_redis_ca_bundle(),
            }
        )
    return kwargs


def build_redis_client_kwargs_from_settings(settings: Any) -> dict[str, Any] | None:
    redis_host = str(getattr(settings, "redis_host", "") or "").strip()
    if not redis_host:
        return None
    return build_redis_client_kwargs(
        redis_host=redis_host,
        redis_port=int(getattr(settings, "redis_port", 6379)),
        redis_db=int(getattr(settings, "redis_db", 0)),
        redis_username=str(getattr(settings, "redis_username", "") or "").strip() or None,
        redis_password=str(getattr(settings, "redis_password", "") or "").strip() or None,
        redis_tls_enabled=bool(getattr(settings, "redis_tls_enabled", False)),
        redis_ca_bundle=str(getattr(settings, "redis_ca_bundle", "") or "").strip() or None,
    )
