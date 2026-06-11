#!/usr/bin/env python3
"""Seed the retail-banking product-spec demo slice into OpenMetadata."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from openmetadata_tls import build_ssl_context


REQUIRED_TERM_PROPERTIES = {
    "product_spec_id": "Stable dq-made-easy product-spec identifier.",
    "product_name": "Canonical product-spec display name.",
    "product_version": "Governed product-spec semantic version.",
    "product_lifecycle_state": "Lifecycle state for the product specification.",
    "product_owner": "Owning team or role for the product specification.",
    "product_objective": "Business objective for the governed product specification.",
    "product_scope": "JSON-encoded scope metadata for the product specification.",
    "business_definition": "Canonical governed business definition.",
    "registry_definition_ids": "JSON-encoded registry-definition identifiers linked to the product spec.",
    "odcs_contract_refs": "JSON-encoded linked ODCS contract references.",
    "provenance": "JSON-encoded provenance metadata.",
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
        default=str(repo_root / "dq-metadata" / "demo" / "openmetadata_product_specs.retail_banking.json"),
        help="Path to the product-spec manifest JSON file.",
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
        default=str(repo_root / "tmp" / "openmetadata-product-specs" / "seed-report.json"),
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
        raise OpenMetadataSeedError(f"Product-spec manifest not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OpenMetadataSeedError(f"Product-spec manifest is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise OpenMetadataSeedError("Product-spec manifest must be a JSON object")

    glossary = payload.get("glossary")
    product_specs = payload.get("product_specs")
    if not isinstance(glossary, dict):
        raise OpenMetadataSeedError("Product-spec manifest must define a glossary object")
    if not isinstance(product_specs, list):
        raise OpenMetadataSeedError("Product-spec manifest must define a product_specs array")
    if len(product_specs) < 1 or len(product_specs) > 5:
        raise OpenMetadataSeedError("Product-spec manifest must contain between 1 and 5 product specs")

    for key in ("name", "display_name", "description"):
        if not clean(glossary.get(key)):
            raise OpenMetadataSeedError(f"Product-spec glossary is missing required field '{key}'")

    normalized_specs: list[dict[str, Any]] = []
    seen_product_spec_ids: set[str] = set()
    seen_term_names: set[str] = set()
    for index, product_spec in enumerate(product_specs, start=1):
        if not isinstance(product_spec, dict):
            raise OpenMetadataSeedError(f"Product spec #{index} must be a JSON object")
        normalized = dict(product_spec)
        for field in (
            "product_spec_id",
            "term_name",
            "display_name",
            "product_name",
            "product_version",
            "product_lifecycle_state",
            "product_owner",
            "product_objective",
            "business_definition",
        ):
            value = clean(normalized.get(field))
            if not value:
                raise OpenMetadataSeedError(f"Product spec #{index} is missing required field '{field}'")
            normalized[field] = value

        normalized["product_scope"] = _require_dict(normalized.get("product_scope"), field="product_scope", index=index)
        normalized["registry_definition_ids"] = _require_string_list(
            normalized.get("registry_definition_ids"),
            field="registry_definition_ids",
            index=index,
        )
        normalized["odcs_contract_refs"] = _require_contract_refs(normalized.get("odcs_contract_refs"), index=index)
        normalized["provenance"] = _require_dict(normalized.get("provenance"), field="provenance", index=index)

        product_spec_id = normalized["product_spec_id"]
        term_name = normalized["term_name"]
        if product_spec_id in seen_product_spec_ids:
            raise OpenMetadataSeedError(f"Product-spec manifest contains duplicate product_spec_id '{product_spec_id}'")
        if term_name in seen_term_names:
            raise OpenMetadataSeedError(f"Product-spec manifest contains duplicate term_name '{term_name}'")
        seen_product_spec_ids.add(product_spec_id)
        seen_term_names.add(term_name)
        normalized_specs.append(normalized)

    return {
        "glossary": glossary,
        "product_specs": normalized_specs,
    }


def _require_dict(value: Any, *, field: str, index: int) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise OpenMetadataSeedError(f"Product spec #{index} must define a non-empty object field '{field}'")
    return dict(value)


def _require_string_list(value: Any, *, field: str, index: int) -> list[str]:
    if not isinstance(value, list) or not value:
        raise OpenMetadataSeedError(f"Product spec #{index} must define a non-empty array field '{field}'")
    normalized = [clean(item) for item in value if clean(item)]
    if not normalized:
        raise OpenMetadataSeedError(f"Product spec #{index} must define a non-empty array field '{field}'")
    return normalized


def _require_contract_refs(value: Any, *, index: int) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise OpenMetadataSeedError(f"Product spec #{index} must define at least one odcs_contract_refs entry")
    normalized: list[dict[str, Any]] = []
    for ref_index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise OpenMetadataSeedError(f"Product spec #{index} ODCS contract reference #{ref_index} must be an object")
        odcs_contract_id = clean(item.get("odcs_contract_id"))
        odcs_contract_name = clean(item.get("odcs_contract_name"))
        odcs_contract_version = clean(item.get("odcs_contract_version"))
        if not odcs_contract_id:
            raise OpenMetadataSeedError(
                f"Product spec #{index} ODCS contract reference #{ref_index} is missing 'odcs_contract_id'"
            )
        if not odcs_contract_name:
            raise OpenMetadataSeedError(
                f"Product spec #{index} ODCS contract reference #{ref_index} is missing 'odcs_contract_name'"
            )
        if not odcs_contract_version:
            raise OpenMetadataSeedError(
                f"Product spec #{index} ODCS contract reference #{ref_index} is missing 'odcs_contract_version'"
            )
        normalized.append(
            {
                "odcs_contract_id": odcs_contract_id,
                "odcs_contract_name": odcs_contract_name,
                "odcs_contract_version": odcs_contract_version,
                "openmetadata_entity_id": clean(item.get("openmetadata_entity_id")),
                "openmetadata_entity_type": clean(item.get("openmetadata_entity_type")) or "data_contract",
                "source_system": clean(item.get("source_system")) or "openmetadata",
            }
        )
    return normalized


def _json_string(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def build_term_payload(product_spec: dict[str, Any], glossary_fqn: str, *, contract_refs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    extension = {
        "product_spec_id": product_spec["product_spec_id"],
        "product_name": product_spec["product_name"],
        "product_version": product_spec["product_version"],
        "product_lifecycle_state": product_spec["product_lifecycle_state"],
        "product_owner": product_spec["product_owner"],
        "product_objective": product_spec["product_objective"],
        "product_scope": _json_string(product_spec["product_scope"]),
        "business_definition": product_spec["business_definition"],
        "registry_definition_ids": _json_string(product_spec["registry_definition_ids"]),
        "odcs_contract_refs": _json_string(contract_refs if contract_refs is not None else product_spec["odcs_contract_refs"]),
        "provenance": _json_string(product_spec["provenance"]),
    }
    return {
        "name": product_spec["term_name"],
        "displayName": product_spec["display_name"],
        "description": product_spec["business_definition"],
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
                    "OpenMetadata rejected the product-spec extension payload for glossary terms. "
                    "Provision glossaryTerm custom properties first and retry."
                ) from exc
            raise

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

    def list_data_contracts(self) -> list[dict[str, Any]]:
        payload = self.request_json("GET", "/v1/dataContracts", params={"limit": 1000})
        raw_items = payload.get("data") if isinstance(payload, dict) else []
        if not isinstance(raw_items, list):
            return []
        return [item for item in raw_items if isinstance(item, dict)]


def _has_named_property(payload: Any, name: str) -> bool:
    if isinstance(payload, dict):
        if clean(payload.get("name")) == name and "propertyType" in payload:
            return True
        return any(_has_named_property(value, name) for value in payload.values())
    if isinstance(payload, list):
        return any(_has_named_property(item, name) for item in payload)
    return False


def seed_product_specs(
    *,
    client: OpenMetadataClient | None,
    manifest: dict[str, Any],
    output_path: Path,
    dry_run: bool,
) -> dict[str, Any]:
    glossary = manifest["glossary"]
    product_specs = manifest["product_specs"]
    glossary_fqn = glossary["name"]

    report: dict[str, Any] = {
        "glossary": {
            "name": glossary["name"],
            "display_name": glossary["display_name"],
            "description": glossary["description"],
            "fully_qualified_name": glossary_fqn,
        },
        "product_spec_count": len(product_specs),
        "dry_run": dry_run,
        "product_specs": [],
        "custom_properties": [],
    }

    if dry_run:
        for product_spec in product_specs:
            report["product_specs"].append(
                {
                    "product_spec_id": product_spec["product_spec_id"],
                    "term_fqn": f"{glossary_fqn}.{product_spec['term_name']}",
                    "payload": build_term_payload(product_spec, glossary_fqn),
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

    data_contracts = client.list_data_contracts()
    for product_spec in product_specs:
        resolved_refs = [_resolve_contract_reference(data_contracts, ref) for ref in product_spec["odcs_contract_refs"]]
        payload = build_term_payload(product_spec, glossary_fqn, contract_refs=resolved_refs)
        entity = client.create_or_update_term(payload)
        report["product_specs"].append(
            {
                "product_spec_id": product_spec["product_spec_id"],
                "term_fqn": clean(entity.get("fullyQualifiedName")) or f"{glossary_fqn}.{product_spec['term_name']}",
                "openmetadata_entity_id": clean(entity.get("id")),
                "linked_contracts": resolved_refs,
            }
        )

    write_report(output_path, report)
    return report


def _resolve_contract_reference(data_contracts: list[dict[str, Any]], reference: dict[str, Any]) -> dict[str, Any]:
    matches = []
    for contract in data_contracts:
        candidates = {
            clean(contract.get("id")),
            clean(contract.get("sourceUrl")),
            clean(contract.get("name")),
            clean(contract.get("fullyQualifiedName")),
        }
        if reference["odcs_contract_id"] in candidates or reference["odcs_contract_name"] in candidates:
            matches.append(contract)

    if not matches:
        raise OpenMetadataSeedError(
            f"Linked ODCS contract '{reference['odcs_contract_id']}' was not found in OpenMetadata. Seed the contract first."
        )
    if len(matches) > 1:
        raise OpenMetadataSeedError(
            f"Linked ODCS contract '{reference['odcs_contract_id']}' resolved to multiple OpenMetadata data contracts"
        )

    contract = matches[0]
    return {
        "odcs_contract_id": reference["odcs_contract_id"],
        "odcs_contract_name": reference["odcs_contract_name"],
        "odcs_contract_version": reference["odcs_contract_version"],
        "openmetadata_entity_id": clean(contract.get("id")),
        "openmetadata_entity_type": reference.get("openmetadata_entity_type") or "data_contract",
        "source_system": reference.get("source_system") or "openmetadata",
    }


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

    report = seed_product_specs(
        client=client,
        manifest=manifest,
        output_path=Path(args.output),
        dry_run=bool(args.dry_run),
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())