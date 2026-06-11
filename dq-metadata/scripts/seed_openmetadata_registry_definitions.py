#!/usr/bin/env python3
"""Seed the retail-banking registry-definition demo slice into OpenMetadata."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from openmetadata_tls import build_ssl_context


REQUIRED_DEFINITION_TYPES = {
    "data_product": 1,
    "data_object": 1,
    "attribute": 3,
}
REQUIRED_TERM_PROPERTIES = {
    "definition_id": "Stable dq-made-easy registry identifier.",
    "definition_type": "Governed registry definition type.",
    "definition_name": "Canonical registry definition name.",
    "object_class": "Business object class for the governed definition.",
    "property": "Governed property name.",
    "representation_term": "ISO 11179 representation term.",
    "status": "Lifecycle status for the governed definition.",
    "owner": "Owning team or role for the governed definition.",
    "version": "Governed definition semantic version.",
    "value_domain": "JSON-encoded governed value-domain metadata.",
    "provenance": "JSON-encoded provenance metadata.",
    "applies_to": "JSON-encoded scope references for the governed definition.",
}


class OpenMetadataSeedError(RuntimeError):
    pass


class OpenMetadataRequestError(RuntimeError):
    def __init__(self, method: str, url: str, status_code: int, body: str) -> None:
        super().__init__(f"OpenMetadata request failed: {method} {url} -> HTTP {status_code}: {body}")
        self.method = method
        self.url = url
        self.status_code = status_code
        self.body = body


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def normalize_endpoint(endpoint: str) -> tuple[str, str]:
    base_url = endpoint.rstrip("/")
    if base_url.endswith("/api"):
        return base_url[:-4], base_url
    return base_url, f"{base_url}/api"


def default_login_email() -> str:
    return clean(os.environ.get("OM_EMAIL") or os.environ.get("OPENMETADATA_OIDC_SEED_USERNAME"))


def default_login_password() -> str:
    return clean(
        os.environ.get("OM_PASSWORD")
        or os.environ.get("OPENMETADATA_OIDC_SEED_PASSWORD")
        or os.environ.get("KEYCLOAK_SEEDED_USER_PASSWORD")
        or os.environ.get("KEYCLOAK_USER_PASSWORD")
    )


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_endpoint = os.environ.get("OM_API_BASE") or os.environ.get("OM_BASE_URL") or "https://openmetadata.jac.dot:8585/api"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default=str(repo_root / "dq-metadata" / "demo" / "openmetadata_registry_definitions.retail_banking.json"),
        help="Path to the registry-definition manifest JSON file.",
    )
    parser.add_argument(
        "--endpoint",
        default=default_endpoint,
        help="OpenMetadata API base URL.",
    )
    parser.add_argument("--token", default=os.environ.get("OM_TOKEN", ""), help="Bearer token for OpenMetadata.")
    parser.add_argument(
        "--email",
        default=default_login_email(),
        help="OpenMetadata login email.",
    )
    parser.add_argument(
        "--password",
        default=default_login_password(),
        help="OpenMetadata login password.",
    )
    parser.add_argument(
        "--password-b64",
        default=os.environ.get("OM_PASSWORD_B64", ""),
        help="Base64-encoded OpenMetadata password for login endpoints.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--output",
        default=str(repo_root / "tmp" / "openmetadata-registry-definitions" / "seed-report.json"),
        help="Path to write the seed report JSON.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the manifest and render payloads without calling OpenMetadata.",
    )
    return parser.parse_args()


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise OpenMetadataSeedError(f"Registry-definition manifest not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OpenMetadataSeedError(f"Registry-definition manifest is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise OpenMetadataSeedError("Registry-definition manifest must be a JSON object")

    glossary = payload.get("glossary")
    definitions = payload.get("definitions")
    if not isinstance(glossary, dict):
        raise OpenMetadataSeedError("Registry-definition manifest must define a glossary object")
    if not isinstance(definitions, list):
        raise OpenMetadataSeedError("Registry-definition manifest must define a definitions array")
    if len(definitions) < 5 or len(definitions) > 10:
        raise OpenMetadataSeedError("Registry-definition manifest must contain between 5 and 10 definitions")

    for key in ("name", "display_name", "description"):
        if not clean(glossary.get(key)):
            raise OpenMetadataSeedError(f"Registry-definition glossary is missing required field '{key}'")

    required_fields = (
        "definition_id",
        "definition_type",
        "definition_name",
        "term_name",
        "display_name",
        "business_definition",
    )
    seen_definition_ids: set[str] = set()
    seen_term_names: set[str] = set()
    counts = {key: 0 for key in REQUIRED_DEFINITION_TYPES}
    normalized_definitions: list[dict[str, Any]] = []
    for index, definition in enumerate(definitions, start=1):
        if not isinstance(definition, dict):
            raise OpenMetadataSeedError(f"Definition #{index} must be a JSON object")
        normalized = dict(definition)
        for field in required_fields:
            value = clean(normalized.get(field))
            if not value:
                raise OpenMetadataSeedError(f"Definition #{index} is missing required field '{field}'")
            normalized[field] = value

        definition_id = normalized["definition_id"]
        term_name = normalized["term_name"]
        definition_type = normalized["definition_type"]
        if definition_id in seen_definition_ids:
            raise OpenMetadataSeedError(f"Registry-definition manifest contains duplicate definition_id '{definition_id}'")
        if term_name in seen_term_names:
            raise OpenMetadataSeedError(f"Registry-definition manifest contains duplicate term_name '{term_name}'")
        if definition_type not in REQUIRED_DEFINITION_TYPES:
            raise OpenMetadataSeedError(
                f"Registry-definition '{definition_id}' has unsupported definition_type '{definition_type}'"
            )
        seen_definition_ids.add(definition_id)
        seen_term_names.add(term_name)
        counts[definition_type] += 1
        normalized_definitions.append(normalized)

    for definition_type, minimum_count in REQUIRED_DEFINITION_TYPES.items():
        if counts[definition_type] < minimum_count:
            raise OpenMetadataSeedError(
                f"Registry-definition manifest must include at least {minimum_count} '{definition_type}' definitions"
            )

    return {
        "glossary": glossary,
        "definitions": normalized_definitions,
    }


def _json_string(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    return clean(value)


def build_term_payload(definition: dict[str, Any], glossary_fqn: str) -> dict[str, Any]:
    extension = {
        "definition_id": definition["definition_id"],
        "definition_type": definition["definition_type"],
        "definition_name": definition["definition_name"],
        "object_class": clean(definition.get("object_class")),
        "property": clean(definition.get("property")),
        "representation_term": clean(definition.get("representation_term")),
        "status": clean(definition.get("status")),
        "owner": clean(definition.get("owner")),
        "version": clean(definition.get("version")),
        "value_domain": _json_string(definition.get("value_domain") or {}),
        "provenance": _json_string(definition.get("provenance") or {}),
        "applies_to": _json_string(definition.get("applies_to") or []),
    }
    return {
        "name": definition["term_name"],
        "displayName": definition["display_name"],
        "description": definition["business_definition"],
        "glossary": glossary_fqn,
        "mutuallyExclusive": False,
        "extension": extension,
    }


class OpenMetadataClient:
    def __init__(
        self,
        *,
        endpoint: str,
        repo_root: Path,
        timeout_seconds: int,
        token: str = "",
        email: str = "",
        password: str = "",
        password_b64: str = "",
    ) -> None:
        self.base_url, self.api_base = normalize_endpoint(endpoint)
        self.timeout_seconds = max(int(timeout_seconds), 1)
        self.token = clean(token)
        self.email = clean(email)
        self.password = clean(password)
        self.password_b64 = clean(password_b64)
        self.ssl_context = build_ssl_context(endpoint, repo_root)

    def ensure_token(self) -> str:
        if self.token:
            return self.token
        if not self.email or not (self.password or self.password_b64):
            raise OpenMetadataSeedError(
                "OpenMetadata authentication requires either --token or both --email and --password/--password-b64"
            )

        encoded_password = self.password_b64 or base64.b64encode(self.password.encode("utf-8")).decode("ascii")
        payload = {"email": self.email, "password": encoded_password}
        failures: list[str] = []
        for login_path in ("/v1/users/login", "/v1/auth/login"):
            try:
                response = self.request_json("POST", login_path, body=payload, authenticated=False)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{login_path}: {exc}")
                continue
            token = clean((response or {}).get("accessToken"))
            if token:
                self.token = token
                return token
            failures.append(f"{login_path}: response did not include accessToken")
        raise OpenMetadataSeedError("Failed OpenMetadata login. " + " | ".join(failures))

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: Any | None = None,
        authenticated: bool = True,
        allow_not_found: bool = False,
    ) -> Any:
        query = f"?{parse.urlencode(params, doseq=True)}" if params else ""
        url = f"{self.api_base}{path}{query}"
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.ensure_token()}"

        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

        req = request.Request(url=url, data=data, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=self.timeout_seconds, context=self.ssl_context) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return {}
                return json.loads(raw)
        except error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            if allow_not_found and exc.code == 404:
                return None
            raise OpenMetadataRequestError(method.upper(), url, exc.code, body_text[:400]) from exc
        except error.URLError as exc:
            raise OpenMetadataSeedError(f"Failed to reach OpenMetadata at {url}: {exc}") from exc

    def create_or_update_glossary(self, *, name: str, display_name: str, description: str) -> dict[str, Any]:
        return self.request_json(
            "PUT",
            "/v1/glossaries",
            body={
                "name": name,
                "displayName": display_name,
                "description": description,
                "mutuallyExclusive": False,
            },
        )

    def create_or_update_term(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.request_json("PUT", "/v1/glossaryTerms", body=payload)
        except OpenMetadataRequestError as exc:
            if exc.status_code == 400 and payload.get("extension"):
                raise OpenMetadataSeedError(
                    "OpenMetadata rejected the registry-definition extension payload for glossary terms. "
                    "Provision glossaryTerm custom properties first and retry."
                ) from exc
            raise

    def get_glossary_term(self, term_fqn: str) -> dict[str, Any] | None:
        encoded = parse.quote(term_fqn, safe="")
        return self.request_json("GET", f"/v1/glossaryTerms/name/{encoded}", allow_not_found=True)

    def ensure_glossary_term_property(self, name: str, description: str) -> bool:
        glossary_term_type = self.request_json("GET", "/v1/metadata/types/name/glossaryTerm")
        if _has_named_property(glossary_term_type, name):
            return False
        glossary_term_type_id = clean((glossary_term_type or {}).get("id"))
        if not glossary_term_type_id:
            raise OpenMetadataSeedError("OpenMetadata glossaryTerm metadata type response did not include an id")

        string_type = self.request_json("GET", "/v1/metadata/types/name/string")
        string_type_id = clean((string_type or {}).get("id"))
        if not string_type_id:
            raise OpenMetadataSeedError("OpenMetadata string metadata type response did not include an id")

        self.request_json(
            "PUT",
            f"/v1/metadata/types/{glossary_term_type_id}",
            body={
                "name": name,
                "description": description,
                "propertyType": {
                    "id": string_type_id,
                    "type": "type",
                },
            },
        )
        return True


def _has_named_property(payload: Any, name: str) -> bool:
    if isinstance(payload, dict):
        if clean(payload.get("name")) == name and "propertyType" in payload:
            return True
        return any(_has_named_property(value, name) for value in payload.values())
    if isinstance(payload, list):
        return any(_has_named_property(item, name) for item in payload)
    return False


def seed_registry_definitions(
    *,
    client: OpenMetadataClient | None,
    manifest: dict[str, Any],
    output_path: Path,
    dry_run: bool,
) -> dict[str, Any]:
    glossary = manifest["glossary"]
    definitions = manifest["definitions"]
    glossary_fqn = glossary["name"]

    report: dict[str, Any] = {
        "glossary": {
            "name": glossary["name"],
            "display_name": glossary["display_name"],
            "description": glossary["description"],
            "fully_qualified_name": glossary_fqn,
        },
        "definition_count": len(definitions),
        "dry_run": dry_run,
        "definitions": [],
        "custom_properties": [],
    }

    if dry_run:
        for definition in definitions:
            report["definitions"].append(
                {
                    "definition_id": definition["definition_id"],
                    "definition_type": definition["definition_type"],
                    "term_fqn": f"{glossary_fqn}.{definition['term_name']}",
                    "payload": build_term_payload(definition, glossary_fqn),
                }
            )
        write_report(output_path, report)
        return report

    if client is None:
        raise OpenMetadataSeedError("A live OpenMetadata client is required unless --dry-run is used")

    glossary_entity = client.create_or_update_glossary(
        name=glossary["name"],
        display_name=glossary["display_name"],
        description=glossary["description"],
    )
    glossary_fqn = clean(glossary_entity.get("fullyQualifiedName")) or glossary["name"]
    report["glossary"]["fully_qualified_name"] = glossary_fqn

    for property_name, description in REQUIRED_TERM_PROPERTIES.items():
        created = client.ensure_glossary_term_property(property_name, description)
        report["custom_properties"].append({"name": property_name, "created": created})

    for definition in definitions:
        payload = build_term_payload(definition, glossary_fqn)
        entity = client.create_or_update_term(payload)
        report["definitions"].append(
            {
                "definition_id": definition["definition_id"],
                "definition_type": definition["definition_type"],
                "term_fqn": clean(entity.get("fullyQualifiedName")) or f"{glossary_fqn}.{definition['term_name']}",
                "openmetadata_entity_id": clean(entity.get("id")),
            }
        )

    write_report(output_path, report)
    return report


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    manifest = load_manifest(Path(args.manifest))
    repo_root = Path(__file__).resolve().parents[2]
    client = None
    if not args.dry_run:
        client = OpenMetadataClient(
            endpoint=args.endpoint,
            repo_root=repo_root,
            timeout_seconds=args.timeout_seconds,
            token=args.token,
            email=args.email,
            password=args.password,
            password_b64=args.password_b64,
        )

    report = seed_registry_definitions(
        client=client,
        manifest=manifest,
        output_path=Path(args.output),
        dry_run=bool(args.dry_run),
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())