from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from dq_utils.auth_utils import AuthConfigError
from dq_utils.auth_utils import OidcClientCredentialsTokenProvider
from dq_utils.auth_utils import OidcPasswordTokenProvider
from dq_utils.auth_utils import StaticTokenProvider
from dq_utils.auth_utils import TokenProvider
from dq_utils.auth_utils import resolve_oidc_token_url

from app.core.otel_metrics import increment_contract_policy_cache_event


logger = logging.getLogger(__name__)

_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
_FIELDS = "sla,extension,sourceUrl"


class DataContractLookupError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class JoinConsistencyContractResolver(Protocol):
    async def resolve_contract_policy(
        self,
        contract_id: str,
        *,
        dataset_id: str | None = None,
        cache_ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        ...


class OpenMetadataContractResolver:
    def __init__(
        self,
        *,
        provider: str | None,
        endpoint: str | None,
        api_key: str | None,
        oidc_issuer: str | None = None,
        oidc_token_url: str | None = None,
        oidc_client_id: str | None = None,
        oidc_client_secret: str | None = None,
        oidc_scope: str | None = None,
        oidc_username: str | None = None,
        oidc_password: str | None = None,
        timeout_seconds: int,
        redis_host: str | None = None,
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: str | None = None,
        redis_contract_cache_key_prefix: str = "dq:openmetadata:contract-policy",
    ) -> None:
        self._provider = str(provider or "").strip().lower()
        self._endpoint = str(endpoint or "").rstrip("/")
        self._api_key = str(api_key or "").strip()
        self._oidc_issuer = str(oidc_issuer or "").strip()
        self._oidc_token_url = str(oidc_token_url or "").strip()
        self._oidc_client_id = str(oidc_client_id or "").strip()
        self._oidc_client_secret = str(oidc_client_secret or "").strip()
        self._oidc_scope = str(oidc_scope or "").strip()
        self._oidc_username = str(oidc_username or "").strip()
        self._oidc_password = str(oidc_password or "").strip()
        self._timeout_seconds = max(int(timeout_seconds), 1)
        self._redis_host = str(redis_host or "").strip()
        self._redis_port = int(redis_port)
        self._redis_db = int(redis_db)
        self._redis_password = str(redis_password or "").strip() or None
        self._redis_contract_cache_key_prefix = str(redis_contract_cache_key_prefix or "").strip() or "dq:openmetadata:contract-policy"
        self._redis_client: Any | None = None
        self._redis_client_init_attempted = False
        self._token_provider, self._token_provider_error = self._initialize_token_provider()

    def _initialize_token_provider(self) -> tuple[TokenProvider | None, str | None]:
        try:
            if self._api_key:
                return StaticTokenProvider(self._api_key), None

            has_oidc_inputs = any(
                value
                for value in (
                    self._oidc_issuer,
                    self._oidc_token_url,
                    self._oidc_client_id,
                    self._oidc_client_secret,
                    self._oidc_scope,
                    self._oidc_username,
                    self._oidc_password,
                )
            )
            if not has_oidc_inputs:
                return None, None

            token_url = resolve_oidc_token_url(
                issuer=self._oidc_issuer,
                token_url=self._oidc_token_url,
            )
            if self._oidc_username or self._oidc_password:
                return (
                    OidcPasswordTokenProvider(
                        token_url=token_url or "",
                        client_id=self._oidc_client_id,
                        client_secret=self._oidc_client_secret or None,
                        username=self._oidc_username,
                        password=self._oidc_password,
                        scope=self._oidc_scope or None,
                        timeout_seconds=self._timeout_seconds,
                    ),
                    None,
                )

            return (
                OidcClientCredentialsTokenProvider(
                    token_url=token_url or "",
                    client_id=self._oidc_client_id,
                    client_secret=self._oidc_client_secret,
                    scope=self._oidc_scope or None,
                    timeout_seconds=self._timeout_seconds,
                ),
                None,
            )
        except AuthConfigError as exc:
            return None, str(exc)

    async def resolve_contract_policy(
        self,
        contract_id: str,
        *,
        dataset_id: str | None = None,
        cache_ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._resolve_contract_policy_sync,
            contract_id,
            dataset_id,
            cache_ttl_seconds,
        )

    def _resolve_contract_policy_sync(
        self,
        contract_id: str,
        dataset_id: str | None,
        cache_ttl_seconds: int | None,
    ) -> dict[str, Any]:
        normalized_contract_id = str(contract_id or "").strip()
        if not normalized_contract_id:
            raise DataContractLookupError("JOIN_CONSISTENCY actualityDate requires 'contractId'")
        if self._provider != "openmetadata":
            raise DataContractLookupError(
                "JOIN_CONSISTENCY delivery-contract resolution requires CATALOG_PROVIDER=openmetadata",
                status_code=503,
            )
        if not self._endpoint:
            raise DataContractLookupError(
                "JOIN_CONSISTENCY delivery-contract resolution requires CATALOG_ENDPOINT to be configured",
                status_code=503,
            )

        ttl_seconds = self._normalize_cache_ttl_seconds(cache_ttl_seconds)
        cache_key = self._build_cache_key(normalized_contract_id, dataset_id)
        cached_policy = self._get_cached_policy(cache_key, ttl_seconds)
        if cached_policy is not None:
            increment_contract_policy_cache_event(provider=self._provider, cache_status="hit")
            return dict(cached_policy)

        increment_contract_policy_cache_event(provider=self._provider, cache_status="miss")
        contract_payload = self._fetch_contract(normalized_contract_id)
        policy = self._extract_policy(contract_payload, normalized_contract_id)
        self._set_cached_policy(cache_key, policy, ttl_seconds)
        return policy

    def _build_cache_key(self, contract_id: str, dataset_id: str | None) -> str:
        normalized_dataset_id = str(dataset_id or "").strip()
        return f"{self._redis_contract_cache_key_prefix}:{contract_id}:dataset:{normalized_dataset_id}"

    def _normalize_cache_ttl_seconds(self, ttl_seconds: int | None) -> int:
        if ttl_seconds is None:
            return 300
        return max(int(ttl_seconds), 0)

    def _get_cached_policy(self, cache_key: str, ttl_seconds: int) -> dict[str, Any] | None:
        if ttl_seconds <= 0:
            return None
        client = self._get_redis_client()
        if client is None:
            return None
        try:
            raw_payload = client.get(cache_key)
        except Exception as exc:
            logger.warning("Redis cache get failed for '%s': %s", cache_key, exc)
            return None
        if raw_payload in (None, ""):
            return None
        try:
            parsed = json.loads(str(raw_payload))
        except json.JSONDecodeError as exc:
            logger.warning("Redis cache entry for '%s' is not valid JSON: %s", cache_key, exc)
            return None
        return parsed if isinstance(parsed, dict) else None

    def _set_cached_policy(self, cache_key: str, policy: dict[str, Any], ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        client = self._get_redis_client()
        if client is None:
            return
        try:
            client.setex(cache_key, ttl_seconds, json.dumps(policy, separators=(",", ":")))
        except Exception as exc:
            logger.warning("Redis cache set failed for '%s': %s", cache_key, exc)

    def _get_redis_client(self) -> Any | None:
        if not self._redis_host:
            return None
        if self._redis_client is not None:
            return self._redis_client
        if self._redis_client_init_attempted:
            return None

        self._redis_client_init_attempted = True
        try:
            import redis  # type: ignore

            self._redis_client = redis.Redis(
                host=self._redis_host,
                port=self._redis_port,
                db=self._redis_db,
                password=self._redis_password,
                decode_responses=True,
                socket_connect_timeout=0.3,
                socket_timeout=0.3,
            )
        except Exception as exc:
            logger.warning("Redis cache disabled; Redis client init failed: %s", exc)
            self._redis_client = None
        return self._redis_client

    def _fetch_contract(self, contract_id: str) -> dict[str, Any]:
        for path in self._build_contract_lookup_paths(contract_id):
            payload = self._request_json(path, allow_not_found=True)
            if isinstance(payload, dict) and payload:
                return payload

        list_payload = self._request_json(
            f"/v1/dataContracts?{urlencode({'fields': _FIELDS, 'limit': 1000})}",
            allow_not_found=False,
        )
        contract_payload = self._find_contract_in_list(list_payload, contract_id)
        if contract_payload is not None:
            return contract_payload

        raise DataContractLookupError(
            f"JOIN_CONSISTENCY contract '{contract_id}' was not found in OpenMetadata"
        )

    def _build_contract_lookup_paths(self, contract_id: str) -> list[str]:
        encoded_fields = quote(_FIELDS, safe=",")
        paths: list[str] = []
        if _UUID_PATTERN.fullmatch(contract_id):
            paths.append(f"/v1/dataContracts/{quote(contract_id, safe='')}?fields={encoded_fields}")
        paths.append(f"/v1/dataContracts/name/{quote(contract_id, safe='')}?fields={encoded_fields}")
        return paths

    def _request_json(self, path: str, *, allow_not_found: bool) -> dict[str, Any] | None:
        url = f"{self._endpoint}{path}"
        correlation_id = str(uuid.uuid4())
        headers = {
            "Accept": "application/json",
            "X-Correlation-ID": correlation_id,
        }
        auth_header = self._resolve_authorization_header(correlation_id=correlation_id)
        if auth_header is not None:
            headers["Authorization"] = auth_header

        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            if exc.code == 404 and allow_not_found:
                return None
            detail = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
            logger.warning("OpenMetadata request failed for '%s' with HTTP %s: %s", url, exc.code, detail)
            raise DataContractLookupError(
                f"OpenMetadata request failed with HTTP {exc.code} while resolving data contract",
                status_code=503,
            )
        except URLError as exc:
            logger.warning("OpenMetadata request failed for '%s': %s", url, exc)
            raise DataContractLookupError(
                "OpenMetadata is unavailable while resolving data contracts",
                status_code=503,
            )

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            logger.warning("OpenMetadata response for '%s' was not valid JSON: %s", url, exc)
            raise DataContractLookupError(
                "OpenMetadata returned an invalid data-contract response",
                status_code=503,
            )
        return parsed if isinstance(parsed, dict) else None

    def _resolve_authorization_header(self, *, correlation_id: str) -> str | None:
        if self._token_provider_error:
            raise DataContractLookupError(
                f"OpenMetadata auth is misconfigured: {self._token_provider_error}",
                status_code=503,
            )
        if self._token_provider is None:
            return None

        try:
            token = self._token_provider.get_token(correlation_id=correlation_id)
        except AuthConfigError as exc:
            logger.warning("OpenMetadata auth token acquisition failed: %s", exc)
            raise DataContractLookupError(
                f"OpenMetadata auth token acquisition failed: {exc}",
                status_code=503,
            ) from exc

        normalized_token = str(token or "").strip()
        if not normalized_token:
            raise DataContractLookupError(
                "OpenMetadata auth provider returned an empty access token",
                status_code=503,
            )
        if normalized_token.lower().startswith("bearer "):
            return normalized_token
        return f"Bearer {normalized_token}"

    def _find_contract_in_list(self, payload: dict[str, Any] | None, contract_id: str) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        raw_items = payload.get("data") or payload.get("entities") or payload.get("items") or []
        if not isinstance(raw_items, list):
            return None
        for item in raw_items:
            if isinstance(item, dict) and self._matches_contract_identifier(item, contract_id):
                return item
        return None

    def _matches_contract_identifier(self, payload: dict[str, Any], contract_id: str) -> bool:
        target = contract_id.strip()
        direct_candidates = [
            payload.get("id"),
            payload.get("name"),
            payload.get("fullyQualifiedName"),
            payload.get("sourceUrl"),
        ]
        if any(str(candidate or "").strip() == target for candidate in direct_candidates):
            return True
        return any(value == target for value in self._iter_string_values(payload.get("extension")))

    def _iter_string_values(self, payload: Any) -> list[str]:
        if isinstance(payload, str):
            return [payload.strip()]
        if isinstance(payload, list):
            values: list[str] = []
            for item in payload:
                values.extend(self._iter_string_values(item))
            return values
        if isinstance(payload, dict):
            values = []
            for item in payload.values():
                values.extend(self._iter_string_values(item))
            return values
        return []

    def _extract_policy(self, payload: dict[str, Any], contract_id: str) -> dict[str, Any]:
        sla = payload.get("sla") or {}
        max_latency = sla.get("maxLatency") or {}
        if not isinstance(max_latency, dict) or max_latency.get("value") is None or not max_latency.get("unit"):
            raise DataContractLookupError(
                f"JOIN_CONSISTENCY contract '{contract_id}' does not define sla.maxLatency required for actuality-date tolerance"
            )

        resolved_tolerance_value = int(max_latency.get("value"))
        resolved_tolerance_unit = self._normalize_sla_unit(str(max_latency.get("unit") or "").strip())

        policy = self._extract_override_policy(payload.get("extension"))
        max_override_value = None
        max_override_unit = None
        max_override = policy.get("maxOverrideTolerance") if isinstance(policy, dict) else None
        if isinstance(max_override, str):
            max_override_value, max_override_unit = self._parse_duration_to_value_unit(max_override, field_name="x-dq-rule-policy.joinConsistency.actualityDate.maxOverrideTolerance")
        elif isinstance(max_override, dict):
            raw_value = max_override.get("value")
            raw_unit = self._normalize_override_unit(max_override.get("unit"))
            if raw_value is None or raw_unit is None:
                raise DataContractLookupError(
                    "JOIN_CONSISTENCY contract maxOverrideTolerance must provide both 'value' and a unit of minutes, hours, or days"
                )
            max_override_value = int(raw_value)
            max_override_unit = raw_unit

        return {
            "contractVersion": self._extract_contract_version(payload),
            "resolvedToleranceValue": resolved_tolerance_value,
            "resolvedToleranceUnit": resolved_tolerance_unit,
            "overrideAllowed": bool(policy.get("overrideAllowed", False)) if isinstance(policy, dict) else False,
            "maxOverrideToleranceValue": max_override_value,
            "maxOverrideToleranceUnit": max_override_unit,
        }

    def _extract_contract_version(self, payload: dict[str, Any]) -> str | None:
        extension = payload.get("extension")
        for path in [
            ("odcs", "info", "version"),
            ("source", "info", "version"),
            ("odcsContract", "info", "version"),
            ("sourceContract", "info", "version"),
            ("contract", "info", "version"),
        ]:
            value = self._read_nested_value(extension, *path)
            if str(value or "").strip():
                return str(value).strip()
        version = str(payload.get("version") or "").strip()
        return version or None

    def _extract_override_policy(self, extension: Any) -> dict[str, Any]:
        for path in [
            ("x-dq-rule-policy", "joinConsistency", "actualityDate"),
            ("dqRulePolicy", "joinConsistency", "actualityDate"),
            ("odcs", "x-dq-rule-policy", "joinConsistency", "actualityDate"),
            ("source", "x-dq-rule-policy", "joinConsistency", "actualityDate"),
        ]:
            value = self._read_nested_value(extension, *path)
            if isinstance(value, dict):
                return value
        return {}

    def _read_nested_value(self, payload: Any, *path: str) -> Any:
        current = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _normalize_sla_unit(self, unit: str) -> str:
        normalized = unit.lower()
        mapping = {
            "minute": "minutes",
            "minutes": "minutes",
            "hour": "hours",
            "hours": "hours",
            "day": "days",
            "days": "days",
        }
        if normalized not in mapping:
            raise DataContractLookupError(
                "JOIN_CONSISTENCY contract sla.maxLatency.unit must be minute, hour, or day"
            )
        return mapping[normalized]

    def _normalize_override_unit(self, unit: Any) -> str | None:
        normalized = str(unit or "").strip().lower()
        mapping = {
            "minute": "minutes",
            "minutes": "minutes",
            "hour": "hours",
            "hours": "hours",
            "day": "days",
            "days": "days",
        }
        return mapping.get(normalized)

    def _parse_duration_to_value_unit(self, raw_value: object, *, field_name: str) -> tuple[int, str]:
        normalized = str(raw_value or "").strip().lower()
        match = re.fullmatch(r"(\d+)\s*([mhd])", normalized)
        if match is None:
            raise DataContractLookupError(
                (
                    f"JOIN_CONSISTENCY contract field '{field_name}' must use compact duration syntax like "
                    "'30m', '24h', or '2d'"
                )
            )
        value = int(match.group(1))
        unit = {"m": "minutes", "h": "hours", "d": "days"}[match.group(2)]
        return value, unit